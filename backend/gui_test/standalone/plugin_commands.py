"""Command suffix adapter shared by real plugin registration and the portable CLI."""
import argparse
import json
from pathlib import Path
import time

from ..core.models import TestError
from .plugin_settings_file import SettingsFileBridge, strict_json


def read_json(path):
    return strict_json(Path(path).read_bytes())


def command_parser():
    parser = argparse.ArgumentParser(prog='/bsp-upgrade')
    root = parser.add_subparsers(dest='command', required=True)
    connect = root.add_parser('connect')
    connect.add_argument('operation', nargs='?', choices=['export'])
    connect.add_argument('--watch', action='store_true')
    connect.add_argument('--server'); connect.add_argument('--account')
    connect.add_argument('--ssh-port', type=int, default=22); connect.add_argument('--output', type=Path)
    connector = root.add_parser('connector'); connector.add_argument('operation', choices=['restart', 'receipt']); connector.add_argument('command_id', nargs='?')
    status = root.add_parser('status'); status.add_argument('--boards', action='store_true'); status.add_argument('--diagnose', action='store_true')
    monitor = root.add_parser('monitor'); monitor.add_argument('--edit', action='store_true')
    settings = root.add_parser('settings')
    settings.add_argument('operation', nargs='?', default='show', choices=['show', 'edit', 'save', 'discard', 'export', 'import', 'file', 'connector', 'profiles'])
    settings.add_argument('detail', nargs='?'); settings.add_argument('--file', type=Path)
    settings.add_argument('--kind', choices=['commands', 'flash'], default='commands')
    settings.add_argument('--name'); settings.add_argument('--revision'); settings.add_argument('--runner-id')
    settings.add_argument('--expected-revision'); settings.add_argument('--expected-profile-revision')
    test = root.add_parser('test')
    test.add_argument('operation', choices=['list', 'preview', 'run', 'runs', 'select', 'status', 'logs', 'pause', 'resume', 'cancel', 'reconcile', 'analyze'])
    test.add_argument('run_id', nargs='?'); test.add_argument('--installer'); test.add_argument('--pattern', action='append')
    test.add_argument('--follow', action='store_true'); test.add_argument('--report', action='store_true')
    test.add_argument('--requeue', action='store_true'); test.add_argument('--analysis-id')
    return parser


def dispatch(session, args, *, windows_export=None, shared_file=None):
    client = session.client
    if args.command == 'connect':
        if args.operation == 'export':
            if not args.server or not args.account or not args.output:
                raise ValueError('connect export requires --server, --account and --output')
            if windows_export is None: raise ValueError('Windows artifact exporter is not connected')
            return windows_export(args)
        return session.refresh()
    if args.command == 'connector':
        return session.connector_action('restart') if args.operation == 'restart' else session.connector_receipt(args.command_id)
    if args.command == 'status': return session.refresh()
    if args.command == 'monitor': return client.browser_access(scopes=['settings', 'control'] if args.edit else None)
    if args.command == 'settings':
        op = args.operation
        if op == 'show': return client.settings()
        if op == 'edit':
            session.begin_edit()
            return session.edit(read_json(args.file)) if args.file else session.begin_edit()
        if op == 'save': return session.save_edit()
        if op == 'discard': session.discard_edit(); return {'state': 'DRAFT_DISCARDED'}
        if op == 'export':
            return SettingsFileBridge(client, args.file).sync() if args.file else client.export_settings()
        if op in {'import', 'file'}:
            path = args.file or shared_file
            if path is None: raise ValueError('A shared external settings file is required')
            bridge = SettingsFileBridge(client, path)
            if op == 'import' or args.detail == 'push': return bridge.push()
            if args.detail not in {None, 'sync'}: raise ValueError('settings file supports sync or push')
            return bridge.sync()
        if op == 'connector':
            if args.detail == 'receipt': return session.connector_receipt()
            if args.detail not in {None, 'apply'}: raise ValueError('settings connector supports apply or receipt')
            return session.apply_connector(read_json(args.file) if args.file else None)
        if op == 'profiles':
            if args.detail in {None, 'list'}:
                return client.command_profiles() if args.kind == 'commands' else client.flash_profiles()
            if not args.name: raise ValueError('Profile --name is required')
            if args.detail == 'select':
                if not args.revision or not args.expected_revision: raise ValueError('Profile and settings revisions are required')
                return client.select_profile(args.kind, args.name, revision=args.revision, expected_settings_revision=args.expected_revision)
            if args.detail == 'save' and args.file:
                value = read_json(args.file)
                if args.kind == 'commands': return client.save_command_profile(args.name, value, expected_revision=args.expected_revision)
                if not args.runner_id: raise ValueError('Flash --runner-id is required')
                return client.save_flash_profile(args.name, value, runner_id=args.runner_id,
                    expected_revision=args.expected_revision, expected_profile_revision=args.expected_profile_revision)
            raise ValueError('settings profiles supports list, save --file, or select')
    if args.command == 'test':
        op = args.operation
        if op == 'list':
            if args.run_id or args.installer or args.pattern:
                raise ValueError('test list reads the common TC folder; use test preview for installer/pattern selection')
            return client.connector_test_status()
        if op == 'preview':
            if args.run_id:
                return client.preparation(args.run_id)
            return dict(session.preview(args.installer, args.pattern), scope='selected-integration-preview',
                        hint='Repeat test preview <preparation_id> to read the fixed TC list; server prepares asynchronously')
        if op == 'run': return session.start(args.installer, args.pattern)
        if op == 'runs': return session.runs()
        if op == 'select':
            if not args.run_id: raise ValueError('test select requires an execution ID')
            return session.select(args.run_id)
        if op in {'pause', 'resume', 'cancel', 'reconcile'}: return session.action(op, args.run_id)
        run = session.run(args.run_id)
        if op == 'status':
            return {'run': run, 'events': client.events(run['id'])} if args.report else run
        if op == 'logs':
            logs = []
            for attempt in run.get('attempts', []):
                identity = attempt.get('id')
                if identity:
                    logs.append({'attempt_id': identity, 'stdout': client.attempt_log(run['id'], identity),
                                 'stderr': client.attempt_log(run['id'], identity, 'stderr')})
            return {'run_id': run['id'], 'state': run['state'], 'attempts': logs, 'console': client.board_console(), 'errors': client.connector_errors()}
        if op == 'analyze':
            analyses = [item for item in client.analyses()['analyses'] if item.get('run_id') == run['id']]
            if args.requeue:
                matches = [item for item in analyses if item['id'] == args.analysis_id]
                if len(matches) != 1: raise ValueError('Requeue requires the matching --analysis-id')
                return client.requeue_analysis(matches[0]['id'], run['version'])
            return {'run_id': run['id'], 'analyses': analyses, 'runtime': client.analysis_status()}
    raise ValueError('Unsupported plugin command')


def execute(session, argv, *, windows_export=None, shared_file=None, emit=None):
    args = command_parser().parse_args(argv)
    emit = emit or (lambda value: print(json.dumps(value, ensure_ascii=False), flush=True))
    if args.command == 'connect' and args.watch:
        if args.operation: raise ValueError('connect export cannot watch')
        session.render = emit
        session.watch()
        return 0
    while True:
        value = dispatch(session, args, windows_export=windows_export, shared_file=shared_file)
        emit(value)
        if not (args.command == 'test' and args.operation == 'logs' and args.follow): return 0
        if value['state'] in {'COMPLETED', 'CANCELLED'}: return 0
        time.sleep(3)
