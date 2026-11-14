"""Export the independent three-root source bundle or stage an installed wheel.

Only backend/gui_test is canonical Python source. The gui_test wheel namespace
is synthesized into a fresh staging directory, never maintained as a second tree.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parents[2]
HOST_TARGET = 'bsp-dashboard-host-v1'
SOURCE_ROOTS = ['apps/gui-test', 'backend/gui_test', 'packages/gui-test-ui/src']
HOST_REFERENCE = 'backend/services/gui_test_host.py'
UI_FIXTURE_SOURCE = 'workflow_diagram/tests/portable-ui-host.tsx'
UI_FIXTURE_COMMAND = ('node apps/gui-test/node_modules/vite/bin/vite.js '
                      '--config ui-verification/vite.config.mjs --host 127.0.0.1 --port 18779 --strictPort')
PORTABLE_TEST_FILES = [
    'test_core.py', 'test_api.py', 'test_commands.py', 'test_windows_runner.py',
    'test_portable_host.py', 'test_sources.py', 'test_source_snapshots.py',
    'test_source_transport.py', 'test_git_info.py', 'test_package.py',
]
HOST_ONLY_TESTS = [
    'test_integrated_mock_routes_leave_existing_dashboard_unchanged',
    'test_source_api_normal_and_live_share_contract_and_keep_catalog_available_offline',
    'test_actual_host_archive_is_self_contained_and_hashes_every_entry',
]
PORTABLE_TEST_COMMAND = ('python -m pytest ' + ' '.join('backend/gui_test/tests/' + name for name in PORTABLE_TEST_FILES)
                         + ' -q -k "' + ' and '.join('not ' + name for name in HOST_ONLY_TESTS) + '"')
PYTHON_DIRS = {'core', 'adapters', 'api', 'standalone', 'demo', 'execution', 'connector', 'tests'}
APP_FILES = {'launch.py', 'package.py', 'build-windows-package.cmd', 'build-windows-package.ps1',
             'bsp-gui-test.service.example',
             'package.json', 'package-lock.json', 'vite.config.ts', 'tsconfig.json',
             'index.html', 'pyproject.toml', 'requirements.lock', 'README.md', 'VALIDATION.md'}
IGNORED = {'__pycache__', 'node_modules', 'build', 'dist', 'runtime', 'logs'}
UI_SUFFIXES = {'.ts', '.tsx', '.css', '.json', '.svg', '.mjs'}


def regular_files(folder):
    """Return regular files without traversing hidden/runtime/symlink trees."""
    if folder.is_symlink() or not folder.is_dir():
        return
    for current, directories, files in os.walk(folder, followlinks=False):
        directories[:] = sorted(name for name in directories
                                 if not name.startswith('.') and name not in IGNORED
                                 and not name.endswith('.egg-info')
                                 and not (Path(current) / name).is_symlink())
        for name in sorted(files):
            path = Path(current) / name
            if (not name.startswith('.') and not name.endswith(('.local.json', '.db', '.db-wal', '.db-shm'))
                    and not path.is_symlink() and path.is_file()):
                yield path, path.relative_to(folder)


def package_files(source_root):
    """Read bounded app/backend/shared-UI roots; no Dashboard or Git needed."""
    source_root = Path(source_root).resolve()
    names = {'backend/__init__.py': b'"""Portable GUI Test source namespace."""\n'}
    backend = source_root / 'backend/gui_test'
    app = source_root / 'apps/gui-test'
    ui = source_root / 'packages/gui-test-ui/src'
    for folder in (backend, app, ui):
        relative = folder.relative_to(source_root)
        if any(source_root.joinpath(*relative.parts[:i]).is_symlink()
               for i in range(1, len(relative.parts) + 1)):
            raise ValueError(f'Source root must not be a symlink: {folder}')
    for path, rel in regular_files(backend):
        if (len(rel.parts) == 1 and rel.name in {'__init__.py', 'runtime.py', 'catalog_settings.py'}
                or len(rel.parts) > 1 and rel.parts[0] in PYTHON_DIRS) and (path.suffix == '.py' or
                    rel.as_posix() in {'connector/web_assets/index.html', 'connector/web_assets/host.mjs'}):
            names['backend/gui_test/' + rel.as_posix()] = path.read_bytes()
    for path, rel in regular_files(app):
        allowed = (len(rel.parts) == 1 and rel.name in APP_FILES
                   or len(rel.parts) > 1 and rel.parts[0] == 'src' and path.suffix in UI_SUFFIXES
                   or len(rel.parts) > 1 and rel.parts[0] == 'config' and path.name.endswith('.example.json')
                   or len(rel.parts) > 1 and rel.parts[0] == 'static')
        if allowed:
            names['apps/gui-test/' + rel.as_posix()] = path.read_bytes()
    for path, rel in regular_files(ui):
        if path.suffix in UI_SUFFIXES:
            names['packages/gui-test-ui/src/' + rel.as_posix()] = path.read_bytes()
            if rel.as_posix() in {'connector_web/view.mjs', 'connector_web/style.css'}:
                names['backend/gui_test/connector/web_assets/' + rel.name] = path.read_bytes()
    return names


def stage_wheel(source_root, destination, *, include_ui=True):
    """Stage canonical code/resources into the legacy installed gui_test namespace."""
    names = package_files(source_root)
    if include_ui and 'apps/gui-test/static/index.html' not in names:
        raise ValueError('Build standalone UI before staging: npm ci --prefix apps/gui-test && npm run build --prefix apps/gui-test')
    staged = {}
    for name, content in names.items():
        if name.startswith('backend/gui_test/'):
            relative = name.removeprefix('backend/gui_test/')
            if relative.split('/')[0] != 'tests':
                staged['gui_test/' + relative] = content
        elif name.startswith(('apps/gui-test/static/', 'apps/gui-test/config/')):
            if not include_ui and name.startswith('apps/gui-test/static/'):
                continue
            staged['gui_test/' + name.removeprefix('apps/gui-test/')] = content
    for name in ('pyproject.toml', 'requirements.lock', 'README.md'):
        key = 'apps/gui-test/' + name
        if key not in names:
            raise ValueError(f'Missing wheel input: {key}')
        staged[name if name != 'README.md' else 'gui_test/README.md'] = names[key]
    staged['gui_test/requirements.lock'] = names['apps/gui-test/requirements.lock']
    destination = Path(destination).resolve()
    if destination.exists() and (not destination.is_dir() or any(destination.iterdir())):
        raise ValueError('Wheel staging destination must be a fresh or empty directory')
    destination.mkdir(parents=True, exist_ok=True)
    for name, content in staged.items():
        target = destination / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
    return destination


def build_integration_archive(source_root, output, *, include_ui=False):
    """GUI-only source delivery, including a headless wheel staging command."""
    names = package_files(source_root)
    if include_ui and 'apps/gui-test/static/index.html' not in names:
        raise ValueError('Build optional standalone UI before including it')
    if not include_ui:
        names = {name: data for name, data in names.items() if not name.startswith(('apps/gui-test/static/', 'packages/', 'apps/gui-test/src/'))}
    names['INSTALL.md'] = b'''# BSP plugin GUI Test backend

This is the reusable GUI Test service and reference plugin client, not a private
company plugin implementation. No BSP scheduler, model or Jira service is needed.

From the extracted source root:

```sh
python -m pip install -r apps/gui-test/requirements.lock
python apps/gui-test/package.py --stage-headless-wheel /tmp/bsp-gui-test-stage
python -m pip wheel /tmp/bsp-gui-test-stage --no-deps --no-build-isolation -w wheels
```

Install that wheel in the service account's virtual environment. Copy and adapt
apps/gui-test/bsp-gui-test.service.example using the company's service policy.
Do not launch API/worker as a plugin request child. Configure the installed unit
once; the reference SystemdService adapter only starts that same unit.

Start the service, pin its runtime/package identity in PluginClient, and use
settings()/save_settings() for allowed Linux image roots, TC root and timeouts.
Create the TC command with save_command_profile(name, {single: [...], dual: [...]})
and select_profile('commands', name, revision=..., expected_settings_revision=...).
Updates require the saved revision; do not write the database directly.
Use flash_profiles()/save_flash_profile() for Windows named flash settings and
wait for the actual Host revision before selecting the flash profile.
export_connector_bootstrap(server=..., account=..., ssh_port=22,
remote_dashboard_port=8767, path=...) produces the nonsecret initial connection
file. Import it with board-connector.cmd --import-profile FILE in the matching
Windows source package. Use a Windows-reachable Linux host, not localhost.
SSH keys stay on Windows. No TC path is duplicated into that connection file.
No Runner, registration, or plugin connection token is required. Keep the service
on loopback and use SSH for cross-machine access. Update both services and the
reference PluginClient together; older versions may still require tokens.

Run installed service entrypoint:

```sh
python -m gui_test.standalone.integration --runtime /var/lib/bsp-gui-test --port 8767
```

For source-only local host adaptation use backend.gui_test in place of gui_test.
The runtime, profile, TC root, allowed image roots, Runner identity and reviewed
BAT/splitter profiles must be real company settings. No listed example is ready
to operate hardware. Use the matching editable source TEST BOARD CONNECTOR (Windows) (no new
frozen EXE distribution); require
source_snapshot_v1, installer_stream_v1 and bsp_upgrade_integration_v1.
Dashboard web rebuilds alone do not require replacing the Runner. For the
RQ-62 setup update, apply the reviewed src/scripts/setup_flashing.py and restart
normally while keeping the existing external user home, SSH settings and runtime.
The post-BAT fresh prompt contains 'login :'; the TC owns the root login.
Do not use 'fastboot init success' as the pre-fast lkshell readiness marker.

Plugin mapping: standalone.plugin_client.PluginClient.ensure_service checks
runtime/package/config/runner identity and starts the installed
unit when unreachable; PatternDefaults.suggest keeps explicit per-run overrides;
preview/preparation returns an optional frozen token; start requires a stable
idempotency key and returns existing Run.id. Poll run(id), events(id),
attempt_log(id, attempt_id) and board_console(). Use action() for versioned
pause/resume/cancel/reconcile and delete_run() for explicit permanent deletion
after terminal/termination/ownership checks. Every request carries the pinned
runtime/package identifiers. Never replace a lost-response key or treat HTTP 202
as test success. BspPluginClient is only for the separate full Agent Monitor
host advertising bsp-control-v1; this GUI-only service rejects BSP job scope.

Use PluginClient.connect() for the plugin's connection/status action. Provide
log_dir and diagnostic_callback to display each failed attempt's correlation ID,
UTC time, phase, duration, attempt count, safe target, code, cause, action hint
and log path. Default logs are account-local
~/.bsp-upgrade/gui-test-logs/connections.jsonl (8 MiB x 8 files). Backend WindowsRemote
accepts an injected DiagnosticRecorder for the service account log directory.
Log-write failures are returned as log_error without hiding the connection error.
Do not log exception repr, environment dumps or service/Runner credentials.

Optional details UI: build the standalone UI and export --integration --include-ui
or stage the built UI with --stage-wheel. PluginClient.browser_access() returns
a 60-second single-use read-only URL. It exchanges a URL fragment bootstrap for
a 30-minute HttpOnly/SameSiteStrict cookie; the persistent service token never
enters browser URLs/storage. Existing status/log/report views work with this
cookie; browser mutation/control requests remain denied. Install the optional
UI static assets alongside the backend, or pass --static-dir to the service.

Back up runtime DB, gui-test.json, source-storage/integration-inputs and secure
credential references before upgrade. Restore into a separate runtime using the
same package version; do not erase UNKNOWN reservations or reopen policy Runs
with older workers. SHA256SUMS.json covers every other file. This archive is
working-tree source, not a fixed commit or proof of tests/company acceptance.
'''
    names['INTEGRATION.json'] = json_bytes({'contract': 'bsp-upgrade-integration-v1', 'package_version': '0.1.0',
        'include_ui': include_ui, 'backend_entrypoint': 'backend.gui_test.standalone.integration:main',
        'installed_entrypoint': 'gui_test.standalone.integration:main',
        'plugin_reference': 'backend/gui_test/standalone/plugin_client.py',
        'service_template': 'apps/gui-test/bsp-gui-test.service.example',
        'provenance': host_provenance(source_root, names), 'company_acceptance': 'NOT_RUN'})
    names['SHA256SUMS.json'] = json_bytes({name: hashlib.sha256(data).hexdigest() for name, data in sorted(names.items())})
    output = Path(output).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=output.parent, prefix=output.name + '.', suffix='.tmp', delete=False) as stream:
        temporary = Path(stream.name)
    try:
        with zipfile.ZipFile(temporary, 'w', zipfile.ZIP_DEFLATED) as archive:
            for name, content in sorted(names.items()):
                archive.writestr(name, content)
        temporary.replace(output)
    finally:
        temporary.unlink(missing_ok=True)
    return {'file': str(output), 'files': len(names), 'bytes': output.stat().st_size,
            'sha256': hashlib.sha256(output.read_bytes()).hexdigest(), 'mode': 'integration'}


def validate_mode(*, base=None, standalone=False, host_integration=False, target=None,
                  wheelhouse=None, wheels=None):
    # Validate before reading a source tree, invoking Git, or touching output.
    if base is not None:
        raise ValueError('--base is retired: cumulative patches omit untracked files and host dependencies; use --host-integration --target bsp-dashboard-host-v1')
    if bool(standalone) == bool(host_integration):
        raise ValueError('Choose exactly one of --standalone or --host-integration')
    if host_integration and target != HOST_TARGET:
        raise ValueError(f'--host-integration requires --target {HOST_TARGET}')
    if not host_integration and target is not None:
        raise ValueError('--target requires --host-integration')
    if host_integration and (wheelhouse is not None or wheels is not None):
        raise ValueError('--host-integration is source-only; --wheelhouse/--wheels require --standalone')


def json_bytes(value):
    return (json.dumps(value, indent=2, ensure_ascii=False) + '\n').encode('utf-8')


def ui_verification_files(source_root):
    """Deliver the same canonical fixture; only its relative import is relocated."""
    source = source_root / UI_FIXTURE_SOURCE
    if source.is_symlink() or not source.is_file() or any(
            source_root.joinpath(*Path(UI_FIXTURE_SOURCE).parts[:i]).is_symlink()
            for i in range(1, len(Path(UI_FIXTURE_SOURCE).parts))):
        raise ValueError(f'Missing regular UI verification fixture: {UI_FIXTURE_SOURCE}')
    canonical = source.read_bytes()
    old = b"from '../../packages/gui-test-ui/src'"
    new = b"from '../packages/gui-test-ui/src'"
    if canonical.count(old) != 1:
        raise ValueError('Canonical UI fixture import changed; review its explicit export relocation')
    fixture = canonical.replace(old, new, 1)
    files = {'ui-verification/portable-ui-host.tsx': fixture,
             'ui-verification/index.html': b'<!doctype html><html lang="ko"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>GUI shared fixture</title><style>body{margin:0}</style></head><body><div id="root"></div><script type="module" src="./portable-ui-host.tsx"></script></body></html>\n',
             'ui-verification/vite.config.mjs': b'''import {createRequire} from 'node:module';
import {fileURLToPath,pathToFileURL} from 'node:url';
const require=createRequire(new URL('../apps/gui-test/package.json',import.meta.url));
const react=(await import(pathToFileURL(require.resolve('@vitejs/plugin-react')).href)).default;
const local=path=>fileURLToPath(new URL(path,import.meta.url));
export default {root:local('.'),plugins:[react()],
 resolve:{dedupe:['react','react-dom'],alias:{react:local('../apps/gui-test/node_modules/react'),'react-dom':local('../apps/gui-test/node_modules/react-dom')}},
 server:{host:'127.0.0.1',fs:{allow:[local('..')]}},
 build:{outDir:local('./dist'),emptyOutDir:true}};
'''}
    files['ui-verification/README.md'] = f'''# Shared Test status visual fixture

This is the same canonical fixture used by the source repository browser tests.
Only its shared-UI relative import is relocated; HOST_INTEGRATION.json records both hashes and the rewrite.
All API, storage, downloads and session behavior use in-memory fixture adapters. No backend, apps/web, Playwright, board or external API is required.

From the extracted ZIP root:

```sh
npm ci --prefix apps/gui-test
{UI_FIXTURE_COMMAND}
```

Open http://127.0.0.1:18779/?observer&terminal for a read-only terminal Run, or ?observer for a paused observer.
The default fixture models an owned paused Run; ?foreign models a different controller. Its callbacks remain simulated.
Stop the local preview with Ctrl+C. npm dependencies require an approved registry/cache; the source ZIP is not an offline dependency installer.

Use the same approved browser version, viewport/device scale, locale/timezone, reduced-motion setting and installed/loaded font on both hosts.
Compare 375/1024/1440px with height 1000, then settings, TC selection and keyboard focus using the same component/CSS/token bytes.
The fixture uses the component's approved system font stack; a missing or different font is an unmet comparison prerequisite.

For the company comparison, place these fixture bytes at the corresponding source root, preserving the ../packages/gui-test-ui/src import or record the one required alias/path mapping.
Mount the same TestPage/ExecutionViewSettings and fixture host in the company UI shell with its normal global CSS; adjust the host mount/import only.
Do not rewrite fixture data or component/CSS implementation to make a comparison pass.
The standalone reference is the clean baseline; the company shell run checks actual host CSS/font/data adapter integration.
Record browser/font/viewport, source hashes and observed differences in company APPLIED.md.
Local fixture rendering does not establish actual company API/Runner/board acceptance; that remains NOT_RUN.
'''.encode('utf-8')
    return files, {'canonical_source': UI_FIXTURE_SOURCE,
                   'canonical_sha256': hashlib.sha256(canonical).hexdigest(),
                   'exported_fixture': 'ui-verification/portable-ui-host.tsx',
                   'exported_sha256': hashlib.sha256(fixture).hexdigest(),
                   'import_rewrite': {'from': old.decode(), 'to': new.decode()},
                   'files': sorted(files),
                   'commands': ['npm ci --prefix apps/gui-test', UI_FIXTURE_COMMAND],
                   'read_only_url': 'http://127.0.0.1:18779/?observer&terminal',
                   'dependencies': 'existing apps/gui-test/package-lock.json toolchain only',
                   'actual_validation': 'NOT_RUN; run the extracted fixture separately'}


def host_provenance(source_root, names):
    """Git is optional provenance for host delivery, never a file enumerator."""
    try:
        head = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=source_root,
                                       stderr=subprocess.DEVNULL).decode().strip()
        dirty = bool(subprocess.check_output(['git', 'status', '--porcelain', '--untracked-files=all'],
                                            cwd=source_root, stderr=subprocess.DEVNULL).strip())
    except (OSError, subprocess.CalledProcessError):
        head, dirty = None, None
    return {'head': head, 'dirty': dirty, 'basis': 'working-tree bytes; HEAD is ancestry, not a fixed release commit',
            'file_sha256': {name: hashlib.sha256(content).hexdigest()
                            for name, content in sorted(names.items())}}


def delivery_documents(host):
    mode = 'Host integration' if host else 'Standalone'
    install = f'''# {mode} source bundle\n\nRead [release scope](RELEASE_SUMMARY.md) and [host contract](docs/HOST_CONTRACT.md).\nKeep apps/gui-test, backend/gui_test and packages/gui-test-ui/src at these relative paths.\nDo not overwrite an existing company's backend/__init__.py with the minimal export namespace.\n\n## Build and run the standalone app\n\nPython and npm dependencies must be available from an approved registry/cache; this source ZIP does not promise offline dependency installation.\n\n```sh\npython -m pip install -r apps/gui-test/requirements.lock\nnpm ci --prefix apps/gui-test\nnpm run build --prefix apps/gui-test\npython apps/gui-test/launch.py start --runtime .runtime-gui-test --port 8767\npython apps/gui-test/launch.py status --runtime .runtime-gui-test --port 8767\npython apps/gui-test/launch.py stop --runtime .runtime-gui-test --port 8767\n```\n\nStage installed namespace with `python apps/gui-test/package.py --stage-wheel <empty-stage>` after building UI, then `python -m pip wheel <empty-stage> --no-deps --no-build-isolation -w <wheels>`.\nInstalled imports remain gui_test.*; source imports are backend.gui_test.*.\n\n## Portable verification\n\nFrom the extracted source root, after installing requirements.lock, run:\n\n```sh\n{PORTABLE_TEST_COMMAND}\n```\n\nThis bounded suite covers core, standalone API, commands, fake Windows execution, source snapshots/transport, local Git and packaging. It excludes three full-host cases (Dashboard API source/demo integration and repackaging the complete original host). Full-host test_live_view.py and test_module_selection.py require the complete host repository; do not collect the entire tests directory in this source ZIP. Tests use temporary local fixtures; Git-specific cases require a local Git executable and otherwise skip. No company/board acceptance is implied.\n\n## Company integration\n\nMap existing API, worker, domain and UI connections to the explicit contract before applying reusable source.\n{'Read HOST_INTEGRATION.json; host-reference is a reviewable example, never an automatic overwrite. Preserve its backend imports when adapting the example in the company backend/services namespace.' if host else 'This bundle contains standalone sources only. Export the explicit host-integration target from a full working tree for the host reference and provenance.'}\nPreserve company authentication, policy gates, runtime/DB, error handling and worker ownership.\nReuse the same shared component, CSS and token version together; adapt host data and callbacks only.\nUse one React instance, fixed browser/viewport and the approved installed font before comparing fixtures.\nActual company authentication, SSH, TC, board and Jira acceptance is NOT_RUN.\n\n## Integrity and rollback\n\nSHA256SUMS.json covers every other archive entry. Verify all bytes before applying.\nBack up company source/settings/DB; apply through its normal review workflow. No automatic data migration or service action is performed.\nRestore reviewed source artifacts without deleting runtime history or UNKNOWN state.\n'''
    contract = '''# Host contract and validation boundary\n\nThis is reusable source plus an explicit host contract, not a cumulative Git patch.\n\n- API: mount the GUI Test router on the existing /api/v1/gui-test prefix and map TestError through the host's normal error response. Retain authentication/origin/command gates.\n- Runtime: use host-reference make_dashboard_manager(runtime, *, engine=None, module_selection_service=None), which injects the Dashboard adapter into common make_manager; inject static/config paths from the app, never from backend into apps.\n- API demo: mount host-reference demo_router(manager, live=False) at the same /api/v1/gui-test prefix separately; the common router does not own Dashboard demo-job endpoints.\n- Worker: one process owns recovery/tick/outbox and automatic work; HTTP requests do not spawn long-running work.\n- Domain: host-reference automatic_result is an internal trusted receiver, never public client-supplied PASS. The host retains authoritative module plans, current Attempts, result/fingerprint validation and final review; standalone rejects production context.\n- UI: import TestPage, ExecutionViewSettings, SettingsSection/AuditDialog and createBrowserGuiTestHost from packages/gui-test-ui/src/index.ts (imports tokens.css, baseline.css, test.css and motion.css). GuiTestHost requires request/download/mode/applyMode/storage; optional ownsSession(controller) enables controller UI, otherwise observer-only. Server validation remains authoritative. Provide a stable host and flattened GuiTestModuleContext; apps/web/src/guiTestHost.ts is the host mapping reference; provide host adapters, settings mount and execution-view callbacks. Keep shared tokens isolated from global selectors.\n- Runner: registered source delivery requires source_snapshot_v1. The approved older distributed EXE has not been verified for this capability. Reject unsupported registered sources; retain legacy behavior.\n\n## Local verification commands\n\n```sh\n{PORTABLE_TEST_COMMAND}\nnpm run build --prefix apps/gui-test\n```\n\nThe command above is the bounded portable suite described in INSTALL.md. Do not collect backend/gui_test/tests as a whole in an extracted source ZIP: test_live_view.py imports backend.api.main, while other host cases need backend.api/domain/services. Run `python -m pytest backend/gui_test/tests -q` and host-specific API/worker/browser regressions only in the complete host repository. The three named -k exclusions require Dashboard API integration or full-host archive regeneration; no product assertion is weakened. Browser/viewport/font must match the approved reference; fixture parity is local evidence only. Actual company acceptance remains NOT_RUN. No model, SSH, board or Jira calls are authorized by these commands.\n\nSee ../HOST_INTEGRATION.json when present for exact source hashes, reference mapping, locks and validation scope.\n'''.replace('{PORTABLE_TEST_COMMAND}', PORTABLE_TEST_COMMAND)
    release = f'''# {mode} release summary\n\nThis archive was generated from current source bytes; it is not a fixed committed release or a company acceptance result.\nThe three canonical roots retain RQ-55/56 working-tree changes.\n{'HOST_INTEGRATION.json records optional HEAD/dirty provenance and per-file hashes. Static builds and wheels are intentionally excluded.' if host else 'Standalone source/wheel behavior is preserved. Build dependencies and production external services are separate prerequisites.'}\nNo cumulative dashboard-integration.patch is included. --base is retired and fails before source collection/output changes.\nLocal product tests, independent review and actual company acceptance are not executed by the packager.\nConsult [installation](INSTALL.md), [host contract](docs/HOST_CONTRACT.md) and SHA256SUMS.json.\n'''
    if host:
        install += '\n## Shared UI comparison\n\nOpen [the delivered visual fixture](ui-verification/README.md). It uses the same canonical fixture and shared UI bytes as the original source browser tests, with only its relative import relocated. The existing apps/gui-test npm toolchain serves it without apps/web, a backend or Playwright. The read-only observer URL, exact command, browser/font/viewport prerequisites and company mount instructions are included there.\n'
        contract += '\n## Shared UI fixture closure\n\n[The delivered fixture](../ui-verification/README.md) and HOST_INTEGRATION.json.ui_verification identify the canonical source/hash, exported hash, single import rewrite, all local fixture assets and exact command. Company integration mounts that same fixture with its normal host CSS; local reference rendering does not establish company acceptance.\n'
        release += '\nThe ui-verification directory contains the bounded canonical Test status fixture and a manual preview entrypoint using the existing standalone npm lock. It adds no shipped browser-test dependency or workflow product module. [Fixture instructions](ui-verification/README.md) describe read-only comparison and company parity prerequisites.\n'
    return {'INSTALL.md': install.encode(), 'RELEASE_SUMMARY.md': release.encode(),
            'docs/HOST_CONTRACT.md': contract.encode()}


def build_archive(source_root, output, *, base=None, standalone=False, host_integration=False,
                  target=None, wheelhouse=None, wheels=None):
    validate_mode(base=base, standalone=standalone, host_integration=host_integration,
                  target=target, wheelhouse=wheelhouse, wheels=wheels)
    source_root = Path(source_root).resolve()
    names = package_files(source_root)
    if standalone and 'apps/gui-test/static/index.html' not in names:
        raise ValueError('Build standalone UI before packaging: npm ci --prefix apps/gui-test && npm run build --prefix apps/gui-test')
    if host_integration:
        names = {name: data for name, data in names.items()
                 if not name.startswith('apps/gui-test/static/')}
        reference = source_root / HOST_REFERENCE
        if reference.is_symlink() or not reference.is_file() or any(
                source_root.joinpath(*Path(HOST_REFERENCE).parts[:i]).is_symlink()
                for i in range(1, len(Path(HOST_REFERENCE).parts))):
            raise ValueError(f'Missing regular host reference: {HOST_REFERENCE}')
        names['host-reference/' + HOST_REFERENCE] = reference.read_bytes()
        reference_mapping = {'host-reference/' + HOST_REFERENCE: HOST_REFERENCE}
        ui_reference = 'apps/web/src/guiTestHost.ts'
        reference = source_root / ui_reference
        if reference.is_file():
            if reference.is_symlink() or any(
                    source_root.joinpath(*Path(ui_reference).parts[:i]).is_symlink()
                    for i in range(1, len(Path(ui_reference).parts))):
                raise ValueError(f'Host reference must not be a symlink: {ui_reference}')
            names['host-reference/' + ui_reference] = reference.read_bytes()
            reference_mapping['host-reference/' + ui_reference] = ui_reference
        verification_files, verification_manifest = ui_verification_files(source_root)
        names.update(verification_files)
    # Exported prose is deliberately bounded and self-contained, not a recursive
    # copy of the repository's historical documentation graph.
    names.update(delivery_documents(host_integration))
    for name in ('README.md', 'VALIDATION.md'):
        names['apps/gui-test/' + name] = b'# GUI Test source delivery\n\nRead [installation](../../INSTALL.md), [release scope](../../RELEASE_SUMMARY.md) and [host contract](../../docs/HOST_CONTRACT.md).\n'
    if host_integration:
        names['HOST_INTEGRATION.json'] = json_bytes({
            'schema': 'gui-test-host-integration-v1', 'target': target,
            'scope': 'GUI Test only; PORT-001/PORT-002 are independently selected and not prerequisites',
            'provenance': host_provenance(source_root, names), 'roots': SOURCE_ROOTS,
            'host_reference_mapping': reference_mapping,
            'required_host_contracts': ['API router/error/authentication', 'runtime and module-selection injection',
                                       'single worker recovery/tick/outbox', 'domain result validation and final review',
                                       'public UI entrypoint/styles/tokens and host adapter', 'Runner source_snapshot_v1 for registered sources'],
            'dependency_locks': ['apps/gui-test/requirements.lock', 'apps/gui-test/package-lock.json'],
            'ui_entrypoint': 'packages/gui-test-ui/src/index.ts',
            'ui_styles': ['packages/gui-test-ui/src/' + name for name in ('tokens.css', 'baseline.css', 'test.css', 'motion.css')],
            'ui_verification': verification_manifest,
            'test_commands': [PORTABLE_TEST_COMMAND, 'npm run build --prefix apps/gui-test'],
            'portable_test_scope': {'files': PORTABLE_TEST_FILES, 'excluded_full_host_cases': HOST_ONLY_TESTS,
                                    'requires': 'extracted source root plus requirements.lock; local Git for Git-specific fixtures'},
            'host_test_commands': {'requires': 'complete host repository, not this extracted source bundle',
                                   'commands': ['python -m pytest backend/gui_test/tests -q']},
            'actual_validation': {'packager': 'source collection and SHA256 generation only',
                                  'product_tests': 'NOT_RUN', 'independent_review': 'NOT_REVIEWED',
                                  'company_acceptance': 'NOT_RUN'}})
    for folder, label in [(wheelhouse, 'wheelhouse'), (wheels, 'wheels')]:
        if folder is not None:
            folder = Path(folder)
            found = sorted(folder.glob('*.whl'))
            if folder.is_symlink() or not found or any(w.is_symlink() or not w.is_file() for w in found):
                raise ValueError(f'{label} must contain regular .whl files: {folder}')
            for wheel in found:
                names[label + '/' + wheel.name] = wheel.read_bytes()
    manifest = {name: hashlib.sha256(content).hexdigest() for name, content in sorted(names.items())}
    names['SHA256SUMS.json'] = (json.dumps(manifest, indent=2) + '\n').encode()
    output = Path(output).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=output.parent, prefix=output.name + '.', suffix='.tmp', delete=False) as stream:
        temporary = Path(stream.name)
    try:
        with zipfile.ZipFile(temporary, 'w', zipfile.ZIP_DEFLATED) as archive:
            for name, content in sorted(names.items()):
                archive.writestr(name, content)
        temporary.replace(output)
    finally:
        temporary.unlink(missing_ok=True)
    return {'file': str(output), 'files': len(names), 'bytes': output.stat().st_size,
            'sha256': hashlib.sha256(output.read_bytes()).hexdigest(),
            'mode': 'standalone' if standalone else 'host-integration'}


def main(argv=None):
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--base', help='Retired; always rejected before source collection')
    mode.add_argument('--standalone', action='store_true', help='Independent source bundle; never calls Git')
    mode.add_argument('--stage-wheel', type=Path, help='Stage an installed wheel namespace into this fresh directory')
    mode.add_argument('--stage-headless-wheel', type=Path, help='Stage GUI-only backend wheel without building UI')
    mode.add_argument('--integration', action='store_true', help='GUI-only persistent plugin backend source bundle')
    mode.add_argument('--host-integration', action='store_true', help='Source-only reusable bundle with explicit host contract')
    parser.add_argument('--target', help=f'Host contract target: {HOST_TARGET}')
    parser.add_argument('--wheelhouse')
    parser.add_argument('--wheels')
    parser.add_argument('--output', default='.local-reports/gui-test-company.zip')
    parser.add_argument('--include-ui', action='store_true', help='Include prebuilt UI with --integration')
    args = parser.parse_args(argv)
    try:
        if args.include_ui and not args.integration:
            raise ValueError('--include-ui requires --integration')
        if args.integration:
            if args.target is not None or args.wheelhouse is not None or args.wheels is not None:
                raise ValueError('--integration is a source delivery and does not accept target/wheel inputs')
            result = build_integration_archive(ROOT, args.output, include_ui=args.include_ui)
        elif args.stage_headless_wheel is not None:
            if args.target is not None or args.wheelhouse is not None or args.wheels is not None:
                raise ValueError('--stage-headless-wheel does not accept target/wheel inputs')
            result = {'stage': str(stage_wheel(ROOT, args.stage_headless_wheel, include_ui=False))}
        elif args.stage_wheel is not None:
            if args.target is not None or args.wheelhouse is not None or args.wheels is not None:
                raise ValueError('--stage-wheel does not accept --target/--wheelhouse/--wheels')
            result = {'stage': str(stage_wheel(ROOT, args.stage_wheel))}
        else:
            result = build_archive(ROOT, args.output, base=args.base,
                                   standalone=args.standalone, host_integration=args.host_integration,
                                   target=args.target, wheelhouse=args.wheelhouse, wheels=args.wheels)
    except ValueError as exc:
        parser.error(str(exc))
    print(json.dumps(result))


if __name__ == '__main__':
    main()
