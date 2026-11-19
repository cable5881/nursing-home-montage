# /// script
# requires-python = ">=3.11,<3.13"
# dependencies = ["opencc-python-reimplemented==0.1.7", "pypinyin==0.55.0"]
# ///
"""All configured people x per-person counts, resumable and bounded by shared concurrency."""
import argparse,csv,hashlib,json,os,shutil,sys
from pathlib import Path
import project_config as pc
import people
from workflow import inventory,validate_plan,read,write,run,sha

def prepare(source,out,selection='all',count=1,counts=None):
    if out.exists():raise ValueError('批次目录已存在，继续时使用start/run，不会覆盖。')
    selected,missing=people.select(selection)
    if not selected:raise ValueError('没有已配置完成的数字人；请先绑定/训练音色。')
    assignments=[]
    for person in selected:
        n=(counts or {}).get(person['id'],(counts or {}).get(person['name'],count))
        if not isinstance(n,int) or not 0<=n<=10000:raise ValueError('每人数量须为0到10000的整数。')
        assignments.extend({'id':person['id']+f'-{i+1:03}','person':person['id'],'personName':person['name'],'number':i+1} for i in range(n))
    if not assignments:raise ValueError('本批数量不能为0。')
    inventory(source,out);(out/'plans').mkdir()
    for i,row in enumerate(assignments):row['plan']=f'plans/{i+1:04}.json';row['job']=f'people/{row["person"]}/{row["number"]:03}';row['steps']=[];row['phase']='needs_plan'
    data={'schema_version':1,'project':str(pc.root()),'source':str(Path(source).resolve()),'items':assignments,'excludedUnreadyPeople':missing,'phase':'needs_plans','max_active':1}
    write(out/'batch.json',data);report(out)
    return {'batch':str(out),'total':len(assignments),'people':len(selected),'excludedUnreadyPeople':missing,'next':'Agent reads material inventory and authors each listed plan; start validates all before any generation.'}

def start(folder,reuse_scripts=False):
    data=read(folder/'batch.json');seen=set();prepared=[]
    # Validate the whole batch before starting any paid work.
    for row in data['items']:
        plan_path=folder/row['plan']
        if not plan_path.is_file():raise ValueError('缺少内部编排方案：'+row['plan'])
        plan=read(plan_path);plan['person']=row['person'];person=pc.person(row['person'],ready=True)
        job=folder/row['job'];job.mkdir(parents=True,exist_ok=True)
        if (job/'plan.json').exists() and read(job/'plan.json')!=plan:raise ValueError('已启动的任务文案被修改，请新建批次。')
        write(job/'plan.json',plan)
        for f in ('inventory.json','source-text.txt'):shutil.copy2(folder/f,job/f)
        plan,_=validate_plan(job)
        write(plan_path,plan)
        content='\n'.join(s['text'] for s in plan['sentences']);h=hashlib.sha256(content.encode()).hexdigest()
        if h in seen and not reuse_scripts:raise ValueError('本批存在相同文案；默认每条不同，明确允许共享脚本时才使用--reuse-scripts。')
        seen.add(h);prepared.append((row,job))
    for row,job in prepared:
        pc.freeze(job);row['phase']='ready' if row['phase']=='needs_plan' else row['phase']
    data['phase']='ready';data['reuse_scripts']=reuse_scripts;write(folder/'batch.json',data);report(folder)
    return {'ready':True,'total':len(data['items']),'uniqueScripts':len(seen),'paidCalls':0}

STEPS=['setup','preflight','voice','build','avatars','provider-review','cutouts','cover','carve','check','snapshot','render','verify','final-review']
def invoke(job,action,extra=None):
    runtime=read(job/'runtime.json');script=Path(runtime['engine'])/'scripts/montage.py'
    args=['uv','run','--python','3.11',script,action,job]+(extra or [])
    if action=='setup':args+=['--install']
    if action=='avatars':args+=['--wait-seconds','0']
    env=os.environ.copy();env['MONTAGE_PROJECT_ROOT']=runtime['project']
    result=run(args,env=env,check=False)
    try:payload=json.loads(result.stdout)
    except ValueError:payload={'error':'阶段未返回有效JSON，请查看任务日志。'}
    return result.returncode,payload

def register_queue(folder):
    data=read(folder/'batch.json')
    sys.path.insert(0,str(Path(__file__).parent/'workbench'))
    from server import App
    app=App(Path(data['project']),Path(__file__).resolve().parents[1],recover=False)
    with app.transaction():
        if data.get('workbenchTaskId') and app.queue.for_task(data['workbenchTaskId']):
            return app,app.task(data['workbenchTaskId'])
        ordered={}
        for row in data['items']:ordered[row['person']]=ordered.get(row['person'],0)+1
        if sum(ordered.values())>100:raise ValueError('统一队列每批最多100条，请拆为多个有序批次')
        progress=any((folder/row['job']/'voice.json').exists() or (folder/row['job']/'runs').exists() for row in data['items'])
        task=app.task(data['workbenchTaskId']) if data.get('workbenchTaskId') else app.create({'source':data['source'],'person':data['items'][0]['person'],
                         'people':[{'id':person,'count':count} for person,count in ordered.items()],
                         'count':len(data['items']),'music':False,'title':folder.name})
        data.update(workbenchTaskId=task['id'],importState='preparing',max_active=1)
        write(folder/'batch.json',data)
        task['legacyBatch']=str(folder);task['planningRequired']=not progress
        app.update(task['id'],**{k:task[k] for k in ('legacyBatch','planningRequired')})
        if progress:
            # Explicitly importing an old batch preserves frozen plans and paid
            # assets. It does not restart the legacy parallel scheduler.
            for i,row in enumerate(data['items']):
                source=folder/row['job'];target=Path(task['job'])/f'variant-{i+1:02d}' if len(data['items'])>1 else Path(task['job'])
                if source.is_dir():shutil.copytree(source,target,dirs_exist_ok=True,ignore=shutil.ignore_patterns('node_modules','.hyperframes'))
        else:
            target,_=app.planning.initialize(task)
            for i,row in enumerate(data['items']):
                source=folder/row['plan']
                if source.is_file():shutil.copy2(source,target/'plans'/f'{i+1:04d}.json')
        app.queue.enqueue(app.task(task['id']))
        if progress:
            queue=app.queue.data()
            for row in queue['items']:
                if row['taskId']!=task['id'] or row['kind']!='video':continue
                try:app.verify_job(Path(row['job']))
                except (OSError,ValueError):pass
                else:row.update(status='completed',settled=True,phase=6,message='旧批次已核验成品已保留')
            app.queue.save(queue);app.queue.sync_task(task['id'])
        data.update(workbenchTaskId=task['id'],max_active=1,queueVersion=2,importState='ready')
        write(folder/'batch.json',data)
        return app,app.task(task['id'])

