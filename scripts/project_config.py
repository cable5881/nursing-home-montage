"""Persistent user data lives outside the replaceable skill installation."""
import copy,hashlib,json,os,re,shutil,subprocess,sys,uuid
from pathlib import Path

SKILL=Path(__file__).resolve().parent.parent
SCHEMA=1
def read(path):return json.loads(Path(path).read_text(encoding='utf-8'))
def write(path,value,private=False):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    # Open private files with restrictive permissions from the first byte.
    tmp=path.with_name(path.name+'.tmp')
    fd=os.open(tmp,os.O_WRONLY|os.O_CREAT|os.O_TRUNC,0o600 if private else 0o644)
    with os.fdopen(fd,'w',encoding='utf-8') as f:json.dump(value,f,ensure_ascii=False,indent=2);f.write('\n')
    if private:os.chmod(tmp,0o600)
    tmp.replace(path)
def root(start=None):
    if os.environ.get('MONTAGE_PROJECT_ROOT'):return Path(os.environ['MONTAGE_PROJECT_ROOT']).resolve()
    current=Path(start or Path.cwd()).resolve()
    for p in (current,*current.parents):
        if (p/'.montage/project.json').is_file():return p
    for p in SKILL.parents:
        if p.name=='.agents':return p.parent
    return current
def directory():return root()/'.montage'
def init():
    d=directory();p=d/'project.json'
    if not p.exists():write(p,{'schema_version':SCHEMA,'project_id':uuid.uuid4().hex,'default_person':None,'connections':{},'settings':{},'people':{},'output_dir':'作品','updates':{'repository':'https://github.com/cable5881/nursing-home-montage','channel':'stable'}})
    config=load()
    (d/'.gitignore').write_text('*\n!.gitignore\n', encoding='utf-8')
    return {'project':str(root()),'config':str(p),'initialized':True,'people':len(config['people'])}
def load():
    p=directory()/'project.json'
    if not p.exists():raise ValueError('项目尚未初始化：先运行 project.py init，再只补齐 doctor 列出的缺项。')
    cfg=read(p)
    if cfg.get('schema_version',0)>SCHEMA:raise ValueError('此项目配置来自更新版本，请先更新skill；不会重置配置。')
    if cfg.get('schema_version')!=SCHEMA:
        raise ValueError('未知配置格式，保留原文件；请提供版本迁移器，不能用默认值覆盖。')
    return cfg
def merge(base,override):
    out=copy.deepcopy(base)
    for k,v in override.items():out[k]=merge(out[k],v) if isinstance(v,dict) and isinstance(out.get(k),dict) else copy.deepcopy(v)
    return out
def save_patch(patch):
    if set(patch)-{'settings','connections','default_person','output_dir','updates'}:raise ValueError('只能修改项目设置、连接或默认人物；人物使用 people 命令。')
    cfg=merge(load(),patch);write(directory()/'project.json',cfg);return {'saved':True}
def asset_path(value):
    if not value:return None
    p=Path(value).expanduser();return p if p.is_absolute() else directory()/p
def secret(ref):
    if not ref:return ''
    if isinstance(ref,str):return os.environ.get(ref,'')
    value=os.environ.get(ref.get('env',''),'')
    if value:return value
    if ref.get('local'):
        p=directory()/'secrets.json'
        return read(p).get(ref['local'],'') if p.exists() else ''
    if ref.get('keychain') and sys.platform=='darwin':
        result=subprocess.run(['/usr/bin/security','find-generic-password','-a','VOLCANO_TTS_API_KEY','-s','com.openai.codex.volcano-tts','-w'],capture_output=True,text=True)
        if result.returncode==0:return result.stdout.strip()
    return ''
def connection_keys(connection):
    api=secret(connection.get('speech_key'));ak=secret(connection.get('access_key'));sk=secret(connection.get('secret_key'))
    legacy=connection.get('access_keys',{}).get('file')
    if not (ak and sk) and legacy:
        p=asset_path(legacy)
        if p.is_file():
            values={}
            for line in p.read_text(encoding='utf-8-sig').splitlines():
                m=re.match(r'^\s*[-*]?\s*(AccessKeyID|SecretAccessKey)\s*[:：=]\s*(.*?)\s*$',line,re.I)
                if m:values[m[1].lower()]=m[2].strip().strip('`"\'')
            ak=values.get('accesskeyid','');sk=values.get('secretaccesskey','')
    return api,ak,sk
def store_connection(name,values):
    if not re.fullmatch(r'[A-Za-z0-9_-]+',name):raise ValueError('连接名称使用字母、数字、横线或下划线。')
    cfg=load();conn=cfg['connections'].get(name,{'provider':'volcengine'})
    secrets=read(directory()/'secrets.json') if (directory()/'secrets.json').exists() else {}
    for key,field in (('api_key','speech_key'),('ak','access_key'),('sk','secret_key')):
        if values.get(key):
            slot=name+'.'+key;secrets[slot]=values[key].strip();conn[field]={'local':slot}
    storage=conn.setdefault('storage',{})
    for k in ('bucket','region','endpoint'):
        if values.get(k):storage[k]=values[k].strip()
    storage.setdefault('prefix','nursing-home-montage');storage.setdefault('url_expires_seconds',14400)
    if storage.get('bucket'):
        storage.setdefault('region','cn-beijing');storage.setdefault('endpoint','tos-'+storage['region']+'.volces.com')
    write(directory()/'secrets.json',secrets,private=True)
    cfg['connections'][name]=conn;write(directory()/'project.json',cfg)
    return {'saved':True,'connection':name}
