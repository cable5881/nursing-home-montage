"""Structured editing and vision calls. The model cannot execute local tools."""
from pathlib import Path
import subprocess

from model_api import image_part


class NeedsInput(ValueError):
    pass


def chunks(items, count):
    for start in range(0, len(items), count):
        yield items[start:start + count]


def frame(path, second=None):
    seek = ['-ss', str(second)] if second is not None else []
    result = subprocess.run(['ffmpeg', '-nostdin', '-v', 'error', *seek, '-protocol_whitelist', 'file,pipe',
                             '-i', str(path), '-frames:v', '1',
                             '-vf', 'scale=768:768:force_original_aspect_ratio=decrease',
                             '-f', 'image2pipe', '-c:v', 'mjpeg', '-threads', '1', '-q:v', '4', 'pipe:1'],
                            capture_output=True, timeout=45)
    if result.returncode or not result.stdout.startswith(b'\xff\xd8'):
        raise ValueError('无法读取媒体检查帧，请确认本地素材可正常播放。')
    return result.stdout


class Editor:
    def __init__(self, skill, client, read, write, checkpoint):
        self.skill, self.client = skill, client
        self.read, self.write, self.checkpoint = read, write, checkpoint

    def rules(self, *names):
        return '\n\n'.join((self.skill / 'references' / (name + '.md')).read_text(encoding='utf-8')
                           for name in names)

    def ask(self, instruction, data, visuals=(), max_tokens=2400):
        self.checkpoint()
        images = []
        for label, data_bytes in visuals:
            images.extend([{'type': 'text', 'text': label}, image_part(data_bytes)])
        result = self.client.ask(instruction, data, images, max_tokens)
        self.checkpoint()
        return result

    def media(self, folder, inventory):
        root = Path(inventory['source']).resolve()
        visual = [x for x in inventory['files'] if x['kind'] in ('image', 'video')]
        cache = folder / 'independent-media-review.json'
        stored = self.read(cache, {})
        result = []
        for group in chunks(visual, 4):
            missing = [x for x in group if x.get('sha256') not in stored]
            if missing:
                visuals = []
                for row in missing:
                    p = (root / row['path']).resolve()
                    if not p.is_relative_to(root):
                        raise ValueError('素材路径越出了所在机构目录。')
                    if row['kind'] == 'video':
                        duration = row['duration']
                        for t in (duration * .2, duration * .65):
                            visuals.append((f"{row['path']} | {t:.2f} 秒", frame(p, t)))
                    else:
                        visuals.append((row['path'], frame(p)))
                response = self.ask(
                    '观察每张实图。按文件名归纳可见内容、裁剪关注位置，视频对照两个时点描述可见运动。'
                    '不凭图片推断护理水平或其他事实。JSON {"media":[{"path":"文件名","description":"可见细节","motion":true}]}。',
                    {'paths': [x['path'] for x in missing]}, visuals)
                by_path = {x.get('path'): x for x in response.get('media', []) if isinstance(x, dict)}
                if set(by_path) != {x['path'] for x in missing}:
                    raise ValueError('模型未逐项完成素材观察，可重试当前步骤。')
                for x in missing:
                    observation = by_path[x['path']]
                    note = observation.get('description')
                    if not isinstance(note, str) or not note.strip():
                        raise ValueError('模型缺少素材观察记录。')
                    stored[x['sha256']] = {'description': note[:700], 'motion': x['kind'] == 'video' and observation.get('motion') is True}
                self.write(cache, stored)
            result.extend({k: x[k] for k in ('path', 'kind', 'duration', 'width', 'height')} | stored[x['sha256']] for x in group)
        if not any(x['kind'] == 'video' and x['motion'] for x in result):
            raise NeedsInput('当前素材观察未找到适合开头和结尾的移动视频，请补充实拍移动素材或说明哪段可用。')
        return result

    def context(self, task, folder, answer):
        inventory = self.read(folder / 'inventory.json')
        sources = {x['path']: x['text'] for x in inventory['files'] if x['kind'] == 'text'}
        return {
            'sources': sources, 'media': self.media(folder, inventory),
            'institutionName': task.get('institutionName') or '',
            'requirements': task.get('requirements', ''), 'answer': answer,
        }

    def outline(self, context):
        result = self.ask(
            '为养老机构的综合探访找出主要事实。只用当前资料可逐字引用的内容，保留各项限定词。'
            '选择资料里能支撑的共同主线，事实不足时给出需补充的具体问题。JSON '
            '{"facts":[{"text":"口语事实概括","source":"对应原文文件名","quote":"原文逐字符引用"}],"question":null}。',
            {k: v for k, v in context.items() if k != 'media'})
        question(result)
        facts = result.get('facts')
        if not isinstance(facts, list) or not 1 <= len(facts) <= 24:
            raise ValueError('模型未提炼出可审核的共同事实。')
        output = []
        for i, fact in enumerate(facts, 1):
            source = fact.get('source')
            quote = fact.get('quote')
            text = fact.get('text')
            if not all(isinstance(x, str) and x.strip() for x in (source, quote, text)) or quote not in context['sources'].get(source, ''):
                raise ValueError('模型给出的事实缺少可核对的逐字原文。')
            output.append({'id': f'f{i}', 'text': text, 'source': source, 'quote': quote})
        return output

    def plan(self, task, index, context, facts, previous, feedback=''):
        prefs = (task.get('videoPreferences') or [''] * task['count'])[index]
        person = (task.get('videoSpecs') or [{'person': task['person']}] * task['count'])[index]['person']
        revised = task.get('revisedNarration', '')
        result = self.ask(
            '你负责写一条中文养老机构探访视频。按下列技能规则先写整篇口语稿并做语言润色，再分句选镜和定封面。'
            '仅使用真实素材，选片基于提供的实看结果。开头和结尾选有运动的源视频；在短片剩余时长足够的区间取镜，'
            '预计每秒 3.5 至 4 个汉字，给足分镜，sourceStart 使用秒数。不要指定资源路径、任何运行设置或关闭审核。'
            '字幕由现有程序生成，可省略 captions；若有精确字幕偏好才逐条完整提供。'
            '统一用传入 fact IDs，综合稿在 sentences 中覆盖全部；仅在用户偏好明确指定专题时返回 topicAuthorization 原话。'
            '若 revisedNarration 非空，逐字保留用户文案及标点，可重新断句但不删改文字。不够信息时填 question。'
            '输出 JSON {"plan":{按规范的单条计划},"openingAngle":"开头","structure":"展开顺序",'
            '"coverAngle":"封面主题","topicAuthorization":"","question":null}。\n'
            + self.rules('plan-schema', 'narration', 'narration-polish', 'covers'),
            {**context, 'facts': facts, 'person': person, 'index': index + 1, 'total': task['count'],
             'preference': prefs, 'previousAngles': previous, 'feedback': feedback,
             'revisedNarration': revised, 'publicationOverride': task.get('publicationOverride', {})},
            max_tokens=12000)
        question(result)
        raw = result.get('plan')
        if not isinstance(raw, dict):
            raise ValueError('模型未返回完整的单条制作计划。')
        plan = {key: raw[key] for key in ('institution', 'sentences', 'asrPrompt', 'cover', 'publication') if key in raw}
        plan.update(version=1, person=person, facts=[{k: x[k] for k in ('id', 'source', 'quote')} for x in facts])
        plan['settings'] = {'music': {'enabled': task['music']}}
        if task.get('musicTrack'):
            plan['settings']['music']['resource'] = task['musicTrack']['resource']
        if context['institutionName']:
            plan['institution']['name'] = context['institutionName']
        selected = {x['path']: x for x in context['media']}
        sentences = plan.get('sentences', [])
        if not sentences or len(sentences) > 100:
            raise ValueError('口播句子缺失或过多。')
        for i, sentence in enumerate(sentences):
            for shot in sentence['shots']:
                media = selected.get(shot['path'])
                if not media or (media['kind'] == 'video' and not 0 <= shot.get('sourceStart', 0) < media['duration']):
                    raise ValueError('选片超出了实际素材或有效时间。')
                if (i == 0 or sentence.get('kind') == 'cta') and not media['motion']:
                    raise ValueError('开头及片尾需选实际观察到运动的视频。')
        if revised:
            text = ''.join(s['text'] for s in sentences)
            if ''.join(revised.split()) != ''.join(text.split()):
                raise ValueError('修订稿必须保留用户原话。')
        for k, value in task.get('publicationOverride', {}).items():
            if k in ('title', 'description') and value:
                plan['publication'][k] = value
        used = list(dict.fromkeys(f for sentence in sentences for f in sentence.get('factIds', [])))
        authorization = result.get('topicAuthorization') or ''
        if authorization and (not isinstance(authorization, str) or authorization not in task.get('requirements', '') + '\n' + prefs):
            raise ValueError('专题需能引用用户明确提出的要求。')
        angles = {k: result.get(k) for k in ('openingAngle', 'structure', 'coverAngle')}
        if any(not isinstance(v, str) or not v.strip() for v in angles.values()):
            raise ValueError('缺少本条的开头、结构或封面角度。')
        if not authorization and set(used) != {x['id'] for x in facts}:
            raise ValueError('综合稿没有覆盖全部共同事实。')
        return plan, {**angles, 'factCoverage': used, 'mode': 'topic' if authorization else 'comprehensive',
                      'topicAuthorization': authorization}

    def content_review(self, job, answer):
        plan = self.read(job / 'plan.json')
        context = self.context({'requirements': ''}, job, answer)
        response = self.ask(
            '核对每句口播与事实原文，核对语义及所有限定词。用已有实看素材描述核对文画关系及封面三槽。'
            '审核口语质量、覆盖范围、结尾咨询、封面及发布文案。材料未支持或文画明显不合时拒绝。'
            'JSON {"ok":true,"note":"具体到口播、事实和素材的审核观察"}。\n' + self.rules('content-review'),
            {**context, 'plan': plan, 'audit': self.read(job / 'content-audit.json', {})})
        return approved(response)

    def review_frames(self, job, paths, instructions, context=None):
        job = job.resolve()
        known = sorted(set(Path(p).resolve() for p in paths))
        if not known or any(not p.is_relative_to(job) or not p.is_file() for p in known):
            raise ValueError('当前工程缺少可验证的检查帧。')
        notes = []
        for group in chunks(known, 6):
            names = [str(p.relative_to(job)) for p in group]
            result = self.ask(instructions + '必须实际查看每张图，发现显著问题时拒绝。'
                              'JSON {"ok":true,"seen":["传入的完整帧文件名"],"note":"具体可见观察"}。',
                              {'frames': names, 'context': context},
                              [(name, frame(p)) for name, p in zip(names, group)])
            seen = result.get('seen')
            if not isinstance(seen, list) or any(not isinstance(x, str) for x in seen) or set(seen) != set(names):
                raise ValueError('模型未确认看完当前检查帧，请重试视觉复核。')
            notes.append(approved(result))
        return [str(p) for p in known], '\n'.join(notes)


def question(result):
    text = result.get('question')
    if isinstance(text, str) and text.strip():
        raise NeedsInput(text[:1200])


def approved(response):
    note = response.get('note')
    if not isinstance(note, str) or not note.strip():
        raise ValueError('模型未返回具体审核结论。')
    if response.get('ok') is not True:
        raise NeedsInput('本条审核需你确认，请补充或修正后继续。' + note[:900])
    return note[:600]
