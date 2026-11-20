"""Structured editing and vision calls. The model cannot execute local tools."""
from pathlib import Path
import re
import subprocess

from model_api import ModelResponseError, image_part


NARRATOR_CONTEXT = (
    '任务中已选的人物是已配置的数字人解说角色。仅用机构资料和实拍做介绍，'
    '无需补充解说人的现实身份、机构关系、到访日期、实际行程或授权信息。'
    '未提供的非必需信息直接略过，只有缺少完成用户必需要求的资料才提问。'
)


class NeedsInput(ValueError):
    pass


class PlanError(ValueError):
    def __init__(self, message, candidate=None):
        super().__init__(message)
        self.candidate = candidate


def chunks(items, count):
    for start in range(0, len(items), count):
        yield items[start:start + count]


def source_evidence(sources):
    evidence = {}
    for source, text in sources.items():
        for quote in re.findall(r'[^。！？\r\n]+[。！？]*', text):
            if quote.strip():
                evidence[f'e{len(evidence) + 1}'] = {'source': source, 'quote': quote.strip()}
    return evidence


def frame(path, second=None, *, timeout=45):
    seek = ['-ss', str(second)] if second is not None else []
    result = subprocess.run(['ffmpeg', '-nostdin', '-v', 'error', *seek, '-protocol_whitelist', 'file,pipe',
                             '-i', str(path), '-frames:v', '1',
                             '-vf', 'scale=768:768:force_original_aspect_ratio=decrease',
                             '-f', 'image2pipe', '-c:v', 'mjpeg', '-threads', '1', '-q:v', '4', 'pipe:1'],
                            capture_output=True, timeout=timeout)
    if result.returncode or not result.stdout.startswith(b'\xff\xd8'):
        raise ValueError('无法读取媒体检查帧，请确认本地素材可正常播放。')
    return result.stdout


