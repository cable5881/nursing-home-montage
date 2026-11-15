"""Compose editable reference-matched orange/green templates from a timed job.

No speech/video generation is performed here. Coordinates are measured in the
916 x 1717 reference canvas and mapped to the production 1080 x 1920 canvas.
"""
from __future__ import annotations

import argparse
import copy
import html
import json
import math
from pathlib import Path

from fontTools import subset
from fontTools.pens.boundsPen import BoundsPen
from fontTools.pens.transformPen import TransformPen
from fontTools.ttLib import TTFont

SKILL = Path(__file__).resolve().parents[1]
VIDEO_EXTENSIONS = {'.mp4', '.mov', '.m4v', '.mkv', '.avi', '.webm'}


def read(path, default=None):
    return json.loads(path.read_text(encoding='utf-8')) if path.is_file() else default


def write(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def esc(value):
    return html.escape(str(value), quote=True)


def merge(base, override):
    result = copy.deepcopy(base)
    for key, value in override.items():
        result[key] = merge(result.get(key, {}), value) if isinstance(value, dict) else value
    return result


class Face:
    def __init__(self, source, index=None):
        self.font = TTFont(source, fontNumber=index) if index is not None else TTFont(source)
        self.gs = self.font.getGlyphSet()
        self.cmap = self.font.getBestCmap()
        self.units = self.font['head'].unitsPerEm
        self.source = str(source)
        self.index = index

    def bounds(self, text, size, focus='', focus_size=None, italic=0):
        pen = BoundsPen(self.gs)
        advance = 0
        k = math.tan(math.radians(italic))
        start = text.find(focus) if focus else -1
        end = start + len(focus) if start >= 0 else -1
        focus_start = focus_end = None
        for i, char in enumerate(text):
            current = focus_size if start <= i < end and start >= 0 else size
            scale = current / self.units
            glyph = self.cmap.get(ord(char), '.notdef')
            if i == start:
                focus_start = advance
            self.gs[glyph].draw(TransformPen(pen, (scale, 0, k * scale, -scale, advance, 0)))
            advance += self.font['hmtx'][glyph][0] * scale
            if i + 1 == end:
                focus_end = advance
        return pen.bounds or (0, -size, advance, 0), advance, (focus_start, focus_end)

    def subset(self, text, target):
        missing = sorted({c for c in text if not c.isspace() and ord(c) not in self.cmap})
        if missing:
            raise ValueError('Template font is missing glyphs: ' + ''.join(missing))
        # Always refresh: changes in narration must never reuse a stale glyph set.
        font = TTFont(self.source, fontNumber=self.index) if self.index is not None else TTFont(self.source)
        options = subset.Options()
        options.flavor = 'woff2'
        sub = subset.Subsetter(options=options)
        sub.populate(text=text)
        sub.subset(font)
        font.flavor = 'woff2'
        font.save(target)


def compose(root, template_id=None):
    natural = read(root / 'natural-timeline.json')
    cues = read(root / 'captions.json')
    shots = read(root / 'shot-list.json')
    avatars = read(root / 'avatars.json', [])
    institution = read(root / 'institution.json', {})
    if not institution:
        institution = read(root / 'plan.json', {}).get('institution', {})
    if not institution:
        institution = {'headline': '养老院实地看', 'displayName': root.name}
    local = read(root / 'template.json', {})
    chosen = template_id or local.get('id', 'orange')
    if chosen not in ('orange', 'green'):
        raise ValueError('Reference template must be orange or green')
    override = {k: v for k, v in local.items() if k not in ('id', 'overrides')}
    override = merge(override, local.get('overrides', {}))
    spec = merge(read(SKILL / 'assets/templates' / f'{chosen}.json'), override)
    total = float(natural['duration'])
    font_dir = root / 'assets/fonts'
    font_dir.mkdir(parents=True, exist_ok=True)
    all_text = ''.join(institution.values()) + ''.join(c['text'] for c in cues)
    all_text += ''.join(str(c[2]) for c in natural['chapters']) + ' ·0123456789'
    faces = {}
    font_report = {}
    font_css = []
    for role in ('title', 'body', 'subtitle'):
        config = spec.get('fonts', {}).get(role, {})
        source = config.get('file') or str(SKILL / 'assets/NotoSansSC-Black.otf')
        face = Face(source, config.get('index'))
        faces[role] = face
        target = font_dir / f'Template-{role}.woff2'
        face.subset(all_text, target)
        font_css.append(f"@font-face{{font-family:'Template-{role}';src:url('assets/fonts/{target.name}') format('woff2');font-weight:100 900;font-display:block}}")
        font_report[role] = {'file': str(source), 'index': config.get('index'), 'family': face.font['name'].getDebugName(1), 'style': face.font['name'].getDebugName(2)}

    def fixed_text(text, role, x, top, height, color, max_width=None, italic=0, stroke=0, outline='#000000', center=True, shadow=False, ident='', target_width=None):
        face = faces[role]
        b, _, _ = face.bounds(text, 100, italic=italic)
        scale = height / (b[3] - b[1])
        width = (b[2] - b[0]) * scale
        if target_width:
            scale_x = target_width / (b[2] - b[0])
            width = target_width
        elif max_width and width > max_width:
            # Header identity length can vary; captions are never resized here.
            scale_x = max_width / (b[2] - b[0])
            width = max_width
        else:
            scale_x = scale
        tx = x - (width / 2 if center else 0) - b[0] * scale_x
        ty = top - b[1] * scale
        k = math.tan(math.radians(italic))
        transform = f'matrix({scale_x:.7f} 0 {-scale_x*k:.7f} {scale:.7f} {tx:.6f} {ty:.6f})'
        attr = f'font-family="Template-{role}" font-size="100" font-weight="900" fill="{color}" stroke="{outline}" stroke-width="{stroke / scale:.5f}" stroke-linejoin="round" paint-order="stroke fill"'
        text_markup = f'<text id="{ident}"  x="0" y="0" {attr}>{esc(text)}</text>'
        shadow_markup = f'<g data-layout-ignore transform="translate(1.5 3)" opacity=".38"><text x="0" y="0" font-family="Template-{role}" font-size="100" fill="#000" stroke="#000" stroke-width="{3/scale}">{esc(text)}</text></g>' if shadow else ''
        return f'<g transform="{transform}">{shadow_markup}{text_markup}</g>', width

    title_spec = spec['title']
    title, _ = fixed_text(institution['headline'], 'title', title_spec['x'], title_spec['top'], title_spec['height'], title_spec['color'], title_spec.get('max_width'), title_spec.get('italic', 0), title_spec.get('stroke', 0), title_spec.get('outline', '#000'), shadow=chosen == 'orange', ident='headline', target_width=title_spec.get('width'))
    ui = []
    if chosen == 'orange':
        subtitle_spec = spec['subtitle']
        subtitle, _ = fixed_text(institution['displayName'].replace('·', ' · '), 'subtitle', subtitle_spec['x'], subtitle_spec['top'], subtitle_spec['height'], subtitle_spec['color'], subtitle_spec['max_width'], stroke=subtitle_spec['stroke'], shadow=True, ident='institution-subtitle', target_width=subtitle_spec.get('width'))
        ui.extend([title, subtitle, '<path d="M0 444H916M0 1252H916" stroke="#FFFDF6" stroke-width="5"/>'])
    else:
        box = title_spec['box']
        ui.append(f'<rect x="{box[0]}" y="{box[1]}" width="{box[2]}" height="{box[3]}" rx="5" fill="white"/>')
        ui.append(title)
        brand = spec['brand']
        brand_lines = spec.get('brand_lines')
        if not brand_lines:
            brand_lines = institution['displayName'].split('·', 1)
            if len(brand_lines) == 1:
                brand_lines = [brand_lines[0], '养老机构']
        ui.append(f'<rect x="{brand["x"]}" y="{brand["top"]}" width="{brand["width"]}" height="{brand["height"]}" rx="{brand["radius"]}" fill="{brand["background"]}"/>')
        for i, line in enumerate(brand_lines[:2]):
            text, _ = fixed_text(line, 'title', brand['text_x'], brand['text_tops'][i], brand['text_height'], brand['color'], brand['width'] - 42, brand['italic'], center=False, ident=f'brand-line-{i}')
            ui.append(text)

    chapters = []
    ch = spec['chapter']
    for i, (start, duration, label) in enumerate(natural['chapters']):
        text, width = fixed_text(label, 'body', ch['x'] + ch['padding_x'], ch['top'], ch['height'], ch['color'], italic=ch.get('italic', 0), stroke=0.6 if chosen == 'orange' else 0, center=False, ident=f'chapter-text-{i}')
        bg = f'<rect x="{ch["x"]}" y="{ch["top"]-ch["padding_y"]}" width="{width+2*ch["padding_x"]}" height="{ch["height"]+2*ch["padding_y"]}" rx="5" fill="{ch["background"]}" opacity="{ch["opacity"]}"/>'
        chapters.append(f'<g id="chapter-{i}" class="clip" data-start="{start}" data-duration="{duration}">{bg}{text}</g>')
    ui.extend(chapters)

    fit = []
    captions = []
    cap = spec['caption']
    for i, cue in enumerate(cues):
        if len(cue['lines']) > 2:
            raise ValueError('Reference templates accept at most two caption lines')
        content = []
        for line_index, line in enumerate(cue['lines']):
            focus = cue.get('focus', '')
            if not focus or focus not in line:
                focus = ''
            b, advance, (focus_start, focus_end) = faces['body'].bounds(line, cap['size'], focus, cap['focus_size'], cap['italic'])
            width = b[2] - b[0] + cap['stroke'] * 2
            fit.append({'cue': i, 'text': line, 'widthRef': round(width, 3), 'maxWidthRef': cap['max_width'], 'passed': width <= cap['max_width']})
            if width > cap['max_width']:
                raise ValueError(f'Caption exceeds locked template width ({width:.1f}>{cap["max_width"]}): {line}; split the cue rather than shrink the font')
            tx = cap['center_x'] - (b[0] + b[2]) / 2
            baseline = cap['baselines'][line_index]
            k = math.tan(math.radians(cap['italic']))
            words = esc(line)
            if focus:
                before, after = line.split(focus, 1)
                words = esc(before) + f'<tspan font-size="{cap["focus_size"]}" fill="{cap["focus_color"]}">{esc(focus)}</tspan>' + esc(after)
            attrs = f'font-family="Template-body" font-size="{cap["size"]}" fill="{cap["color"]}" stroke="#000000" stroke-width="{cap["stroke"]*2}" stroke-linejoin="round" paint-order="stroke fill"'
            transform = f'matrix(1 0 {-k:.7f} 1 {tx:.7f} {baseline:.7f})'
            shadow_words = words.replace(cap['focus_color'], '#000000')
            shadow_attrs = attrs.replace(cap['color'], '#000000')
            shadow = f'<text data-layout-ignore transform="translate(1.5 {cap["shadow"]})" x="0" y="0" {shadow_attrs} opacity=".48">{shadow_words}</text>'
            text = f'<text id="caption-{i}-line-{line_index}"  x="0" y="0" {attrs}>{words}</text>'
            underline = ''
            if focus and cap.get('underline'):
                underline = f'<path d="M{focus_start:.6f} {cap["underline_offset"]}H{focus_end:.6f}" stroke="{cap["underline"]}" stroke-width="{cap["underline_width"]}" stroke-linecap="round"/>'
            content.append(f'<g transform="{transform}">{shadow}{text}{underline}</g>')
        end = total if i == len(cues) - 1 and natural.get('holdLastCaption') else cue['end']
        captions.append(f'<g id="caption-{i}" class="clip" data-start="{cue["start"]}" data-duration="{end-cue["start"]}">{"".join(content)}</g>')

    def svg(content):
        return '<svg class="reference-layout" viewBox="0 0 916 1717" preserveAspectRatio="none" xmlns="http://www.w3.org/2000/svg">' + content + '</svg>'

    css = ''.join(font_css) + '#root{position:absolute;inset:0;pointer-events:none}.reference-layout{position:absolute;inset:0;width:100%;height:100%;overflow:visible}'

    def composition(ident, content):
        return '<template><style>' + css + '</style><div id="root" data-composition-id="' + ident + '" data-width="1080" data-height="1920">' + svg(content) + '</div><script>const tl=gsap.timeline({paused:true});window.__timelines["' + ident + '"]=tl;</script></template>'

    (root / 'compositions').mkdir(exist_ok=True)
    (root / 'compositions/template-ui.html').write_text(composition('template-ui', ''.join(ui)), encoding='utf-8')
    (root / 'compositions/template-captions.html').write_text(composition('template-captions', ''.join(captions)), encoding='utf-8')
    sx, sy = 1080 / 916, 1920 / 1717
    picture = spec['picture']
    band = [picture[0] * sx, picture[1] * sy, picture[2] * sx, picture[3] * sy]
    media = []
    blur = {'effects': {'blur': spec.get('background', {}).get('blur', 0)}}
    for i, shot in enumerate(shots):
        def element(ident, style, track, extra=''):
            common = f'id="{ident}" class="clip footage"  src="{esc(shot["asset"])}" data-start="{shot["start"]}" data-duration="{shot["duration"]}" data-track-index="{track}" style="{style};object-position:50% {shot.get("positionY",50)}%" data-beat="{esc(shot["description"])}" {extra}'
            if Path(shot['asset']).suffix.lower() in VIDEO_EXTENSIONS:
                return f'<video {common} muted playsinline data-media-start="{shot.get("sourceStart",0)}"></video>'
            return f'<img {common} alt="{esc(shot["description"])}">'
        if chosen == 'orange':
            media.append(element(f'background-{i:02}', f'left:0;top:0;width:1080px;height:1920px;z-index:{i+1}', 0, 'data-color-grading="' + esc(json.dumps(blur, separators=(',', ':'))) + '"'))
        media.append(element(f'shot-{i:02}', f'left:{band[0]}px;top:{band[1]}px;width:{band[2]}px;height:{band[3]}px;z-index:{101+i}', 1))
    avatar_markup = []
    animations = []
    actual_avatars = []
    for i, avatar in enumerate(avatars):
        # Build must also work before the provider/cutout phases have finished.
        placement = merge(spec['avatar'], spec.get('avatar_overrides', {}).get(avatar.get('id', str(i)), {}))
        ident = avatar.get('id', str(i))
        start, duration = avatar['start'], avatar['duration']
        x, y = placement['x'], placement['bottom'] - placement['height']
        actual_avatars.append({'id': ident, 'start': start, 'duration': duration, 'x': x, 'y': y, 'width': placement['width'], 'height': placement['height'], 'bottom': placement['bottom']})
        avatar_markup.append(f'<div id="presenter-{ident}-wrap" data-layout-allow-overlap style="position:absolute;left:{x}px;top:{y}px;width:{placement["width"]}px;height:{placement["height"]}px;z-index:350;opacity:0"><video id="presenter-{ident}" class="clip" src="{esc(avatar["video"])}" data-start="{start}" data-duration="{duration}" data-track-index="5" muted playsinline style="width:100%;height:100%;object-fit:contain"></video></div>')
        animations.append(f'mainTL.fromTo("#presenter-{ident}-wrap",{{opacity:0,y:5}},{{opacity:1,y:0,duration:{avatar.get("fadeIn",.18)},immediateRender:false}},{start});')
        fade_out = avatar.get('fadeOut', 0)
        if fade_out:
            animations.append(f'mainTL.to("#presenter-{ident}-wrap",{{opacity:0,duration:{fade_out}}},{start+duration-fade_out});')
    music = ''
    bgm = read(root / 'bgm-timeline.json', {})
    if bgm.get('enabled'):
        attrs = {'id': 'music-bed', 'class': 'clip', 'src': bgm['audio'], 'data-start': 0, 'data-duration': total, 'data-volume': 1, 'data-track-index': 4}
        for key in ('data-fx-chain', 'data-automation', 'data-fx-carve'):
            if key in bgm:
                attrs[key] = json.dumps(bgm[key], ensure_ascii=False, separators=(',', ':'))
        music = '<audio ' + ' '.join(f'{key}="{esc(value)}"' for key, value in attrs.items()) + '></audio>'
    legibility = '<div class="legibility" style="z-index:200;background:linear-gradient(to bottom,transparent 65%,rgba(0,0,0,.58) 100%)"></div>' if chosen == 'green' else f'<div class="legibility" style="z-index:90;background:rgba(0,0,0,{spec["background"]["darken"]})"></div>'
    index = f'''<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=1080,height=1920"><title>{esc(institution['displayName'])} · {esc(spec['name'])}</title><script src="assets/gsap.min.js"></script><style>*{{box-sizing:border-box}}html,body{{margin:0;width:1080px;height:1920px;overflow:hidden;background:#000}}#root{{position:relative;width:1080px;height:1920px;overflow:hidden}}.footage{{position:absolute;object-fit:cover}}.host,.legibility{{position:absolute;inset:0;width:100%;height:100%;pointer-events:none}}</style></head><body><div id="root" data-composition-id="main" data-start="0" data-duration="{total}" data-fps="30" data-width="1080" data-height="1920">
{''.join(media)}{legibility}{''.join(avatar_markup)}
<div id="template-ui" class="clip host" data-composition-id="template-ui" data-composition-src="compositions/template-ui.html" data-start="0" data-duration="{total}" data-width="1080" data-height="1920" data-track-index="2" data-track-kind="graphics" style="z-index:300"></div>
<div id="template-captions" class="clip host" data-composition-id="template-captions" data-composition-src="compositions/template-captions.html" data-start="0" data-duration="{total}" data-width="1080" data-height="1920" data-track-index="3" data-track-kind="captions" style="z-index:400"></div>
<audio id="female-narration" class="clip" src="{esc(natural['audio'])}" data-start="{natural['voiceStart']}" data-duration="{natural['voiceDuration']}" data-volume="1" data-track-index="6"></audio>{music}</div><script>const mainTL=gsap.timeline({{paused:true}});{''.join(animations)}window.__timelines["main"]=mainTL;</script></body></html>'''
    (root / 'index.html').write_text(index, encoding='utf-8')
    report = {'template': chosen, 'referenceCanvas': [916, 1717], 'output': [1080, 1920], 'pictureRef': spec['picture'], 'pictureOutput': band, 'fonts': font_report, 'avatars': actual_avatars, 'captionFit': fit, 'resolvedTemplate': spec, 'referenceImageBakedIntoUI': False}
    write(root / 'template-layout.json', report)
    write(root / 'caption-fit.json', fit)
    return {'template': chosen, 'duration': total, 'shots': len(shots), 'captions': len(cues), 'maxCaptionWidthRef': max((item['widthRef'] for item in fit), default=0), 'avatars': actual_avatars}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('job', type=Path)
    parser.add_argument('--template', choices=('orange', 'green'))
    args = parser.parse_args()
    print(json.dumps(compose(args.job.resolve(), args.template), ensure_ascii=False, indent=2))
