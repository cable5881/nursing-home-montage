"""The workbench's single three-file archive, without a staging media copy."""
import json
from pathlib import Path
import re
import uuid
import zipfile


def publication_text(value):
    return str(value.get('title') or '养老院探访')+'\n\n'+str(value.get('description',''))+'\n\n'+' '.join('#'+str(x).lstrip('#') for x in value.get('topics',[]))


def publish_zip(video, cover, publication, target):
    video,target=Path(video).resolve(),Path(target)
    cover=Path(cover) if cover else None
    target.parent.mkdir(parents=True,exist_ok=True)
    text=publication_text(publication)
    safe=re.sub(r'[^\w\-\u3400-\u9fff（）()]','_',str(publication.get('title') or '养老院探访'))[:70]
    fingerprint={'video':str(video),'videoMtime':video.stat().st_mtime_ns,
        'coverMtime':cover.stat().st_mtime_ns if cover and cover.is_file() else None,'publication':text}
    manifest=target.with_suffix('.json')
    try:previous=json.loads(manifest.read_text())
    except (OSError,ValueError):previous=None
    if target.is_file() and previous==fingerprint:return target
    temp=target.with_name(target.name+'.'+uuid.uuid4().hex+'.tmp')
    try:
        with zipfile.ZipFile(temp,'w',zipfile.ZIP_DEFLATED,compresslevel=1) as archive:
            archive.write(video,safe+'.mp4')
            if cover and cover.is_file():archive.write(cover,safe+'_封面.png')
            archive.writestr(safe+'_发布文案.txt',text)
        with zipfile.ZipFile(temp) as archive:
            if archive.testzip():raise ValueError('发布包完整性检查失败')
        temp.replace(target)
        manifest.write_text(json.dumps(fingerprint,ensure_ascii=False,indent=2)+'\n')
    finally:temp.unlink(missing_ok=True)
    return target
