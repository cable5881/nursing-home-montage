"""Structured editing and vision calls. The model cannot execute local tools."""
from pathlib import Path
import re
import subprocess

from model_api import image_part


class NeedsInput(ValueError):
    pass


class PlanError(ValueError):
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

    def batch_outline(self, context):
        evidence = {}
        for source, text in context['sources'].items():
            for quote in re.findall(r'[^。！？\r\n]+[。！？]*', text):
                if quote.strip():
                    evidence[f'e{len(evidence) + 1}'] = {'source': source, 'quote': quote.strip()}
        data = {k: v for k, v in context.items() if k not in ('sources', 'media')}
        feedback = ''
        for _ in range(3):
            result = self.ask(
                '为每条约一分钟的养老机构综合探访选出家属最关心的两到三组核心特点，通常只需三到五条简短事实。'
                '每项只写一个能在正文里讲清的要点。除非用户特别要求，背景年份、门牌、规模数字和设施清单'
                '无需列为每条都必须重复的共同事实。每条事实必须完全受其对应原文段落支持，并保留限定词。'
                '从 evidence 中选择对应编号（如 e1），由程序取原文。如果已有 feedback，按提示修正。'
                '事实不足时给出具体问题。JSON {"facts":[{"text":"简短事实","evidenceId":"e1"}],"question":null}。',
                {**data, 'evidence': evidence, 'feedback': feedback})
            question(result)
            facts = result.get('facts')
            if not isinstance(facts, list) or not 1 <= len(facts) <= 24:
                feedback = '请在 facts 数组中给出实际可核对的共同事实。'
                continue
            output = []
            for i, fact in enumerate(facts, 1):
                text = fact.get('text') if isinstance(fact, dict) else None
                key = fact.get('evidenceId') if isinstance(fact, dict) else None
                if not isinstance(text, str) or not text.strip() or not isinstance(key, str) or key not in evidence:
                    feedback = f'第 {i} 项必须包含非空的事实内容和 evidence 中实际存在的 evidenceId。'
                    break
                output.append({'id': f'f{i}', 'text': text.strip(), **evidence[key]})
            if len(output) == len(facts):
                return output
        raise ValueError('共同事实提炼未通过原文校验。' + feedback)

    def plan(self, task, index, context, facts, previous, feedback=''):
        prefs = (task.get('videoPreferences') or [''] * task['count'])[index]
        person = (task.get('videoSpecs') or [{'person': task['person']}] * task['count'])[index]['person']
        revised = task.get('revisedNarration', '')
        result = self.ask(
            '你负责写一条中文养老机构探访视频。按下列技能规则先写整篇口语稿并做语言润色，再分句选镜和定封面。'
            '仅使用真实素材，选片基于提供的实看结果。开头和结尾选有运动的源视频；在短片剩余时长足够的区间取镜，'
            '预计每秒 3.5 至 4 个汉字，给足分镜，sourceStart 使用秒数。不要指定资源路径、任何运行设置或关闭审核。'
            '字幕由现有程序生成，可省略 captions；若有精确字幕偏好才逐条完整提供。'
            '各事实写进实际口播后，在对应句的 factIds 数组中逐项标明传入的编号，如 ["f1","f2"]。'
            '综合稿的 sentences 必须覆盖全部传入编号。收到 feedback 时先修正指出的问题。如果有事实遗漏，按原文补写再标注。'
            '仅在用户偏好明确指定专题时返回 topicAuthorization 原话。'
            '若 revisedNarration 非空，逐字保留用户文案及标点，可重新断句但不删改文字。不够信息时填 question。'
            '输出一个 JSON 对象。顶层结构为 {"plan":{},"openingAngle":"本条如何开场","structure":"本条展开顺序",'
            '"coverAngle":"本条封面主题","topicAuthorization":"","question":null}。三项角度均填写具体内容。'
            'plan 必须同时包含 institution、sentences、cover 和 publication。'
            '封面放在 plan.cover，包含 main_title 和三个 labels；发布文案放在 plan.publication，'
            '包含 title、description 和五个不同的 topics。两个字段都按同一条完整口播撰写。\n'
            + self.rules('plan-schema', 'narration', 'narration-polish', 'covers'),
            {**context, 'facts': facts, 'person': person, 'index': index + 1, 'total': task['count'],
             'preference': prefs, 'previousAngles': previous, 'feedback': feedback,
             'revisedNarration': revised, 'publicationOverride': task.get('publicationOverride', {})},
            max_tokens=12000)
        question(result)
        raw = result.get('plan')
        if not isinstance(raw, dict):
            raise PlanError('模型必须在顶层 plan 字段返回完整的单条制作计划。')
        if not isinstance(raw.get('institution'), dict):
            raise PlanError('plan.institution 必须填写为对象。')
        plan = {key: raw[key] for key in ('institution', 'sentences', 'asrPrompt', 'cover', 'publication') if key in raw}
        plan.update(version=1, person=person, facts=[{k: x[k] for k in ('id', 'source', 'quote')} for x in facts])
        plan['settings'] = {'music': {'enabled': task['music']}}
        if task.get('musicTrack'):
            plan['settings']['music']['resource'] = task['musicTrack']['resource']
        if context['institutionName']:
            plan['institution']['name'] = context['institutionName']
        selected = {x['path']: x for x in context['media']}
        sentences = plan.get('sentences', [])
        if not isinstance(sentences, list) or not 1 <= len(sentences) <= 100:
            raise PlanError('plan.sentences 必须是包含口播句子和分镜的数组。')
        for i, sentence in enumerate(sentences):
            if not isinstance(sentence, dict) or not isinstance(sentence.get('text'), str) or not isinstance(sentence.get('shots'), list):
                raise PlanError(f'第 {i + 1} 句须包含口播 text 和 shots 数组。')
            for shot in sentence['shots']:
                path = shot.get('path') if isinstance(shot, dict) else None
                media = selected.get(path) if isinstance(path, str) else None
                start = shot.get('sourceStart', 0) if media else None
                if not media or (media['kind'] == 'video' and
                                 (not isinstance(start, (int, float)) or not 0 <= start < media['duration'])):
                    raise PlanError(f'第 {i + 1} 句选片超出了实际素材或有效时间，请核对 path 和 sourceStart。')
                if (i == 0 or sentence.get('kind') == 'cta') and not media['motion']:
                    raise PlanError('开头及片尾需选实际观察到运动的视频。')
        if revised:
            text = ''.join(s['text'] for s in sentences)
            if ''.join(revised.split()) != ''.join(text.split()):
                raise PlanError('修订稿必须保留用户原话。')
        for k, value in task.get('publicationOverride', {}).items():
            if k in ('title', 'description') and value:
                if not isinstance(plan.get('publication'), dict):
                    raise PlanError('plan.publication 必须填写为对象，以保留用户的发布文案。')
                plan['publication'][k] = value
        used = {}
        for number, sentence in enumerate(sentences, 1):
            ids = sentence.get('factIds', [])
            if not isinstance(ids, list) or any(not isinstance(f, str) for f in ids):
                raise PlanError(f'第 {number} 句的 factIds 必须是编号字符串数组，如 ["f1","f2"]。')
            used.update(dict.fromkeys(ids))
        authorization = result.get('topicAuthorization') or ''
        if authorization and (not isinstance(authorization, str) or authorization not in task.get('requirements', '') + '\n' + prefs):
            raise PlanError('专题需能引用用户明确提出的要求。')
        angles = {k: result.get(k) for k in ('openingAngle', 'structure', 'coverAngle')}
        missing_angles = [k for k, v in angles.items() if not isinstance(v, str) or not v.strip()]
        if missing_angles:
            raise PlanError('请补齐顶层策划角度字段 ' + '、'.join(missing_angles) + '。')
        expected = {x['id'] for x in facts}
        unknown = sorted(set(used) - expected)
        missing = sorted(expected - set(used)) if not authorization else []
        issues = []
        if missing:
            issues.append('口播缺少共同事实 ' + '、'.join(missing) + '，请在对应句写清事实并标注编号')
        if unknown:
            issues.append('factIds 使用了未提供的编号 ' + '、'.join(unknown))
        if issues:
            raise PlanError('。'.join(issues) + '。')
        return plan, {**angles, 'factCoverage': list(used), 'mode': 'topic' if authorization else 'comprehensive',
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