def tick(folder,limit=4,retry_failed=False):
    app,task=register_queue(folder)
    if retry_failed:
        head=app.queue.head()
        if head and head['taskId']==task['id'] and head['status'] in ('failed','interrupted'):
            app.queue.action(head['id'],'retry')
    return {'batch':str(folder),'taskId':task['id'],'queue':app.queue.public(),
            'coordinatorGuide':str(Path(__file__).parent/'workbench/AGENT.md'),
            'instruction':'已进入同一个严格 FIFO。当前宿主按 coordinatorGuide 由原生子 Agent 接单；本命令不启动另一套并行渲染。'}

def reviewed(folder,identifier,frames,note,provider=False):
    if read(folder/'batch.json').get('workbenchTaskId'):raise ValueError('此批次已使用统一队列，请由当前视频子 Agent 通过工作台 pipeline review 记录审核')
    data=read(folder/'batch.json');row=next(r for r in data['items'] if r['id']==identifier);job=folder/row['job']
    if row['phase']!=('provider_review' if provider else 'final_review'):raise ValueError('此条任务当前不处于对应复核阶段。')
    action='review-provider' if provider else 'review';code,result=invoke(job,action,['--frames',*frames,'--note',note])
    if code:raise ValueError(result)
    row['steps'].append('provider-review' if provider else 'final-review');row['phase']='ready' if provider else 'complete';row['lastResult']=result
    if not provider:
        row['delivery']=str((job/'final.mp4').resolve())
        if (job/'delivery.json').is_file():row['publishPackage']=read(job/'delivery.json')['zip']
    data['phase']='complete' if all(r['phase']=='complete' for r in data['items']) else 'in_progress'
    write(folder/'batch.json',data);return report(folder)

def report(folder):
    data=read(folder/'batch.json');summary={}
    for r in data['items']:summary[r['phase']]=summary.get(r['phase'],0)+1
    with (folder/'交付清单.csv').open('w',encoding='utf-8-sig',newline='') as f:
        writer=csv.writer(f);writer.writerow(['任务','数字人','序号','状态','成片','封面','发布包','钩子来源'])
        for r in data['items']:
            job=folder/r['job'];plan=read(job/'plan.json') if (job/'plan.json').is_file() else {}
            writer.writerow([r['id'],r['personName'],r['number'],r['phase'],r.get('delivery',''),str(job/'cover.png') if (job/'cover.png').is_file() else '',r.get('publishPackage',''),plan.get('closingHookSelection',{}).get('source','')])
    return {'batch':str(folder),'total':len(data['items']),'summary':summary,'manifest':str(folder/'交付清单.csv'),'reviewNeeded':[{'id':r['id'],'phase':r['phase'],'job':str(folder/r['job'])} for r in data['items'] if r['phase'] in ('provider_review','final_review')],'excludedUnreadyPeople':data['excludedUnreadyPeople']}

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--project',type=Path);s=p.add_subparsers(dest='action',required=True)
    q=s.add_parser('prepare');q.add_argument('input',type=Path);q.add_argument('--out',type=Path,required=True);q.add_argument('--people',default='all');q.add_argument('--per-person',type=int,default=1);q.add_argument('--counts',type=Path)
    for a in ('start','run','status','review-provider','review'):
        q=s.add_parser(a);q.add_argument('folder',type=Path)
        if a=='start':q.add_argument('--reuse-scripts',action='store_true')
        if a=='run':q.add_argument('--limit',type=int,default=4);q.add_argument('--retry-failed',action='store_true')
        if a in ('review','review-provider'):q.add_argument('--item',required=True);q.add_argument('--frames',nargs='+',required=True);q.add_argument('--note',required=True)
    args=p.parse_args()
    if args.project:os.environ['MONTAGE_PROJECT_ROOT']=str(args.project.resolve())
    if args.action=='prepare':return prepare(args.input,args.out.resolve(),args.people,args.per_person,read(args.counts) if args.counts else None)
    folder=args.folder.resolve();os.environ.setdefault('MONTAGE_PROJECT_ROOT',read(folder/'batch.json')['project'])
    if args.action=='start':
        start(folder,args.reuse_scripts)
        return tick(folder)
    if args.action=='run':return tick(folder,args.limit,args.retry_failed)
    if args.action=='status':return report(folder)
    return reviewed(folder,args.item,args.frames,args.note,args.action=='review-provider')
if __name__=='__main__':
    if hasattr(sys.stdout,'reconfigure'):sys.stdout.reconfigure(encoding='utf-8')
    try:print(json.dumps(main(),ensure_ascii=False,indent=2))
    except Exception as e:print(json.dumps({'error':str(e)},ensure_ascii=False));sys.exit(1)