def person(identifier=None,ready=False):
    cfg=load();identifier=identifier or cfg.get('default_person')
    matches=[p for p in cfg['people'].values() if identifier in (p['id'],p['name'])]
    if len(matches)!=1:raise ValueError('请指定唯一的数字人名称或ID；可先查看人物清单。')
    p=copy.deepcopy(matches[0])
    if ready and not (p.get('speaker') and asset_path(p.get('portrait')).is_file()):raise ValueError('数字人尚未就绪：'+p['name'])
    return p
def resolved(job):
    frozen=job/'runtime.json'
    if frozen.exists():return read(frozen)['settings']
    cfg=load();plan=read(job/'plan.json') if (job/'plan.json').exists() else {}
    out=merge(read(SKILL/'preset.json'),cfg.get('settings',{}))
    identifier=plan.get('person') or cfg.get('default_person')
    p=person(identifier) if identifier else None
    if p:
        out['voice']['speaker']=p.get('speaker');out['voice']['speech_rate']=p.get('speech_rate',out['voice']['speech_rate'])
        out['voice']['custom_speaker_id']=p.get('custom_speaker_id')
        out['avatar']['portrait']=str(asset_path(p.get('portrait')))
        out['person']={'id':p['id'],'name':p['name'],'spokenName':p.get('spoken_name',p['name']),'connection':p['connection']}
    out=merge(out,plan.get('settings',{}))
    conn=cfg['connections'].get(out.get('person',{}).get('connection'),{})
    out['service']={k:copy.deepcopy(conn[k]) for k in ('provider','storage','tts','avatar') if k in conn}
    for section,key in (('avatar','portrait'),('music','resource'),('typography','body_font'),('typography','reference_asset')):
        if out[section].get(key):out[section][key]=str(asset_path(out[section][key]))
    return out
def freeze(job):
    job=Path(job);bound=job/'runtime.json'
    if bound.exists():return read(bound)
    cfg=resolved(job);person_asset=cfg['avatar'].get('portrait')
    if person_asset:
        dest=job/'assets/person'/Path(person_asset).name;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(person_asset,dest);cfg['avatar']['portrait']=str(dest.resolve())
    files=[p for p in SKILL.rglob('*') if p.is_file() and not any(x in ('.git','__pycache__') for x in p.relative_to(SKILL).parts)]
    manifest={str(p.relative_to(SKILL)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(files)}
    ident=hashlib.sha256(json.dumps(manifest,sort_keys=True).encode()).hexdigest()[:20]
    engine=directory()/'engines'/ident
    if not engine.exists():
        staging=engine.with_name(ident+'.tmp')
        if staging.exists():shutil.rmtree(staging)
        staging.mkdir(parents=True)
        for p in files:
            dest=staging/p.relative_to(SKILL);dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(p,dest)
        staging.replace(engine)
    # A pluggable engine implements generate/resume/review and the bundled run.json contract.
    connection=load()['connections'].get(cfg.get('person',{}).get('connection'),{})
    adapters={}
    for kind,path in connection.get('adapters',{}).items():
        if kind not in ('speech','avatar'):raise ValueError('未知服务适配器类型')
        source=asset_path(path);target=job/'assets/adapters'/kind
        if not (source/'generate.py').is_file():raise ValueError('适配器缺少generate.py')
        shutil.copytree(source,target);adapters[kind]=str((target/'generate.py').resolve())
    data={'schema_version':1,'version':(SKILL/'VERSION').read_text(encoding='utf-8').strip(),'engine':str(engine),'project':str(root()),'settings':cfg,'adapters':adapters,'manifest':manifest}
    write(bound,data);return data
def engine_env(job):
    cfg=resolved(job);name=cfg.get('person',{}).get('connection');conn=load()['connections'].get(name,{})
    api,ak,sk=connection_keys(conn);env=os.environ.copy()
    # Explicit values prevent inherited keys from accidentally selecting another account.
    env.update(MONTAGE_PROJECT_ROOT=str(root()),MONTAGE_AVATAR_CONFIG=str(job/'avatar-engine.json'),VOLCANO_TTS_API_KEY=api,VOLC_ACCESSKEY=ak,VOLC_SECRETKEY=sk,MONTAGE_MANAGED_CREDENTIALS='1')
    return env
def doctor():
    cfg=load();tools={k:bool(shutil.which(k)) for k in ('ffmpeg','ffprobe','node','npm','uv')};connections={}
    for name,c in cfg['connections'].items():
        api,ak,sk=connection_keys(c);s=c.get('storage',{})
        connections[name]={'speech_key':bool(api),'access_keys':bool(ak and sk),'storage':all(s.get(k) for k in ('bucket','region','endpoint'))}
    people=[]
    for p in cfg['people'].values():
        people.append({'id':p['id'],'name':p['name'],'portrait':bool(p.get('portrait') and asset_path(p['portrait']).is_file()),'voice':bool(p.get('speaker')),'connection':p['connection'],'status':p.get('status')})
    usable=[p for p in people if p['portrait'] and p['voice'] and p['connection'] in connections and all(connections[p['connection']].values())]
    return {'project':str(root()),'tools':tools,'connections':connections,'people':people,'defaultPerson':cfg.get('default_person'),'ready':all(tools.values()) and bool(usable),'remoteAuthVerified':False}
