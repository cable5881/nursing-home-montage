"""Exercise the locked renderer before any speech/avatar submission."""
import json,os
from pathlib import Path
from workflow import read,write,digest,settings,hyperframes,sha,SKILL,state


def fingerprint(job):
    cfg=settings(job)
    return digest({'render':cfg['render'],'platform':os.sys.platform,'nodeOptions':os.environ.get('NODE_OPTIONS',''),'pythonPath':os.environ.get('PYTHONPATH',''),'browser':os.environ.get('HYPERFRAMES_BROWSER_PATH',''),'sandbox':os.environ.get('CODEX_SANDBOX',''),'renderer':sha(SKILL/'scripts/production.py')})


def preflight(job):
    job=Path(job);folder=job/'.preflight';folder.mkdir(parents=True,exist_ok=True)
    html='<!doctype html><html><meta charset="utf-8"><style>html,body{margin:0;width:1080px;height:1920px}#root{position:relative;width:1080px;height:1920px;background:#237c78}</style><body><div id="root" data-composition-id="main" data-start="0" data-duration="0.1" data-fps="30" data-width="1080" data-height="1920"></div></body></html>'
    (folder/'index.html').write_text(html)
    result=hyperframes(job,['check','--json'],cwd=folder,check=False)
    (folder/'check.log').write_text(result.stdout+'\n'+result.stderr)
    try:data=json.JSONDecoder().raw_decode(result.stdout[result.stdout.index('{'):])[0]
    except (ValueError,json.JSONDecodeError):data={'browserSkipped':True,'runtime':{'errorCount':1,'findings':[{'message':'CLI未返回可解析JSON，查看 .preflight/check.log'}]}}
    ok=not data.get('browserSkipped',True) and not data.get('runtime',{}).get('errorCount',0)
    report={'passed':ok,'fingerprint':fingerprint(job),'browserSkipped':data.get('browserSkipped'),'runtime':data.get('runtime',{}),'log':str(folder/'check.log'),'paidCalls':0}
    if ok:
        shot=hyperframes(job,['snapshot','--at','0','--no-end','--output','frames'],cwd=folder,check=False)
        report['screenshotPassed']=shot.returncode==0 and bool(list((folder/'frames').glob('*.png')))
        report['passed']=report['screenshotPassed'];(folder/'snapshot.log').write_text(shot.stdout+'\n'+shot.stderr)
    write(job/'preflight.json',report)
    if not report['passed']:raise RuntimeError('渲染环境预检失败，未调用配音或数字人；查看 preflight.json 和 .preflight 日志，按 references/troubleshooting.md 排查。')
    state(job,phase='environment_ready',next='review-content if not yet recorded, then voice; environment check has no paid calls')
    return report


def require_preflight(job):
    p=job/'preflight.json'
    if not p.is_file() or not read(p).get('passed') or read(p).get('fingerprint')!=fingerprint(job):
        raise ValueError('付费生成前先执行 preflight；当前环境或渲染设置变化后需要重新预检。')
