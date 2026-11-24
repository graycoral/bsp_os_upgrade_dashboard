"""Portable plugin-owned distribution plus the matching Windows browser GUI source.

No pip/download/Windows launch occurs here. The existing source launcher prepares
its pinned dependencies on Windows; this is not the older embedded CLI bundle.
"""
import json
import os
import re
from pathlib import Path
import shutil

from delivery import REQUIRED as MONITOR_REQUIRED
from delivery import export, verify, relative, sha, MANIFEST

PACKAGE = 'PLUGIN_PACKAGE.json'
FORMAT = 'bsp-plugin-package-v1'
REQUIRED = MONITOR_REQUIRED + ('board-connector.bat', 'board-connector.cmd', 'scripts/board_connector.py',
            'backend/gui_test/connector/bootstrap.py', 'backend/gui_test/connector/__main__.py',
            'backend/gui_test/connector/api.py', 'backend/gui_test/connector/supervisor.py',
            'backend/gui_test/connector/test_status.py', 'backend/gui_test/connector/web.py',
            'backend/gui_test/connector/web_assets/index.html', 'backend/gui_test/connector/web_assets/host.mjs',
            'packages/gui-test-ui/src/connector_web/view.mjs', 'packages/gui-test-ui/src/connector_web/style.css',
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


def _verify_windows_closure(source):
    manifest = verify(source)
    missing = [name for name in REQUIRED if name not in manifest['files']]
    if missing: raise ValueError('Plugin/GUI source closure is incomplete: ' + ', '.join(missing))
    return manifest


def windows_directory(source, output, *, profile=None):
    source, output = Path(source).resolve(), Path(output).resolve()
    manifest = _verify_windows_closure(source)
    if output.exists(): raise ValueError('Use a new artifact path')
    if output.is_relative_to(source): raise ValueError('Export Windows artifacts outside source')
    extra = {}
    if profile is not None:
        # Validation belongs to the same portable contract used by both ends.
        from backend.gui_test.core.connector_bootstrap import parse_bootstrap
        profile = parse_bootstrap(profile).model_dump()
        extra['connector-connection.json'] = (json.dumps(profile, ensure_ascii=False, indent=2) + '\n').encode()
        extra['start-board-connector.bat'] = START.replace('\n', '\r\n').encode('ascii')
    output.mkdir(parents=True, exist_ok=True)
    try:
        for name in sorted(manifest['files']):
            rel = relative(name)
            target = output / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source / rel, target)
        shutil.copy2(source / MANIFEST, output / MANIFEST)
        for name, data in extra.items():
            (output / name).write_bytes(data)
        (output / 'WINDOWS_DELIVERY.json').write_text(json.dumps({
            'format': 'bsp-plugin-windows-gui-v1',
            'release': manifest['release'],
            'entrypoint': 'start-board-connector.bat' if profile else 'board-connector.bat',
            'source_manifest': MANIFEST,
            'connection_files': {k: sha(v) for k, v in extra.items()},
            'python': 'Windows Python 3.11-3.13 x64; 3.13 preferred',
            'company_acceptance': 'NOT_RUN',
        }, indent=2))
    except Exception:
        shutil.rmtree(output, ignore_errors=True)
        raise
    return {'path': str(output), 'release': manifest['release'],
            'kind': 'windows-gui-source', 'company_acceptance': 'NOT_RUN'}


def windows_descriptor(release):
    return {'path': 'agent-monitor', 'entrypoint': 'board-connector.bat',
            'release': release, 'kind': 'windows-gui-source', 'company_acceptance': 'NOT_RUN'}


