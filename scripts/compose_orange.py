from pathlib import Path
import json,math,html,sys
from fontTools.ttLib import TTFont
from fontTools.pens.boundsPen import BoundsPen
from fontTools.pens.transformPen import TransformPen
from fontTools import subset
ROOT=Path(sys.argv[1]).resolve() if len(sys.argv)>1 else Path.cwd()
NATURAL=json.loads((ROOT/'natural-timeline.json').read_text(encoding='utf-8'))
TOTAL=NATURAL['duration']
OUTRO_START=NATURAL['outroStart'];OUTRO_DURATION=NATURAL['outroDuration']
def esc(s):return html.escape(str(s),quote=True)
match=json.loads((ROOT/'orange-font-match.json').read_text(encoding='utf-8'))[0]
body=TTFont(match['file'],fontNumber=match['index'])
chapter=TTFont(ROOT/'assets/fonts/NotoSansSC-Black.otf')
fonts={'OrangeRounded':body,'OrangeLabel':chapter}
institution=json.loads((ROOT/'institution.json').read_text(encoding='utf-8'))
text=(ROOT/'source-description.txt').read_text(encoding='utf-8')+(ROOT/'narration.txt').read_text(encoding='utf-8')+''.join(institution.get(k,'') for k in ('name','displayName','headline'))+"实地探访分区照护居住空间花园环境阅读书画活动空间日常服务文娱活动膳食服务托养服务给长辈选养老院先看再看安排床边有沙发日常休息也方便0123456789 ·"
text+=''.join(str(row[2]) for row in NATURAL['chapters'])
for family,src,index in [('OrangeRounded',match['file'],match['index']),('OrangeLabel',str(ROOT/'assets/fonts/NotoSansSC-Black.otf'),None)]:
 out=ROOT/f'assets/fonts/{family}.woff2'
 f=TTFont(src,fontNumber=index) if index is not None else TTFont(src)
 needed=set(map(ord,text))&set(f.getBestCmap())
 if not out.exists() or not needed.issubset(set(TTFont(out).getBestCmap())):
  o=subset.Options();o.flavor='woff2';sub=subset.Subsetter(options=o);sub.populate(text=text);sub.subset(f);f.flavor='woff2';f.save(out)
FACE="@font-face{font-family:'OrangeRounded';src:url('assets/fonts/OrangeRounded.woff2') format('woff2');font-weight:700;font-display:block}@font-face{font-family:'OrangeLabel';src:url('assets/fonts/OrangeLabel.woff2') format('woff2');font-weight:900;font-display:block}"
ANGLE=match['angle'];TRACK=match['tracking'];THICK=match['stroke'];K=math.tan(math.radians(ANGLE))
def measure(text,family='OrangeRounded',ratio=1,focus=None,angle=ANGLE,tracking=TRACK,inflate=THICK):
 f=fonts[family];gs=f.getGlyphSet();cm=f.getBestCmap();u=f['head'].unitsPerEm
 pen=BoundsPen(gs);adv=0;parts=[];fs=text.find(focus) if focus else -1;fe=fs+len(focus) if fs>=0 else -1
 for i,c in enumerate(text):
  size=112*(ratio if fs<=i<fe and fs>=0 else 1);s=size/u;k=math.tan(math.radians(angle));g=cm.get(ord(c),'.notdef')
  gs[g].draw(TransformPen(pen,(s,0,k*s,-s,adv,0)));adv+=f['hmtx'][g][0]*s+tracking
 b=pen.bounds or (0,-112,adv,0)
 return (b[0]-inflate,b[1]-inflate,b[2]+inflate,b[3]+inflate),adv
pink_box=(152,1511,626,92);white_box=(180,1383,291,102)
pb,_=measure("日常休息也方便");wb,_=measure("床边有")
PSX=pink_box[2]/(pb[2]-pb[0]);PSY=pink_box[3]/(pb[3]-pb[1])
WSX=white_box[2]/(wb[2]-wb[0]);WSY=white_box[3]/(wb[3]-wb[1])
BASE_P=pink_box[1]-PSY*pb[1];BASE_W=white_box[1]-WSY*wb[1]
FOCUS=1.22
def caption_line(text,focus,line,ident):
 is_pink=line>0;sx,sy=(PSX,PSY) if is_pink else (WSX,WSY);base=BASE_P if is_pink else BASE_W
 active=None if is_pink else focus
 b,_=measure(text,ratio=FOCUS,focus=active)
 tx=458-sx*(b[0]+b[2])/2
 before=after='';content=esc(text)
 if active and active in text:
  before,after=text.split(active,1)
  content=esc(before)+f'<tspan id="focus-{ident}" fill="#FDD722" stroke="#FDD722" font-size="{112*FOCUS}">'+esc(active)+'</tspan>'+esc(after)
 col='#FA98C3' if is_pink else '#FFFFFF'
 return f'<g transform="matrix({sx:.8f} 0 {-sx*K:.8f} {sy:.8f} {tx:.6f} {base:.6f})"><text id="text-{ident}" x="0" y="0" font-family="OrangeRounded" font-weight="700" font-size="112" letter-spacing="{TRACK}" fill="{col}" stroke="{col}" stroke-width="{THICK*2}" stroke-linecap="round" stroke-linejoin="round" paint-order="stroke fill">{content}</text></g>'
