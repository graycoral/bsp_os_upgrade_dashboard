"""Copyable full Agent Monitor source, with a byte manifest and no runtime data."""
import argparse
import hashlib
from html.parser import HTMLParser
import json
from pathlib import Path
import subprocess
from urllib.parse import unquote, urlsplit

FORMAT = 'agent-monitor-source-v1'
MANIFEST = 'AGENT_MONITOR_SOURCE.json'
ROOT = Path(__file__).resolve().parents[2]
ROOTS = ('backend','scripts','apps/web','apps/gui-test','apps/board-connector','apps/agent-monitor',
         'packaging','packages','workflow_diagram','config/examples','contracts','examples','tests')
TOP = ('requirements.lock','pyproject.toml','run.sh','board-connector.bat','board-connector.cmd','README.md','AGENTS.md','CLAUDE.md')
PORTING_EVIDENCE = ('docs/testing/runs/20261129-monitor-activation.md',
                    'docs/testing/runs/20261129-multi-plugin-ownership.md')
EXCLUDE = {'node_modules','.venv','__pycache__','.pytest_cache','.git','dist','static','playwright-report','test-results','runtime','.runtime','.local-reports','logs','log','.ssh','credentials','secrets','.build','.cache','.mypy_cache','.ruff_cache','.tox','.nox','.omo','.opencode','.codex'}
UI_ROOTS = ('apps/web/dist', 'apps/gui-test/static')
REQUIRED = ('backend/api/main.py', 'backend/worker/main.py', 'scripts/setup_runtime.py',
            'apps/agent-monitor/manage.py', 'board-connector.cmd')
MONITOR_PORT_HELPER = 'backend/gui_test/core/connector_port.py'
CLI_CONTRACT = 'contracts/plugin-cli-v1.json'
SOURCE_SUFFIXES = {'.py','.pyi','.json','.ts','.tsx','.js','.jsx','.mjs','.cjs','.css','.html','.md','.txt','.toml','.lock','.sh','.bat','.cmd','.ps1','.svg','.png','.jpg','.yml','.yaml','.csv','.ini','.cfg','.spec'}


def sha(data): return hashlib.sha256(data).hexdigest()


def release_id(hashes):
    return sha(json.dumps(hashes, sort_keys=True).encode())


def relative(name):
    path = Path(name)
    if path.is_absolute() or not name or path.as_posix() != name or '\\' in name or '..' in path.parts or ':' in name:
        raise ValueError('Unsafe source path')
    return path


class AssetReferences(HTMLParser):
    def __init__(self):
        super().__init__()
        self.references = []
        self.modules = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == 'script' and attrs.get('src'):
            self.references.append(attrs['src'])
            if attrs.get('type') == 'module':
                self.modules.append(attrs['src'])
        if tag == 'link' and attrs.get('href'):
            rel = (attrs.get('rel') or '').lower().split()
            if set(rel).intersection({'stylesheet', 'modulepreload', 'preload', 'icon'}):
                self.references.append(attrs['href'])


def validate_ui(names, read):
    for root in UI_ROOTS:
        index = f'{root}/index.html'
        if index not in names:
            raise ValueError(f'Build both UIs before full source export. Missing UI index: {index}')
        parser = AssetReferences()
        parser.feed(read(index).decode('utf-8'))
        if not parser.modules:
            raise ValueError(f'UI index lacks a built module script: {index}')
        for ref in parser.references:
            url = urlsplit(ref)
            path = unquote(url.path).lstrip('/').removeprefix('./')
            if url.scheme or url.netloc or not path:
                raise ValueError(f'UI index must refer to bundled assets: {index}: {ref}')
            name = f'{root}/{relative(path).as_posix()}'
            if name not in names or not read(name):
                raise ValueError(f'Missing or empty UI asset: {name}')


def git_provenance(source):
    if not (source / '.git').exists():
        return None, None
    def git(*args):
        return subprocess.check_output(['git', *args], cwd=source, stderr=subprocess.DEVNULL, text=True).strip()
    try:
        return git('rev-parse', 'HEAD'), bool(git('status', '--porcelain', '--untracked-files=all'))
    except (OSError, subprocess.CalledProcessError):
        return None, None


