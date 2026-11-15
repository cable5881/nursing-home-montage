# /// script
# requires-python = ">=3.11,<3.13"
# dependencies = ["opencc-python-reimplemented==0.1.7", "pypinyin==0.55.0"]
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
        plan={'institution':{'name':'测试机构','displayName':'测试机构','headline':'实地看养老'},'facts':[{'id':'a','source':'facts.txt','quote':'有阅读室。'}],'sentences':[{'text':'有阅读室。','factIds':['a'],'shots':[{'path':'v.mp4'}]}]}
        write(job/'plan.json',plan);validate_plan(job);plan['facts'][0]['quote']='免费入住。';write(job/'plan.json',plan)
        with self.assertRaises(ValueError):validate_plan(job)

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

if __name__=='__main__':unittest.main(verbosity=2)
