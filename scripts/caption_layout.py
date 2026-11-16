"""Locked-size glyph measurement and lossless caption reflow for full-frame templates."""
import copy, math, re
from pathlib import Path
from fontTools.ttLib import TTFont
from fontTools.pens.boundsPen import BoundsPen
from fontTools.pens.transformPen import TransformPen


class Typography:
    def __init__(self, font, index, spec):
        self.font=TTFont(font,fontNumber=index) if index is not None else TTFont(font)
        self.gs=self.font.getGlyphSet();self.cm=self.font.getBestCmap();self.units=self.font['head'].unitsPerEm
        self.spec=spec

    def bounds(self,text,focus='',row=0):
        spec=self.spec;pen=BoundsPen(self.gs);advance=0
        start=text.find(focus) if focus else -1
        for i,c in enumerate(text):
            if ord(c) not in self.cm:raise ValueError('Caption font lacks glyph: '+c)
            size=spec['font_size']*(spec['focus_ratio'] if start>=0 and start<=i<start+len(focus) else 1)
            scale=size/self.units;k=math.tan(math.radians(spec['angle']));glyph=self.cm[ord(c)]
            self.gs[glyph].draw(TransformPen(pen,(scale,0,k*scale,-scale,advance,0)))
            advance+=self.font['hmtx'][glyph][0]*scale+spec['tracking']
        b=pen.bounds or (0,-spec['font_size'],advance,0)
        sx,sy=spec['scales'][row]
        if abs(sx-sy)>1e-6:raise ValueError('字幕必须保持字形比例，不能使用横纵不等的缩放。')
        tx=540-sx*(b[0]+b[2])/2;y=spec['baselines'][row]
        # Include outline and shadow in collision checks, not the font em box.
        margin=max(6,spec['stroke']/2+1)
        rect=[tx+sx*b[0]-margin,y+sy*b[1]-7,tx+sx*b[2]+margin,y+sy*b[3]+10]
        return b,tx,rect

    def fits(self,text,focus='',row=0):
        r=self.bounds(text,focus if focus in text else '',row)[2]
        return r[2]-r[0]<=self.spec['max_width']+1e-6


def boundaries(text,focus):
    blocked=set()
    spans=[m.span() for m in re.finditer(r'[0-9零〇一二两三四五六七八九十百千万亿点]+(?:平方米|养老床位|张床位|小时|分钟|号线|平方|公里|床位|秒|天|年|月|家|岁|万|元|米|㎡|%|％)?',text)]
    if focus:
        start=text.find(focus)
        if start>=0:spans.append((start,start+len(focus)))
    for start,end in spans:blocked.update(range(start+1,end))
    return [i for i in range(1,len(text)+1) if i not in blocked]


def wrap(text,focus,typography):
    """Prefer existing semantic cues; find a two-line split without shrinking the font."""
    if typography.fits(text,focus):return [text]
    choices=[]
    for i in boundaries(text,focus):
        if i==len(text):continue
        a,b=text[:i],text[i:]
        if typography.fits(a,focus,0) and typography.fits(b,focus,1):
            choices.append((abs(len(a)-len(b)),i))
    if not choices:return None
    i=min(choices)[1];return [text[:i],text[i:]]


def reflow(cues, typography, clean, character_times=None):
    """No wording or cue timing changes unless an overlong cue must be split."""
    output=[];changes=[]
    for cue in cues:
        original=copy.deepcopy(cue);cue=copy.deepcopy(cue)
        text=''.join(cue['lines']);focus=cue.get('focus','')
        if clean(text)!=clean(cue['text']):raise ValueError('Caption lines change the spoken wording')
        if 1<=len(cue['lines'])<=2 and all(typography.fits(t,focus,j) for j,t in enumerate(cue['lines'])):
            output.append(cue);continue
        # Preserve author-supplied semantic line boundaries. Reflow an oversized
        # existing line first instead of moving fragments of it into the next thought.
        expanded=[]
        for line in cue['lines']:
            wrapped=wrap(line,focus,typography)
            if wrapped:expanded.extend(wrapped)
            else:
                remaining=line
                while remaining:
                    size=max((n for n in boundaries(remaining,focus) if typography.fits(remaining[:n],focus)),default=0)
                    if not size:raise ValueError('An unbreakable highlighted phrase or number exceeds the caption width; revise the caption plan')
                    expanded.append(remaining[:size]);remaining=remaining[size:]
        lines=expanded if len(expanded)<=2 else None
        if lines:
            cue['lines']=lines;output.append(cue)
        else:
            if not character_times or not cue.get('canonicalRange'):
                raise ValueError('Overlong caption needs verified character timing; supply caption-characters.json or verified voice alignment')
            chunks=expanded
            cursor=cue['canonicalRange'][0];pieces=[]
            for i in range(0,len(chunks),2):
                lines=chunks[i:i+2];count=len(clean(''.join(lines)))
                p=copy.deepcopy(cue);p.update(text=''.join(lines),lines=lines,canonicalRange=[cursor,cursor+count])
                from alignment import safe_boundary
                if not safe_boundary(character_times,cursor) or not safe_boundary(character_times,cursor+count):raise ValueError('字幕拆分切入数字时间组，请调整语义分组，不能猜测数字内部时间。')
                p['start']=cue['start'] if not pieces else character_times[cursor]['start']
                p['speechEnd']=character_times[cursor+count-1]['end']
                pieces.append(p);cursor+=count
            if cursor!=cue['canonicalRange'][1]:raise ValueError('Caption reflow lost canonical characters')
            for i,p in enumerate(pieces):
                p['end']=pieces[i+1]['start'] if i+1<len(pieces) else cue['end']
                p['duration']=round(p['end']-p['start'],6)
                if p['duration']<=.2:raise ValueError('Reflowed caption is too brief; revise the semantic cue grouping')
            output.extend(pieces)
        changes.append({'before':original,'after':[copy.deepcopy(p) for p in output if p['start']>=original['start'] and p['start']<original['end']]})
    if ''.join(clean(c['text']) for c in output)!=''.join(clean(c['text']) for c in cues):raise ValueError('Caption reflow changed the spoken content')
    for a,b in zip(output,output[1:]):
        if a['end']>b['start']+1e-6:raise ValueError('Caption reflow produced overlapping cues')
    return output,changes
