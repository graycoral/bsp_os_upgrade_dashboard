"""Standard-library host entry; copy this whole delivery into the plugin repo."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys

HERE = Path(__file__).resolve().parent
SOURCE = HERE / 'agent-monitor' if (HERE / 'agent-monitor/apps/agent-monitor/manage.py').is_file() else HERE.parents[1]
APP = SOURCE / 'apps/agent-monitor'
if str(APP) not in sys.path: sys.path.insert(0, str(APP))

HELP = '''/bsp-upgrade commands (pass the suffix to plugin.py):
connect [--watch [--json] [--read-only] [--no-provision] / --diagnose] | connect profile --server HOST --account USER [--ssh-port PORT]
connect export --output NEW_DIR [--server HOST --account USER] [--remote-dashboard-port PORT | --without-monitor]
status [--json / --boards / --diagnose] | monitor | connector verify|reconnect-ssh|putty|restart|rebind|receipt [ID]
monitor status  (inspect package-derived release, installed release and running Monitor)
monitor ensure [--no-provision]  (start or reuse the managed Monitor without issuing browser access)
settings [show / export / import / connector / profiles]
test list | preview [--flash] | run [--flash] [--no-follow] | watch [ID] [--json] | runs | status [ID] [--json]
test logs [ID] [--follow] | pause/resume/cancel/reconcile [ID] | analyze [ID]
export --output NEW_DIRECTORY [--without-ui] [--without-agent-instructions] | verify PACKAGE_DIRECTORY [--pristine]
Global options before commands: --home PATH --runtime PATH --project KEY --project-root PATH --state-dir PATH --monitor-port PORT (--port alias) --connector-port PORT
test prepare --file NEW_FILE --build BUILD [--flash] | test send --file FILE [--flash]
modules list | modules publish --file FILE --expected-version N
release-evidence PRIOR CURRENT --output NEW_DIR | verify-evidence PRIOR CURRENT EVIDENCE_DIR --sha256 HASH
Direct settings: settings export [--file PATH] | settings import --file PATH (revision checked)
'''


def manager_command(action, home, *, port=None, runtime=None):
    argv = [sys.executable, '-B', str(APP / 'manage.py'), action, '--home', str(home), '--source', str(SOURCE)]
    if port is not None: argv += ['--port', str(port)]
    if runtime is not None: argv += ['--runtime', str(runtime)]
    return argv


def manager_result(action, home, *, port=None, runtime=None):
    result = subprocess.run(manager_command(action, home, port=port, runtime=runtime),
                            stdout=subprocess.PIPE, text=True, check=True)
    return json.loads(result.stdout)


def export_monitor_port(home, runtime):
    from manage import managed_monitor_port
    return managed_monitor_port(home, runtime)


def _has_direct_deps():
    try:
        import httpx  # noqa: F401
        import pydantic  # noqa: F401
        return True
    except ImportError:
        return False


def installed_watch_release(home):
    from manage import read, valid_environment
    try:
        installed = read(home / 'current.json')
        if not isinstance(installed, dict) or not isinstance(installed.get('path'), str):
            return None
        release = Path(installed['path'])
        if (release.is_absolute()
                and (release / 'requirements.lock').read_bytes() == (SOURCE / 'requirements.lock').read_bytes()
                and valid_environment(release)):
            return release
    except (OSError, ValueError):
        pass
    return None


def watch_environment_ready():
    if sys.prefix == sys.base_prefix:
        return False
    try:
        from backend.gui_test.standalone.direct_connector_client import DirectConnectorClient
        from backend.gui_test.standalone.plugin_commands import execute_direct
        return True
    except (ImportError, AttributeError, TypeError):
        return False


def main(argv=None):
    parser = argparse.ArgumentParser(description='Copyable BSP plugin interface', add_help=False, allow_abbrev=False)
    parser.add_argument('--home', type=Path, default=Path.home() / '.local/share/bsp-agent-monitor')
    parser.add_argument('--runtime', type=Path)
    parser.add_argument('--state-dir', type=Path)
    parser.add_argument('--project')
    parser.add_argument('--project-root', type=Path)
    parser.add_argument('--port', type=int)
    parser.add_argument('--monitor-port', type=int)
    parser.add_argument('--connector-port', type=int)
    parser.add_argument('--_dispatch', action='store_true')
    parser.add_argument('-h', '--help', action='store_true')
    parser.add_argument('command', nargs=argparse.REMAINDER)
    options = parser.parse_args(argv)
    command = options.command
    project_key = options.project or str(Path.cwd().resolve())
    if command[:1] == ['help'] and len(command) > 1:
        parser.error('help takes no arguments')
    if not command or options.help or command == ['help']:
        print(HELP); return 0
    if options.port is not None and options.monitor_port is not None and options.port != options.monitor_port:
        parser.error('--port and --monitor-port conflict')
    monitor_port = options.monitor_port if options.monitor_port is not None else options.port
    for p_val in (monitor_port, options.connector_port):
        if p_val is not None and not 1 <= p_val <= 65535:
            parser.error('Invalid port')
    if monitor_port is not None and options.connector_port is not None and monitor_port == options.connector_port:
        print(json.dumps({
            'state': 'ERROR',
            'code': 'PORT_CONFLICT',
            'message': f'--port/--monitor-port ({monitor_port}) and --connector-port ({options.connector_port}) cannot be identical',
        }, ensure_ascii=False), file=sys.stderr)
        return 1
    if (HERE / 'PLUGIN_PACKAGE.json').is_file() or (SOURCE / 'AGENT_MONITOR_SOURCE.json').is_file():
        sys.dont_write_bytecode = True
    try:
        from plugin_delivery import export_plugin, verify_plugin, PACKAGE, windows_directory
        if (HERE / PACKAGE).is_file(): verify_plugin(HERE)
        if str(SOURCE) not in sys.path:
            sys.path.insert(0, str(SOURCE))
        from backend.gui_test.core.plugin_paths import external_output, project_directory
        project_root = project_directory(options.project, options.project_root)
        home = options.home.expanduser().resolve()
        managed_packages = (home / 'releases',)
        if command[0] == 'export':
            export_parser = argparse.ArgumentParser(allow_abbrev=False); export_parser.add_argument('--output', type=Path, required=True)
            export_parser.add_argument('--without-ui', action='store_true')
            export_parser.add_argument('--without-agent-instructions', action='store_true')
            args = export_parser.parse_args(command[1:])
            args.output = external_output(args.output, SOURCE, project_root=project_root, additional_roots=managed_packages)
            result = export_plugin(SOURCE, args.output, include_ui=not args.without_ui,
                                   without_agent_instructions=args.without_agent_instructions)
            print(json.dumps({'state': 'EXPORTED', 'output': str(args.output), 'release': result['release'], 'windows': result['windows']})); return 0
        if command[0] in {'release-evidence', 'verify-evidence'}:
            from plugin_delivery import write_evidence, verify_evidence
            evidence = argparse.ArgumentParser(prog=command[0], allow_abbrev=False)
            evidence.add_argument('prior', type=Path)
            evidence.add_argument('current', type=Path)
            if command[0] == 'release-evidence':
                evidence.add_argument('--output', type=Path, required=True)
                args = evidence.parse_args(command[1:])
                output = external_output(args.output, SOURCE, project_root=project_root,
                                         additional_roots=(*managed_packages, args.prior, args.current))
                result = write_evidence(args.prior, args.current, output)
            else:
                evidence.add_argument('directory', type=Path)
                evidence.add_argument('--sha256', required=True)
                args = evidence.parse_args(command[1:])
                result = verify_evidence(args.prior, args.current, args.directory, args.sha256)
            print(json.dumps(result))
            return 0
        if command[0] == 'verify':
            verify_parser = argparse.ArgumentParser(prog='plugin.py verify', allow_abbrev=False)
            verify_parser.add_argument('package', type=Path)
            verify_parser.add_argument('--pristine', action='store_true')
            args = verify_parser.parse_args(command[1:])
            result = verify_plugin(args.package, pristine=args.pristine)
            print(json.dumps({'state': 'VERIFIED', 'release': result['release']})); return 0
        state_dir = options.state_dir or home / 'plugin-state'
        from backend.gui_test.standalone.plugin_parser import module_parser, parse_direct_args
        no_provision = False
        if command[0] == 'modules':
            module_parser().parse_args(command[1:])
        elif command != ['monitor', 'status']:
            parsed = parse_direct_args(command)
            no_provision = parsed.command == 'connect' and parsed.no_provision
            if parsed.command == 'monitor' and parsed.operation == 'ensure':
                ensure = manager_command('ensure', home, port=monitor_port, runtime=options.runtime)
                if parsed.no_provision:
                    ensure.append('--no-provision')
                if options.connector_port is not None:
                    ensure += ['--connector-port', str(options.connector_port)]
                return subprocess.run(ensure).returncode
        if command[0:2] == ['settings', 'file']:
            print(json.dumps({'state': 'ERROR', 'code': 'UNSUPPORTED_DIRECT_SETTINGS',
                              'message': 'Use settings export or settings import in direct mode.'}), file=sys.stderr)
            return 1

        # Direct Connector path: connect / status / connector / settings / test NEVER start Agent Monitor (8766).
        if command[0] != 'monitor':
            usable = watch_environment_ready() if no_provision else _has_direct_deps()
            if not usable and (no_provision or not options._dispatch):
                if no_provision:
                    release = None if options._dispatch else installed_watch_release(home)
                    if release is None:
                        print(json.dumps({'state': 'ERROR', 'code': 'NOT_PROVISIONED',
                                          'message': 'A provisioned plugin virtual environment is required.'}), file=sys.stderr)
                        return 6
                else:
                    prep = manager_result('prepare-env', home, runtime=options.runtime)
                    release = Path(prep['path'])
                reexec = [
                    str(release / '.venv/bin/python'), str(APP / 'plugin.py'),
                    '--_dispatch', '--home', str(home), '--state-dir', str(state_dir),
                ]
                if options.project is not None:
                    reexec += ['--project', options.project]
                reexec += ['--project-root', str(project_root)]
                if monitor_port is not None:
                    reexec += ['--monitor-port', str(monitor_port)]
                if options.runtime is not None:
                    reexec += ['--runtime', str(options.runtime)]
                if options.connector_port is not None:
                    reexec += ['--connector-port', str(options.connector_port)]
                if ((command[0] == 'connect' and '--watch' in command)
                        or (command[:2] == ['test', 'watch'] and '--json' in command)):
                    # Supervisor signals and lifetime follow the actual observer.
                    os.execv(reexec[0], [*reexec, *command])
                return subprocess.run([*reexec, *command], stdin=None).returncode

            if str(SOURCE) not in sys.path:
                sys.path.insert(0, str(SOURCE))
            if command[0] == 'modules':
                from backend.gui_test.standalone.module_commands import execute_modules
                return execute_modules(command[1:], home=home, port=monitor_port,
                                       managed_status=lambda: manager_result('status', home, runtime=options.runtime))
            from backend.gui_test.standalone.direct_connector_client import DirectConnectorClient
            from backend.gui_test.standalone.plugin_commands import execute_direct
            direct = DirectConnectorClient(
                home=home,
                runtime_dir=options.runtime,
                connector_port=options.connector_port,
                state_dir=state_dir,
                project=options.project,
            )
            try:
                return execute_direct(direct, command, source_root=SOURCE, project=project_key, project_root=project_root,
                                      monitor_port=monitor_port,
                                      managed_monitor_port=lambda: export_monitor_port(home, direct.runtime_dir))
            finally:
                direct.close()

        if not options._dispatch:
            # monitor command only: ensure Agent Monitor is running
            result = manager_result('status', home, runtime=options.runtime)
            if command == ['monitor', 'status']:
                print(json.dumps(result, ensure_ascii=False)); return 0
            if result.get('deployment', {}).get('state') in {'UPDATE_REQUIRED', 'UNVERIFIED'}:
                print(json.dumps(result, ensure_ascii=False)); return 1
            if result['state'] != 'READY':
                receipt_path = home / 'service.json'
                receipt = json.loads(receipt_path.read_text()) if receipt_path.exists() else {}
                port = monitor_port if monitor_port is not None else receipt.get('port', 8766)
                result = manager_result('start', home, port=port, runtime=options.runtime)
            if result['state'] == 'READY':
                result = manager_result('status', home, runtime=options.runtime)
            if result['state'] != 'READY' or result.get('deployment', {}).get('state') in {'UPDATE_REQUIRED', 'UNVERIFIED'}:
                print(json.dumps(result, ensure_ascii=False)); return 1
            if monitor_port is not None and result['url'] != 'http://127.0.0.1:' + str(monitor_port):
                raise ValueError('Configured service uses another port; keep its existing home/port')
            current = json.loads((home / 'current.json').read_text())
            release = Path(current['path'])
            if result['release'] != current['release']: raise ValueError('Managed release identity changed')
            if (release / 'requirements.lock').read_bytes() != (SOURCE / 'requirements.lock').read_bytes():
                raise ValueError('UPDATE_REQUIRED: dependency locks differ; update the managed release safely first')
            return subprocess.run([str(release / '.venv/bin/python'), str(APP / 'plugin.py'),
                '--_dispatch', '--home', str(home), '--state-dir', str(state_dir), '--project', project_key, *command],
                stdin=None).returncode
        result = manager_result('status', home)
        if result['state'] != 'READY' or result.get('deployment', {}).get('state') in {'UPDATE_REQUIRED', 'UNVERIFIED'}:
            print(json.dumps(result, ensure_ascii=False)); return 1
        sys.path.insert(0, str(SOURCE))
        from backend.gui_test.standalone.plugin_client import PluginClient
        from backend.gui_test.standalone.plugin_runtime import PluginSession
        from backend.gui_test.standalone.plugin_commands import execute
        health = result['health']
        client = PluginClient(result['url'], expected_identity={key: health[key] for key in ('runtime_id', 'package_version')}, log_dir=home / 'plugin-logs')
        session = PluginSession(client, project=project_key, state_dir=state_dir)
        def export_windows(args):
            profile = client.export_connector_bootstrap(server=args.server, account=args.account,
                ssh_port=args.ssh_port, remote_dashboard_port=int(result['url'].rsplit(':', 1)[1]))
            if (SOURCE / 'AGENT_MONITOR_SOURCE.json').is_file():
                return windows_directory(SOURCE, args.output, profile=profile)
            import tempfile
            from delivery import export
            with tempfile.TemporaryDirectory(prefix='plugin-board-source-') as temporary:
                snapshot = Path(temporary) / 'source'
                export(SOURCE, snapshot, include_ui=False)
                return windows_directory(snapshot, args.output, profile=profile)
        try:
            return execute(session, command, windows_export=export_windows, shared_file=home / 'shared/settings.json')
        finally:
            session.close(); client.client.close()
    except KeyboardInterrupt:
        return 130
    except Exception as exc:
        # Contract validation and transport already redact API diagnostics; never
        # dump response objects, environments or Python tracebacks to the plugin.
        message = getattr(exc, 'message', None) or str(exc)
        print(json.dumps({'state': 'ERROR', 'code': getattr(exc, 'code', 'PLUGIN_FAILED'), 'message': message}, ensure_ascii=False), file=sys.stderr)
        return 1


if __name__ == '__main__': raise SystemExit(main())
