# /// script
# requires-python = ">=3.11,<3.13"
# dependencies = ["fonttools>=4.50,<5", "brotli>=1,<2"]
# ///
"""Offline real-render tests using synthetic assets; no customer data or paid calls."""
from pathlib import Path
import json,os,shutil,tempfile,unittest,zipfile
from unittest.mock import patch
import project_config as pc
import cover,delivery
from workflow import read,write,run,sha,settings,hyperframes_cli

class CoverTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name);self.env=patch.dict(os.environ,{'MONTAGE_PROJECT_ROOT':str(self.root)});self.env.start();pc.init()
        self.source=self.root/'material';self.source.mkdir();self.job=self.root/'job';self.job.mkdir()
        for name,color in [('photo','beige'),('avatar','navy')]:run(['ffmpeg','-y','-v','error','-f','lavfi','-i',f'color=c={color}:s=710x986','-frames:v','1',self.source/(name+'.png')])
        cfg=pc.load();cfg['people']={'p':{'id':'p','name':'测试人物','social_media_name':'测试人物带你看','portrait':str(self.source/'avatar.png'),'cover_portrait':str(self.source/'avatar.png'),'connection':'main','speaker':'fixture'}};cfg['default_person']='p';cfg['settings']={'cover':{'header_text':'重庆养老院探访'}};pc.write(pc.directory()/'project.json',cfg)
        self.plan={'institution':{'name':'测试机构（测试地区）老年公寓'},'cover':{'main_title':{'text':'养老生活\n能有多丰富？','highlights':['丰富']},'labels':[{'text':t,'source':'photo.png'} for t in ('居住环境','活动空间','院区环境')]},'publication':{'title':'实地了解养老生活','description':'想了解居住安排，欢迎留言咨询。','topics':['养老院','养老生活','养老选择','实地探访','养老咨询']}}
        write(self.job/'plan.json',self.plan);write(self.job/'inventory.json',{'source':str(self.source),'files':[{'path':'photo.png','kind':'image','sha256':sha(self.source/'photo.png')}]})
    def tearDown(self):self.env.stop();self.temp.cleanup()
    def test_shared_layout_handles_full_name_and_equal_tag_sizes(self):
        cover.generate(self.job);d=read(self.job/'cover.json');r=d['layout'];self.assertFalse(r['errors']);self.assertEqual(len(r['title']['lines']),2)
        self.assertEqual(''.join(r['brand']['lines']),self.plan['institution']['name']);self.assertGreaterEqual(r['brand']['em'],64)
        self.assertTrue(48<=r['tags']['em']<=64);self.assertTrue(all(c['w']<=324 for c in r['tags']['cards']));self.assertEqual(r['label_texts'],['居住环境','活动空间','院区环境'])
        text=(self.job/'cover-editor.html').read_text();self.assertNotIn('__LAYOUT__',text);self.assertNotIn(str(self.root),text)
        self.assertTrue(cover.generate(self.job)['reused'])
        # A second job can recover the complete web font from the project cache.
        (self.job/'assets/cover/cover-font.woff2').unlink();(self.job/'assets/cover/font.json').unlink()
        with patch('fontTools.ttLib.TTFont',side_effect=AssertionError('font conversion must be cached')):
            self.assertTrue(cover.generate(self.job)['reused'])
        self.plan['cover']['main_title']['highlights']=['不存在'];write(self.job/'plan.json',self.plan)
        with self.assertRaises(ValueError):cover.require_current(self.job)
    def test_long_title_fails_without_truncation(self):
        self.plan['cover']['main_title']={'text':'给爸妈挑选养老院的时候到底应该怎样全面了解居住环境照护安排活动空间以及一日三餐','highlights':[]};write(self.job/'plan.json',self.plan)
        with self.assertRaisesRegex(RuntimeError,'主标题'):cover.generate(self.job)
    def test_one_frame_overlay_and_publish_package(self):
        cover.generate(self.job);shutil.copy2(pc.SKILL/'assets/gsap.min.js',self.job/'gsap.min.js')
        run(['ffmpeg','-y','-v','error','-f','lavfi','-i','sine=frequency=440:duration=0.4','-c:a','pcm_s16le',self.job/'tone.wav'])
        (self.job/'index.html').write_text('''<!doctype html><html><head><script src="gsap.min.js"></script><style>html,body{margin:0;width:1080px;height:1920px}#root{position:relative;width:1080px;height:1920px}</style></head><body><div id="root" data-composition-id="main" data-duration="0.4" data-start="0" data-fps="30" data-width="1080" data-height="1920"><div class="clip" data-start="0" data-duration="0.4" style="position:absolute;inset:0;background:rgb(0,180,40)"></div><audio id="tone" class="clip" src="tone.wav" data-start="0" data-duration="0.4"></audio></div><script>window.__timelines["main"]=gsap.timeline({paused:true});</script></body></html>''')
        cover.attach(self.job);a=(self.job/'index.html').read_text();cover.attach(self.job);self.assertEqual(a,(self.job/'index.html').read_text())
        import production
        before=production.input_fingerprint(self.job);self.assertTrue(before)
        record=read(self.job/'cover.json');write(self.job/'cover.json',{**record,'fixtureChange':True});self.assertNotEqual(before,production.input_fingerprint(self.job));write(self.job/'cover.json',record)
        for f in ('package.json','package-lock.json','hyperframes.json'):shutil.copy2(pc.SKILL/'assets/orange-template'/f,self.job/f)
        video=self.job/'final.mp4';run([*hyperframes_cli(self.job),'render','--fps','30','--workers','2','--crf','14','--output',video],cwd=self.job)
        def frame(index):return run(['ffmpeg','-v','error','-i',video,'-vf',f'select=eq(n\\,{index}),scale=54:96','-frames:v','1','-pix_fmt','rgb24','-f','rawvideo','-'],binary=True).stdout
        expected=run(['ffmpeg','-v','error','-i',self.job/'cover.png','-vf','scale=54:96','-pix_fmt','rgb24','-f','rawvideo','-'],binary=True).stdout
        first,second=frame(0),frame(1);self.assertEqual(len(first),len(expected));self.assertLess(sum(abs(a-b) for a,b in zip(first,expected))/len(first),6)
        self.assertLess(sum(abs(second[i]-[0,180,40][i%3]) for i in range(len(second)))/len(second),3)
        from workflow import probe
        meta=probe(video);v=next(s for s in meta['streams'] if s['codec_type']=='video');self.assertEqual(int(v['nb_frames']),12);self.assertAlmostEqual(float(meta['format']['duration']),.4,places=2)
        audio=next(s for s in meta['streams'] if s['codec_type']=='audio');self.assertLess(abs(float(audio.get('start_time',0))),.034)
        write(self.job/'verification.json',{'sha256':sha(video),'visualReviewPending':False});result=delivery.package(self.job)
        with zipfile.ZipFile(result['zip']) as z:
            self.assertEqual(len(z.namelist()),4);self.assertIsNone(z.testzip());copy=z.read(next(n for n in z.namelist() if n.endswith('.txt'))).decode('utf-8-sig');self.assertEqual(copy.count('#'),5)
        # Package rebuild is idempotent in content and excludes internal manifests.
        self.assertEqual(delivery.package(self.job)['files'],result['files'])

if __name__=='__main__':unittest.main(verbosity=2)
