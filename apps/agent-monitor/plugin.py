"""Standard-library host entry; copy this whole delivery into the plugin repo."""
import argparse
import json
from pathlib import Path
import subprocess
import sys

HERE = Path(__file__).resolve().parent
SOURCE = HERE / 'agent-monitor' if (HERE / 'agent-monitor/apps/agent-monitor/manage.py').is_file() else HERE.parents[1]
APP = SOURCE / 'apps/agent-monitor'
if str(APP) not in sys.path: sys.path.insert(0, str(APP))

HELP = '''/bsp-upgrade commands (pass the suffix to plugin.py):
connect [--diagnose] | connect export --server HOST --account USER --output NEW_DIR
status [--boards / --diagnose] | monitor | connector verify|reconnect-ssh|putty|restart|rebind|receipt [ID]
settings [show / edit / save / discard / export / import / file / connector / profiles]
test list | preview | run [--no-follow] | watch [ID] | runs | status [ID]
test logs [ID] [--follow] | pause/resume/cancel/reconcile [ID] | analyze [ID]
export --output NEW_DIRECTORY [--without-ui] | verify PACKAGE_DIRECTORY
Global options before commands: --home PATH --runtime PATH --project KEY --state-dir PATH --port PORT --connector-port PORT
Shared settings: settings file sync|push --file PATH (outside both Git repositories)
'''


def manager_result(action, home, *, port=None, runtime=None):
    argv = [sys.executable, str(APP / 'manage.py'), action, '--home', str(home), '--source', str(SOURCE)]
    if port is not None: argv += ['--port', str(port)]
    if runtime is not None: argv += ['--runtime', str(runtime)]
    result = subprocess.run(argv, stdout=subprocess.PIPE, text=True, check=True)
    return json.loads(result.stdout)


def _has_direct_deps():
    try:
        import httpx  # noqa: F401
        import pydantic  # noqa: F401
        return True
    except ImportError:
        return False


def main(argv=None):
    parser = argparse.ArgumentParser(description='Copyable BSP plugin interface', add_help=False)
    parser.add_argument('--home', type=Path, default=Path.home() / '.local/share/bsp-agent-monitor')
    parser.add_argument('--runtime', type=Path)
    parser.add_argument('--state-dir', type=Path)
    parser.add_argument('--project', default=str(Path.cwd().resolve()))
    parser.add_argument('--port', type=int)
    parser.add_argument('--monitor-port', type=int)
    parser.add_argument('--connector-port', type=int)
    parser.add_argument('--_dispatch', action='store_true')
    options, command = parser.parse_known_args(argv)
    if not command or command[0] in {'help', '--help', '-h'}:
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
    try:
        from plugin_delivery import export_plugin, verify_plugin, PACKAGE, windows_directory
        if (HERE / PACKAGE).is_file(): verify_plugin(HERE)
        if command[0] == 'export':
            export_parser = argparse.ArgumentParser(); export_parser.add_argument('--output', type=Path, required=True)
            export_parser.add_argument('--without-ui', action='store_true')
            args = export_parser.parse_args(command[1:])
            result = export_plugin(SOURCE, args.output, include_ui=not args.without_ui)
            print(json.dumps({'state': 'EXPORTED', 'output': str(args.output), 'release': result['release'], 'windows': result['windows']})); return 0
        if command[0] == 'verify':
            if len(command) != 2: raise ValueError('verify requires a package directory')
            result = verify_plugin(command[1]); print(json.dumps({'state': 'VERIFIED', 'release': result['release']})); return 0
        home = options.home.expanduser().resolve()
        state_dir = options.state_dir or home / 'plugin-state'

        # Direct Connector path: connect / status / connector / settings / test NEVER start Agent Monitor (8766).
        if command[0] != 'monitor':
            if not options._dispatch and not _has_direct_deps():
                prep = manager_result('prepare-env', home, runtime=options.runtime)
                release = Path(prep['path'])
                reexec = [
                    str(release / '.venv/bin/python'), str(APP / 'plugin.py'),
                    '--_dispatch', '--home', str(home), '--state-dir', str(state_dir), '--project', options.project,
                ]
                if options.runtime is not None:
                    reexec += ['--runtime', str(options.runtime)]
                if options.connector_port is not None:
                    reexec += ['--connector-port', str(options.connector_port)]
                return subprocess.run([*reexec, *command], stdin=None).returncode

            if str(SOURCE) not in sys.path:
                sys.path.insert(0, str(SOURCE))
            from backend.gui_test.standalone.direct_connector_client import DirectConnectorClient
            from backend.gui_test.standalone.plugin_commands import execute_direct
            direct = DirectConnectorClient(
                home=home,
                runtime_dir=options.runtime,
                connector_port=options.connector_port,
                state_dir=state_dir,
            )
            try:
                return execute_direct(direct, command, source_root=SOURCE)
            finally:
                direct.close()

        if not options._dispatch:
            # monitor command only: ensure Agent Monitor is running
            result = manager_result('status', home)
            if result['state'] != 'READY':
                receipt_path = home / 'service.json'
                receipt = json.loads(receipt_path.read_text()) if receipt_path.exists() else {}
                port = monitor_port if monitor_port is not None else receipt.get('port', 8766)
                result = manager_result('start', home, port=port, runtime=options.runtime)
            if result['state'] != 'READY':
                print(json.dumps(result, ensure_ascii=False)); return 1
            if monitor_port is not None and result['url'] != 'http://127.0.0.1:' + str(monitor_port):
                raise ValueError('Configured service uses another port; keep its existing home/port')
            current = json.loads((home / 'current.json').read_text())
            release = Path(current['path'])
            if result['release'] != current['release']: raise ValueError('Managed release identity changed')
            if (release / 'requirements.lock').read_bytes() != (SOURCE / 'requirements.lock').read_bytes():
                raise ValueError('UPDATE_REQUIRED: dependency locks differ; update the managed release safely first')
            return subprocess.run([str(release / '.venv/bin/python'), str(APP / 'plugin.py'),
                '--_dispatch', '--home', str(home), '--state-dir', str(state_dir), '--project', options.project, *command],
                stdin=None).returncode
        result = manager_result('status', home)
        if result['state'] != 'READY': raise ValueError('Managed service is not READY')
        sys.path.insert(0, str(SOURCE))
        from backend.gui_test.standalone.plugin_client import PluginClient
        from backend.gui_test.standalone.plugin_runtime import PluginSession
        from backend.gui_test.standalone.plugin_commands import execute
        health = result['health']
        client = PluginClient(result['url'], expected_identity={key: health[key] for key in ('runtime_id', 'package_version')}, log_dir=home / 'plugin-logs')
        session = PluginSession(client, project=options.project, state_dir=state_dir)
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