cues=json.loads((ROOT/'captions.json').read_text(encoding='utf-8'))
chapters=[tuple(row) for row in NATURAL['chapters']]
def svg(content):
 return '<svg class="orange-layout" viewBox="0 0 916 1717" preserveAspectRatio="none" xmlns="http://www.w3.org/2000/svg">'+content+'</svg>'
CSS=FACE+'#root{position:absolute;inset:0;pointer-events:none}.orange-layout{position:absolute;inset:0;width:100%;height:100%;overflow:visible}'
if institution.get('headerMode')=='reference' and (ROOT/'assets/reference/orange-ui-target.png').is_file():
 header='<defs><clipPath id="orange-header-mask"><rect x="0" y="0" width="916" height="428"/></clipPath></defs><g id="orange-header"><image href="assets/reference/orange-ui-target.png" width="916" height="1717" clip-path="url(#orange-header-mask)"/></g>'
else:
 title=esc(institution['headline']);brand=esc(institution['displayName'])
 header=f'''<g id="orange-header"><text x="458" y="220" text-anchor="middle" font-family="OrangeLabel" font-size="86" font-weight="900" font-style="italic" textLength="{min(820,max(330,len(institution['headline'])*82))}" lengthAdjust="spacingAndGlyphs" fill="white">{title}</text><path fill="#FF941F" d="M58 265L788 251L856 265L829 278L877 288L853 304L887 316L871 330L883 344L858 354L871 370L827 383L92 401L38 383L51 369L24 351L45 337L26 321L55 306L42 291L76 281Z"/><text x="458" y="353" text-anchor="middle" font-family="OrangeLabel" font-weight="900" font-style="italic" font-size="82" textLength="{min(790,max(330,len(institution['displayName'])*78))}" lengthAdjust="spacingAndGlyphs" fill="white" stroke="black" stroke-width="10" paint-order="stroke fill" stroke-linejoin="round">{brand}</text></g>'''
chapter_html=[];chapter_anim=[]
for i,(st,du,copy) in enumerate(chapters):
 if copy=='居住空间' and (ROOT/'assets/reference/orange-ui-target.png').is_file():
  draw='<svg x="33" y="454" width="228" height="64" viewBox="33 454 228 64" overflow="hidden"><image href="assets/reference/orange-ui-target.png" width="916" height="1717"/></svg>'
 else:
  b,_=measure(copy,'OrangeLabel',angle=0,tracking=0,inflate=0);sx=186/(b[2]-b[0]);sy=42/(b[3]-b[1]);tx=53-sx*b[0];ty=465-sy*b[1]
  draw=f'<rect x="33" y="454" width="228" height="64" rx="4" fill="#FF9B35"/><g transform="matrix({sx:.7f} 0 0 {sy:.7f} {tx:.5f} {ty:.5f})"><text x="0" y="0" font-family="OrangeLabel" font-weight="900" font-size="112" fill="#000">{esc(copy)}</text></g>'
 chapter_html.append(f'<g id="chapter-{i}" class="clip" data-start="{st}" data-duration="{du}" data-track-index="2"><g id="chapter-content-{i}">{draw}</g></g>')
 chapter_anim.append(f'tl.fromTo("#chapter-content-{i}",{{x:-14,opacity:0}},{{x:0,opacity:1,duration:.2,ease:"power3.out",immediateRender:false}},{st});tl.to("#chapter-content-{i}",{{opacity:0,duration:.1}},{st+du-.1});')
