"""Volcengine visual async tasks with durable submission state and private TOS audio."""
import ast
import base64
import contextlib
import hashlib
import io
import json
import time
import urllib.request
import uuid
from pathlib import Path

from common import access_keys, now, sanitized, save_state


class AvatarClient:
    def __init__(self, cfg):
        from volcengine.visual.VisualService import VisualService
        self.cfg = cfg
        self.ak, self.sk = access_keys(cfg)
        self.service = VisualService()
        self.service.set_ak(self.ak)
        self.service.set_sk(self.sk)
        self.service.set_scheme("https")

    def call(self, action, payload):
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            try:
                value = getattr(self.service, action)(payload)
                return value if isinstance(value, dict) else json.loads(value)
            except Exception as error:
                message = str(error)
                try:
                    value = ast.literal_eval(message)
                    parsed = json.loads(value.decode() if isinstance(value, bytes) else value)
                    if isinstance(parsed, dict):
                        return parsed
                except (ValueError, SyntaxError, TypeError, UnicodeError):
                    pass
                raise RuntimeError(sanitized(message, (self.ak, self.sk))) from None

    def query(self, task_id):
        return self.call("cv_sync2async_get_result", {"req_key": self.cfg["avatar"]["req_key"], "task_id": task_id})

    def storage_client(self):
        import tos
        settings = self.cfg["storage"]
        return tos.TosClientV2(self.ak, self.sk, settings["endpoint"], settings["region"])

    def cleanup(self, directory, state):
        entry = state.get("upload")
        if not entry or entry.get("deleted"):
            return
        try:
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                self.storage_client().delete_object(entry["bucket"], entry["key"])
            entry["deleted"] = True
            entry.pop("cleanup_error", None)
        except Exception as error:
            entry["cleanup_error"] = sanitized(str(error), (self.ak, self.sk))
        save_state(directory, state)

    def submit(self, directory, state):
        if state.get("task_id"):
            return
        if state["phase"] in ("submitting", "submission_unknown"):
            raise RuntimeError("上次提交状态不明，不能自动重提。先核查请求记录，取得任务ID后再继续。")
        if state.get("qa_status") not in ("passed", "reviewed"):
            raise RuntimeError("配音核对尚未通过，不能提交视频。")
        if hashlib.sha256(Path(state["submitted_audio"]).read_bytes()).hexdigest() != state["submitted_audio_sha256"]:
            raise RuntimeError("提交音频在核验后发生变化，先重新核验。")
        if hashlib.sha256(Path(state["image"]).read_bytes()).hexdigest() != state["image_sha256"]:
            raise RuntimeError("人物图在准备后发生变化，先核对新的图像。")
        import tos
        settings = self.cfg["storage"]
        if not state.get("upload"):
            state["upload"] = {"bucket": settings["bucket"], "key": settings["prefix"].rstrip("/") +
                               "/" + uuid.uuid4().hex + "/narration.mp3", "deleted": False}
        save_state(directory, state)
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            storage = self.storage_client()
            storage.put_object_from_file(state["upload"]["bucket"], state["upload"]["key"],
                                         state["submitted_audio"], content_type="audio/mpeg")
            url = storage.pre_signed_url(tos.HttpMethodType.Http_Method_Get,
                bucket=state["upload"]["bucket"], key=state["upload"]["key"],
                expires=settings["url_expires_seconds"]).signed_url
        avatar = self.cfg["avatar"]
        body = {"req_key": avatar["req_key"], "binary_data_base64": [base64.b64encode(
                    Path(state["image"]).read_bytes()).decode()], "audio_url": url,
                "prompt": avatar["prompt"], "enable_watermark": avatar["enable_watermark"]}
        state["phase"] = "submitting"
        save_state(directory, state)
        try:
            response = self.call("cv_sync2async_submit_task", body)
        except Exception as error:
            state["phase"] = "submission_unknown"
            state["error"] = sanitized(str(error), (self.ak, self.sk, url))
            save_state(directory, state)
            raise RuntimeError(state["error"]) from None
        state["submit_response"] = sanitized(response, (self.ak, self.sk))
        task_id = (response.get("data") or {}).get("task_id")
        if response.get("code") != 10000 or not task_id:
            state["phase"] = "submit_rejected"
            save_state(directory, state)
            self.cleanup(directory, state)
            raise RuntimeError("提交被拒绝：" + json.dumps(state["submit_response"], ensure_ascii=False))
        state.update(task_id=task_id, phase="generating")
        save_state(directory, state)

    def poll(self, directory, state, wait_seconds=45):
        if not state.get("task_id"):
            raise RuntimeError("尚无 task_id；不能恢复查询。")
        deadline = time.monotonic() + wait_seconds
        while True:
            try:
                response = self.query(state["task_id"])
            except RuntimeError as error:
                state["last_query_error"] = str(error)
                save_state(directory, state)
                return False
            data = response.get("data") or {}
            status = data.get("status")
            state.setdefault("polls", []).append({"at": now(), "response": sanitized(response, (self.ak, self.sk))})
            save_state(directory, state)
            print(json.dumps({"task_id": state["task_id"], "code": response.get("code"), "status": status},
                             ensure_ascii=False), flush=True)
            if response.get("code") == 10000 and status == "done" and data.get("video_url"):
                target = Path(directory) / "provider-video.mp4"
                temporary = target.with_suffix(".download")
                urllib.request.urlretrieve(data["video_url"], temporary)
                temporary.replace(target)
                state["phase"] = "downloaded"
                save_state(directory, state)
                self.cleanup(directory, state)
                return True
            if ((response.get("code") not in (10000, 50429, 50430, 50500, 50501)) or
                    status in ("expired", "not_found") or
                    (status == "done" and response.get("code") == 10000)):
                state["phase"] = "failed"
                save_state(directory, state)
                self.cleanup(directory, state)
                raise RuntimeError("视频任务失败或未返回视频：" + json.dumps(sanitized(response), ensure_ascii=False))
            if time.monotonic() + 15 > deadline:
                return False
            time.sleep(15)
