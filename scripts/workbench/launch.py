#!/usr/bin/env python3
"""Start or reopen the local workbench, using only Python's standard library."""
import argparse
import http.cookiejar
from contextlib import contextmanager
import json
import os
from pathlib import Path
import shutil
import shlex
import socket
import subprocess
import sys
import time
import urllib.request
import uuid
import webbrowser


@contextmanager
def launch_lock(project):
    data=project/'.montage/workbench';data.mkdir(parents=True,exist_ok=True)
    with (data/'launch.lock').open('a+b') as f:
        if sys.platform=='win32':
            import msvcrt
            f.write(b'0');f.flush();f.seek(0);msvcrt.locking(f.fileno(),msvcrt.LK_LOCK,1)
        else:
            import fcntl
            fcntl.flock(f.fileno(),fcntl.LOCK_EX)
        try:yield
        finally:
            if sys.platform=='win32':f.seek(0);msvcrt.locking(f.fileno(),msvcrt.LK_UNLCK,1)
            else:fcntl.flock(f.fileno(),fcntl.LOCK_UN)


def write_shortcut(project):
    """Leave a project-specific entry that opens a browser without an Agent."""
    if sys.platform!='darwin': return
    target=Path(project)/'打开视频工作台.command'
    marker='# montage-workbench-project-shortcut'
    if target.exists() and marker not in target.read_text(): return
    command=shlex.quote(sys.executable)+' '+shlex.quote(str(Path(__file__).resolve()))+' --project '+shlex.quote(str(Path(project).resolve()))
    content='#!/bin/bash\n'+marker+'\nif command -v rtk >/dev/null 2>&1; then\n  rtk '+command+'\nelse\n  '+command+'\nfi\n'
    if not target.exists() or target.read_text()!=content: target.write_text(content)
    target.chmod(0o700)


def launch(project, no_open=False, managed=False, independent=False):
    project=Path(project).resolve()
    project.mkdir(parents=True,exist_ok=True)
    write_shortcut(project)
    with launch_lock(project):
        return _launch(project,no_open,managed,independent)


def _launch(project,no_open,managed,independent):
    data = project / ".montage/workbench"
    record = data / "server.json"
    try: previous = json.loads(record.read_text())
    except (FileNotFoundError,json.JSONDecodeError): previous = None
    restart_port = None
    if previous:
        client = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
        base=previous['url'].split('/?')[0]
        page_alive=False
        try:
            with client.open(previous['url'],timeout=2) as response:page_alive=response.status==200
        except Exception:pass  # The cookie redirect may succeed even if file access is broken.
        try:
            with client.open(base+'/api/runtime',timeout=3) as response:runtime=json.load(response)
        except Exception as exc:
            if page_alive:raise RuntimeError('旧版工作台仍在运行，请先停止旧 HTTP 服务再打开新入口；任务文件与执行锁保留。') from exc
            runtime=None
        alive=runtime is not None
        if runtime:
            if runtime.get('project')!=str(project):raise RuntimeError('已有服务属于其他项目，未复用')
            from server import code_fingerprint
            try:
                with client.open(base+'/api/health',timeout=3) as response:healthy=json.load(response).get('ok') is True
            except Exception:healthy=False
            if runtime.get('codeFingerprint')!=code_fingerprint() or not healthy or (independent and runtime.get('serviceMode')!='standalone'):
                try:queue=json.loads((data/'queue.json').read_text())
                except FileNotFoundError:queue={'items':[]}
                except (OSError,json.JSONDecodeError) as exc:raise RuntimeError('无法核对执行锁，未自动重启服务') from exc
                if any(not row.get('settled',True) for row in queue.get('items',[])):
                    if not healthy:raise RuntimeError('任务仍持有执行锁，服务不可读；未自动重启或释放任务')
                    opened=webbrowser.open(previous['url']) if not no_open else False
                    return {**previous,'reused':True,'deferredUpgrade':True,'browserOpened':bool(opened)}
                request=urllib.request.Request(base+'/api/shutdown',data=b'{}',headers={'Origin':base,'Content-Type':'application/json'})
                client.open(request,timeout=5).read()
                restart_port=previous['port']
                alive=False
        if alive:
            if not no_open:opened=webbrowser.open(previous['url'])
            return {**previous,'reused':True,'browserOpened':bool(opened) if not no_open else False}
    if managed:
        from server import python_command
        command=python_command(Path(__file__).with_name('server.py'))+' --project '+shlex.quote(str(project))+' --port 0 --host workbuddy --service-mode host'
        return {'httpStarted':False,'needsHostService':True,'serverCommand':command,'instruction':'使用 WorkBuddy 原生命令工具的官方后台模式运行 serverCommand，保存真实后台句柄；服务就绪后重新执行原入口，检查 /api/health 并复用同一服务。无需启动 Terminal 或执行项目快捷方式。不要通过自行脱离子进程或删除宿主环境变量绕过执行生命周期。'}
    data.mkdir(parents=True, exist_ok=True)
    preferred_port = restart_port or 8765
    port = 0
    for _ in range(15 if restart_port else 1):
        with socket.socket() as probe:
            probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                probe.bind(('127.0.0.1', preferred_port))
            except OSError:
                if restart_port: time.sleep(.1)
            else:
                port=preferred_port
                break
    cmd = [sys.executable, str(Path(__file__).with_name("server.py")), "--project", str(project), "--port", str(port)]
    if shutil.which("rtk"):
        cmd = ["rtk", "proxy", *cmd]
    log_path = data / "server.log"
    fd = os.open(log_path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
    # A double-clicked Windows batch window can close as soon as launch returns.
    background = {'creationflags': subprocess.DETACHED_PROCESS} if sys.platform == 'win32' else {'start_new_session': True}
    with os.fdopen(fd, "a") as log:
        launch_id = uuid.uuid4().hex
        process = subprocess.Popen(
            cmd, cwd=project, env={**os.environ, "MONTAGE_WORKBENCH_LAUNCH_ID": launch_id},
            stdin=subprocess.DEVNULL, stdout=log, stderr=log, **background)
    for _ in range(100):
        if process.poll() is not None:
            raise SystemExit("工作台启动失败，请查看 .montage/workbench/server.log")
        if record.exists():
            current = json.loads(record.read_text())
            if current.get("launchId") == launch_id:
                if not no_open:
                    opened=webbrowser.open(current["url"])
                return {**current, "browserOpened":bool(opened) if not no_open else False}
        time.sleep(.1)
    raise SystemExit("工作台启动超时，请检查本地服务日志")


def main():
    p=argparse.ArgumentParser(description=__doc__)
    candidates=[Path.cwd(),*Path(__file__).resolve().parents]
    existing=next((x for x in candidates if (x/'.montage/project.json').is_file()),None)
    p.add_argument('--project',type=Path)
    p.add_argument('--ask-project',action='store_true',help='找不到已有项目时，询问用于存放素材和作品的项目目录')
    p.add_argument('--no-open',action='store_true')
    args=p.parse_args()
    project=args.project or existing
    if project is None and args.ask_project:
        try:
            entered=input('请输入养老视频项目目录（可粘贴完整路径）：').strip().strip('"')
        except EOFError:
            p.error('请使用 --project 指定项目目录。')
        if not entered:
            p.error('请输入项目目录，或使用 --project 指定路径。')
        project=Path(entered).expanduser()
    print(json.dumps(launch(project or Path.cwd(),args.no_open,independent=True),ensure_ascii=False))


if __name__ == "__main__":
    main()
