"""User-friendly project setup. Agent invokes these commands; users do not edit JSON."""
import argparse,json,os,secrets,shutil,subprocess,sys,time
from pathlib import Path
from http.server import BaseHTTPRequestHandler,HTTPServer
import project_config as pc
import people

PAGE='''<!doctype html><meta charset="utf-8"><title>混剪项目设置</title><style>body{font:16px system-ui;max-width:680px;margin:40px auto;padding:0 20px;background:#faf9f6;color:#222}label{display:block;margin:18px 0}input,select{display:block;box-sizing:border-box;width:100%;padding:10px;margin-top:6px;font:inherit}button{background:#fa8d1b;border:0;padding:12px 25px;font:inherit;border-radius:8px}small{color:#666}pre{white-space:pre-wrap}</style><h1>混剪项目设置</h1><p>仅补齐缺少的信息。留空的项目会保留原配置。所有数字人共用这套服务连接。</p><form id="setup"><label>服务连接名称<input name="connection" value="main" required></label><label>语音 API Key<input name="api_key" type="password" autocomplete="off"></label><label>Access Key ID<input name="ak" type="password" autocomplete="off"></label><label>Secret Access Key<input name="sk" type="password" autocomplete="off"></label><label>音频存储桶名<input name="bucket"></label><label>存储区域<input name="region" placeholder="例如 cn-beijing"></label><label>存储 Endpoint<input name="endpoint" placeholder="例如 tos-cn-beijing.volces.com"></label><label>新人物声音复刻方式<select name="clone_mode"><option value="">保留现有设置／以后再选</option><option value="prepaid">使用已有音色槽位</option><option value="postpaid">创建后付费音色（首次正式合成产生槽位费用）</option></select></label><label>已有空闲音色槽位（可选）<input name="speaker_pool" placeholder="多个ID用逗号分隔"></label><button>保存并检查</button></form><p><small>只保存到当前项目的私有配置，更新技能时保留。机构素材和人物文件夹可以直接在对话中提供。</small></p><pre id="result"></pre><script>document.querySelector('form').onsubmit=async e=>{e.preventDefault();let values=Object.fromEntries(new FormData(e.target));let r=await fetch(location.pathname,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(values)});document.querySelector('#result').textContent=await r.text();for(let p of document.querySelectorAll('input[type=password]'))p.value='';};</script>'''

def serve(port=0,token=None):
    pc.init();token=token or secrets.token_urlsafe(24);last=[time.monotonic()]
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args):pass
        def reply(self,status,text,kind='text/plain; charset=utf-8'):
            self.send_response(status);self.send_header('Content-Type',kind);self.send_header('Cache-Control','no-store');self.end_headers();self.wfile.write(text.encode())
        def do_GET(self):
            if self.path!='/'+token:return self.reply(404,'页面不存在')
            last[0]=time.monotonic();self.reply(200,PAGE,'text/html; charset=utf-8')
        def do_POST(self):
            if self.path!='/'+token:return self.reply(403,'无效设置页面')
            expected='http://'+self.headers.get('Host','')
            if self.headers.get('Origin')!=expected or self.headers.get('Content-Type')!='application/json':return self.reply(403,'请从本地设置页面保存')
            size=int(self.headers.get('Content-Length','0'))
            if size>20000:return self.reply(400,'输入内容过长')
            try:
                values=json.loads(self.rfile.read(size));name=values.pop('connection','main');pc.store_connection(name,values)
                cfg=pc.load();c=cfg['connections'][name]
                if values.get('clone_mode'):c['clone_mode']=values['clone_mode']
                if values.get('speaker_pool'):c['speaker_pool']=[s.strip() for s in values['speaker_pool'].replace('，',',').split(',') if s.strip()]
                pc.write(pc.directory()/'project.json',cfg);last[0]=time.monotonic();self.reply(200,'已保存。\n'+json.dumps(pc.doctor(),ensure_ascii=False,indent=2))
            except Exception:self.reply(400,'未完成保存，请检查输入。已有配置会保留。')
    server=HTTPServer(('127.0.0.1',port),Handler);server.timeout=1
    url=f'http://127.0.0.1:{server.server_port}/{token}'
    pc.write(pc.directory()/'setup-server.json',{'url':url,'pid':os.getpid()});print(json.dumps({'setupUrl':url}),flush=True)
    while time.monotonic()-last[0]<1800:server.handle_request()
    server.server_close()

def launch():
    pc.init();previous=pc.directory()/'setup-server.json'
    if previous.exists():
        import urllib.request
        try:
            with urllib.request.urlopen(pc.read(previous)['url'],timeout=1):return pc.read(previous)
        except Exception:pass
    log=open(pc.directory()/'setup-server.log','a')
    args=[sys.executable,str(Path(__file__).resolve()),'--project',str(pc.root()),'_serve']
    if shutil.which('rtk'):args=['rtk','proxy',*args]
    subprocess.Popen(args,stdout=log,stderr=log,start_new_session=True);log.close()
    for _ in range(150):
        if previous.exists():
            item=pc.read(previous)
            try:
                import urllib.request
                with urllib.request.urlopen(item['url'],timeout=1):return item
            except Exception:pass
        time.sleep(.1)
    raise RuntimeError('本地设置页未能启动；可改用凭据文件导入。')

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--project',type=Path);sub=p.add_subparsers(dest='action',required=True)
    for a in ('init','doctor','people','setup-ui','_serve'):sub.add_parser(a)
    q=sub.add_parser('configure');q.add_argument('--file',type=Path,required=True)
    q=sub.add_parser('credentials');q.add_argument('--file',type=Path,required=True);q.add_argument('--connection',default='main')
    q=sub.add_parser('import-people');q.add_argument('folder',type=Path);q.add_argument('--connection',default='main')
    q=sub.add_parser('bind');q.add_argument('person');q.add_argument('--speaker',required=True);q.add_argument('--custom')
    q=sub.add_parser('default');q.add_argument('person')
    q=sub.add_parser('train');q.add_argument('person');q.add_argument('--speaker');q.add_argument('--custom')
    q=sub.add_parser('identity');q.add_argument('person');q.add_argument('--file',type=Path,required=True)
    args=p.parse_args()
    if args.project:os.environ['MONTAGE_PROJECT_ROOT']=str(args.project.resolve())
    if args.action=='init':return pc.init()
    if args.action=='doctor':return pc.doctor()
    if args.action=='people':return people.listing()
    if args.action=='configure':return pc.save_patch(pc.read(args.file))
    if args.action=='credentials':return pc.store_connection(args.connection,pc.read(args.file))
    if args.action=='import-people':return people.import_people(args.folder,args.connection)
    if args.action=='bind':return people.bind(args.person,args.speaker,args.custom)
    if args.action=='identity':return people.identity(args.person,pc.read(args.file))
    if args.action=='default':return pc.save_patch({'default_person':pc.person(args.person)['id']})
    if args.action=='train':
        from voice_clone import prepare
        return prepare(args.person,args.speaker,args.custom)
    if args.action=='setup-ui':return launch()
    if args.action=='_serve':return serve()
if __name__=='__main__':
    if hasattr(sys.stdout,'reconfigure'):sys.stdout.reconfigure(encoding='utf-8')
    try:
        result=main();print(json.dumps(result,ensure_ascii=False,indent=2))
        if isinstance(result,dict) and result.get('pending'):sys.exit(2)
    except Exception as e:print(json.dumps({'error':str(e)},ensure_ascii=False));sys.exit(1)
