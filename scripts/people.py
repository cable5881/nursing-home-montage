"""Batch import and name-based selection; credentials are connection-level only."""
import hashlib,re,shutil
from pathlib import Path
import project_config as pc

IMAGES={'.png','.jpg','.jpeg','.webp'}
AUDIO={'.wav','.mp3','.m4a','.aac','.flac','.ogg'}
def listing():return list(pc.load()['people'].values())

def identity(identifier,patch):
    """Save a user's selected identity and optional hooks; never infer a social name."""
    allowed={'social_media_name','spoken_name','cover_portrait','closing_hooks'}
    if set(patch)-allowed:raise ValueError('未知身份字段')
    cfg=pc.load();p=pc.person(identifier)
    for key in ('social_media_name','spoken_name'):
        if key in patch and (not isinstance(patch[key],str) or not patch[key].strip()):raise ValueError('姓名不能为空：'+key)
    if patch.get('social_media_name') and any(q['id']!=p['id'] and q.get('social_media_name')==patch['social_media_name'].strip() for q in cfg['people'].values()):raise ValueError('该社媒名已绑定其他数字人，请指定不同名字或明确处理原绑定。')
    if patch.get('cover_portrait') and not pc.asset_path(patch['cover_portrait']).is_file():raise ValueError('固定封面人像不存在')
    if 'closing_hooks' in patch:
        hooks=patch['closing_hooks'];library=hooks.get('library',{})
        if not isinstance(library,dict):raise ValueError('钩子库应为 ID 到条目的映射')
        for key,item in library.items():
            if not key or not isinstance(item,dict) or not isinstance(item.get('text'),str) or not item['text'].strip():raise ValueError('钩子需要 ID 和原文')
        if hooks.get('default_id') and hooks['default_id'] not in library:raise ValueError('默认钩子不在个人库中')
    p.update(patch)
    for key in ('social_media_name','spoken_name'):
        if key in patch:p[key]=patch[key].strip()
    cfg['people'][p['id']]=p;pc.write(pc.directory()/'project.json',cfg)
    return {'saved':True,'id':p['id'],'social_media_name':p.get('social_media_name'),'hooks':len(p.get('closing_hooks',{}).get('library',{}))}

def closing_hook(plan,cfg):
    """Resolve only this person's saved entries, retaining an explicit authored CTA."""
    options=cfg.get('closing_hook',{});person=cfg.get('person',{})
    if not options.get('enabled',True):return {'source':'disabled','person_id':person.get('id'),'text':None}
    current=plan.get('sentences',[{}])[-1]
    local=plan.get('settings',{}).get('closing_hook',{})
    library=person.get('closingHooks',{});items=library.get('library',{})
    selected=local.get('hook_id')
    text=local.get('text');source='task-text'
    if text and selected:raise ValueError('本次钩子 text 与 hook_id 只能指定一个')
    if not text and selected:
        if selected not in items:raise ValueError('所选钩子不属于当前数字人：'+selected)
        text=items[selected]['text'];source='person-selected'
    # A finalized authored sentence is an explicit task input, never silently overwritten.
    if not text and current.get('kind')=='cta' and current.get('text'):
        text=current['text'];source='task-plan'
    if not text and library.get('default_id'):
        selected=library['default_id']
        if selected not in items:raise ValueError('人物默认钩子已失效')
        text=items[selected]['text'];source='person-default'
    if not text:
        keyword=options.get('keyword')
        if not keyword:raise ValueError('缺少本次咨询钩子；请撰写末句或确认项目咨询关键词。')
        text='想了解这家养老院的具体情况，评论区留言“'+keyword+'”咨询。';source='project-consultation'
    if not isinstance(text,str) or not text.strip():raise ValueError('咨询钩子不能为空')
    return {'source':source,'person_id':person.get('id'),'hook_id':selected,'text':text.strip()}
