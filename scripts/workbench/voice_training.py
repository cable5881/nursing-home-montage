"""Background voice registration and polling for the local workbench."""
import base64
import re
import tempfile
import threading
import time
import uuid
import wave
from pathlib import Path

import voice_clone


MAX_AUDIO_BYTES = 10_000_000
AUDIO_FORMATS = {'.wav': 'wav', '.mp3': 'mp3', '.m4a': 'mov', '.aac': 'aac', '.flac': 'flac', '.ogg': 'ogg'}
ACTIVE = {'queued', 'checking', 'submitting', 'training'}
UNSENT = {'prepared', 'workbench_queued'}
PERSON_ID = r'[A-Za-z0-9_-]{1,80}'


class VoiceTraining:
    def __init__(self, app, read, write, run):
        self.app, self.pc, self.read, self.write, self.run = app, app.pc, read, write, run
        self.worker = None

    def folder(self, ident):
        if not re.fullmatch(PERSON_ID, ident):
            raise ValueError('数字人标识无效。')
        root = self.pc.directory().resolve()
        folder = (root / 'people' / ident).resolve()
        if not folder.is_relative_to(root):
            raise ValueError('人物目录不在当前项目中。')
        return folder

    def path(self, ident):
        return self.folder(ident) / 'voice-training.json'

    def public(self, person):
        record = self.read(self.path(person['id']), {})
        state = record.get('workbench', {})
        phase = record.get('phase')
        sample = self.pc.asset_path(person.get('sample'))
        return {
            'state': 'ready' if person.get('speaker') else state.get('state') or ('paused' if phase else 'idle'),
            'message': state.get('message', ''),
            'hasSample': bool(sample and sample.is_file()),
            'canUpload': not person.get('speaker') and (not phase or phase in UNSENT) and state.get('state') not in ACTIVE,
            'canStart': not person.get('speaker') and (bool(sample and sample.is_file()) or bool(phase and phase not in UNSENT)),
            'canQuery': bool(phase and phase not in UNSENT),
        }

    def active(self, ident):
        return self.read(self.path(ident), {}).get('workbench', {}).get('state') in ACTIVE

    def load_person(self, ident):
        self.folder(ident)
        cfg = self.pc.load()
        person = cfg['people'].get(ident)
        if not person:
            raise ValueError('找不到该数字人。')
        return cfg, person

    def sample(self, person):
        path = self.pc.asset_path(person.get('sample'))
        if not path or not path.is_file():
            raise ValueError('请先上传这位数字人的录音。')
        if not 0 < path.stat().st_size <= MAX_AUDIO_BYTES:
            raise ValueError('复刻用录音须大于 0 且不超过 10 MB。')
        try:
            with wave.open(str(path)) as audio:
                if not audio.getnframes():
                    raise ValueError('录音文件为空。')
        except (wave.Error, EOFError):
            raise ValueError('工作台无法读取这段 WAV 录音，请重新上传。') from None
        return path

    def attach(self, ident, filename, data):
        suffix = Path(filename).suffix.lower()
        if suffix not in self.app.people.AUDIO or not 0 < len(data) <= MAX_AUDIO_BYTES:
            raise ValueError('请选择不超过 10 MB 的 WAV、MP3、M4A、AAC、FLAC 或 OGG 录音。')
        cfg, person = self.load_person(ident)
        if not self.public(person)['canUpload']:
            raise ValueError('这位数字人已有绑定的音色或正在查询复刻结果。')
        with tempfile.TemporaryDirectory(prefix='voice-', dir=self.app.data) as directory:
            source = Path(directory) / ('upload' + suffix)
            source.write_bytes(data)
            sample = source.with_name('sample.wav')
            self.normalize_sample(source, sample)
            with self.app.transaction():
                cfg, person = self.load_person(ident)
                if not self.public(person)['canUpload']:
                    raise ValueError('这位数字人的复刻状态已变化，请刷新后查看。')
                folder = self.folder(ident)
                folder.mkdir(parents=True, exist_ok=True)
                destination = folder / ('sample-' + uuid.uuid4().hex[:12] + '.wav')
                sample.replace(destination)
                person['sample'] = str(destination.relative_to(self.pc.directory().resolve()))
                try:
                    self.pc.write(self.pc.directory() / 'project.json', cfg)
                except Exception:
                    destination.unlink(missing_ok=True)
                    raise
                return self.public(person)

    def normalize_sample(self, source, sample):
        result = self.run(['ffmpeg', '-nostdin', '-v', 'error', '-protocol_whitelist', 'file,pipe',
                           '-f', AUDIO_FORMATS[source.suffix], '-i', source, '-map', '0:a:0',
                           '-ar', '24000', '-ac', '1', '-c:a', 'pcm_s16le', '-fs',
                           str(MAX_AUDIO_BYTES + 1), sample], capture_output=True, timeout=30)
        if result.returncode:
            raise ValueError('无法读取这个录音文件，请重新选择。')
        self.sample({'sample': str(sample)})

    def reserve(self, cfg, person, connection):
        if connection.get('clone_mode') == 'postpaid':
            return {'speaker_id': 'custom_speaker_id', 'custom_speaker_id': 'montage_' + uuid.uuid4().hex}
        if connection.get('clone_mode') != 'prepaid':
            raise ValueError('请先在设置 → 制作服务中选择复刻方式。')
        used = {p.get('speaker') for p in cfg['people'].values()}
        for other in cfg['people']:
            if other != person['id']:
                used.add(self.read(self.path(other), {}).get('speaker_id'))
        speaker = next((s for s in connection.get('speaker_pool', []) if s and s not in used and s != 'custom_speaker_id'), None)
        if not speaker:
            raise ValueError('当前没有空闲预付费音色槽位，请在制作服务中填写未占用的槽位 ID。')
        return {'speaker_id': speaker}

    def start(self, ident):
        with self.app.transaction():
            cfg, person = self.load_person(ident)
            if person.get('speaker') or self.active(ident):
                return self.public(person)
            connection = cfg['connections'].get(person.get('connection'), {})
            if not self.pc.connection_keys(connection)[0]:
                raise ValueError('请先在制作服务中保存语音 API Key。')
            path = self.path(ident)
            record = self.read(path, {})
            phase = record.get('phase')
            if not phase or phase in UNSENT:
                self.sample(person)
                if phase != 'prepared':
                    record = {**self.reserve(cfg, person, connection), 'phase': 'workbench_queued'}
            now = time.time()
            record['workbench'] = {'state': 'queued', 'nextAt': now, 'until': now + 600,
                                   'message': '等待提交录音' if record['phase'] in UNSENT else '等待查询复刻状态'}
            self.write(path, record)
            return self.public(person)

    def tick(self):
        if self.worker and self.worker.is_alive():
            return
        now = time.time()
        with self.app.transaction():
            due = []
            for ident in self.pc.load()['people']:
                path = self.path(ident)
                record = self.read(path, {})
                state = record.get('workbench', {})
                if state.get('state') in ACTIVE and state.get('nextAt', 0) <= now:
                    due.append((state.get('nextAt', 0), ident, path, record))
            if not due:
                return
            _, ident, path, record = min(due)
            ticket = uuid.uuid4().hex
            record['workbench'].update(ticket=ticket, nextAt=now + 75)
            self.write(path, record)
        self.worker = threading.Thread(target=self.step, args=(ident, path, record, ticket), daemon=True)
        self.worker.start()

    def step(self, ident, path, record, ticket):
        state = record['workbench']
        try:
            cfg, person = self.load_person(ident)
            if person.get('speaker'):
                self.finish(path, record, ticket, 'ready', '音色已绑定')
                return
            key = self.pc.connection_keys(cfg['connections'].get(person.get('connection'), {}))[0]
            if not key:
                raise ValueError('语音 API Key 已失效，请补齐后继续。')
            phase = record['phase']
            identity = {k: record[k] for k in ('speaker_id', 'custom_speaker_id') if record.get(k)}
            if phase == 'ready':
                self.bind(ident, path, record, ticket, identity)
            elif phase in UNSENT:
                if identity['speaker_id'] != 'custom_speaker_id' and time.time() - record.get('slotCheckedAt', 0) > 60:
                    self.check_slot(path, record, ticket, identity, key)
                    return
                payload = {**identity, 'audio': {'data': base64.b64encode(self.sample(person).read_bytes()).decode(), 'format': 'wav'}}
                record['phase'] = 'submission_unknown'
                if not self.finish(path, record, ticket, 'submitting', '正在提交录音', delay=75):
                    return
                voice_clone.call('voice_clone', payload, key)
                record['phase'] = 'submitted'
                self.finish(path, record, ticket, 'training', '复刻请求已提交，等待服务返回状态', delay=1)
            else:
                self.query(ident, path, record, ticket, identity, key)
        except Exception as error:
            reason = self.app.redact(str(error))[:350]
            if record.get('phase') in UNSENT:
                self.finish(path, record, ticket, 'failed', reason)
            elif record.get('phase') == 'submission_unknown' and state.get('state') == 'submitting':
                self.finish(path, record, ticket, 'training', '等待核对提交结果。' + reason, delay=5)
            else:
                failures = state.get('queryErrors', 0) + 1
                state['queryErrors'] = failures
                polling = failures < 3 and time.time() < state['until']
                self.finish(path, record, ticket, 'training' if polling else 'paused', '查询暂未成功。' + reason, delay=6 if polling else 0)

    def check_slot(self, path, record, ticket, identity, key):
        if not self.finish(path, record, ticket, 'checking', '正在检查预付费槽位', delay=75):
            return
        reply = voice_clone.call('get_voice', identity, key)
        if reply.get('status') not in (0, 3) or reply.get('available_training_times') == 0:
            raise ValueError('这个槽位已有音色、正在复刻或不可用。请在制作服务中换一个空闲槽位。')
        record['slotCheckedAt'] = time.time()
        self.finish(path, record, ticket, 'queued', '槽位可用，等待提交录音')

    def query(self, ident, path, record, ticket, identity, key):
        reply = voice_clone.call('get_voice', identity, key)
        status = reply.get('status')
        record['status'] = status
        record['workbench'].pop('queryErrors', None)
        if status in (2, 4):
            self.bind(ident, path, record, ticket, identity)
        elif status == 3:
            self.finish(path, record, ticket, 'failed', '语音服务报告复刻失败。可以继续查询，或查看语音控制台。')
        elif time.time() >= record['workbench']['until']:
            self.finish(path, record, ticket, 'paused', '暂未获得最终结果，可以继续查询。')
        else:
            progress = '语音服务正在复刻' if status == 1 else '等待语音服务确认任务'
            self.finish(path, record, ticket, 'training', progress, delay=5)

    def bind(self, ident, path, record, ticket, identity):
        with self.app.transaction():
            if self.read(path, {}).get('workbench', {}).get('ticket') != ticket:
                return
            _, person = self.load_person(ident)
            if not person.get('speaker'):
                self.app.people.bind(ident, identity['speaker_id'], identity.get('custom_speaker_id'))
            record['phase'] = 'ready'
            self.finish(path, record, ticket, 'ready', '复刻完成，音色 ID 已自动填写')

    def finish(self, path, record, ticket, state, message, delay=0):
        with self.app.transaction():
            if self.read(path, {}).get('workbench', {}).get('ticket') != ticket:
                return False
            record['workbench'].update(state=state, message=message, nextAt=time.time() + delay)
            self.write(path, record)
            return True
