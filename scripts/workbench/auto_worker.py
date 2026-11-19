"""Independent FIFO coordinator for the existing production pipeline."""
import os
from pathlib import Path
import re
import threading
import uuid

from auto_editor import Editor, NeedsInput, PlanError, approved
from pipeline import Pipeline, fingerprint
from planning import digest


class StageError(ValueError):
    pass


class LocalCoordinator:
    def __init__(self, app, read, write):
        self.app, self.read, self.write = app, read, write
        self.thread = None

    def tick(self):
        if self.app.service_mode != 'standalone':
            return
        if self.thread and self.thread.is_alive():
            return
        head = self.app.queue.head() or {}
        owner = head.get('localExecution')
        if owner and not head.get('settled'):
            if process_alive(owner['pid']) or self.app.channel.has_active(head['id']):
                return
            evidence = '独立工作台进程和本阶段子进程均已退出，按已有检查点恢复'
            self.app.queue.recover(head['id'], head['lease'], evidence, local=owner)
        config = self.app.models.public()
        if not config['enabled'] or not config['providers'][config['provider']]['configured']:
            return
        owner = {'id': uuid.uuid4().hex, 'pid': os.getpid()}
        row = self.app.queue.claim_next(local=owner)
        if row:
            self.thread = threading.Thread(target=self.run, args=(row,), daemon=True)
            self.thread.start()

    def run(self, row):
        queue = self.app.queue
        ident, lease = row['id'], row['lease']
        worker = Production(self.app, row, self.read, self.write)
        try:
            queue.accept(ident, lease, row['localExecution']['id'])
            worker.execute()
        except NeedsInput as exc:
            note = self.app.redact(str(exc))[:1200]
            worker.terminal('needs_input', '本条需要你补充或核对', note)
        except Exception as exc:
            worker.terminal('failed', self.app.redact(str(exc))[:1000])
        finally:
            queue.settle(ident, lease, local=row['localExecution'])


def process_alive(pid):
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