def import_people(source,connection='main'):
    source=Path(source).resolve();cfg=pc.load();groups=[];unmatched=[]
    if connection not in cfg['connections']:raise ValueError('先保存服务连接：'+connection)
    for folder in [source,*sorted(p for p in source.rglob('*') if p.is_dir())]:
        files=[p for p in folder.iterdir() if p.is_file() and not p.name.startswith('.')]
        images=[p for p in files if p.suffix.lower() in IMAGES];audio=[p for p in files if p.suffix.lower() in AUDIO]
        if len(images)==1 and len(audio)<=1:
            groups.append((folder.name,images[0],audio[0] if audio else None))
        elif images:
            for image in images:
                matches=[p for p in audio if p.stem==image.stem]
                if len(matches)==1:groups.append((image.stem,image,matches[0]))
                else:unmatched.append(str(image))
    imported=[]
    for name,image,audio in groups:
        h=hashlib.sha256(image.read_bytes()+(audio.read_bytes() if audio else b'')).hexdigest()
        previous=next((p for p in cfg['people'].values() if p.get('source_hash')==h and p['name']==name),None)
        if previous:imported.append({'id':previous['id'],'name':name,'reused':True});continue
        ident='p-'+hashlib.sha256((name+h).encode()).hexdigest()[:12];folder=pc.directory()/'people'/ident;folder.mkdir(parents=True,exist_ok=True)
        # Normalize portrait encoding, preserving framing, to a predictable supported image.
        from workflow import run,probe
        portrait=folder/'portrait.png';run(['ffmpeg','-y','-v','error','-i',image,'-vf',r'scale=min(1600\,iw):-1','-frames:v','1',portrait])
        if portrait.stat().st_size>=4_700_000:raise ValueError('人物图过大，请提供背景更简单的图片：'+name)
        sample=None
        if audio:
            sample=folder/'sample.wav';run(['ffmpeg','-y','-v','error','-i',audio,'-vn','-ar','24000','-ac','1','-c:a','pcm_s16le',sample])
            if float(probe(sample)['format']['duration'])<=0:raise ValueError('声音样本为空：'+name)
        p={'id':ident,'name':name,'portrait':str(portrait.relative_to(pc.directory())),'sample':str(sample.relative_to(pc.directory())) if sample else None,'connection':connection,'speaker':None,'status':'needs_voice','source_hash':h}
        cfg['people'][ident]=p;imported.append({'id':ident,'name':name,'status':'needs_voice'})
    pc.write(pc.directory()/'project.json',cfg)
    return {'imported':imported,'unmatched':unmatched,'next':'绑定已有音色ID，或在首次选用人物时训练其声音。'}
def bind(identifier,speaker,custom=None):
    cfg=pc.load();p=pc.person(identifier)
    if speaker=='custom_speaker_id' and not custom:raise ValueError('需要custom_speaker_id')
    # Reject accidental reuse of a cloned voice slot by two different people.
    if any(q['id']!=p['id'] and q.get('speaker')==speaker and q.get('custom_speaker_id')==custom and q['connection']==p['connection'] for q in cfg['people'].values()):raise ValueError('该音色已绑定其他人物，不能覆盖其声音。')
    p.update(speaker=speaker,custom_speaker_id=custom,status='ready');cfg['people'][p['id']]=p
    cfg['default_person']=cfg.get('default_person') or p['id'];pc.write(pc.directory()/'project.json',cfg)
    return {'id':p['id'],'name':p['name'],'status':'ready'}
def select(names='all',allow_unready=False):
    cfg=pc.load();items=listing() if names=='all' else [pc.person(x) for x in names.split(',')]
    if not items:raise ValueError('数字人库为空，请先导入。')
    ready=[p for p in items if p.get('speaker') and pc.asset_path(p.get('portrait')).is_file()]
    missing=[{'id':p['id'],'name':p['name'],'status':p.get('status')} for p in items if p not in ready]
    if names!='all' and missing and not allow_unready:raise ValueError('所选人物尚未就绪：'+','.join(p['name'] for p in missing))
    return (items if allow_unready else ready),missing
