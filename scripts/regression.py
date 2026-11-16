# /// script
# requires-python = ">=3.11,<3.13"
# dependencies = ["fonttools>=4.50,<5", "brotli>=1,<2", "numpy>=1.26,<3", "opencc-python-reimplemented==0.1.7", "pypinyin==0.55.0"]
# ///
"""Offline replay of an existing approved project through the packaged composer/render/check path."""
from pathlib import Path
import argparse,json,shutil,sys
from workflow import *
from build_job import compose
import production

def main():
    p=argparse.ArgumentParser();p.add_argument('--baseline',type=Path,required=True);p.add_argument('--out',type=Path,required=True);p.add_argument('--reference-video',type=Path,required=True);p.add_argument('--template',choices=('legacy-orange','orange','green','fullscreen-orange'),default='legacy-orange');p.add_argument('--cover-image',type=Path);p.add_argument('--resume',action='store_true');args=p.parse_args()
    source=args.baseline.resolve();job=args.out.resolve()
    signature={'baseline':str(source),'reference':sha(args.reference_video),'template':args.template,'cover':sha(args.cover_image) if args.cover_image else None}
    if args.resume:
        if not (job/'regression-source.json').is_file() or read(job/'regression-source.json')!=signature:raise RuntimeError('Resume inputs do not match this regression job')
    else:
        if job.exists():raise RuntimeError('Use a new regression output directory, or --resume the reviewed job')
        job.mkdir(parents=True)
        for f in ('natural-timeline.json','avatars.json','captions.json','shot-list.json','bgm-timeline.json','orange-font-match.json','narration.txt','source-description.txt','package.json','package-lock.json','hyperframes.json'):
            shutil.copy2(source/f,job/f)
        (job/'assets').mkdir()
        # Media are referenced without mutation. Fonts are private because compose can refresh subsets.
        # The replay never invokes voice, avatars or paid APIs.
        for f in (source/'assets').iterdir():
            if f.name in ('fonts','person','cover','cover-input'):shutil.copytree(f,job/'assets'/f.name)
            else:(job/'assets'/f.name).symlink_to(f.resolve(),target_is_directory=f.is_dir())
        import project_config as pc
        metadata=read(source/'institution.json')
        write(job/'institution.json',metadata)
        plan=read(source/'plan.json') if (source/'plan.json').exists() else {}
        plan.setdefault('settings',{}).update({'template':{'id':args.template},'delivery':{'enabled':False}})
        plan['settings']['cover']={'enabled':bool(args.cover_image)}
        if args.cover_image:plan['settings']['cover']['image']=str(args.cover_image.resolve())
        write(job/'plan.json',plan)
        for name in ('inventory.json','source-text.txt'):
            if (source/name).is_file():shutil.copy2(source/name,job/name)
        pc.freeze(job)
        if args.cover_image:
            from cover import generate
            generate(job)
        write(job/'regression-source.json',signature)
        compose(job)
    total=read(job/'natural-timeline.json')['duration']
    points=[0,1/30,2.2,total/2,total-1/30]
    checks=read(job/'check.json') if (job/'check.json').is_file() else {}
    if not production.accepted_check(job,checks):production.check(job)
    production.snapshot(job,','.join(map(str,points)));production.render(job);report=production.verify(job)
    scores=[]
    for t in ([0,1/30] if args.cover_image else [])+[min(2.2,total/3),total/2,total-1/30]:
        def frame(f):return run(['ffmpeg','-v','error','-ss',t,'-i',f,'-frames:v','1','-vf','scale=360:640','-pix_fmt','rgb24','-f','rawvideo','-'],binary=True).stdout
        a,b=frame(args.reference_video),frame(job/'renders/final.mp4')
        if len(a)!=len(b) or not a:raise RuntimeError('Missing regression frame')
        error=sum(abs(x-y) for x,y in zip(a,b))/len(a);scores.append({'time':t,'meanAbsolutePixelDifference':error})
        if error>1.5:raise RuntimeError('Visual regression differs at '+str(t)+': '+str(error))
    def audio_hash(f):return run(['ffmpeg','-v','error','-i',f,'-map','0:a:0','-c','copy','-f','hash','-hash','sha256','-']).stdout.strip()
    if audio_hash(args.reference_video)!=audio_hash(job/'renders/final.mp4'):raise RuntimeError('Audio regression differs')
    result={'passed':True,'paidGenerationCalls':0,'baseline':str(source),'referenceVideo':str(args.reference_video.resolve()),'replayedVideo':report['video'],'duration':report['duration'],'pixelComparisons':scores,'audioBitstreamIdentical':True,'visualReviewPending':True}
    write(job/'regression.json',result);print(json.dumps(result,ensure_ascii=False,indent=2))

if __name__=='__main__':
    try:main()
    except Exception as e:print(json.dumps({'status':'failed','error':str(e)},ensure_ascii=False));sys.exit(1)
