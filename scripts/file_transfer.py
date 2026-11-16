"""Audio handoff for avatar services: anonymous tfLink by default, optional TOS."""
import hashlib
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from pathlib import Path

UPLOAD_ENDPOINT = 'https://tmpfile.link/api/upload'
MAX_BYTES = 100_000_000
RETENTION_SECONDS = 7 * 24 * 3600
# Identify this API client explicitly; the default Python urllib UA received CF 1010.
USER_AGENT = 'nursing-home-montage/2.4'


def storage_settings(value=None):
    settings = dict(value or {})
    # Existing bucket-only connections keep their behaviour; new connections need no bucket.
    settings.setdefault('provider', 'tos' if settings.get('bucket') else 'tmpfile')
    if settings['provider'] not in ('tmpfile', 'tos'):
        raise ValueError('文件中转服务只能为 tmpfile 或 tos。')
    if settings['provider'] == 'tos':
        settings.setdefault('region', 'cn-beijing')
        settings.setdefault('endpoint', 'tos-' + settings['region'] + '.volces.com')
        settings.setdefault('prefix', 'nursing-home-montage')
        settings.setdefault('url_expires_seconds', 14400)
    return settings


def _download_url(value):
    if not isinstance(value, str):
        raise RuntimeError('tmpfile 未返回有效下载直链。')
    parsed = urllib.parse.urlsplit(value)
    if (parsed.scheme != 'https' or parsed.hostname != 'd.tmpfile.link'
            or parsed.username or parsed.password or parsed.port not in (None, 443)
            or not parsed.path.startswith('/public/')):
        raise RuntimeError('tmpfile 返回了非预期的下载直链。')
    return value


def _check_download(url, prefix):
    request = urllib.request.Request(url, headers={
        'Range': 'bytes=0-' + str(len(prefix) - 1), 'User-Agent': USER_AGENT})
    with urllib.request.urlopen(request, timeout=30) as response:
        _download_url(response.geturl())
        if response.status not in (200, 206) or response.read(len(prefix)) != prefix:
            raise RuntimeError('tmpfile 直链下载校验失败；未提交数字人任务。')


def _private_write(path, value):
    temporary = path.with_suffix('.tmp')
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    os.chmod(temporary, 0o600)
    with os.fdopen(fd, 'w', encoding='utf-8') as output:
        json.dump(value, output)
    temporary.replace(path)


def tmpfile_audio(directory, audio):
    """Return a checked direct URL plus non-secret metadata; never call the avatar API."""
    directory, audio = Path(directory), Path(audio)
    size = audio.stat().st_size
    if not 0 < size <= MAX_BYTES:
        raise ValueError('tmpfile 音频须大于 0 且不超过 100MB。')
    content = audio.read_bytes()
    digest = hashlib.sha256(content).hexdigest()
    record = directory / 'transfer-link.json'
    cached = json.loads(record.read_text(encoding='utf-8')) if record.exists() else {}
    try:
        if (cached.get('sha256') == digest and cached.get('expires_at', 0) > time.time() + 60):
            url = _download_url(cached.get('url'))
            try:
                _check_download(url, content[:128])
                return url, {k: v for k, v in cached.items() if k != 'url'}
            except urllib.error.HTTPError as error:
                if error.code not in (404, 410):
                    raise
        boundary = 'montage-' + uuid.uuid4().hex
        filename = 'audio-' + uuid.uuid4().hex + '.mp3'
        body = (f'--{boundary}\r\nContent-Disposition: form-data; name="file"; '
                f'filename="{filename}"\r\nContent-Type: audio/mpeg\r\n\r\n').encode()
        body += content + f'\r\n--{boundary}--\r\n'.encode()
        request = urllib.request.Request(UPLOAD_ENDPOINT, data=body, headers={
            'Content-Type': 'multipart/form-data; boundary=' + boundary,
            'User-Agent': USER_AGENT, 'Accept': 'application/json'}, method='POST')
        with urllib.request.urlopen(request, timeout=60) as response:
            result = json.loads(response.read(65536))
        url = _download_url(result.get('downloadLinkEncoded') or result.get('downloadLink'))
        uploaded = time.time()
        cached = {'provider': 'tmpfile', 'sha256': digest, 'bytes': size,
                  'uploaded_at': uploaded, 'expires_at': uploaded + RETENTION_SECONDS,
                  'deletion': 'automatic_after_7_days', 'url': url}
        # A failed download check can resume from this upload without uploading again.
        _private_write(record, cached)
        _check_download(url, content[:128])
        return url, {k: v for k, v in cached.items() if k != 'url'}
    except (urllib.error.URLError, TimeoutError, OSError, ValueError, RuntimeError) as error:
        # Never echo third-party response bodies or private download URLs.
        status = f' HTTP {error.code}' if isinstance(error, urllib.error.HTTPError) else ''
        raise RuntimeError('tmpfile 文件中转失败' + status + '；未提交数字人任务，可稍后恢复。') from None
