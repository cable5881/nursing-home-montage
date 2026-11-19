"""Bounded deterministic execution, with native Agent review gates.

This worker runs inside the authorized local service. It never starts an LLM,
accepts arbitrary shell text, or declares a visual review on the Agent's behalf.
"""
import hashlib
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import time

STEPS = ['validate-plan', 'setup', 'content-review', 'preflight', 'voice', 'build',
         'avatars', 'provider-review', 'cutouts', 'cover', 'carve', 'check',
         'snapshot', 'layout-review', 'render', 'verify', 'final-review', 'package']
PHASE = {'validate-plan':1, 'setup':1, 'preflight':2, 'content-review':1, 'voice':2,
         'build':2, 'avatars':2, 'provider-review':2, 'cutouts':3, 'cover':3,
         'carve':3, 'check':3, 'snapshot':3, 'layout-review':3, 'render':4,
         'verify':4, 'final-review':4, 'package':5}
REVIEW_ACTIONS = {'content':'review-content', 'provider':'review-provider',
                  'final':'review', 'contrast':'review-contrast'}


def fingerprint(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


class Pipeline:
    def __init__(self, app, read, write, invoke=None):
        self.app, self.read, self.write = app, read, write
        self.invoke_override = invoke

    def row(self, ident, lease):
        _, row = self.app.queue.checked(ident, lease)
        if row['status'] not in ('running', 'stopping'): raise ValueError('请先由当前子 Agent 领取作业')
        return row

    def engine(self, job):
        runtime = self.read(job / 'runtime.json', {})
        skill = Path(runtime.get('engine', self.app.skill))
        entry = skill / 'scripts/montage.py'
        if not entry.is_file(): raise ValueError('原冻结引擎缺失，不改用新版继续付费生成')
        return entry

    def command(self, entry, *args):
        if getattr(self.app,'service_mode','standalone')=='host':
            # Retain the target's declared uv environment and the narrow mkdir
            # compatibility fix; native host permissions still apply unchanged.
            return [sys.executable,str(Path(__file__).with_name('runtime_compat.py')),str(entry),*map(str,args)]
        return ['uv','run','--python','3.11',str(entry),*map(str,args)]

    def invoke(self, row, lease, action, extra=None, job=None, cli_args=None):
        if self.invoke_override: return self.invoke_override(row, lease, action, extra or [], job)
        job = Path(job or row['job'])
        args = self.command(self.engine(job), *(cli_args or [action, job, *(extra or [])]))
        if action == 'setup': args.append('--install')
        if action == 'avatars': args += ['--wait-seconds','0']
        if shutil.which('rtk'): args = ['rtk','proxy',*args]
        env = {**os.environ, 'MONTAGE_PROJECT_ROOT':str(self.app.project),
               'MONTAGE_QUEUE_ITEM':row['id'], 'MONTAGE_QUEUE_LEASE':lease}
        owner=Path(row['job'])
        if action=='revise':
            owner=self.app.data/'queue-workers'/row['id']
        log_dir = (owner if action=='revise' else job) / 'pipeline-logs'; self.app.ensure_dir(log_dir)
        stdout, stderr = log_dir / (action+'.out'), log_dir / (action+'.err')
        receipt=owner/'pipeline-process.json';prior=self.read(receipt,{})
        if prior.get('state')=='running':
            try:os.kill(prior['pid'],0)
            except ProcessLookupError:pass
            else:raise ValueError('上次本地执行进程尚未确认退出，不能重复启动阶段')
        with stdout.open('w') as out, stderr.open('w') as err:
            process = subprocess.Popen(args, cwd=self.app.project, env=env, stdout=out, stderr=err,start_new_session=sys.platform!='win32')
            self.write(receipt,{'pid':process.pid,'state':'running','action':action,'leaseHash':hashlib.sha256(lease.encode()).hexdigest(),'started':time.time()})
            last_report = time.monotonic()
            deadline = last_report + 600 if action in ('inventory','revise') else None
            while process.poll() is None:
                current = self.app.queue.item(row['id'])
                timed_out = deadline is not None and time.monotonic() >= deadline
                if current.get('lease') != lease or current['status']!='running' or timed_out:
                    if sys.platform!='win32':os.killpg(process.pid,signal.SIGTERM)
                    else:process.terminate()
                    try: process.wait(timeout=15)
                    except subprocess.TimeoutExpired: process.kill(); process.wait()
                    if sys.platform!='win32':
                        try:os.killpg(process.pid,signal.SIGKILL)
                        except ProcessLookupError:pass
                    self.write(receipt,{'pid':process.pid,'state':'exited','action':action,'cancelled':True,'ended':time.time()})
                    raise ValueError('素材准备超时，可重试原序号' if timed_out else '当前阶段已停止，云端任务 ID 与已有资产保留')
                if time.monotonic()-last_report >= 60:
                    self.app.queue.report(row['id'],lease,PHASE.get(action,0),'running','仍在执行本地步骤：'+action)
                    last_report=time.monotonic()
                time.sleep(.5)
        self.write(receipt,{'pid':process.pid,'state':'exited','action':action,'returnCode':process.returncode,'ended':time.time()})
        try: result = json.loads(stdout.read_text())
        except ValueError: result = {'error':self.app.redact(stderr.read_text()[-1500:] or stdout.read_text()[-1500:])}
        return process.returncode, result

    def gate(self, job, step):
        if step == 'content-review':
            review=self.read(job/'content-review.json',{})
            value={'plan':self.read(job/'plan.json'),'inventory':self.read(job/'inventory.json')}
            expected=hashlib.sha256(json.dumps(value,sort_keys=True,ensure_ascii=False).encode()).hexdigest()
            return review.get('inputFingerprint')==expected
        if step == 'provider-review':
            for avatar in self.read(job/'avatars.json',[]):
                data=self.read(job/'assets'/('avatar-'+avatar['id'])/'generation-source.json',{})
                if data.get('visualReviewPending',True): return False
                if fingerprint(data['video'])!=data.get('videoSha256'): return False
            return True
        if step == 'layout-review':
            review=self.read(job/'layout-review.json',{})
            if review.get('composition')!=fingerprint(job/'index.html'): return False
            return bool(review.get('frames')) and all(Path(f['file']).is_file() and fingerprint(f['file'])==f['sha256'] for f in review['frames'])
        if step == 'final-review':
            verify=self.read(job/'verification.json',{})
            if verify.get('visualReviewPending',True) or not verify.get('fullDecode'): return False
            path=Path(verify.get('video',''))
            return path.is_file() and fingerprint(path)==verify.get('sha256')
        return False

    def advance(self, ident, lease, max_seconds=600):
        row=self.row(ident,lease)
        if row['kind']!='video': raise ValueError('策划任务不运行视频流水线')
        job=Path(row['job']);self.app.ensure_dir(job)
        journal_path=job/'pipeline.json';journal=self.read(journal_path,{'steps':[]})
        if not (job/'plan.json').is_file(): raise ValueError('缺少本条批准计划')
        if journal.get('plan') and journal['plan']!=fingerprint(job/'plan.json'):
            raise ValueError('执行期间计划发生变化，请另存重做或先复核受影响资产')
        deadline=time.monotonic()+max_seconds
        for step in STEPS:
            current=self.row(ident,lease)
            if current['status']=='stopping':
                self.app.queue.report(ident,lease,PHASE[step],'running','已到停止检查点')
            if step in journal['steps']: continue
            if step=='check' and journal.get('reviewedCheck') and (job/'check.json').is_file() and journal['reviewedCheck']==fingerprint(job/'check.json'):
                journal.pop('reviewedCheck')
            elif step.endswith('-review'):
                if not self.gate(job,step):
                    self.write(journal_path,{**journal,'plan':fingerprint(job/'plan.json'),'waiting':step})
                    return {'state':'needs_review','gate':step,'job':str(job),'phase':PHASE[step]}
            else:
                self.app.queue.report(ident,lease,PHASE[step],'running','正在执行：'+step)
                code,result=self.invoke(row,lease,step)
                while (code==2 or result.get('pending')) and time.monotonic()+10<deadline:
                    # Poll the same registered provider task; no model round trip.
                    time.sleep(10)
                    current=self.row(ident,lease)
                    if current['status']=='stopping':self.app.queue.report(ident,lease,PHASE[step],'running','已到停止检查点')
                    code,result=self.invoke(row,lease,step)
                if code==2 or result.get('pending'):
                    self.write(journal_path,{**journal,'plan':fingerprint(job/'plan.json'),'waiting':step})
                    return {'state':'pending','step':step,'result':result}
                if code: return {'state':'failed','step':step,'result':result,'job':str(job)}
            journal['steps'].append(step);journal['plan']=fingerprint(job/'plan.json');journal.pop('waiting',None)
            self.write(journal_path,journal)
            if time.monotonic()>=deadline: return {'state':'checkpoint','step':step,'job':str(job)}
        self.app.verify_job(job)
        self.app.queue.report(ident,lease,5,'completed','视频已核验并打包，等待用户验收')
        return {'state':'completed','job':str(job)}

    def review(self, ident, lease, kind, note, frames=None):
        row=self.row(ident,lease);job=Path(row['job'])
        if not isinstance(note,str) or not note.strip(): raise ValueError('请记录实际查看后的具体观察')
        if not isinstance(frames or [],list): raise ValueError('检查帧格式错误')
        for path in frames or []:
            if not Path(path).resolve().is_relative_to(job.resolve()) or not Path(path).is_file():
                raise ValueError('仅接受当前工程的实际检查帧')
        if kind=='layout':
            if not frames or any(not Path(p).resolve().is_relative_to((job/'qc-layout').resolve()) for p in frames):
                raise ValueError('请提供当前工程 qc-layout 的实际排版检查帧')
            self.write(job/'layout-review.json',{'composition':fingerprint(job/'index.html'),
                       'frames':[{'file':str(Path(p).resolve()),'sha256':fingerprint(p)} for p in frames],'note':note})
            return {'recorded':True}
        if kind not in REVIEW_ACTIONS: raise ValueError('未知审核类型')
        extra=['--note',note]
        if kind!='content':extra+=['--frames',*(frames or [])]
        code,result=self.invoke(row,lease,REVIEW_ACTIONS[kind],extra)
        if code: raise ValueError(str(result))
        if kind=='contrast' and result.get('renderAcceptedWithVisualContrastReview'):
            journal_path=job/'pipeline.json'
            journal=self.read(journal_path,{})
            if journal.get('plan')==fingerprint(job/'plan.json') and 'carve' in journal.get('steps',[]) and 'check' not in journal['steps']:
                self.write(journal_path,{**journal,'reviewedCheck':fingerprint(job/'check.json')})
        return result
