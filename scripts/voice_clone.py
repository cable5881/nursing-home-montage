"""Volcengine V3 voice registration/query with durable, non-repeating submissions."""
import base64,json,urllib.request,urllib.error,uuid
import project_config as pc
import people

def call(action,payload,key):
    request=urllib.request.Request('https://openspeech.bytedance.com/api/v3/tts/'+action,data=json.dumps(payload).encode(),headers={'Content-Type':'application/json','X-Api-Key':key,'X-Api-Request-Id':str(uuid.uuid4())},method='POST')
    try:
        with urllib.request.urlopen(request,timeout=60) as response:result=json.loads(response.read())
    except urllib.error.HTTPError as e:
        raise RuntimeError('声音服务HTTP '+str(e.code)+'；检查服务开通、音色槽位及请求记录。') from None
    if result.get('code',0) not in (0,20000000):raise RuntimeError('声音服务返回错误码 '+str(result['code']))
    return result
def prepare(identifier,speaker=None,custom=None):
    p=pc.person(identifier);cfg=pc.load();c=cfg['connections'][p['connection']];key=pc.connection_keys(c)[0]
    if not key:raise ValueError('缺少语音API Key')
    path=pc.directory()/'people'/p['id']/'voice-training.json'
    if p.get('speaker') and not path.exists():return {'id':p['id'],'ready':True,'reusedExistingVoice':True}
    if path.exists():record=pc.read(path)
    else:
        if not p.get('sample'):raise ValueError('请提供该人物的声音样本，或绑定已有音色ID。')
        used={q.get('speaker') for q in cfg['people'].values() if q['connection']==p['connection']}
        # Reserve slots even while another voice is still training.
        for f in (pc.directory()/'people').glob('*/voice-training.json'):used.add(pc.read(f).get('speaker_id'))
        if not speaker and c.get('clone_mode')=='prepaid':speaker=next((s for s in c.get('speaker_pool',[]) if s not in used),None)
        if not speaker and c.get('clone_mode')=='postpaid':speaker='custom_speaker_id';custom='montage_'+uuid.uuid4().hex
        if not speaker:raise ValueError('请提供未占用的音色槽位ID，或在服务设置中选择后付费自定义音色。')
        if speaker in used and speaker!='custom_speaker_id':raise ValueError('音色槽位已被占用，不能覆盖其他人物。')
        record={'speaker_id':speaker,'custom_speaker_id':custom,'phase':'prepared'};pc.write(path,record)
    identity={k:v for k,v in record.items() if k in ('speaker_id','custom_speaker_id') and v}
    if record['phase']=='prepared':
        payload={**identity,'audio':{'data':base64.b64encode(pc.asset_path(p['sample']).read_bytes()).decode(),'format':'wav'}}
        record['phase']='submission_unknown';pc.write(path,record)
        # An interrupted/uncertain submission is queried on resume, never retrained automatically.
        response=call('voice_clone',payload,key);record['phase']='submitted';record['response']={k:v for k,v in response.items() if k!='demo_audio'};pc.write(path,record)
    response=call('get_voice',identity,key);record['status']=response.get('status');record['phase']='ready' if response.get('status') in (2,4) else record['phase'];pc.write(path,record)
    if record['phase']=='ready':people.bind(p['id'],identity['speaker_id'],identity.get('custom_speaker_id'));return {'id':p['id'],'ready':True}
    if response.get('status')==3:raise RuntimeError('该人物音色训练失败；保留记录，先核查原因。')
    return {'id':p['id'],'pending':True,'status':response.get('status'),'next':'继续同一train命令查询；不会重复提交训练。'}