class Editor:
    def __init__(self, skill, client, read, write, checkpoint):
        self.skill, self.client = skill, client
        self.read, self.write, self.checkpoint = read, write, checkpoint
        self.time_budget = lambda maximum: maximum

    def read_frame(self, path, second=None):
        return frame(path, second, timeout=self.time_budget(45))

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
        candidates = {f'M{i}': row for i, row in enumerate(visual, 1)}
        frames = {}

        def observe(ids):
            visuals = []
            for ident in ids:
                row = candidates[ident]
                if ident not in frames:
                    p = (root / row['path']).resolve()
                    if not p.is_relative_to(root):
                        raise ValueError('素材路径越出了所在机构目录。')
                    times = (.2 * row['duration'], .65 * row['duration']) if row['kind'] == 'video' else (None,)
                    frames[ident] = [(f'{ident} 图 {index}', self.read_frame(p, time)) for index, time in enumerate(times, 1)]
                visuals.extend(frames[ident])
            try:
                response = self.ask(
                    '按素材短编号观察实图。每个编号返回一条可见内容，视频对照两个时点描述可见运动。'
                    '不凭图片推断护理水平或身份。JSON {"media":[{"id":"M1","description":"可见细节","motion":true}]}。',
                    {'media': {i: candidates[i]['kind'] for i in ids}}, visuals)
            except ModelResponseError:
                return
            items = response.get('media')
            if not isinstance(items,list):return
            observed = set()
            for item in items:
                if not isinstance(item,dict):continue
                ident,note = item.get('id'),item.get('description')
                if not isinstance(ident,str) or ident not in ids or ident in observed or not isinstance(note,str) or not note.strip():continue
                row = candidates[ident]
                stored[row['sha256']] = {'description':note.strip()[:700], 'motion':row['kind']=='video' and item.get('motion') is True}
                observed.add(ident)
            if observed:self.write(cache,stored)

        for group in chunks(list(candidates),4):
            missing = [i for i in group if candidates[i]['sha256'] not in stored]
            if missing:observe(missing)
            for ident in missing:
                if candidates[ident]['sha256'] not in stored:observe([ident])
        result = [{k:x[k] for k in ('path','kind','duration','width','height')} | stored[x['sha256']]
                  for x in visual if x['sha256'] in stored]
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

    def batch_outline(self, context, evidence):
        data = {k: v for k, v in context.items() if k not in ('sources', 'media')}
        feedback = ''
        for _ in range(3):
            result = self.ask(
                NARRATOR_CONTEXT + '为每条约一分钟的养老机构综合探访选出家属最关心的两到三组核心特点，通常只需三到五条简短事实。'
                '每项只写一个能在正文里讲清的要点。除非用户特别要求，详细门牌和交通线路留在发布文案，'
                '背景年份、规模数字和设施清单'
                '无需列为每条都必须重复的共同事实。每条事实必须完全受其对应原文段落支持，并保留限定词。'
                '从 evidence 中选择对应编号（如 e1），由程序取原文。如果已有 feedback，按提示修正。'
                '事实不足时给出具体问题。JSON {"facts":[{"text":"简短事实","evidenceId":"e1"}],"question":null}。',
                {**data, 'evidence': evidence, 'feedback': feedback})
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
        question(result)
        raise ValueError('共同事实提炼未通过原文校验。' + feedback)

    def rebind_fact_references(self, sentences, references, candidate, *, editable=False, omit_unsupported=False):
        affected = {str(i):s for i,s in enumerate(sentences,1)
                    if any(ident not in references for ident in s.get('factIds',[]))
                    or (s.get('kind','fact')=='fact' and not s.get('factIds'))}
        if not affected:return
        response = self.ask(
            '只修复这些句子的事实引用。逐句选择能直接支持其中全部事实及限定词的原文编号。'
            '只能使用 evidence 中现有的编号，正文核心要点优先使用对应的 f 编号。'
            '允许修改文案时，如果原文只能支持句中的部分内容，在 rewrites 中给出简短的修订句，'
            '保留能证实的内容和原有主题。references 填修订句对应的编号。不能验证时填空数组。'
            '返回 {"references":{"句号":["原文编号"]},"rewrites":{"句号":"修订句"}}，使用输入的数字键。',
            {'sentences':{i:s['text'] for i,s in affected.items()},'evidence':references,'mayRewrite':editable},max_tokens=3000)
        bindings = response.get('references')
        rewrites = response.get('rewrites', {})
        if not isinstance(bindings,dict) or bindings.keys()!=affected.keys():
            raise PlanError('请按现有原文逐句纠正不存在的 factIds。',candidate)
        if not isinstance(rewrites,dict) or rewrites.keys()-affected.keys() or (rewrites and not editable):
            raise PlanError('请只修改指定句子的引用，保留不能改动的文案。',candidate)
        if any(not isinstance(value,str) or not value.strip() for value in rewrites.values()):
            raise PlanError('请用有出处的完整句子修复缺少引用的文案。',candidate)
        discarded=[]
        for i,s in affected.items():
            values=bindings[i]
            if not isinstance(values,list) or not values or any(not isinstance(v,str) or v not in references for v in values):
                if (omit_unsupported and 1<int(i)<len(sentences) and s.get('kind','fact')=='fact'
                        and not any(ident in references for ident in s.get('factIds',[]))):
                    discarded.append(int(i)-1)
                    continue
                raise PlanError(f'第 {i} 句仍缺少可核验的原文引用，请重新选择原文或改写。',candidate)
        for i,s in affected.items():
            if int(i)-1 in discarded:
                continue
            s['factIds']=list(dict.fromkeys(bindings[i]))
            if i in rewrites:
                s['text']=rewrites[i].strip()
        for index in sorted(discarded,reverse=True):
            del sentences[index]

    def fit_institution_labels(self, institution, context, candidate):
        fields = ('displayName', 'headline')
        invalid = [key for key in fields if not self.short_label(institution.get(key))]
        if not invalid:
            return
        labels = self.ask(
            '只修正片中标题条的字段，每项 1 至 12 个字符，空格和标点也计数。'
            'displayName 用真实机构简称，headline 用简短的实地探访主题。保留原意和原文限定，'
            '禁止新增事实。按 labels 给出的键返回 JSON，值是字符串。',
            {'institutionName': institution.get('name', ''), 'labels': {key: institution.get(key) for key in invalid},
             'requirements': context['requirements']}, max_tokens=256)
        for key in invalid:
            label = labels.get(key)
            if self.short_label(label):
                institution[key] = label.strip()
            elif key == 'headline':
                institution[key] = '养老机构实地探访'
            else:
                raise PlanError('请给出最多 12 字、能对应真实机构名称的 displayName。', candidate)

    @staticmethod
    def short_label(value):
        return isinstance(value, str) and bool(value.strip()) and len(value) <= 12 and not any(c in value for c in '\r\n')

    def plan(self, task, index, context, facts, previous, feedback='', *, evidence=None, candidate=None):
        prefs = (task.get('videoPreferences') or [''] * task['count'])[index]
        person = (task.get('videoSpecs') or [{'person': task['person']}] * task['count'])[index]['person']
        revised = task.get('revisedNarration', '')
        evidence = evidence or {}
        result = self.ask(
            NARRATOR_CONTEXT + '你负责写一条中文养老机构探访视频。按下列技能规则先写整篇口语稿并做语言润色，再分句选镜和定封面。'
            '仅使用真实素材，选片基于提供的实看结果。开头和结尾选有运动的源视频；在短片剩余时长足够的区间取镜，'
            '预计每秒 3.5 至 4 个汉字，给足分镜，sourceStart 使用秒数。不要指定资源路径、任何运行设置或关闭审核。'
            '默认口播讲照护和生活场景，地点只需说到片区；除非用户明确要求口播地址或路线，'
            '详细街道、门牌和地铁线路可以留到发布文案。院名按自然口语念出，用原文可对应的真实简称，避免反复念全称。'
            '无需生成 captions。工作台使用配音时间和字宽排字幕。'
            '各事实写进实际口播后，在对应句的 factIds 数组中逐项标明传入的编号，如 ["f1","f2"]。'
            '综合稿的 sentences 必须覆盖 facts 中全部 f 编号。额外细节可用 supportingEvidence 中支持该句的 e 编号，'
            '这些细节无需全部写入。句子有多个事实时可标多个编号。封面标签或 publication 写了数字时也提供 factIds。'
            '默认优先讲 facts 的重点。没有确切出处的补充细节可以省略，避免在一句中合并多个来源各自未能支持的结论。'
            '收到 feedback 时逐项修正。candidate 是待修订的上一个草稿，保留其中已符合要求的内容。'
            '用对应原文编号支持每个事实句，不用无关编号凑数。'
            '仅在用户偏好明确指定专题时返回 topicAuthorization 原话。'
            '若 revisedNarration 非空，逐字保留用户文案及标点，可重新断句但不删改文字。不够信息时填 question。'
            '输出一个 JSON 对象。顶层结构为 {"plan":{},"openingAngle":"本条如何开场","structure":"本条展开顺序",'
            '"coverAngle":"本条封面主题","topicAuthorization":"","question":null}。三项角度均填写具体内容。'
            'plan 必须同时包含 institution、sentences、cover 和 publication。'
            'asrPrompt 可给出本稿实际出现的少见专名，供配音识别复核使用，不能换掉任何口播用词。'
            'institution.displayName 和 institution.headline 各最多 12 字，标点也计入。'
            '封面放在 plan.cover，包含 main_title 和三个 labels；发布文案放在 plan.publication，'
            '包含 title、description 和五个不同的 topics。两个字段都按同一条完整口播撰写。\n'
            + self.rules('plan-schema', 'narration', 'narration-polish', 'covers'),
            {**context, 'facts': facts, 'supportingEvidence': evidence, 'person': person, 'index': index + 1, 'total': task['count'],
             'preference': prefs, 'previousAngles': previous, 'feedback': feedback, 'candidate': candidate,
             'revisedNarration': revised, 'publicationOverride': task.get('publicationOverride', {})},
            max_tokens=12000)
        raw = result.get('plan')
        if not isinstance(raw, dict):
            question(result)
            raise PlanError('模型必须在顶层 plan 字段返回完整的单条制作计划。')
        if not isinstance(raw.get('institution'), dict):
            raise PlanError('plan.institution 必须填写为对象。')
        plan = {key: raw[key] for key in ('institution', 'sentences', 'asrPrompt', 'cover', 'publication') if key in raw}
        references = {x['id']: {k: x[k] for k in ('id', 'source', 'quote')} for x in facts}
        references.update({ident: {'id': ident, **quote} for ident, quote in evidence.items()})
        plan.update(version=1, person=person, facts=list(references.values()))
        plan['settings'] = {'music': {'enabled': task['music']}}
        if task.get('musicTrack'):
            plan['settings']['music']['resource'] = task['musicTrack']['resource']
        if context['institutionName']:
            plan['institution']['name'] = context['institutionName']
        self.fit_institution_labels(plan['institution'], context, result)
        selected = {x['path']: x for x in context['media']}
        sentences = plan.get('sentences', [])
        if not isinstance(sentences, list) or not 1 <= len(sentences) <= 100:
            raise PlanError('plan.sentences 必须是包含口播句子和分镜的数组。')
        for i, sentence in enumerate(sentences):
            if not isinstance(sentence, dict) or not isinstance(sentence.get('text'), str) or not isinstance(sentence.get('shots'), list):
                raise PlanError(f'第 {i + 1} 句须包含口播 text 和 shots 数组。')
            # Layout uses the measured speech and glyph geometry in the render engine.
            sentence.pop('captions', None)
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
        for number, sentence in enumerate(sentences, 1):
            ids = sentence.get('factIds', [])
            if not isinstance(ids, list) or any(not isinstance(f, str) for f in ids):
                raise PlanError(f'第 {number} 句的 factIds 必须是编号字符串数组，如 ["f1","f2"]。', result)
        omit_unsupported = task['count']==1 and not (revised or task.get('requirements') or prefs)
        self.rebind_fact_references(sentences,references,result,editable=not revised,omit_unsupported=omit_unsupported)
        used={ident:None for sentence in sentences for ident in sentence.get('factIds',[])}
        authorization = result.get('topicAuthorization') or ''
        if authorization and (not isinstance(authorization, str) or authorization not in task.get('requirements', '') + '\n' + prefs):
            raise PlanError('专题需能引用用户明确提出的要求。')
        angles = {k: result.get(k) for k in ('openingAngle', 'structure', 'coverAngle')}
        missing_angles = [k for k, v in angles.items() if not isinstance(v, str) or not v.strip()]
        if missing_angles:
            raise PlanError('请补齐顶层策划角度字段 ' + '、'.join(missing_angles) + '。', result)
        expected = {x['id'] for x in facts}
        unknown = sorted(set(used) - references.keys())
        missing = sorted(expected - set(used)) if not authorization else []
        issues = []
        if missing:
            issues.append('口播缺少共同事实 ' + '、'.join(missing) + '，请在对应句写清事实并标注编号')
        if unknown:
            issues.append('factIds 使用了未提供的编号 ' + '、'.join(unknown))
        if issues:
            raise PlanError('。'.join(issues) + '。', result)
        return plan, {**angles, 'factCoverage': [f for f in used if f in expected], 'mode': 'topic' if authorization else 'comprehensive',
                      'topicAuthorization': authorization}

    def content_review(self, job, answer):
        plan = self.read(job / 'plan.json')
        context = self.context({'requirements': ''}, job, answer)
        return self.review_plan(context, plan, self.read(job / 'content-audit.json', {}))

    def review_plan(self, context, plan, audit):
        response = self.ask(
            NARRATOR_CONTEXT + '核对每句口播与事实原文，核对语义及所有限定词。用已有实看素材描述核对文画关系及封面三槽。'
            '审核口语质量、覆盖范围、结尾咨询、封面及发布文案。材料未支持或文画明显不合时拒绝。'
            'JSON {"ok":true,"note":"具体到口播、事实和素材的审核观察"}。\n' + self.rules('content-review'),
            {**context, 'plan': plan, 'audit': audit})
        return approved(response)

    def review_frames(self, job, paths, instructions, context=None, *, findings=None):
        job = job.resolve()
        known = sorted(set(Path(p).resolve() for p in paths))
        if not known or any(not p.is_relative_to(job) or not p.is_file() for p in known):
            raise ValueError('当前工程缺少可验证的检查帧。')
        notes = []
        times = {}
        for index, path in enumerate(known, 1):
            match = re.search(r'-([0-9.]+)s$', path.stem)
            if match:
                times[f'F{index}'] = float(match[1])

        def inspect(visuals):
            ids = [ident for ident, _ in visuals]
            result = self.ask(instructions + '查看每张图，发现可见的显著问题时拒绝。'
                              '返回 JSON 对象，ok 为布尔值，seen 为 frames 中实际看过的短编号数组，'
                              'note 为具体可见观察，若提供了秒数请写清对应时间。',
                              {'frames': ids, 'seconds': {ident: times[ident] for ident in ids if ident in times},
                               'context': context}, visuals)
            seen = result.get('seen')
            if not isinstance(seen, list) or any(not isinstance(x, str) for x in seen) or set(seen) != set(ids):
                return None
            if findings is not None and result.get('ok') is False:
                note = result.get('note')
                if isinstance(note, str) and note.strip():
                    note = note.strip()[:600]
                    findings.append(note)
                    return note
            return approved(result)

        for group in chunks(list(enumerate(known, 1)), 6):
            visuals = [(f'F{index}', self.read_frame(path)) for index, path in group]
            note = inspect(visuals)
            if note is not None:
                notes.append(note)
                continue
            for visual, (_, path) in zip(visuals, group):
                note = inspect([visual])
                if note is None:
                    raise ValueError(f'视觉复核回传缺少帧确认：{path.relative_to(job)}。')
                notes.append(note)
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
