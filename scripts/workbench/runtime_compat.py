"""Run an installed skill entry with idempotent mkdir in desktop filesystem shims."""
from pathlib import Path
import runpy
import sys
import re
import shutil
import subprocess

def install():
    original=Path.mkdir
    if getattr(original,'_montage_idempotent',False):return
    def mkdir(self,mode=0o777,parents=False,exist_ok=False):
        if exist_ok and self.is_dir():return
        try:return original(self,mode=mode,parents=parents,exist_ok=exist_ok)
        except FileExistsError:
            if not(exist_ok and self.is_dir()):raise
    mkdir._montage_idempotent=True
    Path.mkdir=mkdir


if __name__=='__main__':
    if len(sys.argv)<2:raise SystemExit('需要已安装 skill 的 Python 入口路径')
    inside=sys.argv[1]=='--in-env'
    args=sys.argv[2:] if inside else sys.argv[1:]
    if not args:raise SystemExit('缺少 Python 入口')
    entry=Path(args[0]).resolve()
    # Keep the target script's declared environment; system Python may lack its deps.
    metadata=re.search(r'^# /// script\n(.*?)^# ///',entry.read_text(encoding='utf-8'),re.M|re.S)
    if metadata and not inside:
        import tomllib
        config=tomllib.loads('\n'.join(line.removeprefix('#').removeprefix(' ') for line in metadata[1].splitlines()))
        uv=shutil.which('uv')
        if not uv:raise SystemExit('制作入口需要 uv 和 Python 3.11，请先按 skill 运行规范准备环境')
        command=[uv,'run','--no-project','--python','3.11']
        for dependency in config.get('dependencies',[]):command+=['--with',dependency]
        command += [str(Path(__file__).resolve()),'--in-env',str(entry),*args[1:]]
        if shutil.which('rtk'):command=['rtk','proxy',*command]
        raise SystemExit(subprocess.run(command).returncode)
    install()
    sys.argv=[str(entry),*args[1:]];sys.path.insert(0,str(entry.parent))
    runpy.run_path(str(entry),run_name='__main__')
