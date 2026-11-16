# /// script
# requires-python = ">=3.11,<3.13"
# dependencies = ["numpy>=1.26,<3", "opencv-python-headless>=4.10,<5", "pillow>=10,<13"]
# ///
"""Build a video overlay from the genuine per-frame person matte; no facial synthesis."""
from pathlib import Path
import subprocess,json,math,argparse,shutil
import numpy as np
import cv2
from PIL import Image,ImageDraw

parser=argparse.ArgumentParser()
parser.add_argument('--project',type=Path,default=Path.cwd())
parser.add_argument('--asset-dir',default='assets/avatar-opening')
parser.add_argument('--min-seconds',type=float,default=6)
opts=parser.parse_args()
ROOT=opts.project.resolve()
OUT=ROOT/opts.asset_dir
src=OUT/'avatar-matte.mov'
def run(args):return subprocess.run(((['rtk','proxy'] if shutil.which('rtk') else [])+list(map(str,args))),check=True,capture_output=True,text=True)
meta=json.loads(run(['ffprobe','-v','error','-show_entries','stream=width,height,r_frame_rate','-of','json',src]).stdout)['streams'][0]
iw,ih=meta['width'],meta['height']
# Keep the full head and upper torso; hands and chair remain below this crop.
W,H=320,440;pad=10;fw,fh=W-2*pad,H-2*pad
cx,cy,cw=round(iw*.04),round(ih*.02),round(iw*.92)
if round(cw*fh/fw)+cy>ih:
    cw=math.floor((ih-cy)*fw/fh);cx=round((iw-cw)/2)
ch=round(cw*fh/fw)
assert cy+ch<=ih
args=([('rtk'),('proxy')] if shutil.which('rtk') else [])+['ffmpeg','-v','error','-i',str(src),'-vf',f'fps=30,crop={cw}:{ch}:{cx}:{cy},scale={fw}:{fh}:flags=lanczos','-f','rawvideo','-pix_fmt','rgba','-']
decoder=subprocess.Popen(args,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
encoder=subprocess.Popen((['rtk','proxy'] if shutil.which('rtk') else [])+['ffmpeg','-y','-v','error','-f','rawvideo','-pix_fmt','rgba','-s',f'{W}x{H}','-r','30','-i','-','-an','-c:v','libvpx-vp9','-pix_fmt','yuva420p','-lossless','1','-auto-alt-ref','0','-metadata:s:v:0','alpha_mode=1',str(OUT/'avatar-outlined.webm')],stdin=subprocess.PIPE,stderr=subprocess.PIPE)
frames=0;alpha_stats=[]
try:
    while True:
        buf=decoder.stdout.read(fw*fh*4)
        if not buf:break
        assert len(buf)==fw*fh*4
        rgba=np.frombuffer(buf,np.uint8).reshape(fh,fw,4).copy()
        alpha=rgba[:,:,3]
        # Suppress low-confidence fringe without touching opaque face pixels.
        alpha[:]=np.clip((alpha.astype(float)-14)*255/241,0,255).astype(np.uint8)
        edge=alpha<220
        purple=edge&(rgba[:,:,2].astype(int)>rgba[:,:,1].astype(int)+14)&(rgba[:,:,0].astype(int)>rgba[:,:,1].astype(int)+6)
        luminance=(rgba[:,:,:3].astype(float)*[.2126,.7152,.0722]).sum(axis=2)
        for channel in range(3):rgba[:,:,channel]=np.where(purple,rgba[:,:,channel]*.25+luminance*.75,rgba[:,:,channel]).astype(np.uint8)
        # Spatial smoothing only: preserve hair detail and avoid isolated flecks.
        mask=(alpha>80).astype(np.uint8)*255
        count,labels,stats,_=cv2.connectedComponentsWithStats(mask,8)
        if count>1:
            biggest=1+np.argmax(stats[1:,cv2.CC_STAT_AREA]);mask=np.where(labels==biggest,255,0).astype(np.uint8)
        mask=cv2.morphologyEx(mask,cv2.MORPH_CLOSE,np.ones((3,3),np.uint8))
        # Offset the contour outwards so dashes sit off the hair and jacket.
        wide=cv2.dilate(np.pad(mask,((pad,pad),(pad,pad))),cv2.getStructuringElement(cv2.MORPH_ELLIPSE,(7,7)))
        contours,_=cv2.findContours(wide,cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_NONE)
        line=Image.new('RGBA',(W,H),(0,0,0,0));draw=ImageDraw.Draw(line)
        if contours:
            points=max(contours,key=cv2.contourArea)[:,0,:].astype(float)
            points=np.concatenate([points,points[:1]],axis=0)
            lengths=np.linalg.norm(np.diff(points,axis=0),axis=1);dist=np.r_[0,np.cumsum(lengths)]
            # Fixed dash phase follows the silhouette; the outline does not chase itself.
            for at in np.arange(0,dist[-1],17):
                ends=np.arange(at,min(at+9,dist[-1])+.01,1.2)
                xx=np.interp(ends,dist,points[:,0]);yy=np.interp(ends,dist,points[:,1])
                xy=[(float(x),float(y)) for x,y in zip(xx,yy) if y<H-46]
                if len(xy)>1:draw.line(xy,fill=(255,255,255,105),width=1)
        actor=Image.new('RGBA',(W,H));actor.paste(Image.fromarray(rgba),(pad,pad))
        composed=Image.alpha_composite(line,actor)
        arr=np.array(composed)
        fade=np.clip((H-10-np.arange(H))/80,0,1);fade=fade*fade*(3-2*fade)
        arr[:,:,3]=(arr[:,:,3]*fade[:,None]).astype(np.uint8)
        encoder.stdin.write(arr.tobytes())
        if frames in (0,45,90,150):
            Image.fromarray(arr).save(OUT/f'outlined-frame-{frames:03}.png')
        alpha_stats.append(float((arr[:,:,3]>128).mean()));frames+=1
finally:
    decoder.stdout.close();derr=decoder.stderr.read().decode();dc=decoder.wait()
    encoder.stdin.close();eerr=encoder.stderr.read().decode();ec=encoder.wait()
assert dc==0,derr
assert ec==0,eerr
assert frames>=math.floor(opts.min_seconds*30),frames
report={'source':str(src),'output':str(OUT/'avatar-outlined.webm'),'frames':frames,'fps':30,'size':[W,H],'cropSource':[cx,cy,cw,ch],'alphaCoverageRange':[min(alpha_stats),max(alpha_stats)],'method':'edge-only purple spill suppression, low-opacity narrow contour and smooth bottom alpha fade; opaque face pixels and speech timing unchanged'}
(OUT/'outline-verification.json').write_text(json.dumps(report,ensure_ascii=False,indent=2), encoding='utf-8')
print(json.dumps(report,ensure_ascii=False,indent=2))
