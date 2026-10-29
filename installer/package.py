"""Package only versioned source files. Requires the private packaging venv."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]


def main():
    if subprocess.check_output(['git','-C',str(ROOT),'status','--porcelain']):
        raise SystemExit('Commit source changes before packaging.')
    commit=subprocess.check_output(['git','-C',str(ROOT),'rev-parse','HEAD'],text=True).strip()
    output=ROOT/'build/package'/commit
    stage=output/'sources'
    if stage.exists():raise SystemExit('Packaging staging already exists; use a new commit or inspect it.')
    for row in subprocess.check_output(['git','-C',str(ROOT),'ls-files','-z']).split(b'\0'):
        if not row:continue
        name=row.decode('utf-8')
        if name.startswith(('installer/','tools/','ports/','patches/')) or name in ('LICENSE','THIRD_PARTY_NOTICES.md'):
            dest=stage/name;dest.parent.mkdir(parents=True,exist_ok=True)
            dest.write_bytes(subprocess.check_output(['git','-C',str(ROOT),'show',commit+':'+name]))
    (stage/'installer/build.json').write_text(json.dumps({'commit':commit}),encoding='utf-8')
    name=json.loads((stage/'installer/game.json').read_text())['game']+'-Setup'
    subprocess.run([sys.executable,'-m','PyInstaller','--noconfirm','--clean','--onefile','--windowed',
        '--name',name,'--paths',str(stage),'--add-data',str(stage)+';.',
        '--distpath',str(output/'dist'),'--workpath',str(output/'work'),'--specpath',str(output),
        str(stage/'installer/setup_ui.py')],check=True,cwd=ROOT)
    exe=output/'dist'/(name+'.exe')
    (exe.with_suffix('.exe.sha256')).write_text(hashlib.sha256(exe.read_bytes()).hexdigest()+'  '+exe.name+'\n',encoding='ascii')
    print(exe)


if __name__=='__main__':main()
