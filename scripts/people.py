"""Batch import and name-based selection; credentials are connection-level only."""
import hashlib,re,shutil
from pathlib import Path
import project_config as pc

IMAGES={'.png','.jpg','.jpeg','.webp'}
AUDIO={'.wav','.mp3','.m4a','.aac','.flac','.ogg'}
def listing():return list(pc.load()['people'].values())
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