def source_files(source, include_ui=True):
    source = Path(source).resolve()
    manifest = source / MANIFEST
    if manifest.is_file():
        value = verify(source, require_current_ui=include_ui)
        return {name:(source/relative(name)).read_bytes() for name in value['files']
                if include_ui or not name.startswith(('apps/web/dist/','apps/gui-test/static/'))}
    names = {name for name in TOP if (source / name).is_file()}
    names.update(name for name in PORTING_EVIDENCE if (source / name).is_file() and not (source / name).is_symlink())
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
        for root in UI_ROOTS:
            names.update(p.relative_to(source).as_posix() for p in (source/root).rglob('*') if p.is_file() and not p.is_symlink())
    return {name:(source/relative(name)).read_bytes() for name in sorted(names)}


def check_activation_dependency(files, read_file):
    if MONITOR_PORT_HELPER in files:
        return
    contract = json.loads(read_file(CLI_CONTRACT)) if CLI_CONTRACT in files else {}
    if 'monitor ensure' in contract.get('commands', {}):
        raise ValueError('Monitor activation dependency missing: ' + MONITOR_PORT_HELPER)


def verify(root, *, require_current_ui=True):
    root = Path(root).resolve()
    manifest = root / MANIFEST
    if manifest.is_symlink():
        raise ValueError('Source manifest must be a regular file')
    value = json.loads(manifest.read_text())
    if (not isinstance(value, dict) or value.get('format') != FORMAT or not isinstance(value.get('files'), dict)
            or type(value.get('include_ui')) is not bool):
        raise ValueError('Unsupported source manifest')
    if value.get('release') != release_id(value['files']):
        raise ValueError('Source release integrity mismatch')
    for name, checksum in value['files'].items():
        path = root / relative(name)
        if any(p.is_symlink() for p in [path,*path.parents] if p!=root.parent) or not path.is_file() or sha(path.read_bytes()) != checksum:
            raise ValueError('Source integrity mismatch: '+name)
    check_activation_dependency(value['files'], lambda name: (root / name).read_bytes())
    if require_current_ui and value['include_ui']:
        validate_ui(value['files'], lambda name: (root / name).read_bytes())
    return value


def export(source, destination, include_ui=True, *, without_agent_instructions=False):
    source, destination = Path(source).resolve(), Path(destination).resolve()
    if destination == source or source.is_relative_to(destination):
        raise ValueError('Destination must not contain source')
    if destination.exists() and any(destination.iterdir()):
        raise ValueError('Use a new or empty delivery directory')
    files=source_files(source,include_ui)
    if without_agent_instructions:
        files = {name: data for name, data in files.items()
                 if Path(name).name.casefold() not in {'agents.md', 'claude.md'}
                 and '/.claude/agents/' not in '/' + name.casefold()}
    if not all(name in files for name in REQUIRED):
        raise ValueError('Full monitor/connector dependency closure is incomplete')
    check_activation_dependency(files, files.__getitem__)
    if include_ui:
        validate_ui(files, files.__getitem__)
    origin = verify(source, require_current_ui=include_ui) if (source / MANIFEST).is_file() else None
    head, dirty = (origin.get('source_head'), origin.get('source_dirty')) if origin else git_provenance(source)
    destination.mkdir(parents=True,exist_ok=True)
    for name,data in files.items():
        path=destination/relative(name);path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(data)
        if path.suffix=='.sh': path.chmod(0o755)
    hashes={name:sha(data) for name,data in files.items()}
    value={'format':FORMAT,'source_head':head,'source_dirty':dirty,'files':hashes,'release':release_id(hashes),
           'include_ui':include_ui,'entrypoint':'apps/agent-monitor/manage.py','company_acceptance':'NOT_RUN'}
    (destination/MANIFEST).write_text(json.dumps(value,indent=2)+'\n')
    return value


if __name__=='__main__':
    parser=argparse.ArgumentParser(description='Export full Agent Monitor and matching connector sources')
    parser.add_argument('--source',type=Path,default=ROOT);parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--without-ui',action='store_true');args=parser.parse_args()
    result=export(args.source,args.output,not args.without_ui)
    print(json.dumps({'output':str(args.output),'release':result['release'],'files':len(result['files'])}))
