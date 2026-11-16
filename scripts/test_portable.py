# /// script
# requires-python = ">=3.11,<3.13"
# dependencies = ["opencc-python-reimplemented==0.1.7", "pypinyin==0.55.0", "fonttools>=4.50,<5", "brotli>=1,<2"]
# ///
"""Portable behaviour tests: no client assets, credentials or paid APIs."""
import copy,json,os,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import project_config as pc
import people,batch,voice_clone,install
from workflow import write,read,settings

class PortableTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        self.env=patch.dict(os.environ,{'MONTAGE_PROJECT_ROOT':str(self.root)});self.env.start();pc.init()
        pc.save_patch({'settings':{'cover':{'enabled':False},'delivery':{'enabled':False}}})
        pc.store_connection('main',{'api_key':'fixture-api','ak':'fixture-ak','sk':'fixture-sk','bucket':'fixture','region':'cn-beijing','endpoint':'tos-cn-beijing.volces.com'})
    def tearDown(self):self.env.stop();self.temp.cleanup()
    def people(self,n=1,ready=True):
        cfg=pc.load()
        for i in range(n):
            name=f'p{i:02}';img=pc.directory()/'people'/name/'portrait.png';img.parent.mkdir(parents=True);img.write_bytes(b'image fixture')
            cfg['people'][name]={'id':name,'name':'人物'+str(i),'portrait':str(img),'connection':'main','speaker':'speaker'+str(i) if ready else None,'status':'ready' if ready else 'needs_voice'}
        cfg['default_person']='p00';pc.write(pc.directory()/'project.json',cfg)
    def job(self):
        job=self.root/'job';job.mkdir();write(job/'plan.json',{'settings':{}});return job
    def test_init_is_idempotent_and_keeps_secrets(self):
        self.people(30);pc.save_patch({'settings':{'avatar':{'width':333}}});before=(pc.directory()/'project.json').read_bytes();secret=(pc.directory()/'secrets.json').read_bytes()
        pc.init();self.assertEqual(before,(pc.directory()/'project.json').read_bytes());self.assertEqual(secret,(pc.directory()/'secrets.json').read_bytes())
    def test_configuration_priority(self):
        self.people();pc.save_patch({'settings':{'avatar':{'width':350}}});job=self.job();write(job/'plan.json',{'settings':{'avatar':{'width':300}}})
        self.assertEqual(settings(job)['avatar']['width'],300)
    def test_all_people_share_one_credential_connection(self):
        self.people(40);items,missing=people.select('all');self.assertEqual(len(items),40);self.assertFalse(missing)
        self.assertTrue(all(p['connection']=='main' and 'api_key' not in p for p in items));self.assertEqual(len(pc.load()['connections']),1)
    def test_unready_people_are_reported(self):
        self.people(2,False);items,missing=people.select('all');self.assertFalse(items);self.assertEqual(len(missing),2)
    def test_clone_slot_cannot_be_shared_accidentally(self):
        self.people(2)
        with self.assertRaises(ValueError):people.bind('p01','speaker0')
    def test_no_secrets_in_public_config_or_doctor(self):
        self.people();text=json.dumps(pc.load())+json.dumps(pc.doctor())
        for secret in ('fixture-api','fixture-ak','fixture-sk'):self.assertNotIn(secret,text)
        if os.name=='posix':self.assertEqual((pc.directory()/'secrets.json').stat().st_mode&0o777,0o600)
    def test_frozen_person_and_parameters_survive_project_changes(self):
        self.people();job=self.job();runtime=pc.freeze(job);pc.save_patch({'settings':{'avatar':{'width':220}}})
        original=pc.asset_path(pc.person()['portrait']);original.write_bytes(b'changed')
        self.assertEqual(settings(job)['avatar']['width'],runtime['settings']['avatar']['width'])
        self.assertEqual(Path(runtime['settings']['avatar']['portrait']).read_bytes(),b'image fixture')
        self.assertTrue((Path(runtime['engine'])/'scripts/montage.py').is_file())
    def test_batch_counts_and_assignments(self):
        self.people(30);source=self.root/'institution';source.mkdir();(source/'facts.txt').write_text('本机构设有阅读室。', encoding='utf-8')
        out=self.root/'batch';result=batch.prepare(source,out,'all',3,{'p00':2});self.assertEqual(result['total'],89)
        data=read(out/'batch.json');self.assertEqual(len({r['id'] for r in data['items']}),89)
    def test_batch_resumes_completed_steps_and_caps_pending_jobs(self):
        self.people(4);folder=self.root/'batch';folder.mkdir()
        items=[{'id':f'p{i}','personName':'人物','number':1,'job':f'j{i}','steps':[],'phase':'ready'} for i in range(4)]
        write(folder/'batch.json',{'items':items,'phase':'ready','max_active':2,'excludedUnreadyPeople':[]})
        calls=[]
        def invoke(job,action,extra=None):
            calls.append((job.name,action));return (2,{'pending':[1]}) if action=='avatars' else (0,{})
        with patch('batch.invoke',side_effect=invoke):batch.tick(folder,limit=10)
        data=read(folder/'batch.json');self.assertEqual(sum(r['phase']=='pending' for r in data['items']),2)
        calls.clear()
        with patch('batch.invoke',side_effect=invoke):batch.tick(folder,limit=10)
        self.assertTrue(all(action=='avatars' for _,action in calls));self.assertEqual(len(calls),2)
    def test_voice_training_resumes_without_another_submission(self):
        self.people(1,False);cfg=pc.load();sample=pc.directory()/'sample.wav';sample.write_bytes(b'wav fixture');cfg['people']['p00']['sample']=str(sample);pc.write(pc.directory()/'project.json',cfg)
        calls=[]
        def api(action,payload,key):calls.append(action);return {'status':1}
        with patch('voice_clone.call',side_effect=api):
            voice_clone.prepare('p00','S_test');voice_clone.prepare('p00')
        self.assertEqual(calls.count('voice_clone'),1);self.assertEqual(calls.count('get_voice'),2)
    def test_custom_voice_training_becomes_ready(self):
        self.people(1,False);cfg=pc.load();sample=pc.directory()/'sample.wav';sample.write_bytes(b'wav');cfg['people']['p00']['sample']=str(sample);cfg['connections']['main']['clone_mode']='postpaid';pc.write(pc.directory()/'project.json',cfg)
        with patch('voice_clone.call',return_value={'status':2}):self.assertTrue(voice_clone.prepare('p00')['ready'])
        self.assertEqual(pc.person()['speaker'],'custom_speaker_id');self.assertTrue(pc.person()['custom_speaker_id'])
    def test_installer_updates_code_without_touching_user_data(self):
        self.people(10);target=self.root/'.agents/skills/nursing-home-montage';target.mkdir(parents=True);(target/'old.txt').write_text('old', encoding='utf-8')
        original=(pc.directory()/'project.json').read_bytes();credentials=(pc.directory()/'secrets.json').read_bytes()
        def git(args):
            if args[1]=='ls-remote':return 'abc\trefs/tags/v2.0.0\nabc\trefs/tags/v2.1.0\n'
            if args[1]=='clone':
                dest=Path(args[-1]);dest.mkdir();(dest/'scripts').mkdir()
                for name in ('SKILL.md','preset.json','scripts/montage.py','scripts/project.py'):(dest/name).write_text('fixture', encoding='utf-8')
                (dest/'release.json').write_text(json.dumps({'config_schema':1}), encoding='utf-8')
            return ''
        with patch('install.run',side_effect=git):result=install.install(self.root)
        self.assertEqual(result['version'],'v2.1.0');self.assertEqual(original,(pc.directory()/'project.json').read_bytes());self.assertEqual(credentials,(pc.directory()/'secrets.json').read_bytes());self.assertTrue((Path(result['previousCode'])/'old.txt').exists())
    def test_source_quotation_validation(self):
        from workflow import validate_plan
        job=self.job();write(job/'inventory.json',{'files':[{'path':'facts.txt','kind':'text','text':'有阅读室。'},{'path':'v.mp4','kind':'video'}]})
        plan={'settings':{'closing_hook':{'enabled':False}},'institution':{'name':'测试机构','displayName':'测试机构','headline':'实地看养老'},'facts':[{'id':'a','source':'facts.txt','quote':'有阅读室。'}],'sentences':[{'text':'有阅读室。','factIds':['a'],'shots':[{'path':'v.mp4'}]}]}
        write(job/'plan.json',plan);validate_plan(job);plan['facts'][0]['quote']='免费入住。';write(job/'plan.json',plan)
        with self.assertRaises(ValueError):validate_plan(job)

    def test_closing_hook_requires_moving_footage_and_keeps_opening_only(self):
        from workflow import validate_plan
        self.people();job=self.job()
        write(job/'inventory.json',{'files':[{'path':'v.mp4','kind':'video'},{'path':'p.jpg','kind':'image'}]})
        plan={'institution':{'name':'测试机构','displayName':'测试机构','headline':'实地看养老'},'facts':[], 'sentences':[{'text':'先看居住空间。','kind':'hook','shots':[{'path':'v.mp4'}]}]}
        write(job/'plan.json',plan)
        with self.assertRaisesRegex(ValueError,'结尾需要'):validate_plan(job)
        plan['sentences'].append({'text':'关注老师，想咨询参观，评论区留言养老服务。','kind':'cta','shots':[{'path':'p.jpg'}]})
        write(job/'plan.json',plan)
        with self.assertRaisesRegex(ValueError,'moving footage'):validate_plan(job)
        plan['sentences'][-1]['shots']=[{'path':'v.mp4'}];write(job/'plan.json',plan);validate_plan(job)
        self.assertEqual(settings(job)['avatar']['mode'],'opening')
        self.assertEqual(settings(job)['template']['id'],'legacy-orange')

    def test_template_switch_does_not_change_voice_person_or_connection(self):
        self.people();job=self.job();before=settings(job)
        write(job/'plan.json',{'settings':{'template':{'id':'green'}}});after=settings(job)
        self.assertEqual(after['template']['id'],'green')
        for key in ('voice','person','service'):self.assertEqual(before[key],after[key])

    def test_ui_common_placement_is_lower_than_needed_but_never_obscured(self):
        from platform_ui import lowest_box,audit
        a={'screenshot_size':[1080,1920],'viewport':[0,0,1080,1920],'gap_px':20,'regions':[{'name':'bottom','rect':[0,1650,1080,1920]},{'name':'rail','rect':[950,900,1080,1800]}]}
        b=copy.deepcopy(a);b['regions'][0]['rect'][1]=1750
        common=lowest_box(750,280,[80,800,900,1920],{'a':a,'b':b})
        individual=lowest_box(750,280,[80,800,900,1920],{'b':b})
        self.assertEqual(common[3],1630);self.assertEqual(individual[3],1730)
        self.assertTrue(all(not row['overlappingOrClippedLines'] for row in audit([common],{'a':a,'b':b})))

    def test_ui_mapping_includes_crop_and_rejects_invalid_regions(self):
        from platform_ui import native_regions,lowest_box
        p={'screenshot_size':[1200,2600],'viewport':[0,100,1200,2400],'regions':[]}
        m=native_regions(p);self.assertEqual(m['scale'],1.25);self.assertEqual(m['visible'][0],60)
        p['regions']=[{'name':'bad','rect':[0,0,1300,2600]}]
        with self.assertRaises(ValueError):native_regions(p)
        with self.assertRaises(ValueError):lowest_box(1000,300,[100,100,900,1900],{})

    def test_glyph_reflow_preserves_words_size_and_verified_split_times(self):
        from caption_layout import Typography,reflow
        from workflow import clean
        spec=read(pc.SKILL/'assets/templates/fullscreen-orange.json')['caption']
        font=Typography(pc.SKILL/'assets/NotoSansSC-Black.otf',None,spec)
        text='服务包括二十四小时生活照料以及健康管理和康复护理';n=len(clean(text))
        cue={'text':text,'lines':['服务包括24小时生活照料以及健康管理和康复护理'],'focus':'24小时','start':0,'end':n*.3,'duration':n*.3,'canonicalRange':[0,n]}
        timing=[{'start':i*.3,'end':(i+1)*.3} for i in range(n)]
        with self.assertRaisesRegex(ValueError,'verified character timing'):reflow([cue],font,clean)
        cues,changes=reflow([cue],font,clean,timing)
        self.assertGreater(len(cues),1);self.assertTrue(changes)
        self.assertEqual(''.join(clean(c['text']) for c in cues),clean(text))
        self.assertEqual(cues[0]['start'],0);self.assertEqual(cues[-1]['end'],cue['end'])
        for a,b in zip(cues,cues[1:]):self.assertEqual(a['end'],b['start']);self.assertIn(b['start'],[t['start'] for t in timing])
        for c in cues:
            self.assertLessEqual(len(c['lines']),2)
            self.assertTrue(all(font.fits(line,c.get('focus',''),j) for j,line in enumerate(c['lines'])))
        self.assertTrue(any('24小时' in line for c in cues for line in c['lines']))
        self.assertEqual(font.spec['font_size'],spec['font_size'])

    def test_fullscreen_standard_compose_is_portable_and_repeatable(self):
        import shutil
        from build_job import compose
        self.people();job=self.job();write(job/'plan.json',{'settings':{'template':{'id':'fullscreen-orange'}}})
        (job/'assets/fonts').mkdir(parents=True)
        shutil.copy2(pc.SKILL/'assets/NotoSansSC-Black.otf',job/'assets/fonts/NotoSansSC-Black.otf')
        write(job/'orange-font-match.json',[{'family':'fixture','file':str(pc.SKILL/'assets/NotoSansSC-Black.otf'),'index':None,'angle':3,'tracking':4,'stroke':3}])
        write(job/'institution.json',{'name':'测试机构','displayName':'测试机构','headline':'实地看养老'})
        (job/'narration.txt').write_text('床边有沙发。',encoding='utf-8');(job/'source-description.txt').write_text('测试',encoding='utf-8')
        write(job/'natural-timeline.json',{'duration':3,'voiceStart':0,'voiceDuration':3,'audio':'assets/voice.wav','outroStart':3,'outroDuration':0,'chapters':[[0,3,'居住空间']]})
        write(job/'captions.json',[{'text':'床边有沙发','lines':['床边有','沙发'],'focus':'沙发','start':0,'end':3,'duration':3}])
        write(job/'avatars.json',[]);write(job/'shot-list.json',[{'asset':'assets/room.mp4','start':0,'duration':3,'positionY':50,'description':'fixture footage','sourceStart':0}])
        compose(job);first=(job/'index.html').read_bytes();caps=(job/'compositions/orange-captions.html').read_bytes()
        self.assertEqual(read(job/'template-layout.json')['pictureOutput'],[0,0,1080,1920])
        self.assertIn('测试机构',(job/'compositions/orange-ui.html').read_text())
        self.assertFalse(read(job/'template-layout.json')['socialUIBurnedIn'])
        compose(job);self.assertEqual(first,(job/'index.html').read_bytes());self.assertEqual(caps,(job/'compositions/orange-captions.html').read_bytes())

    def test_missing_template_font_stops_before_freezing_or_paid_work(self):
        from workflow import setup
        self.people();job=self.job();write(job/'plan.json',{'settings':{'template':{'id':'green','overrides':{'fonts':{'title':{'file':str(self.root/'missing.ttc'),'index':2}}}}}})
        with self.assertRaisesRegex(ValueError,'Template font is missing'):setup(job)
        self.assertFalse((job/'runtime.json').exists())

    def test_reference_contrast_review_cannot_hide_runtime_errors_or_changed_inputs(self):
        import production
        job=self.job();check={'ok':False,'inputFingerprint':'a','runtime':{'errorCount':0},'contrast':{'errorCount':1},'visualContrastReview':{'inputFingerprint':'a','frames':[{'file':'reviewed.png'}]}}
        with patch('production.input_fingerprint',return_value='a'):
            self.assertTrue(production.accepted_check(job,check))
            check['runtime']['errorCount']=1;self.assertFalse(production.accepted_check(job,check))
            check['runtime']['errorCount']=0
        with patch('production.input_fingerprint',return_value='b'):self.assertFalse(production.accepted_check(job,check))

    def test_real_media_import_is_deduplicated_and_project_owned(self):
        import shutil
        from workflow import run
        if not shutil.which('ffmpeg'):self.skipTest('FFmpeg is needed for media normalization')
        source=self.root/'people-in';first=source/'老师甲';first.mkdir(parents=True)
        run(['ffmpeg','-y','-v','error','-f','lavfi','-i','color=c=orange:s=100x140','-frames:v','1',first/'photo.png'])
        run(['ffmpeg','-y','-v','error','-f','lavfi','-i','sine=frequency=220:duration=1',first/'voice.wav'])
        for name in ('老师乙','老师丙'):shutil.copytree(first,source/name)
        result=people.import_people(source);self.assertEqual(len(result['imported']),3)
        again=people.import_people(source);self.assertTrue(all(p['reused'] for p in again['imported']))
        shutil.rmtree(source)
        self.assertTrue(all(pc.asset_path(p['portrait']).is_file() and pc.asset_path(p['sample']).is_file() for p in people.listing()))

    def test_local_setup_page_saves_credentials_without_echoing_them(self):
        import subprocess,time,urllib.request
        script=Path(__file__).with_name('project.py')
        prefix=['rtk','proxy'] if __import__('shutil').which('rtk') else []
        log=open(self.root/'setup-test.log','w',encoding='utf-8')
        child=subprocess.Popen(prefix+[__import__('sys').executable,str(script),'--project',str(self.root),'_serve'],stdout=log,stderr=log)
        try:
            record=pc.directory()/'setup-server.json'
            for _ in range(600):
                if record.exists():break
                if child.poll() is not None:raise RuntimeError((self.root/'setup-test.log').read_text(encoding='utf-8'))
                time.sleep(.05)
            if not record.exists():raise RuntimeError('Setup server did not become ready in 30s: '+(self.root/'setup-test.log').read_text(encoding='utf-8'))
            url=pc.read(record)['url']
            with urllib.request.urlopen(url) as response:self.assertIn('password',response.read().decode())
            data=json.dumps({'connection':'main','api_key':'local-form-fixture'}).encode()
            origin=url.rsplit('/',1)[0]
            req=urllib.request.Request(url,data=data,headers={'Content-Type':'application/json','Origin':origin})
            with urllib.request.urlopen(req) as response:self.assertNotIn('local-form-fixture',response.read().decode())
            self.assertEqual(pc.connection_keys(pc.load()['connections']['main'])[0],'local-form-fixture')
        finally:
            if record.exists():
                import signal
                try:os.kill(pc.read(record)['pid'],signal.SIGTERM)
                except ProcessLookupError:pass
            if child.poll() is None:child.terminate()
            child.wait(timeout=10)
            log.close()

    def test_identity_and_hooks_survive_freeze_without_cross_person_use(self):
        self.people(2)
        people.identity('p00',{'social_media_name':'甲带你看','closing_hooks':{'default_id':'visit','library':{'visit':{'text':'留言咨询居住安排。'}}}})
        job=self.job();write(job/'plan.json',{'person':'p00','settings':{}})
        frozen=pc.freeze(job);people.identity('p00',{'social_media_name':'修改后的名字'})
        self.assertEqual(settings(job)['person']['socialMediaName'],'甲带你看')
        plan={'sentences':[{'kind':'cta','text':''}],'settings':{}}
        result=people.closing_hook(plan,frozen['settings']);self.assertEqual(result['source'],'person-default')
        plan['settings']={'closing_hook':{'hook_id':'visit'}}
        cfg=copy.deepcopy(frozen['settings']);cfg['person']['id']='p01';cfg['person']['closingHooks']={}
        with self.assertRaisesRegex(ValueError,'不属于'):people.closing_hook(plan,cfg)

    def test_hook_priority_disable_and_empty_optional_library(self):
        cfg={'person':{'id':'a','closingHooks':{'default_id':'d','library':{'d':{'text':'个人默认咨询。'}}}},'closing_hook':{'enabled':True,'keyword':'养老'}}
        plan={'sentences':[{'kind':'cta','text':'本次已写咨询。'}],'settings':{}}
        self.assertEqual(people.closing_hook(plan,cfg)['text'],'本次已写咨询。')
        with self.assertRaises(ValueError):people.closing_hook({**plan,'settings':{'closing_hook':{'text':'咨询。','hook_id':'d'}}},cfg)
        plan['settings']={'closing_hook':{'text':'本次指定咨询。'}}
        self.assertEqual(people.closing_hook(plan,cfg)['source'],'task-text')
        cfg['closing_hook']['enabled']=False;self.assertEqual(people.closing_hook(plan,cfg)['source'],'disabled')
        cfg['closing_hook']['enabled']=True;cfg['person']['closingHooks']={};plan={'sentences':[{'kind':'cta','text':''}],'settings':{}}
        self.assertEqual(people.closing_hook(plan,cfg)['source'],'project-consultation')

    def test_publication_requires_exactly_five_unique_topics_and_safe_names(self):
        from delivery import validate_publication,safe_name
        value={'title':'真实探访','description':'了解生活安排。','topics':['养老院','养老生活','养老选择','实地探访','养老咨询']}
        self.assertEqual(len(validate_publication(value)['topics']),5)
        value['topics'][-1]='养老院'
        with self.assertRaises(ValueError):validate_publication(value)
        self.assertEqual(safe_name('养老生活\n能有多丰富？'),'养老生活能有多丰富')

    def test_missing_cover_identity_stops_before_paid_work(self):
        from cover import validate_content
        self.people();job=self.job();cfg=settings(job);cfg['cover']['enabled']=True
        with self.assertRaisesRegex(ValueError,'社交媒体名'):validate_content({},cfg,{})

    def test_cover_review_accepts_relative_evidence_paths(self):
        import production
        from workflow import sha
        job=self.job();video=job/'render.mp4';video.write_bytes(b'verified fixture');frames=[]
        for name in ('first.png','second.png'):
            p=job/name;p.write_bytes(b'frame fixture');frames.append(str(p.resolve()))
        write(job/'verification.json',{'video':str(video),'sha256':sha(video),'duration':1,'renderedReviewFrames':frames})
        with patch('production.settings',return_value={'cover':{'enabled':True},'delivery':{'enabled':False}}):
            production.review(job,[os.path.relpath(p) for p in frames],'已查看实际检查帧')
        self.assertEqual(read(job/'verification.json')['visualReview']['frames'],frames)

if __name__=='__main__':unittest.main(verbosity=2)