outro=caption_line(institution['displayName'],None,0,'end-0')
outro_group=f'<g id="outro-slot" class="clip" data-start="{OUTRO_START}" data-duration="{OUTRO_DURATION}" data-track-index="2"><g id="outro-copy">{outro}</g></g>' if OUTRO_DURATION>0 else ''
outro_anim=f'tl.fromTo("#outro-copy",{{opacity:0}},{{opacity:1,duration:.15,ease:"power2.out",immediateRender:false}},{OUTRO_START});' if OUTRO_DURATION>0 else ''
ui='<template><style>'+CSS+'</style><div id="root" data-composition-id="orange-ui" data-width="1080" data-height="1920">'+svg(header+''.join(chapter_html)+outro_group)+'</div><script>const tl=gsap.timeline({paused:true});'+''.join(chapter_anim)+outro_anim+'window.__timelines["orange-ui"]=tl;</script></template>'
groups=[];anims=[]
for i,c in enumerate(cues):
 lines=''.join(caption_line(line,c['focus'] if c['focus'] in line else None,j,f'{i}-{j}') for j,line in enumerate(c['lines']))
 groups.append(f'<g id="caption-{i}" class="clip" data-start="{c["start"]}" data-duration="{c["duration"]}" data-track-index="0"><g id="caption-inner-{i}">{lines}</g></g>')
 anims.append(f'tl.fromTo("#caption-inner-{i}",{{y:6,opacity:0}},{{y:0,opacity:1,duration:.12,ease:"power2.out",immediateRender:false}},{c["start"]});tl.to("#caption-inner-{i}",{{opacity:0,duration:.07}},{c["end"]-.07:.4f});tl.set("#caption-inner-{i}",{{opacity:0}},{c["end"]});')
 if i==len(cues)-1 and NATURAL.get('holdLastCaption'):
  anims[-1]=f'tl.fromTo("#caption-inner-{i}",{{y:6,opacity:0}},{{y:0,opacity:1,duration:.12,ease:"power2.out",immediateRender:false}},{c["start"]});'
caps='<template><style>'+CSS+'</style><div id="root" data-composition-id="orange-captions" data-width="1080" data-height="1920">'+svg(''.join(groups))+'</div><script>const tl=gsap.timeline({paused:true});'+''.join(anims)+'window.__timelines["orange-captions"]=tl;</script></template>'
ui=ui.replace('data-start="57.2" data-duration="2.8"',f'data-start="{OUTRO_START}" data-duration="{OUTRO_DURATION}"').replace(',57.2);',f',{OUTRO_START});')
(ROOT/'compositions').mkdir(exist_ok=True)
(ROOT/'compositions/orange-ui.html').write_text(ui, encoding='utf-8');(ROOT/'compositions/orange-captions.html').write_text(caps, encoding='utf-8')
shots=json.loads((ROOT/'shot-list.json').read_text(encoding='utf-8'))
media=[]
for i,s in enumerate(shots):
 common=f'id="shot-{i:02d}" class="clip footage" src="{s["asset"]}" data-start="{s["start"]}" data-duration="{s["duration"]}" data-track-index="0" style="z-index:{i+1};object-position:50% {s["positionY"]}%" data-beat="{esc(s["description"])}"'
 if Path(s['asset']).suffix.lower() in ('.mp4','.mov','.m4v','.mkv','.avi','.webm'):
  media.append(f'<video {common} muted playsinline data-media-start="{s["sourceStart"]}"></video>')
 else:media.append(f'<img {common} alt="{esc(s["description"])}">')
videos='\n'.join(media)
# Music mixing is stored beside the composition so regeneration keeps the exact mix.
bgm_path=ROOT/'bgm-timeline.json'
BGM=json.loads(bgm_path.read_text(encoding='utf-8')) if bgm_path.exists() else None
music=''
if BGM and BGM.get('enabled'):
 attrs={'id':'music-bed','class':'clip','src':BGM['audio'],'data-start':0,'data-duration':TOTAL,'data-volume':1,'data-track-index':4}
 for key in ['data-fx-chain','data-automation','data-fx-carve']:
  if key in BGM: attrs[key]=json.dumps(BGM[key],ensure_ascii=False,separators=(',',':'))
 music='<audio '+' '.join(f'{key}="{esc(value)}"' for key,value in attrs.items())+'></audio>'

