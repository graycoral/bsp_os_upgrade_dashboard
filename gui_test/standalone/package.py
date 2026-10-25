"""Build a company import ZIP from a fixed allowlist; never include runtime/private files."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import zipfile

ROOT=Path(__file__).resolve().parents[2]
HOOKS=['backend/api/main.py','backend/domain/engine.py','backend/worker/main.py',
       'apps/web/src/main.tsx','apps/web/package.json','apps/web/tsconfig.json','apps/web/vite.config.ts','pyproject.toml']


def main():
    p=argparse.ArgumentParser();p.add_argument('--base',required=True);p.add_argument('--wheelhouse');p.add_argument('--wheels');p.add_argument('--output',default='.local-reports/gui-test-company.zip');args=p.parse_args()
    output=Path(args.output).resolve();output.parent.mkdir(parents=True,exist_ok=True)
    package=ROOT/'gui_test'
    if not (package/'static/index.html').is_file():raise SystemExit('Build standalone UI before packaging: npm run build:gui-test')
    # git diff includes both committed and working-tree hook changes relative to the reviewed base.
    patch=subprocess.check_output(['git','diff','--binary',args.base,'--',*HOOKS],cwd=ROOT)
    names={}
    for path in package.rglob('*'):
        rel=path.relative_to(package)
        if not path.is_file() or path.is_symlink():continue
        if any(part.startswith('.') or part in {'__pycache__','node_modules','build','dist'} or part.endswith('.egg-info') for part in rel.parts):continue
        if path.suffix not in {'.py','.md','.toml','.json','.ps1','.tsx','.css','.html','.js','.lock'}:continue
        if path.name.endswith('.local.json'):continue
        names['gui_test/'+rel.as_posix()]=path.read_bytes()
    names['dashboard-integration.patch']=patch
    names['INSTALL.md']=(package/'README.md').read_bytes()
    for folder,label in [(args.wheelhouse,'wheelhouse'),(args.wheels,'wheels')]:
        if folder:
            for wheel in sorted(Path(folder).glob('*.whl')):names[label+'/'+wheel.name]=wheel.read_bytes()
    manifest={name:hashlib.sha256(content).hexdigest() for name,content in sorted(names.items())}
    names['SHA256SUMS.json']=(json.dumps(manifest,indent=2)+'\n').encode()
    with zipfile.ZipFile(output,'w',zipfile.ZIP_DEFLATED) as z:
        for name,data in sorted(names.items()):z.writestr(name,data)
    print(json.dumps({'file':str(output),'files':len(names),'bytes':output.stat().st_size,'sha256':hashlib.sha256(output.read_bytes()).hexdigest()}))


if __name__=='__main__':main()
