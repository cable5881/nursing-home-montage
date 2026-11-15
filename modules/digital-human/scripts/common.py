"""Project paths, credential lookup, and durable non-secret run records."""
import json
import os
import re
import subprocess
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

SKILL_DIR = Path(__file__).resolve().parent.parent
PROJECT_ROOT = Path(os.environ['MONTAGE_PROJECT_ROOT']).resolve() if os.environ.get('MONTAGE_PROJECT_ROOT') else next((p.parent for p in SKILL_DIR.parents if p.name=='.agents'),Path.cwd())
_SECRET_VALUES = set()


def now():
    return datetime.now(ZoneInfo("Asia/Shanghai")).isoformat(timespec="seconds")


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write_json(path, value):
    path = Path(path)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def config():
    return read_json(Path(os.environ.get('MONTAGE_AVATAR_CONFIG',SKILL_DIR / 'config.json')))


def merge_rules(existing, additions):
    rules = {}
    for source in (existing, additions):
        if not isinstance(source, dict) or not isinstance(source.get("tone"), list):
            raise RuntimeError('发音词典须为 {"tone":["原词/(拼音)"]}。')
        for rule in source["tone"]:
            if not isinstance(rule, str):
                raise RuntimeError("发音规则必须为字符串。")
            word, separator, replacement = rule.partition("/")
            if not separator or not replacement or not 1 <= len(word) <= 9 or any(x.isspace() for x in word):
                raise RuntimeError("发音原词须为1至9字且不含空格，并提供修正内容。")
            rules[word] = rule
    return {"tone": list(rules.values())}


def command(args):
    import shutil
    result = subprocess.run((['rtk','proxy'] if shutil.which('rtk') else [])+[str(x) for x in args], capture_output=True)
    if result.returncode:
        raise RuntimeError(result.stderr.decode(errors="replace")[-3000:])
    return result.stdout


def tts_key():
    value = os.environ.get("VOLCANO_TTS_API_KEY", "").strip()
    if not value and not os.environ.get('MONTAGE_MANAGED_CREDENTIALS') and os.name=='posix' and Path('/usr/bin/security').exists():
        result = subprocess.run(["/usr/bin/security", "find-generic-password", "-a",
                                 "VOLCANO_TTS_API_KEY", "-s", "com.openai.codex.volcano-tts", "-w"],
                                capture_output=True, text=True, timeout=10)
        if result.returncode == 0:
            value = result.stdout.strip()
    if not value:
        raise RuntimeError("缺少 VOLCANO_TTS_API_KEY 或既有 macOS 钥匙串凭据。")
    _SECRET_VALUES.add(value)
    return value


def access_keys(cfg):
    ak = os.environ.get("VOLC_ACCESSKEY", "").strip()
    sk = os.environ.get("VOLC_SECRETKEY", "").strip()
    if not (ak and sk) and not os.environ.get('MONTAGE_MANAGED_CREDENTIALS'):
        path = Path(os.environ.get("VOLC_CREDENTIALS_FILE", PROJECT_ROOT / cfg["credentials_file"]))
        values = {}
        for line in path.read_text(encoding="utf-8-sig").splitlines():
            match = re.match(r"^\s*[-*]?\s*(AccessKeyID|SecretAccessKey)\s*[:：=]\s*(.*?)\s*$", line, re.I)
            if match:
                values[match[1].lower()] = match[2].strip().strip("`\"'")
        ak, sk = values.get("accesskeyid"), values.get("secretaccesskey")
    if not (ak and sk):
        raise RuntimeError("缺少有效的火山 AK/SK。")
    _SECRET_VALUES.update((ak, sk))
    return ak, sk


def sanitized(value, secrets=()):
    secrets = set(secrets) | _SECRET_VALUES
    if isinstance(value, dict):
        return {k: ("[temporary URL omitted]" if k.lower() in
                    {"video_url", "demo_audio", "signed_url", "audio_url"} else sanitized(v, secrets))
                for k, v in value.items()}
    if isinstance(value, list):
        return [sanitized(x, secrets) for x in value]
    if isinstance(value, str):
        for secret in secrets:
            if secret:
                value = value.replace(secret, "[REDACTED]")
        return re.sub(r"https?://[^\s\"']+(?:[?&](?:x-signature|X-Tos-Signature))[^\s\"']*",
                      "[temporary signed URL omitted]", value, flags=re.I)
    return value


def save_state(directory, state):
    state["updated_at"] = now()
    write_json(Path(directory) / "run.json", sanitized(state))


def probe(path):
    return json.loads(command(["ffprobe", "-v", "error", "-show_format", "-show_streams",
                               "-of", "json", path]))


def pcm(path, sample_rate=24000):
    return command(["ffmpeg", "-v", "error", "-i", path, "-vn", "-ac", "1", "-ar",
                    sample_rate, "-f", "s16le", "pipe:1"])


def audio_duration(path):
    return len(pcm(path)) / (2 * 24000)