top=428*1920/1717;height=919*1920/1717
avatar='';avatar_anim=''
avatar_path=ROOT/'avatars.json'
avatars=json.loads(avatar_path.read_text(encoding='utf-8')) if avatar_path.exists() else [json.loads((ROOT/'avatar-opening.json').read_text(encoding='utf-8'))]
for n,A in enumerate(avatars):
 if (ROOT/A['video']).exists():
  ident=A.get('id',str(n))
  avatar+=f'''<div id="presenter-{ident}-wrap" data-layout-allow-overlap style="position:absolute;left:{A['x']}px;top:{A['y']}px;width:{A['width']}px;height:{A['height']}px;z-index:35;pointer-events:none;opacity:0"><video id="presenter-{ident}" class="clip" src="{A['video']}" data-start="{A['start']}" data-duration="{A['duration']}" data-track-index="{5+n}" muted playsinline style="width:100%;height:100%;object-fit:contain"></video></div>'''
  avatar_anim+=f'''mainTL.fromTo("#presenter-{ident}-wrap",{{opacity:0,y:7}},{{opacity:1,y:0,duration:{A['fadeIn']},ease:"power2.out",immediateRender:false}},{A['start']});'''
  if A.get('fadeOut',0)>0:
   avatar_anim+=f'''mainTL.to("#presenter-{ident}-wrap",{{opacity:0,y:4,duration:{A['fadeOut']},ease:"power2.in"}},{A['start']+A['duration']-A['fadeOut']});'''
index=f'''<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=1080,height=1920"><title>{esc(institution['displayName'])} · 橙色混剪</title><script src="assets/gsap.min.js"></script><style>
*{{box-sizing:border-box}}html,body{{margin:0;width:1080px;height:1920px;overflow:hidden;background:#000}}#root{{position:relative;width:100%;height:100%;overflow:hidden;background:#000}}.footage{{position:absolute;left:0;top:{top}px;width:1080px;height:{height}px;object-fit:cover;object-position:50% 50%}}.host{{position:absolute;inset:0;width:100%;height:100%;pointer-events:none}}
</style></head><body><div id="root" data-composition-id="main" data-start="0" data-duration="{TOTAL}" data-fps="30" data-width="1080" data-height="1920">
{videos}
{avatar}
<div id="orange-ui" class="clip host" data-composition-id="orange-ui" data-composition-src="compositions/orange-ui.html" data-start="0" data-duration="{TOTAL}" data-width="1080" data-height="1920" data-track-index="1" data-track-kind="graphics" style="z-index:30"></div>
<div id="orange-captions" class="clip host" data-composition-id="orange-captions" data-composition-src="compositions/orange-captions.html" data-start="0" data-duration="{TOTAL}" data-width="1080" data-height="1920" data-track-index="2" data-track-kind="captions" style="z-index:40"></div>
<audio id="female-narration" class="clip" src="{NATURAL['audio']}" data-start="{NATURAL['voiceStart']}" data-duration="{NATURAL['voiceDuration']}" data-volume="1" data-track-index="3"></audio>
{music}
</div><script>const mainTL=gsap.timeline({{paused:true}});{avatar_anim}window.__timelines["main"]=mainTL;</script></body></html>'''
(ROOT/'index.html').write_text(index, encoding='utf-8')
(ROOT/'captions-orange.json').write_text(json.dumps(cues,ensure_ascii=False,indent=2), encoding='utf-8')
(ROOT/'orange-typography.json').write_text(json.dumps({'referenceCanvas':[916,1717],'output':[1080,1920],'headerRegion':[0,0,916,428],'pictureRegion':[0,428,916,919],'chapterRegion':[33,454,228,64],'captionWhiteBox':white_box,'captionPinkBox':pink_box,'captionBaselines':[BASE_W,BASE_P],'whiteScale':[WSX,WSY],'pinkScale':[PSX,PSY],'focusRatio':FOCUS,'colors':{'white':'#FFFFFF','pink':'#FA98C3','yellow':'#FDD722'},'font':match},ensure_ascii=False,indent=2), encoding='utf-8')
print(json.dumps({'font':match['family'],'whiteScale':[WSX,WSY],'pinkScale':[PSX,PSY],'baselines':[BASE_W,BASE_P],'videoBand':[top,height]},ensure_ascii=False))

fit=[]
for c in cues:
 for j,line in enumerate(c['lines']):
  b,_=measure(line,ratio=FOCUS,focus=c['focus'] if j==0 and c['focus'] in line else None)
  sx=WSX if j==0 else PSX
  width=(b[2]-b[0])*sx
  fit.append({'text':line,'widthRef':round(width,2),'marginRef':round((916-width)/2,2)})
  assert width<=836,(line,width)
(ROOT/'caption-fit.json').write_text(json.dumps(fit,ensure_ascii=False,indent=2), encoding='utf-8')
print('MAX_CAPTION_WIDTH_REF',max(x['widthRef'] for x in fit))