def export_plugin(source, destination, *, include_ui=True):
    source, destination = Path(source).resolve(), Path(destination).resolve()
    if destination.exists(): raise ValueError('Use a new plugin delivery directory')
    if destination.is_relative_to(source) or source.is_relative_to(destination):
        raise ValueError('Plugin delivery must be outside the source tree')
    destination.mkdir(parents=True)
    try:
        release = export(source, destination / 'agent-monitor', include_ui)
        _verify_windows_closure(destination / 'agent-monitor')
        shutil.copyfile(destination / 'agent-monitor/apps/agent-monitor/plugin.py', destination / 'plugin.py')
        (destination / 'README.md').write_text('''# Plugin-owned BSP connector package

Implement the company GUI Test commands and hooks using the
[board connector integration workflow](agent-monitor/docs/agents/BOARD_CONNECTOR_PLUGIN_WORKFLOW.md).
It covers board ownership, flash and test execution, recovery and result reporting.

Copy this complete directory into the plugin Git repository. Do not copy runtime,
SSH keys or settings into Git. `python3 plugin.py help` needs only Python 3.11+.
For manual observation, run `python3 plugin.py --home HOME --project KEY connect --watch --json`.
For opt-in automatic observation, register `agent-monitor/examples/activate-connector-watch.sh`
with the company's child-process supervisor. Pass the same global options. Start it asynchronously
and terminate its owned process handle on shutdown. Both entrypoints share one OS lock per endpoint.

Use [PORT-017](agent-monitor/docs/porting/PORT-017.md) for JSON status and exit codes,
official request schema and examples, prepared request replay, export paths,
module publication, mock acceptance commands/results and independent release verification.
The module inventory example is `agent-monitor/examples/connector-runs/modules.json`.

Save the Windows-reachable Linux SSH endpoint once with
`connect profile --server HOST --account USER [--ssh-port PORT]`. Use the same
runtime and connector port as the activation hook. `connect export --output NEW_DIR`
copies the matching Windows GUI with the saved nonsecret bootstrap. Double-click
`start-board-connector.bat` once, and later launches reuse the matching Manager.
For manual setup, use `agent-monitor/board-connector.bat`. SSH keys and COM/device
mappings remain site prerequisites. Python
and public tools/dependencies are prepared by the existing launcher. No offline
embedded Python, driver installation or company acceptance is claimed.

Keep settings JSON outside both repositories. Use `settings export --file NEW_FILE`
and `settings import --file PATH` for a revision-checked direct settings transfer.
The service DB remains authoritative. For a clean handoff run `verify NEW_DIR --pristine`.
Use `monitor status` to compare this package,
the active installation and the running Monitor, then follow the owner-approved update
procedure if the release differs. Source ownership moves out of the company dashboard Git; map imports/service/UI clients
to this vendor package before removing duplicate source. Keep the same runtime,
service, DB and single Worker. See agent-monitor/docs/porting/PORT-011.md.

For the image flashing settings update, see agent-monitor/docs/porting/PORT-016.md.
It maps the Linux CLI, dashboard bundles and Windows connector files in this
package and describes how to check saved BAT and profile values with test preview --flash.
''')
        paths = [p for p in destination.rglob('*') if p.is_file()]
        files = {p.relative_to(destination).as_posix(): sha(p.read_bytes()) for p in sorted(paths)}
        manifest = {'format': FORMAT, 'files': files, 'release': release['release'],
                    'windows': windows_descriptor(release['release']),
                    'entrypoint': 'plugin.py',
                    'settings_authority': 'existing-service-db', 'company_acceptance': 'NOT_RUN'}
        (destination / PACKAGE).write_text(json.dumps(manifest, indent=2) + '\n')
        return verify_plugin(destination, pristine=True)
    except Exception:
        # Only the newly-created, dedicated staging directory belongs to us.
        shutil.rmtree(destination)
        raise


def generated_bytecode(path, root, expected):
    if path.parent.name != '__pycache__':
        return False
    match = re.fullmatch(r'(.+)\.cpython-3[0-9]+(?:\.opt-[12])?\.pyc', path.name)
    return bool(match and (path.parent.parent / (match[1] + '.py')).relative_to(root).as_posix() in expected)


