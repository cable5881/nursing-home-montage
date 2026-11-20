"""Project-private, content-addressed material and artifact reuse.

Cache entries own their files. They never point into disposable video jobs.
All consumers verify hashes and copy artifacts into their own job before using them.
"""
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import sys
import uuid

VERSION = 1


def file_hash(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def key_for(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


@contextmanager
def file_lock(path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('a+b') as stream:
        if sys.platform == 'win32':
            import msvcrt
            stream.write(b'0'); stream.flush(); stream.seek(0)
            msvcrt.locking(stream.fileno(), msvcrt.LK_LOCK, 1)
        else:
            import fcntl
            fcntl.flock(stream.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            if sys.platform == 'win32':
                stream.seek(0); msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(stream.fileno(), fcntl.LOCK_UN)


class SharedCache:
    def __init__(self, project):
        self.root = Path(project).resolve() / '.montage/cache/v1'

    def path(self, namespace, key):
        if not re.fullmatch(r'[a-z][a-z0-9-]{0,40}', namespace) or not re.fullmatch(r'[a-f0-9]{64}', key):
            raise ValueError('Invalid cache identity')
        return self.root / namespace / key

    def read(self, namespace, key):
        directory = self.path(namespace, key)
        try:
            record = json.loads((directory / 'entry.json').read_text())
            body = record['body']
            if record['sha256'] != key_for(body):
                return None
            for item in body.get('files', {}).values():
                path = directory / item['name']
                if path.is_symlink() or path.parent != directory or file_hash(path) != item['sha256']:
                    return None
            return body
        except (OSError, ValueError, KeyError, TypeError):
            return None

    def _store(self, namespace, key, data, files=None):
        directory = self.path(namespace, key)
        directory.parent.mkdir(parents=True, exist_ok=True)
        temp = directory.with_name('.' + key + '-' + uuid.uuid4().hex)
        temp.mkdir(mode=0o700)
        try:
            copied = {}
            for i, (label, source) in enumerate((files or {}).items()):
                source = Path(source)
                name = str(i) + source.suffix.lower()
                shutil.copy2(source, temp / name)
                copied[label] = {'name': name, 'sha256': file_hash(temp / name)}
            body = {'version': VERSION, 'data': data, 'files': copied}
            (temp / 'entry.json').write_text(json.dumps({'body': body, 'sha256': key_for(body)}, ensure_ascii=False))
            if directory.exists():
                # Only replace a corrupt/incomplete entry in this private cache.
                old = directory.with_name('.invalid-' + uuid.uuid4().hex)
                directory.rename(old)
                shutil.rmtree(old)
            temp.rename(directory)
            return body
        finally:
            if temp.exists(): shutil.rmtree(temp)

    def memo(self, namespace, key, producer):
        directory = self.path(namespace, key)
        with file_lock(directory.with_suffix('.lock')):
            value = self.read(namespace, key)
            if value is not None:
                return value['data'], True
            data = producer()
            self._store(namespace, key, data)
            return data, False

    def _reference(self, namespace, key, owner):
        if owner is None: return
        path=self.root/'refs'/namespace/(key+'.json')
        path.parent.mkdir(parents=True,exist_ok=True)
        try: owners=json.loads(path.read_text())
        except (OSError,ValueError): owners=[]
        owner=str(Path(owner).resolve())
        if owner not in owners: owners.append(owner)
        temp=path.with_suffix('.tmp');temp.write_text(json.dumps(owners));temp.replace(path)

    def store_files(self, namespace, key, files, metadata=None, owner=None):
        directory = self.path(namespace, key)
        with file_lock(directory.with_suffix('.lock')):
            existing = self.read(namespace, key)
            if existing is None: existing=self._store(namespace, key, metadata or {}, files)
            self._reference(namespace,key,owner)
            return existing

    def restore_files(self, namespace, key, destinations, owner=None):
        directory = self.path(namespace, key)
        with file_lock(directory.with_suffix('.lock')):
            body = self.read(namespace, key)
            if body is None or not set(destinations).issubset(body['files']):
                return None
            for label, target in destinations.items():
                target = Path(target)
                target.parent.mkdir(parents=True, exist_ok=True)
                source = directory / body['files'][label]['name']
                temp = target.with_name(target.name + '.' + uuid.uuid4().hex + '.tmp')
                try:
                    shutil.copy2(source, temp)
                    temp.replace(target)
                finally:
                    temp.unlink(missing_ok=True)
            self._reference(namespace,key,owner)
            return body['data']

    def share_immutable(self, source, target, owner, namespace='font-sources'):
        """Use a verified, project-owned snapshot for a read-only input."""
        source,target=Path(source),Path(target)
        key=key_for({'sha256':file_hash(source),'suffix':source.suffix.lower()})
        self.store_files(namespace,key,{'asset':source},owner=owner)
        directory=self.path(namespace,key)
        with file_lock(directory.with_suffix('.lock')):
            entry=self.read(namespace,key)
            if entry is None:raise ValueError('共享文件校验未通过')
            item = entry['files'].get('asset') or entry['files']['font']
            cached=directory/item['name']
            target.parent.mkdir(parents=True,exist_ok=True)
            temp=target.with_name(target.name+'.'+uuid.uuid4().hex+'.tmp')
            try:
                if os.name=='nt':shutil.copy2(cached,temp)
                else:
                    cached.chmod(0o400)
                    try:os.link(cached,temp)
                    except OSError:shutil.copyfile(cached,temp)
                temp.replace(target)
            finally:temp.unlink(missing_ok=True)
        return {'key':key,'shared':str(cached)}

    def release_owners(self, owners):
        """Called only after the user accepts cleanup. Never follows job links."""
        owners={str(Path(p).resolve()) for p in owners};released=0
        for namespace in ('voice','avatar','cutout','font-sources','assets'):
            for path in (self.root/'refs'/namespace).glob('*.json'):
                key=path.stem
                directory=self.path(namespace,key)
                with file_lock(directory.with_suffix('.lock')):
                    references=json.loads(path.read_text())
                    remaining=[p for p in references if p not in owners]
                    if remaining==references: continue
                    if remaining:
                        temp=path.with_suffix('.tmp');temp.write_text(json.dumps(remaining));temp.replace(path)
                    else:
                        if directory.exists():
                            released+=sum(p.stat().st_size for p in directory.rglob('*') if p.is_file())
                            shutil.rmtree(directory)
                        path.unlink(missing_ok=True)
        return released

    def material(self, path, analyzer, version):
        path = Path(path)
        content_hash = file_hash(path)
        key = key_for({'content': content_hash, 'suffix': path.suffix.lower(), 'analyzer': version})
        value, hit = self.memo('materials', key, lambda: analyzer(path))
        return value, hit, content_hash


def install_dependencies(project, job, template, run):
    """Install one pinned dependency tree per lockfile/platform, then share it."""
    import platform
    node=run(['node','--version']).stdout.strip()
    key=key_for({'lock':file_hash(template/'package-lock.json'),'package':file_hash(template/'package.json'),
                 'platform':sys.platform,'arch':platform.machine(),'node':node})
    pool=SharedCache(project).path('dependencies',key)
    with file_lock(pool.with_suffix('.lock')):
        marker=pool/'installed.json'
        if not marker.is_file() or not (pool/'node_modules').is_dir():
            pool.mkdir(parents=True,exist_ok=True)
            for name in ('package.json','package-lock.json'):shutil.copy2(template/name,pool/name)
            run(['npm','ci','--ignore-scripts','--no-audit','--no-fund'],cwd=pool)
            marker.write_text(json.dumps({'key':key,'lock':file_hash(pool/'package-lock.json')}))
        elif json.loads(marker.read_text()).get('lock')!=file_hash(pool/'package-lock.json'):
            raise RuntimeError('Shared dependency lock changed; refusing reuse')
        destination=job/'node_modules'
        if destination.is_symlink():
            if destination.resolve()!=(pool/'node_modules').resolve():destination.unlink()
        elif destination.exists():
            # Preserve existing isolated dependency directories; npm validates them
            # once rather than deleting or linking over a user-owned directory.
            receipt=job/'dependencies-cache.json'
            if not receipt.is_file() or json.loads(receipt.read_text()).get('key')!=key:
                run(['npm','ci','--ignore-scripts','--no-audit','--no-fund'],cwd=job)
        if not destination.exists():
            try:destination.symlink_to(pool/'node_modules',target_is_directory=True)
            except OSError:shutil.copytree(pool/'node_modules',destination)
        (job/'dependencies-cache.json').write_text(json.dumps({'key':key,'shared':str(pool)}))
    return {'key':key,'shared':str(pool)}
