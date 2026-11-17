"""Portable plugin-owned distribution plus the matching Windows browser GUI source.

No pip/download/Windows launch occurs here. The existing source launcher prepares
its pinned dependencies on Windows; this is not the older embedded CLI bundle.
"""
import hashlib
import json
from pathlib import Path
import shutil
import zipfile

from delivery import export, verify, relative, sha, ROOT, MANIFEST

PACKAGE = 'PLUGIN_PACKAGE.json'
FORMAT = 'bsp-plugin-package-v1'
WINDOWS = 'windows-board-connector.zip'
REQUIRED = ('board-connector.bat', 'board-connector.cmd', 'scripts/board_connector.py',
            'backend/gui_test/connector/bootstrap.py', 'backend/gui_test/connector/__main__.py',
            'backend/gui_test/connector/web_assets/index.html',
            'packages/gui-test-ui/src/connector_web/view.mjs',
            'apps/gui-test/requirements.lock', 'apps/board-connector/requirements.lock',
            'apps/agent-monitor/plugin.py', 'apps/agent-monitor/plugin_delivery.py',
            'backend/gui_test/standalone/plugin_runtime.py',
            'packaging/board-connector-inputs.lock.json')
START = '''@echo off
setlocal EnableExtensions DisableDelayedExpansion
set "ERRORLEVEL="
"%SystemRoot%\\System32\\cmd.exe" /d /e:on /v:off /s /c ^""%~dp0board-connector.cmd" --bootstrap-profile "%~dp0connector-connection.json" %*^"
exit /b %errorlevel%
'''


def windows_archive(source, output, *, profile=None):
    source, output = Path(source).resolve(), Path(output).absolute()
    manifest = verify(source)
    missing = [name for name in REQUIRED if name not in manifest['files']]
    if missing: raise ValueError('Plugin/GUI source closure is incomplete: ' + ', '.join(missing))
    if output.exists(): raise ValueError('Use a new artifact path')
    if output.is_relative_to(source): raise ValueError('Export Windows artifacts outside source')
    output.parent.mkdir(parents=True, exist_ok=True)
    extra = {}
    if profile is not None:
        # Validation belongs to the same portable contract used by both ends.
        from backend.gui_test.core.connector_bootstrap import ConnectorBootstrap
        profile = ConnectorBootstrap.model_validate(profile).model_dump()
        extra['connector-connection.json'] = (json.dumps(profile, ensure_ascii=False, indent=2) + '\n').encode()
        extra['start-board-connector.bat'] = START.replace('\n', '\r\n').encode('ascii')
    with zipfile.ZipFile(output, 'x', compression=zipfile.ZIP_DEFLATED) as archive:
        for name in sorted(manifest['files']): archive.write(source / relative(name), name)
        archive.write(source / MANIFEST, MANIFEST)
        for name, data in extra.items(): archive.writestr(name, data)
        archive.writestr('WINDOWS_DELIVERY.json', json.dumps({'format': 'bsp-plugin-windows-gui-v1',
            'release': manifest['release'], 'entrypoint': 'start-board-connector.bat' if profile else 'board-connector.bat',
            'source_manifest': MANIFEST, 'connection_files': {k: sha(v) for k, v in extra.items()},
            'python': 'Windows Python 3.11-3.13 x64; 3.13 preferred',
            'company_acceptance': 'NOT_RUN'}, indent=2))
    return {'path': str(output), 'sha256': sha(output.read_bytes()), 'release': manifest['release'],
            'kind': 'windows-gui-source', 'company_acceptance': 'NOT_RUN'}


def export_plugin(source, destination, *, include_ui=True):
    source, destination = Path(source).resolve(), Path(destination).absolute()
    if destination.exists(): raise ValueError('Use a new plugin delivery directory')
    if destination.is_relative_to(source) or source.is_relative_to(destination):
        raise ValueError('Plugin delivery must be outside the source tree')
    destination.mkdir(parents=True)
    try:
        release = export(source, destination / 'agent-monitor', include_ui)
        artifact = windows_archive(destination / 'agent-monitor', destination / WINDOWS)
        shutil.copyfile(destination / 'agent-monitor/apps/agent-monitor/plugin.py', destination / 'plugin.py')
        (destination / 'README.md').write_text('''# Plugin-owned BSP connector package

Copy this complete directory into the plugin Git repository. Do not copy runtime,
SSH keys or settings into Git. `python3 plugin.py help` needs only Python 3.11+.
The plugin install/activate hook calls `python3 plugin.py connect --watch` with
its persistent --home and explicit --project. JSON output is machine-readable;
installation progress goes to stderr. Closing observation does not stop work.

`connect export --server HOST --account USER --output NEW.zip` creates the same
version Windows GUI source ZIP with its nonsecret bootstrap. Extract on Windows
and double-click start-board-connector.bat once; later launches reuse the matching
Manager. Initial SSH/key/COM/device mappings remain site prerequisites. Python
and public tools/dependencies are prepared by the existing launcher. No offline
embedded Python, driver installation or company acceptance is claimed.

Shared settings JSON is outside both repositories: use settings file sync/push.
The service DB remains authoritative and concurrent edits are preserved. Source
ownership moves out of the company dashboard Git; map imports/service/UI clients
to this vendor package before removing duplicate source. Keep the same runtime,
service, DB and single Worker. See agent-monitor/docs/porting/PORT-011.md.
''')
        paths = [p for p in destination.rglob('*') if p.is_file()]
        files = {p.relative_to(destination).as_posix(): sha(p.read_bytes()) for p in sorted(paths)}
        manifest = {'format': FORMAT, 'files': files, 'release': release['release'],
                    'windows': dict(artifact, path=WINDOWS), 'entrypoint': 'plugin.py',
                    'settings_authority': 'existing-service-db', 'company_acceptance': 'NOT_RUN'}
        (destination / PACKAGE).write_text(json.dumps(manifest, indent=2) + '\n')
        return verify_plugin(destination)
    except Exception:
        # Only the newly-created, dedicated staging directory belongs to us.
        shutil.rmtree(destination)
        raise


def verify_plugin(root):
    root = Path(root).absolute()
    value = json.loads((root / PACKAGE).read_text())
    if value.get('format') != FORMAT or not isinstance(value.get('files'), dict):
        raise ValueError('Invalid plugin package manifest')
    for name, checksum in value['files'].items():
        path = root / relative(name)
        if any(part.is_symlink() for part in [path, *path.parents]) or not path.is_file() or sha(path.read_bytes()) != checksum:
            raise ValueError('Plugin package integrity mismatch: ' + name)
    release = verify(root / 'agent-monitor')
    if release['release'] != value['release'] or value['windows']['sha256'] != sha((root / WINDOWS).read_bytes()):
        raise ValueError('Plugin package release/artifact mismatch')
    return value
