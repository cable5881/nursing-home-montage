"""One publish-ready ZIP per video. Internal production records stay in the job."""
from pathlib import Path
import json,re,shutil,zipfile,os
from workflow import read,write,sha,settings
from cover import title_text

def validate_publication(value):
    if not isinstance(value,dict) or not all(isinstance(value.get(k),str) and value[k].strip() for k in ('title','description')):raise ValueError('请编写社交媒体发布标题和描述，保存到 plan.publication')
    topics=value.get('topics',[])
    if not isinstance(topics,list) or len(topics)!=5 or any(not isinstance(t,str) or not t.strip().lstrip('#') or re.search(r'\s',t.strip().lstrip('#')) for t in topics):raise ValueError('发布文案需要恰好 5 个不含空格的话题')
    normalized=[t.strip().lstrip('#') for t in topics]
    if len(set(normalized))!=5:raise ValueError('五个话题不得重复')
    return {**value,'topics':normalized}

def safe_name(text):
    text=re.sub(r'[<>:"/\\|?*？\x00-\x1f]','',text)
    text=re.sub(r'\s+','',text).strip('. ')
    return text[:85] or '视频'

def package(job):
    cfg=settings(job);plan=read(job/'plan.json');meta=validate_publication(plan.get('publication',{}))
    video=job/'final.mp4';report=read(job/'verification.json')
    if not video.is_file() or sha(video)!=report.get('sha256') or report.get('visualReviewPending',True):raise ValueError('实际成片通过核验与视觉复核后才能打包')
    from cover import require_current
    require_current(job)
    for name in ('cover.png','cover-editor.html'):
        if not (job/name).is_file():raise ValueError('发布包缺少 '+name)
    if os.environ.get('MONTAGE_QUEUE_ITEM') or cfg.get('delivery',{}).get('mode')=='workbench':
        from publish_assets import publish_zip,publication_text
        archive=publish_zip(video,job/'cover.png',meta,job/'delivery/发布包.zip')
        (job/'发布文案.txt').write_text(publication_text(meta),encoding='utf-8')
        record={'zip':str(archive.resolve()),'folder':None,'name':meta['title'],
                'files':3,'zipSha256':sha(archive),'videoSha256':report['sha256'],'topics':5,'mode':'workbench'}
        write(job/'delivery.json',record);return record
    person=cfg.get('person',{});base=safe_name(person.get('name') or person.get('socialMediaName') or '')+'_'+safe_name(title_text(plan))
    folder=job/'delivery'/base;folder.mkdir(parents=True,exist_ok=True)
    targets={base+'.mp4':video,base+'_封面.png':job/'cover.png',base+'_更换封面.html':job/'cover-editor.html'}
    for name,source in targets.items():shutil.copy2(source,folder/name)
    copy='标题：'+meta['title'].strip()+'\n\n描述：\n'+meta['description'].strip()+'\n\n话题：\n'+' '.join('#'+t for t in meta['topics'])+'\n'
    text=folder/(base+'_发布文案.txt');text.write_text(copy,encoding='utf-8-sig')
    expected=[*targets,text.name]
    archive=job/'delivery'/(base+'.zip');temp=archive.with_suffix('.zip.tmp')
    with zipfile.ZipFile(temp,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        for name in expected:z.write(folder/name,arcname=base+'/'+name)
    with zipfile.ZipFile(temp) as z:
        if z.testzip() or len(z.namelist())!=4:raise RuntimeError('压缩包完整性检查失败')
    temp.replace(archive)
    record={'zip':str(archive.resolve()),'folder':str(folder.resolve()),'name':base,'files':{n:sha(folder/n) for n in expected},'zipSha256':sha(archive),'videoSha256':report['sha256'],'topics':5}
    write(job/'delivery.json',record);return record
