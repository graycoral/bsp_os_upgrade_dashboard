"""Copyable full Agent Monitor source, with a byte manifest and no runtime data."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

FORMAT = 'agent-monitor-source-v1'
MANIFEST = 'AGENT_MONITOR_SOURCE.json'
ROOT = Path(__file__).resolve().parents[2]
ROOTS = ('backend','scripts','apps/web','apps/gui-test','apps/board-connector','apps/agent-monitor',
         'packages','workflow_diagram','config/examples','contracts','examples','tests')
TOP = ('requirements.lock','pyproject.toml','run.sh','board-connector.cmd','README.md','AGENTS.md','CLAUDE.md')
EXCLUDE = {'node_modules','.venv','__pycache__','.pytest_cache','.git','dist','static','playwright-report','test-results','runtime','.runtime','.local-reports','logs','log','.ssh','credentials','secrets','.build','.cache','.mypy_cache','.ruff_cache','.tox','.nox'}
SOURCE_SUFFIXES = {'.py','.pyi','.json','.ts','.tsx','.js','.jsx','.mjs','.cjs','.css','.html','.md','.txt','.toml','.lock','.sh','.cmd','.ps1','.svg','.png','.jpg','.yml','.yaml','.csv','.ini','.cfg','.spec'}


def sha(data): return hashlib.sha256(data).hexdigest()


def relative(name):
    path = Path(name)
    if path.is_absolute() or not name or '\\' in name or '..' in path.parts or ':' in name:
        raise ValueError('Unsafe source path')
    return path


def source_files(source, include_ui=True):
    source = Path(source).resolve()
    manifest = source / MANIFEST
    if manifest.is_file():
        value = verify(source)
        return {name:(source/relative(name)).read_bytes() for name in value['files']
                if include_ui or not name.startswith(('apps/web/dist/','apps/gui-test/static/'))}
    names = set(name for name in TOP if (source/name).is_file())
    for root in ROOTS:
        folder = source / root
        if not folder.is_dir(): continue
        for p in folder.rglob('*'):
            if p.is_symlink():
                if not any(part in EXCLUDE for part in p.relative_to(folder).parts):
                    raise ValueError('Source symlinks are not supported: '+str(p))
                continue
            rel = p.relative_to(source)
            if (p.is_file() and not any(part in EXCLUDE for part in p.relative_to(folder).parts)
                    and p.suffix in SOURCE_SUFFIXES
                    and '.local.' not in p.name and not p.name.startswith('.env')):
                names.add(rel.as_posix())
    for folder in ('docs/design','docs/agents','docs/roles','docs/requirements','docs/porting','docs/gui_test','.claude/agents'):
        names.update(p.relative_to(source).as_posix() for p in (source/folder).rglob('*.md') if p.is_file() and not p.is_symlink())
    if include_ui:
        if not (source/'apps/web/dist/index.html').is_file():
            raise ValueError('Build Agent Monitor UI before source export; recipients use the prebuilt assets.')
        for root in ('apps/web/dist','apps/gui-test/static'):
            names.update(p.relative_to(source).as_posix() for p in (source/root).rglob('*') if p.is_file() and not p.is_symlink())
    return {name:(source/relative(name)).read_bytes() for name in sorted(names)}


def verify(root):
    root = Path(root).resolve()
    value = json.loads((root/MANIFEST).read_text())
    if value.get('format') != FORMAT or not isinstance(value.get('files'), dict):
        raise ValueError('Unsupported source manifest')
    if value.get('release') != sha(json.dumps(value['files'],sort_keys=True).encode()):
        raise ValueError('Source release integrity mismatch')
    for name, checksum in value['files'].items():
        path = root / relative(name)
        if any(p.is_symlink() for p in [path,*path.parents] if p!=root.parent) or not path.is_file() or sha(path.read_bytes()) != checksum:
            raise ValueError('Source integrity mismatch: '+name)
    return value


def export(source, destination, include_ui=True):
    source, destination = Path(source).resolve(), Path(destination).resolve()
    if destination == source or source.is_relative_to(destination):
        raise ValueError('Destination must not contain source')
    if destination.exists() and any(destination.iterdir()):
        raise ValueError('Use a new or empty delivery directory')
    files=source_files(source,include_ui)
    if not all(name in files for name in ('backend/api/main.py','backend/worker/main.py','scripts/setup_runtime.py','apps/agent-monitor/manage.py','board-connector.cmd')):
        raise ValueError('Full monitor/connector dependency closure is incomplete')
    destination.mkdir(parents=True,exist_ok=True)
    for name,data in files.items():
        path=destination/relative(name);path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(data)
        if path.suffix=='.sh': path.chmod(0o755)
    try:
        head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=source,stderr=subprocess.DEVNULL,text=True).strip()
    except (OSError,subprocess.CalledProcessError): head=None
    hashes={name:sha(data) for name,data in files.items()}
    value={'format':FORMAT,'source_head':head,'files':hashes,'release':sha(json.dumps(hashes,sort_keys=True).encode()),
           'include_ui':include_ui,'entrypoint':'apps/agent-monitor/manage.py','company_acceptance':'NOT_RUN'}
    (destination/MANIFEST).write_text(json.dumps(value,indent=2)+'\n')
    return value


if __name__=='__main__':
    parser=argparse.ArgumentParser(description='Export full Agent Monitor and matching connector sources')
    parser.add_argument('--source',type=Path,default=ROOT);parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--without-ui',action='store_true');args=parser.parse_args()
    result=export(args.source,args.output,not args.without_ui)
    print(json.dumps({'output':str(args.output),'release':result['release'],'files':len(result['files'])}))
