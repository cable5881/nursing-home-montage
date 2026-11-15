"""Create an editable template variant from a timed job without speech/avatar API calls."""
import argparse,copy,json,shutil
from pathlib import Path
from workflow import read,write,settings,setup,state
from build_job import compose

def variant(source,out,template,platform=None):
    source=Path(source).resolve();out=Path(out).resolve()
    if out.exists():raise ValueError('Use a new variant directory; existing work is preserved')
    if template not in ('orange','green','legacy-orange','fullscreen-orange'):raise ValueError('Unknown template')
    required=('plan.json','natural-timeline.json','shot-list.json','captions.json','avatars.json')
    for name in required:
        if not (source/name).is_file():raise ValueError('Missing timed source: '+name)
    cfg=copy.deepcopy(settings(source));cfg['template']['id']=template
    if template=='fullscreen-orange':
        import project_config as pc
        cfg['platform_ui']=pc.merge(pc.load().get('settings',{}).get('platform_ui',{}),cfg.get('platform_ui',{}))
        if platform:
            cfg['platform_ui']['mode']='common' if platform=='common' else 'platform'
            cfg['platform_ui']['platform']=platform
    plan=read(source/'plan.json');plan['settings']=cfg
    out.mkdir(parents=True)
    for name in ('inventory.json','source-text.txt','narration.txt','voice.json','build-inputs.json','institution.json','natural-timeline.json','captions.json','caption-characters.json','subtitles.srt','shot-list.json','asset-sources.json','bgm-timeline.json','avatars.json','orange-font-match.json','source-description.txt'):
        if (source/name).is_file():shutil.copy2(source/name,out/name)
    shutil.copytree(source/'assets',out/'assets',symlinks=False)
    write(out/'plan.json',plan);setup(out);compose(out)
    write(out/'variant-source.json',{'source':str(source),'template':template,'paidGenerationCalls':0,'narrationUnchanged':True,'avatarDriversUnchanged':True})
    state(out,phase='composed',next='setup --install, check, snapshot, render and verify')
    return {'job':str(out),'template':template,'paidGenerationCalls':0}

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('source',type=Path);p.add_argument('--out',type=Path,required=True);p.add_argument('--template',choices=('orange','green','legacy-orange','fullscreen-orange'),required=True);p.add_argument('--platform')
    a=p.parse_args();print(json.dumps(variant(a.source,a.out,a.template,a.platform),ensure_ascii=False,indent=2))
