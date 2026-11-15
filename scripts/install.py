"""Install/update from GitHub tags; user configuration and old engines stay outside the skill."""
import argparse,hashlib,json,os,re,shutil,subprocess,tempfile,sys
from pathlib import Path

def run(args):
    p=subprocess.run((['rtk','proxy'] if shutil.which('rtk') else [])+list(map(str,args)),capture_output=True,text=True,encoding="utf-8")
    if p.returncode:raise RuntimeError(p.stderr[-1500:])
    return p.stdout
def semver(tag):
    m=re.fullmatch(r'v?(\d+)\.(\d+)\.(\d+)',tag);return tuple(map(int,m.groups())) if m else None
def install(project,repository='https://github.com/cable5881/nursing-home-montage',version=None,replace_local=False):
    project=project.resolve();target=project/'.agents/skills/nursing-home-montage';private=project/'.montage';private.mkdir(parents=True,exist_ok=True)
    if not re.fullmatch(r'https://github.com/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+(?:\.git)?',repository):raise ValueError('使用GitHub仓库HTTPS地址。')
    tags=[line.split('refs/tags/',1)[1] for line in run(['git','ls-remote','--tags','--refs',repository]).splitlines()]
    stable=[t for t in tags if semver(t)]
    version=version or (max(stable,key=semver) if stable else None)
    if not version or version not in tags:raise ValueError('没有对应稳定版本tag，请指定仓库已经发布的版本。')
    if target.exists() and (target/'.git').exists() and not replace_local and run(['git','-C',target,'status','--porcelain']).strip():raise ValueError('技能代码有本地修改。请先保存/发布修改；项目配置无须迁移。')
    with tempfile.TemporaryDirectory(prefix='montage-install-') as tmp:
        source=Path(tmp)/'skill';run(['git','clone','--depth','1','--branch',version,repository,source])
        manifest=json.loads((source/'release.json').read_text(encoding='utf-8'))
        if manifest['config_schema']!=1:raise ValueError('此发行版需要配置迁移，保留原安装；请先执行发行版的迁移说明。')
        for name in ('SKILL.md','scripts/montage.py','scripts/project.py','preset.json'):
            if not (source/name).is_file():raise ValueError('发行包不完整')
        if (source/'.montage').exists():raise ValueError('发行包错误地包含用户配置')
        # Retain previous code before replacement; frozen jobs retain their own engines as well.
        backup=private/'install-backups'/('previous-'+os.urandom(6).hex())
        if target.exists():
            backup.parent.mkdir(parents=True,exist_ok=True);target.replace(backup)
        try:
            target.parent.mkdir(parents=True,exist_ok=True);shutil.copytree(source,target)
        except Exception:
            if target.exists():shutil.rmtree(target)
            if backup.exists():backup.replace(target)
            raise
    return {'installed':str(target),'version':version,'userConfigurationPreserved':True,'previousCode':str(backup) if backup.exists() else None}
def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--project',type=Path,default=Path.cwd());p.add_argument('--repository',default='https://github.com/cable5881/nursing-home-montage');p.add_argument('--version');p.add_argument('--replace-local',action='store_true');a=p.parse_args();print(json.dumps(install(a.project,a.repository,a.version,a.replace_local),ensure_ascii=False,indent=2))
if __name__=='__main__':
    if hasattr(sys.stdout,'reconfigure'):sys.stdout.reconfigure(encoding='utf-8')
    try:main()
    except Exception as e:print(json.dumps({'error':str(e)},ensure_ascii=False));sys.exit(1)
