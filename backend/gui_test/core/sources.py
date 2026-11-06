"""Persist source selection and prepare immutable, portable execution snapshots."""
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
from urllib.parse import urlsplit

from .discovery import discover
from .models import TestError, now, uid
from ..execution.source import EXCLUDED, read_source, source_path
from ..execution.source_snapshots import manifest, publish, load_manifest, checked_files, file_manifest

LEGACY = {'version': 0, 'active': {'kind': 'legacy', 'location': '', 'ref': None, 'commit': None,
          'inspection_id': None, 'snapshot_id': None, 'source_revision': None}}


class SourceService:
    def __init__(self, store, runtime=None):
        self.store = store
        self.root = source_path(runtime or store.path.parent / 'source-storage').resolve()
        self.snapshots = self.root / 'snapshots'

    def state(self, connection=None):
        if connection is None:
            with self.store.connection() as c:
                return self.state(c)
        row = connection.execute("SELECT data FROM documents WHERE kind='source-state' AND name='active'").fetchone()
        return json.loads(row[0]) if row else json.loads(json.dumps(LEGACY))

    @staticmethod
    def git(root, *args):
        # No inherited Git executable/config/path overrides or interactive credential prompts.
        env = {k: v for k, v in os.environ.items() if not k.upper().startswith('GIT_')}
        # The service account's ordinary global credential helper remains usable;
        # supplied URLs never contain HTTPS userinfo/passwords and cannot prompt.
        env.update(GIT_TERMINAL_PROMPT='0', GIT_CONFIG_NOSYSTEM='1',
                   GIT_SSH_COMMAND='ssh -oBatchMode=yes -oStrictHostKeyChecking=yes -oConnectTimeout=10')
        command = ['git', '-c', 'core.hooksPath=' + os.devnull, '-c', 'core.longpaths=true', '-c', 'protocol.file.allow=never',
                   '-c', 'protocol.ext.allow=never', '-c', 'protocol.http.allow=never',
                   '-c', 'credential.interactive=false', '-C', str(root), *args]
        try:
            with tempfile.TemporaryFile() as out, tempfile.TemporaryFile() as err:
                result = subprocess.run(command, stdout=out, stderr=err, stdin=subprocess.DEVNULL,
                                        env=env, timeout=60, shell=False)
                if result.returncode:
                    raise TestError('Git source could not be read; verify access and repository configuration', 'SOURCE_GIT_FAILED', 422)
                if out.tell() > 32 * 1024 * 1024:
                    raise TestError('Git source output exceeds limit', 'SOURCE_LIMIT', 422)
                out.seek(0)
                return out.read()
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise TestError('Git source is unavailable or timed out', 'SOURCE_GIT_FAILED', 422) from exc

    @staticmethod
    def location(kind, location):
        if not isinstance(location, str) or not location.strip() or len(location) > 2048 or any(ord(c) < 32 for c in location):
            raise TestError('Enter a valid source location', status=422)
        location = location.strip()
        if kind == 'server-folder':
            path = Path(location)
            if not path.is_absolute() or path.is_symlink():
                raise TestError('Source must be an absolute server folder without links', 'SOURCE_UNSAFE', 422)
            try:
                resolved = path.resolve(strict=True)
                if not resolved.is_dir() or any(parent.is_symlink() or (getattr(parent.lstat(), 'st_file_attributes', 0) & 0x400)
                                                for parent in [path, *path.parents]):
                    raise ValueError()
                return str(resolved)
            except (OSError, ValueError) as exc:
                raise TestError('Server source folder is unavailable', 'SOURCE_NOT_FOUND', 422) from exc
        if kind != 'git-url':
            raise TestError('Choose server-folder or git-url', status=422)
        try:
            parsed = urlsplit(location)
            # SSH login names are repository identities; passwords and HTTPS userinfo are forbidden.
            if parsed.scheme not in {'https', 'ssh'} or not parsed.hostname or parsed.password or (parsed.scheme == 'https' and parsed.username) or parsed.query or parsed.fragment or not parsed.path or parsed.path == '/' or parsed.port == 0:
                raise ValueError()
            if parsed.username and not re.fullmatch(r'[A-Za-z0-9_.-]+', parsed.username):
                raise ValueError()
        except ValueError as exc:
            raise TestError('Use an HTTPS or SSH clone URL without embedded credentials', 'SOURCE_URL_INVALID', 422) from exc
        return location

    def inspect(self, kind, location):
        if kind == 'legacy':
            if location != '':
                raise TestError('Legacy source location must be empty', status=422)
        else:
            location = self.location(kind, location)
        refs, default_ref, repository = [], None, kind == 'git-url'
        private = {}
        if kind == 'legacy':
            rows = []
        elif kind == 'server-folder':
            # A .git marker or enclosing work tree means committed tree semantics.
            try:
                repository = self.git(location, 'rev-parse', '--is-inside-work-tree').strip() == b'true'
                bare = not repository and self.git(location, 'rev-parse', '--is-bare-repository').strip() == b'true'
                repository = repository or bare
            except TestError:
                if (Path(location) / '.git').exists():
                    raise
                repository = False
                bare = False
            if repository:
                top = location if bare else self.git(location, 'rev-parse', '--show-toplevel').decode().strip()
                private = {'_repository_root': str(Path(top).resolve()),
                           '_prefix': Path(location).relative_to(Path(top).resolve()).as_posix()}
                if private['_prefix'] == '.':
                    private['_prefix'] = ''
                rows = self.git(location, 'for-each-ref', '--format=%(objectname) %(refname)', 'refs/heads/').decode().splitlines()
                try:
                    default_ref = self.git(location, 'symbolic-ref', '--quiet', 'HEAD').decode().strip()
                except TestError:
                    pass
            else:
                file_manifest(read_source(location))
                rows = []
        else:
            self.root.mkdir(parents=True, exist_ok=True)
            rows = self.git(self.root, 'ls-remote', '--heads', '--', location).decode().splitlines()
            head = self.git(self.root, 'ls-remote', '--symref', '--', location, 'HEAD').decode().splitlines()
            default_ref = next((r.split()[1] for r in head if r.startswith('ref: ') and r.endswith('\tHEAD')), None)
        for row in rows:
            parts = row.split()
            if len(parts) != 2 or not re.fullmatch(r'[a-f0-9]{40}|[a-f0-9]{64}', parts[0]) or not parts[1].startswith('refs/heads/'):
                raise TestError('Invalid Git branch response', 'SOURCE_GIT_FAILED', 422)
            refs.append({'name': parts[1][11:], 'ref': parts[1], 'commit': parts[0]})
        refs.sort(key=lambda row: row['name'])
        if repository and not refs:
            raise TestError('Git source has no committed branches', 'SOURCE_EMPTY', 422)
        if default_ref not in {r['ref'] for r in refs}:
            default_ref = refs[0]['ref'] if refs else None
        item = {'inspection_id': uid(), 'kind': kind, 'location': location, 'repository': repository,
                'refs': refs, 'default_ref': default_ref, 'inspected_at': now()}
        with self.store.transaction() as c:
            c.execute('INSERT INTO documents VALUES(?,?,?)', ('source-inspection', item['inspection_id'], json.dumps(item | private)))
        return item

    def git_files(self, root, commit, prefix=''):
        records = self.git(root, 'ls-tree', '-rz', '--full-tree', commit, *(['--', prefix + '/'] if prefix else [])).split(b'\x00')
        files, total = {}, 0
        for record in records:
            if not record:
                continue
            info, raw_name = record.split(b'\t', 1)
            mode, kind, blob = info.decode('ascii').split()
            name = raw_name.decode('utf-8')
            if prefix:
                if not name.startswith(prefix + '/'):
                    raise TestError('Git subtree path mismatch', 'SOURCE_UNSAFE', 422)
                name = name[len(prefix) + 1:]
            if mode not in {'100644', '100755'} or kind != 'blob':
                raise TestError('Git links/submodules are not supported', 'SOURCE_UNSAFE', 422)
            if any(p.startswith('.') or p in EXCLUDED for p in name.split('/')):
                continue
            size = int(self.git(root, 'cat-file', '-s', blob).strip())
            if size > 16 * 1024 * 1024 or total + size > 128 * 1024 * 1024 or len(files) >= 10000:
                raise TestError('Source snapshot exceeds file/byte limits', 'SOURCE_LIMIT', 422)
            data = self.git(root, 'cat-file', 'blob', blob)
            if len(data) != size:
                raise TestError('Git source bytes changed', 'SOURCE_CHANGED')
            total += size
            files[name] = data
        return files

    def apply(self, inspection_id, ref, expected_version):
        state = self.state()
        if type(expected_version) is not int or state['version'] != expected_version:
            raise TestError('Source selection changed; reload before applying', 'VERSION_CONFLICT')
        with self.store.connection() as c:
            row = c.execute("SELECT data FROM documents WHERE kind='source-inspection' AND name=?", (inspection_id,)).fetchone()
        if not row:
            raise TestError('Inspect the source before applying', 'SOURCE_INSPECTION_REQUIRED', 422)
        item = json.loads(row[0])
        if item['kind'] == 'legacy':
            if ref is not None:
                raise TestError('Legacy source has no inspected branch', 'SOURCE_REF_INVALID', 422)
            result = json.loads(json.dumps(LEGACY))
            result['version'] = expected_version + 1
            with self.store.transaction() as c:
                if self.state(c)['version'] != expected_version:
                    raise TestError('Source selection changed during preparation', 'VERSION_CONFLICT')
                c.execute("INSERT INTO documents VALUES('source-state','active',?) ON CONFLICT(kind,name) DO UPDATE SET data=excluded.data", (json.dumps(result),))
            return result | {'catalog': None}
        commit = None
        if item['repository']:
            chosen = next((r for r in item['refs'] if r['ref'] == ref), None)
            if not chosen:
                raise TestError('Select an inspected source branch', 'SOURCE_REF_INVALID', 422)
            commit = chosen['commit']
        elif ref is not None:
            raise TestError('A plain folder has no branch', 'SOURCE_REF_INVALID', 422)
        self.root.mkdir(parents=True, exist_ok=True)
        try:
            if item['kind'] == 'git-url':
                with tempfile.TemporaryDirectory(dir=self.root, prefix='git-') as temp:
                    self.git(temp, 'init', '--bare', '.')
                    self.git(temp, 'fetch', '--no-tags', '--depth=1', '--', item['location'], ref)
                    fetched = self.git(temp, 'rev-parse', '--verify', 'FETCH_HEAD^{commit}').decode().strip()
                    if fetched != commit:
                        raise TestError('Branch changed since inspection; inspect it again', 'SOURCE_CHANGED')
                    files = self.git_files(temp, commit)
            elif item['repository']:
                files = self.git_files(item.get('_repository_root', item['location']), commit, item.get('_prefix', ''))
            else:
                files = read_source(item['location'])
            source = {k: item[k] for k in ('kind', 'location', 'inspection_id')}
            source.update(ref=ref, commit=commit, generation=expected_version + 1)
            value = manifest(files, source, {})
            directory = self.snapshots / value['snapshot_id']
            publish(files, value, directory)
            catalog = discover(directory, {}) | {'revision': value['source_revision'], 'branch': ref or 'folder'}
        except (OSError, UnicodeError, ValueError) as exc:
            raise TestError('Source preparation failed; previous source is unchanged', 'SOURCE_PREPARE_FAILED', 422) from exc
        active = {k: source[k] for k in ('kind', 'location', 'ref', 'commit', 'inspection_id')}
        active.update(snapshot_id=value['snapshot_id'], source_revision=value['source_revision'])
        result = {'version': expected_version + 1, 'active': active}
        with self.store.transaction() as c:
            if self.state(c)['version'] != expected_version:
                raise TestError('Source selection changed during preparation', 'VERSION_CONFLICT')
            c.execute("INSERT INTO documents VALUES('source-state','active',?) ON CONFLICT(kind,name) DO UPDATE SET data=excluded.data", (json.dumps(result),))
        return result | {'catalog': catalog}

    def catalog(self):
        state = self.state()
        if state['active']['kind'] == 'legacy':
            return None
        directory = self.directory(state['active'])
        value = load_manifest(directory, state['active']['snapshot_id'])
        checked_files(directory, value)
        return discover(directory, {}) | {'revision': state['active']['source_revision'], 'branch': state['active']['ref'] or 'folder'}

    def descriptor(self):
        state = self.state()
        return None if state['active']['kind'] == 'legacy' else {'version': state['version'], **state['active']}

    def directory(self, descriptor):
        identity = descriptor.get('snapshot_id', '')
        if not isinstance(identity, str) or not re.fullmatch('[a-f0-9]{64}', identity):
            raise TestError('Invalid frozen source descriptor', 'SOURCE_CHANGED')
        return self.snapshots / identity