def verify_plugin(root, *, pristine=False):
    root = Path(root).absolute()
    if root.is_symlink() or (root / PACKAGE).is_symlink() or (root / 'agent-monitor').is_symlink():
        raise ValueError('Plugin package symlinks are unsupported')
    root = root.resolve()
    value = json.loads((root / PACKAGE).read_text())
    if not isinstance(value, dict) or value.get('format') != FORMAT or not isinstance(value.get('files'), dict):
        raise ValueError('Invalid plugin package manifest')
    source = root / 'agent-monitor'
    release = _verify_windows_closure(source)
    expected = {'plugin.py', 'README.md', f'agent-monitor/{MANIFEST}'}
    expected.update(f'agent-monitor/{name}' for name in release['files'])
    if set(value['files']) != expected:
        raise ValueError('Plugin package manifest does not match source closure')
    actual = set()
    for folder, dirs, files in os.walk(root):
        folder = Path(folder)
        if folder == root:
            # An enclosing vendor Git repository may store local metadata here.
            if '.git' in dirs:
                dirs.remove('.git')
            if '.git' in files:
                files.remove('.git')
        for name in dirs:
            if (folder / name).is_symlink():
                raise ValueError('Unsupported plugin package symlink: ' + str((folder / name).relative_to(root)))
        for name in files:
            path = folder / name
            rel = path.relative_to(root).as_posix()
            if path.is_symlink() or not path.is_file():
                raise ValueError('Unsupported plugin package entry: ' + rel)
            if pristine or not generated_bytecode(path, root, expected):
                actual.add(rel)
    if actual != expected | {PACKAGE}:
        raise ValueError('Plugin package directory does not match manifest: ' +
                         ', '.join(sorted(actual.symmetric_difference(expected | {PACKAGE}))))
    for name, checksum in value['files'].items():
        path = root / relative(name)
        expected_hash = release['files'].get(name.removeprefix('agent-monitor/')) if name.startswith('agent-monitor/') else None
        if (expected_hash or sha(path.read_bytes())) != checksum:
            raise ValueError('Plugin package integrity mismatch: ' + name)
    if (release['release'] != value.get('release') or value.get('entrypoint') != 'plugin.py'
            or value.get('windows') != windows_descriptor(release['release'])
            or value['files']['plugin.py'] != release['files']['apps/agent-monitor/plugin.py']):
        raise ValueError('Plugin package release/artifact mismatch')
    return value


def release_evidence(prior, current):
    """Build the same byte-for-byte delta that the recipient verifies independently."""
    inventories = []
    releases = {}
    for label, package in (('prior', prior), ('current', current)):
        root = Path(package)
        outer = verify_plugin(root, pristine=True)
        source_manifest = (root / 'agent-monitor' / MANIFEST).read_bytes()
        source = json.loads(source_manifest)
        package_digest = sha((root / PACKAGE).read_bytes())
        inventories.append(outer['files'] | {PACKAGE: package_digest})
        releases[label] = {
            'source_commit': source.get('source_head'), 'source_dirty': source.get('source_dirty'),
            'release': outer['release'], 'package_manifest_sha256': package_digest,
            'source_manifest_sha256': sha(source_manifest),
        }
    before, after = inventories
    lines = ['path\tprior_sha256\tcurrent_sha256']
    for name in sorted(before.keys() | after.keys()):
        if before.get(name) != after.get(name):
            if any(char in name for char in '\t\r\n'):
                raise ValueError('Invalid path for release delta')
            lines.append('\t'.join((name, before.get(name, '-'), after.get(name, '-'))))
    delta = ('\n'.join(lines) + '\n').encode('utf-8')
    metadata = {'schema_version': 1, **releases, 'manifest_delta_sha256': sha(delta)}
    return delta, (json.dumps(metadata, sort_keys=True, indent=2) + '\n').encode('utf-8')


def write_evidence(prior, current, output):
    delta, receipt = release_evidence(prior, current)
    output.mkdir(parents=True, exist_ok=False)
    try:
        (output / 'MANIFEST_DELTA.tsv').write_bytes(delta)
        (output / 'RELEASE_EVIDENCE.json').write_bytes(receipt)
    except Exception:
        shutil.rmtree(output)
        raise
    return {'state': 'EXPORTED', 'output': str(output), 'sha256': sha(receipt)}


def verify_evidence(prior, current, directory, expected):
    receipt = (directory / 'RELEASE_EVIDENCE.json').read_bytes()
    if sha(receipt) != expected:
        raise ValueError('Independent RELEASE_EVIDENCE.json digest mismatch')
    delta, rebuilt = release_evidence(prior, current)
    if receipt != rebuilt or (directory / 'MANIFEST_DELTA.tsv').read_bytes() != delta:
        raise ValueError('Release evidence does not match the verified packages')
    return {'state': 'VERIFIED', 'sha256': expected}