class Production:
    def __init__(self, app, row, read, write):
        self.app, self.row, self.read, self.write = app, row, read, write
        self.item, self.lease = row['id'], row['lease']
        self.job = Path(row['job'])
        self.pipe = Pipeline(app, read, write)
        self.editor = None

    def status(self):
        return self.app.queue.item(self.item)

    def checkpoint(self):
        row = self.status()
        if row['status'] == 'stopping':
            self.app.queue.report(self.item, self.lease, min(5, row['phase']), 'running', '已到停止检查点')
        self.pipe.row(self.item, self.lease)

    def terminal(self, status, note, question=None):
        row = self.status()
        if row['status'] not in ('running', 'stopping'):
            return
        try:
            self.app.queue.report(self.item, self.lease, min(5, row['phase']), status, note, question)
        except ValueError:
            if self.status()['status'] != 'cancelled':
                raise

    def progress(self, message):
        row = self.status()
        self.app.queue.report(self.item, self.lease, min(5, row['phase']), 'running', message)

    def invoke(self, action, *, job=None, cli_args=None, extra=None):
        self.checkpoint()
        code, result = self.pipe.invoke(self.row, self.lease, action, extra=extra, job=job, cli_args=cli_args)
        if code:
            raise StageError(str(result.get('error') or result))
        return result

    def inventory(self, task, folder):
        if not (folder / 'inventory.json').is_file():
            self.progress('正在整理机构素材')
            self.invoke('inventory', job=folder, cli_args=['inventory', task['source'], '--out', folder])
        if task.get('facts'):
            self.app.planning.append_facts(task, folder)

    def execute(self):
        self.editor = Editor(self.app.skill, self.app.models.client(), self.read, self.write, self.checkpoint)
        task = self.app.task(self.row['taskId'])
        answer = {'question': self.row.get('answerQuestion'), 'reply': self.row.get('answer')}
        if self.row['kind'] == 'planning':
            self.plan_batch(task, answer)
            self.terminal('completed', '整批策划及逐条结构校验已通过')
            return
        self.prepare_video(task, answer)
        while True:
            result = self.pipe.advance(self.item, self.lease)
            state = result['state']
            if state == 'completed':
                return
            if state == 'needs_review':
                self.review(result['gate'], answer)
            elif state == 'failed':
                if result['step'] == 'check' and self.review_contrast(answer):
                    continue
                detail = result.get('result', {})
                raise ValueError(f"{result['step']} 阶段暂停：" + str(detail.get('error') or detail))
            elif state not in ('checkpoint', 'pending'):
                raise ValueError('制作阶段返回了未知状态。')

    def plan_batch(self, task, answer):
        folder, input_fingerprint = self.app.planning.initialize(task)
        if (folder / 'approved.json').is_file():
            self.app.planning.verify(task)
            return
        self.inventory(task, folder)
        self.progress('正在向模型提交机构资料及实拍检查帧')
        context = self.editor.context(task, folder, answer)
        cache_path = folder / 'independent-planning.json'
        # Rebuild unfinished outlines written before the batch stopped treating source details as core facts.
        identity = digest({'input': input_fingerprint, 'answer': answer, 'editorialVersion': 2})
        cache = self.read(cache_path, {})
        if cache.get('input') != identity:
            cache = {'input': identity, 'facts': self.editor.batch_outline(context), 'plans': []}
            self.write(cache_path, cache)
        facts = cache['facts']
        items = []
        for index in range(task['count']):
            self.checkpoint()
            path = folder / 'plans' / f'{index + 1:04d}.json'
            if index < len(cache['plans']):
                item = cache['plans'][index]
                if path.is_file() and item['sha256'] == fingerprint(path):
                    items.append(item['item'])
                    continue
                cache['plans'] = cache['plans'][:index]
            self.progress(f'整批策划：正在编排第 {index + 1}/{task["count"]} 条')
            feedback = ''
            for attempt in range(3):
                try:
                    plan, angles = self.editor.plan(task, index, context, facts, items[-12:], feedback)
                    self.app.planning.validate_item(task, folder, index, plan,
                                                    lambda job: self.invoke('validate-plan', job=job))
                    break
                except (PlanError, StageError) as exc:
                    feedback = self.app.redact(str(exc))[:1000]
                    if attempt == 2:
                        raise ValueError(f'第 {index + 1} 条计划未通过校验。{feedback}') from exc
                    self.progress(f'整批策划：正在修正第 {index + 1}/{task["count"]} 条的校验问题')
            self.write(path, plan)
            item = {**angles, 'index': index, 'plan': str(path.relative_to(folder)), 'person': plan['person']}
            cache['plans'].append({'sha256': fingerprint(path), 'item': item})
            self.write(cache_path, cache)
            items.append(item)
        review = self.editor.ask(
            '审核整批事实和切入差异是否符合当前任务范围。综合稿要求覆盖共同核心，专题需能引用用户授权。'
            '按 JSON {"ok":true,"note":"真实判断","facts":"事实范围","differences":"差异检查","preferences":"偏好检查"}。'
            '逐条真实性与文画还将在每条付费前另行核验。',
            {'facts': facts, 'items': items, 'requirements': task.get('requirements', ''),
             'preferences': task.get('videoPreferences', [])}, max_tokens=2500)
        approved(review)
        draft = {'inputFingerprint': input_fingerprint, 'items': items, 'review': review,
                 'coreFacts': [{'id': x['id'], 'text': x['text'], 'evidence': {k: x[k] for k in ('source', 'quote')}} for x in facts]}
        self.write(folder / 'draft.json', draft)
        try:
            self.app.planning.check(task, lambda job: self.invoke('validate-plan', job=job))
        except Exception:
            # A fresh request may repair structurally invalid proposals.
            cache_path.unlink(missing_ok=True)
            raise

    def prepare_video(self, task, answer):
        plan_path = self.job / 'plan.json'
        if (self.job / 'runtime.json').is_file() or (plan_path.is_file() and task.get('planningRequired')):
            return
        marker = self.job / 'independent-plan.json'
        if plan_path.is_file():
            if not marker.exists():
                return  # An earlier approved or manually authored plan.
            plan_hash = fingerprint(plan_path)
            if plan_hash in (self.read(marker, {}).get('validated'), self.read(self.job / 'pipeline.json', {}).get('plan')):
                return
        is_revision = task.get('kind') == 'revision' and not task.get('revisionFromArchive')
        folder = self.app.data / 'queue-workers' / self.item / 'revision-input' if is_revision else self.job
        self.inventory(task, folder)
        context = self.editor.context(task, folder, answer)
        facts = self.editor.outline(context)
        feedback = ''
        for _ in range(3):
            try:
                plan, _ = self.editor.plan(task, self.row['index'], context, facts, [], feedback)
                if is_revision:
                    revised = folder.parent / 'revised-plan.json'
                    self.write(revised, plan)
                    self.invoke('revise', cli_args=['revise', task['baseJob'], '--out', self.job, '--plan', revised])
                    self.app.planning.append_facts(task, self.job)
                else:
                    self.write(marker, {'generated': True})
                    self.write(plan_path, plan)
                self.invoke('validate-plan')
                if not is_revision:
                    self.write(marker, {'validated': fingerprint(plan_path)})
                return
            except NeedsInput:
                raise
            except (ValueError, KeyError, AttributeError, TypeError) as exc:
                if is_revision:
                    raise
                feedback = self.app.redact(str(exc))[:1500]
        raise ValueError('模型计划未能通过结构检查：' + feedback)

    def review(self, gate, answer):
        name = gate.removesuffix('-review')
        self.progress('正在审核' + {'content': '文案和分镜', 'provider': '数字人原片',
                                     'layout': '封面和排版', 'final': '成片检查帧'}[name])
        if name == 'content':
            self.pipe.review(self.item, self.lease, name, self.editor.content_review(self.job, answer))
            return
        if name == 'provider':
            frames = []
            for avatar in self.read(self.job / 'avatars.json'):
                source = self.read(self.job / 'assets' / ('avatar-' + avatar['id']) / 'generation-source.json')
                frames.extend(source['visualReviewFrames'])
            instructions = '审核数字人原片的嘴形、眼神、脸、手、构图、水印和是否有明显变形。'
        elif name == 'layout':
            frames = sorted((self.job / 'qc-layout').glob('*.png'))
            instructions = '查看实际封面、正文、字幕与分镜。检查文字是否裁切、遮挡、可读，画面是否与内容协调。'
        else:
            frames = self.read(self.job / 'verification.json')['renderedReviewFrames']
            instructions = '核查所有实际成片帧，包括封面首帧、正文次帧、切镜与字幕差异。发现黑屏、错人、裁切或遮挡应拒绝。'
        evidence, note = self.editor.review_frames(self.job, frames, instructions, answer)
        self.pipe.review(self.item, self.lease, name, note, evidence)

    def review_contrast(self, answer):
        check = self.read(self.job / 'check.json', {})
        if check.get('browserSkipped') or any(value.get('errorCount') for name, value in check.items()
                                              if name not in ('contrast', 'visualContrastReview') and isinstance(value, dict)):
            return False
        findings = [x for x in check.get('contrast', {}).get('findings', []) if x.get('severity') == 'error']
        if not findings or any(x.get('code') != 'contrast_aa_failure' or not isinstance(x.get('time'), (float, int)) for x in findings):
            return False
        self.progress('正在按原样式复核有对比度提示的检查帧')
        times = sorted({round(x['time'], 3) for x in findings})
        self.invoke('snapshot', extra=['--at', ','.join(map(str, times))])
        all_frames = sorted((self.job / 'qc-layout').glob('*.png'))
        frames = []
        for p in all_frames:
            sample = re.search(r'-at-([0-9.]+)s', p.name)
            if sample and any(abs(float(sample[1])-t)<.004 for t in times):
                frames.append(p)
        if not frames:
            raise ValueError('未截取到对比度提示对应的实际检查帧。')
        evidence, note = self.editor.review_frames(
            self.job, frames, '按原样式判断提示位置的描边和文字是否实际清晰可读。'
            '真实难以辨认时必须拒绝，保留自动对比度失败。', {'findings': findings, 'answer': answer})
        result = self.pipe.review(self.item, self.lease, 'contrast', note, evidence)
        return result.get('renderAcceptedWithVisualContrastReview') is True
