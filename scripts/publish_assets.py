"""The workbench's single three-file archive, without a staging media copy."""
import hashlib
import json
import os
import shutil
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


def file_digest(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def link_or_copy(source, target):
    """Materialize a stable, read-only input or a finished product atomically."""
    source, target = Path(source), Path(target)
    if source == target:
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    temp = target.with_name('.' + target.name + '.' + uuid.uuid4().hex)
    try:
        try:
            os.link(source, temp)
        except OSError:
            shutil.copyfile(source, temp)
        temp.replace(target)
    finally:
        temp.unlink(missing_ok=True)


def write_publication(path, text):
    path = Path(path)
    temp = path.with_name('.' + path.name + '.' + uuid.uuid4().hex)
    try:
        temp.write_text(text, encoding='utf-8')
        temp.replace(path)
    finally:
        temp.unlink(missing_ok=True)


def workspace_product(job, output, publication, verified_hash):
    job, output = Path(job), Path(output)
    if output.resolve() != output.absolute():
        raise ValueError('交付产物目录不能经过链接')
    output.mkdir(parents=True, exist_ok=True)
    video, cover = job/'final.mp4', job/'cover.png'
    if not video.is_file() or file_digest(video) != verified_hash or not cover.is_file():
        raise ValueError('交付源文件缺失或与核验记录不一致')
    for source, target in ((video, output/'final.mp4'), (cover, output/'cover.png')):
        link_or_copy(source, target)
    write_publication(output/'发布文案.txt', publication_text(publication))
    return {'mode': 'workspace', 'folder': str(output), 'files': 3,
            'name': publication['title'], 'videoSha256': verified_hash}


def workspace_zip(stream, folder, title):
    """Build a ZIP on request. MP4 and PNG already contain compressed data."""
    safe = re.sub(r'[^\w\-\u3400-\u9fff（）()]', '_', title or '养老院探访')[:70]
    with zipfile.ZipFile(stream, 'w', zipfile.ZIP_STORED) as archive:
        for name, arcname in (('final.mp4', safe+'.mp4'), ('cover.png', safe+'_封面.png'),
                              ('发布文案.txt', safe+'_发布文案.txt')):
            archive.write(Path(folder)/name, arcname)
