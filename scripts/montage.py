# /// script
# requires-python = ">=3.11,<3.13"
# dependencies = ["faster-whisper==1.2.1", "pypinyin==0.55.0", "opencc-python-reimplemented==0.1.7", "fonttools>=4.50,<5", "brotli>=1,<2", "numpy>=1.26,<3"]
# ///
"""Institution materials -> swappable template montage -> verified final.mp4."""
import argparse,json,sys
from pathlib import Path
from workflow import *
from build_job import build,compose
import production

def main():
    p=argparse.ArgumentParser(description=__doc__);sub=p.add_subparsers(dest='action',required=True)
    q=sub.add_parser('inventory');q.add_argument('input',type=Path);q.add_argument('--out',type=Path,required=True)
    q=sub.add_parser('variant');q.add_argument('job',type=Path);q.add_argument('--out',type=Path,required=True);q.add_argument('--template',choices=('orange','green','legacy-orange','fullscreen-orange'),required=True);q.add_argument('--platform')
    for name in ('validate-plan','setup','voice','build','avatars','review-provider','cutouts','compose','carve','check','snapshot','preview','render','verify','review','review-contrast','status'):
        q=sub.add_parser(name);q.add_argument('job',type=Path)
        if name=='setup':q.add_argument('--install',action='store_true')
        if name=='voice':q.add_argument('--reuse-audio',type=Path)
        if name=='avatars':q.add_argument('--wait-seconds',type=int,default=45,choices=range(0,46),metavar='0..45')
        if name=='snapshot':q.add_argument('--at')
        if name=='preview':q.add_argument('--port',type=int,default=3043)
        if name in ('review','review-provider','review-contrast'):q.add_argument('--frames',nargs='+',required=True);q.add_argument('--note',required=True)
    args=p.parse_args()
    if args.action=='inventory':return inventory(args.input,args.out.resolve())
    job=args.job.resolve();action=args.action
    if action=='variant':
        from variant import variant
        return variant(job,args.out,args.template,args.platform)
    # Continue jobs with their original code, even after the installed skill is updated.
    if (job/'runtime.json').exists():
        runtime=read(job/'runtime.json');os.environ['MONTAGE_PROJECT_ROOT']=runtime['project']
        frozen=Path(runtime['engine'])/'scripts/montage.py'
        if not frozen.is_file():raise RuntimeError('任务绑定的流程版本缺失，请恢复 .montage/engines；不会改用新版继续付费生成。')
        if frozen.resolve()!=Path(__file__).resolve():
            result=run(['uv','run','--python','3.11',frozen,*sys.argv[1:]],check=False)
            print(result.stdout,end='');print(result.stderr,end='',file=sys.stderr);sys.exit(result.returncode)
    if action=='validate-plan':validate_plan(job);return {'planValid':True}
    if action=='setup':return setup(job,args.install)
    if action=='voice':return voice(job,args.reuse_audio)
    if action=='build':return build(job)
    if action=='avatars':return production.avatars(job,args.wait_seconds)
    if action=='review-provider':return production.review_provider(job,args.frames,args.note)
    if action=='review-contrast':return production.contrast_review(job,args.frames,args.note)
    if action=='cutouts':return production.cutouts(job)
    if action=='compose':compose(job);return {'composition':str(job/'index.html')}
    if action=='carve':return production.carve(job)
    if action=='check':return production.check(job)
    if action=='snapshot':return production.snapshot(job,args.at)
    if action=='preview':
        r=run([*hyperframes_cli(job),'preview','--background','--port',args.port],cwd=job)
        return {'result':r.stdout}
    if action=='render':return production.render(job)
    if action=='verify':return production.verify(job)
    if action=='review':return production.review(job,args.frames,args.note)
    if action=='status':return read(job/'state.json')

if __name__=='__main__':
    if hasattr(sys.stdout,'reconfigure'):sys.stdout.reconfigure(encoding='utf-8')
    try:
        result=main();print(json.dumps(result,ensure_ascii=False,indent=2))
        if isinstance(result,dict) and result.get('pending'):sys.exit(2)
    except Exception as e:
        # Engine errors are sanitized by the bundled client; never print environment or credential values.
        print(json.dumps({'status':'stopped','error':str(e)},ensure_ascii=False,indent=2));sys.exit(1)
