"""Command suffix adapter shared by real plugin registration and the portable CLI."""
import argparse
import json
from pathlib import Path
import time

from pydantic import ValidationError

from ..core.models import TestError
from ..core.shared_settings_store import DEFAULT_CONNECTOR_PORT
from .plugin_settings_file import SettingsFileBridge, strict_json


def read_json(path):
    return strict_json(Path(path).read_bytes())


def command_parser(*, direct=False):
    parser = argparse.ArgumentParser(prog='/bsp-upgrade')
    root = parser.add_subparsers(dest='command', required=True)
    connect = root.add_parser('connect')
    connect.add_argument('operation', nargs='?', choices=['export', 'profile'])
    connect.add_argument('--watch', action='store_true')
    connect.add_argument('--diagnose', action='store_true')
    connect.add_argument('--server'); connect.add_argument('--account')
    connect.add_argument('--ssh-port', type=int); connect.add_argument('--output', type=Path)
    connect.add_argument('--remote-runner-port', type=int)
    connect.add_argument('--remote-dashboard-port', type=int)
    connector = root.add_parser('connector')
    connector.add_argument('operation', choices=['restart', 'receipt', 'verify', 'reconnect-ssh', 'putty', 'rebind'])
    connector.add_argument('command_id', nargs='?')
    connector.add_argument('--board-id'); connector.add_argument('--runner-id')
    status = root.add_parser('status'); status.add_argument('--boards', action='store_true'); status.add_argument('--diagnose', action='store_true')
    monitor = root.add_parser('monitor'); monitor.add_argument('--edit', action='store_true')
    settings = root.add_parser('settings')
    settings.add_argument('operation', nargs='?', default='show', choices=['show', 'edit', 'save', 'discard', 'export', 'import', 'file', 'connector', 'profiles'])
    settings.add_argument('detail', nargs='?'); settings.add_argument('--file', type=Path)
    settings.add_argument('--kind', choices=['commands', 'flash'], default='commands')
    settings.add_argument('--name'); settings.add_argument('--revision'); settings.add_argument('--runner-id')
    settings.add_argument('--expected-revision'); settings.add_argument('--expected-profile-revision')
    test = root.add_parser('test')
    test.add_argument('operation', choices=['list', 'preview', 'run', 'runs', 'select', 'status', 'watch', 'logs', 'pause', 'resume', 'cancel', 'reconcile', 'analyze'])
    test.add_argument('run_id', nargs='?'); test.add_argument('--installer'); test.add_argument('--pattern', action='append')
    test.add_argument('--tc-root', type=Path); test.add_argument('--module')
    test.add_argument('--flash-profile')
    if direct:
        test.add_argument('--flash', action='store_true', help='퓨징 요청에 저장한 BAT와 프로파일 사용')
    test.add_argument('--follow', action='store_true'); test.add_argument('--no-follow', action='store_true')
    test.add_argument('--stream', default='stdout'); test.add_argument('--action', default='MARK_ABORTED'); test.add_argument('--reason', default='')
    test.add_argument('--report', action='store_true'); test.add_argument('--consumer')
    test.add_argument('--requeue', action='store_true'); test.add_argument('--analysis-id')
    return parser


def dispatch(session, args, *, windows_export=None, shared_file=None):
    client = session.client
    if args.command == 'connect':
        if args.operation == 'export':
            if not args.server or not args.account or not args.output:
                raise ValueError('connect export requires --server, --account and --output')
            if windows_export is None: raise ValueError('Windows artifact exporter is not connected')
            if args.ssh_port is None:
                args.ssh_port = 22
            if args.remote_runner_port is None:
                args.remote_runner_port = DEFAULT_CONNECTOR_PORT
            return windows_export(args)
        if args.operation == 'profile':
            raise ValueError('connect profile is available in direct mode')
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
        if args.operation: raise ValueError(f'connect {args.operation} cannot watch')
        session.render = emit
        session.watch()
        return 0
    while True:
        value = dispatch(session, args, windows_export=windows_export, shared_file=shared_file)
        emit(value)
        if not (args.command == 'test' and args.operation == 'logs' and args.follow): return 0
        if value['state'] in {'COMPLETED', 'CANCELLED'}: return 0
        time.sleep(3)


def execute_direct(direct, argv, *, source_root=None, emit=None):
    """Execute /bsp-upgrade command directly against DirectConnectorClient (127.0.0.1:<port>)."""
    args = command_parser(direct=True).parse_args(argv)
    emit = emit or (lambda value: print(json.dumps(value, ensure_ascii=False), flush=True))

    if args.command == 'connect':
        if args.operation and (args.watch or args.diagnose):
            raise ValueError(f'connect {args.operation} cannot use --watch or --diagnose')
        if args.operation == 'profile':
            if not args.server or not args.account:
                raise ValueError('connect profile requires --server and --account')
            if any(value is not None for value in (args.output, args.remote_runner_port, args.remote_dashboard_port)):
                raise ValueError('connect profile accepts --server, --account and --ssh-port')
            try:
                profile = direct.store.save_bootstrap_ssh(
                    server=args.server,
                    account=args.account,
                    ssh_port=args.ssh_port if args.ssh_port is not None else 22,
                )
            except ValidationError:
                raise ValueError('Supply a valid Windows-reachable Linux SSH host, account and port') from None
            emit({'state': 'SAVED', 'bootstrap_ssh': profile})
            return 0
        if args.operation == 'export':
            if args.output is None:
                raise ValueError('connect export requires --output')
            if source_root is None:
                raise ValueError('source_root is required for local connect export')
            from .direct_connector_client import export_windows_bootstrap_local
            preferences = direct.store.read_preferences()
            if args.server is not None or args.account is not None:
                if not args.server or not args.account:
                    raise ValueError('Supply --server and --account together for a one-time override')
                profile = {'server': args.server, 'account': args.account, 'ssh_port': 22}
            else:
                profile = direct.store.read_bootstrap_ssh()
            if profile is None:
                raise ValueError(
                    'Configure Linux SSH once with connect profile --server HOST --account USER, '
                    'or supply both options to connect export'
                )
            try:
                value = export_windows_bootstrap_local(
                    Path(source_root),
                    args.output,
                    server=profile['server'],
                    account=profile['account'],
                    ssh_port=args.ssh_port if args.ssh_port is not None else profile['ssh_port'],
                    remote_runner_port=args.remote_runner_port if args.remote_runner_port is not None else direct.port,
                    remote_dashboard_port=args.remote_dashboard_port,
                    expected_runner_id=preferences.get('expected_runner_id'),
                )
            except ValidationError:
                raise ValueError('Supply a valid Windows-reachable Linux SSH host, account and ports') from None
            emit(value)
            return 0
        if args.watch:
            direct.watch_connection(on_change=emit)
            return 0
        diag = direct.diagnose()
        if diag['linux_diagnostics'].get('reachable'):
            inv = direct.inventory()
            diag['inventory'] = inv
            try:
                shared = direct.store.read()['integration']
                if shared.get('tc_root') and Path(shared['tc_root']).is_dir():
                    direct.push_tc_projection(Path(shared['tc_root']))
            except Exception:
                pass
        emit(diag)
        return 0 if diag['linux_diagnostics'].get('reachable') else 1

    if args.command == 'status':
        diag = direct.diagnose()
        out = {'diagnostics': diag}
        if diag['linux_diagnostics'].get('reachable'):
            inv = direct.inventory()
            out['boards'] = inv.get('boards', [])
            out['runner_id'] = inv.get('runner_id')
            out['active_run'] = inv.get('active_connector_run')
            out['pending_analyses'] = direct.list_analyses(status='PENDING')
        emit(out)
        return 0

    if args.command == 'connector':
        if args.operation == 'verify':
            emit(direct.verify_connection(wait=True))
            return 0
        if args.operation == 'reconnect-ssh':
            emit(direct.reconnect_ssh())
            return 0
        if args.operation == 'putty':
            emit(direct.open_putty(args.board_id))
            return 0
        if args.operation == 'restart':
            emit(direct.restart_connector())
            return 0
        if args.operation == 'rebind':
            emit(direct.rebind_runner(args.runner_id))
            return 0
        if args.operation == 'receipt':
            if not args.command_id:
                raise ValueError('connector receipt requires task_id')
            emit(direct._request('GET', f'/v1/control/tasks/{args.command_id}'))
            return 0

    if args.command == 'settings':
        op = args.operation
        if op == 'file':
            raise ValueError('Direct settings file sync/push is unavailable; use settings export or settings import')
        if op in {'import', 'export', 'save'} and args.detail is not None:
            raise ValueError(f'Unexpected direct settings {op} argument: {args.detail}')
        if op == 'show':
            shared = direct.store.read()
            timeouts = direct.store.read_timeouts()
            storage = direct.store.read_storage_policy()
            prefs = direct.store.read_preferences()
            emit({
                'shared_settings': shared,
                'timeouts': timeouts,
                'storage_policy': storage,
                'connector_preferences': prefs,
            })
            return 0
        if op == 'profiles':
            if args.detail in {None, 'list'}:
                if args.kind == 'commands':
                    emit({'profiles': direct.store.read_command_profiles()})
                else:
                    inv = direct.inventory()
                    emit({'flash_profile_revisions': inv.get('flash_profile_revisions', {}), 'flash_setup': inv.get('flash_setup')})
                return 0
            if args.detail == 'save' and args.file and args.name and args.kind == 'commands':
                val = read_json(args.file)
                emit(direct.store.save_command_profile(args.name, val, expected_revision=args.expected_revision))
                return 0
        if op == 'export':
            exported = direct.store.export()
            if args.file:
                args.file.parent.mkdir(parents=True, exist_ok=True)
                args.file.write_text(json.dumps(exported, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
                emit({'exported': True, 'file': str(args.file), 'expected_revision': exported['expected_revision']})
            else:
                emit(exported)
            return 0
        if op == 'import':
            if args.file is None:
                raise ValueError('Direct settings import requires --file PATH')
            emit(direct.store.import_file(read_json(args.file)))
            return 0
        if op == 'save' and args.file:
            val = read_json(args.file)
            if 'integration' in val and 'timeouts' in val and 'expected_revision' in val:
                emit(direct.store.save({
                    'expected_revision': val['expected_revision'],
                    'integration': val['integration'],
                    'timeouts': val['timeouts'],
                }))
                return 0
            if 'timeouts' in val:
                cur_t = direct.store.read_timeouts()
                direct.store.save_timeouts(dict(val['timeouts'], expected_revision=cur_t['revision']))
            if 'storage_policy' in val:
                cur_s = direct.store.read_storage_policy()
                direct.store.save_storage_policy(dict(val['storage_policy'], expected_revision=cur_s['revision']))
            shared_patch = {k: val[k] for k in ('installer_roots', 'source_roots', 'installer_path', 'flash_profile', 'tc_root', 'module_defaults', 'global_defaults') if k in val}
            if shared_patch:
                cur = direct.store.read()
                if 'flash_profile' in shared_patch and shared_patch['flash_profile'] != cur['integration'].get('flash_profile'):
                    shared_patch['flash_profile_revision'] = None
                direct.store.save({'expected_revision': cur['revision'], 'integration': cur['integration'] | shared_patch, 'timeouts': {k: v for k, v in cur['timeouts'].items() if k != 'revision'}})
            emit({'saved': True})
            return 0
        if op == 'connector':
            if args.detail in {None, 'apply'} and args.file:
                emit(direct.update_connector_settings(read_json(args.file)))
                return 0
            emit(direct.connector_settings())
            return 0
        raise ValueError(f'Unsupported direct settings operation: {op}')

    if args.command == 'test':
        op = args.operation
        if args.flash and op not in {'preview', 'run'}:
            raise ValueError('--flash는 test preview 또는 test run에 사용하세요.')
        if op == 'list':
            try:
                res = direct.push_tc_projection()
                emit({'projected': True, 'catalog': res['catalog'], 'ack': res['ack']})
            except TestError:
                shared = direct.store.read()['integration']
                from ..core.discovery import discover
                root = Path(shared.get('tc_root') or '').expanduser()
                if not str(root) or not root.is_dir():
                    raise
                emit({'projected': False, 'catalog': discover(root)})
            return 0
        def _follow_with_auto_analysis(initial_run_id: str) -> dict:
            cur_id = initial_run_id
            while True:
                cur = direct.watch_run(cur_id)
                if cur.get('detached'):
                    return cur
                if cur.get('state') == 'PAUSED' and cur.get('pause_reason') == 'FAILURE_STOP_LATCH':
                    decision = direct.analyze_once(run_id=cur_id, consumer=args.consumer)
                    if not decision:
                        return direct.get_run(cur_id)
                    enforced = ((decision.get('analysis') or {}).get('decision') or {}).get('enforced_verdict')
                    if enforced == 'RETRY' or (decision.get('run') or {}).get('state') == 'QUEUED':
                        continue
                    child_id = (decision.get('child_run') or {}).get('run_id')
                    if enforced == 'REPREPARE' and child_id:
                        cur_id = child_id
                        continue
                    return decision.get('run') or direct.get_run(cur_id)
                return cur

        if op in {'preview', 'run'}:
            installer = args.installer
            profile = args.flash_profile
            if args.flash:
                saved = direct.store.read()['integration']
                installer = installer or saved.get('installer_path')
                profile = profile or saved.get('flash_profile')
                if not installer or not profile:
                    raise ValueError('보드 커넥터의 이미지 퓨징 설정에서 Linux 설치 BAT와 플래싱 프로파일을 지정하세요.')
            options = dict(tc_root=args.tc_root, patterns=args.pattern, module=args.module,
                           installer=Path(installer) if installer else None, flash_profile=profile or 'default')
            if op == 'preview':
                emit(direct.preview_run(**options))
                return 0
            run = direct.start_run(**options)
            if args.no_follow:
                emit(run)
                return 0
            emit(_follow_with_auto_analysis(run['run_id']))
            return 0
        def _selected_run_id():
            if args.run_id:
                return args.run_id
            sel_file = direct.state_dir / 'selected-run.txt'
            if sel_file.is_file():
                val = sel_file.read_text(encoding='utf-8').strip()
                if val:
                    return val
            return None

        if op == 'select':
            if not args.run_id:
                raise ValueError('test select requires a run ID')
            run = direct.get_run(args.run_id)
            direct.state_dir.mkdir(parents=True, exist_ok=True)
            (direct.state_dir / 'selected-run.txt').write_text(run['run_id'], encoding='utf-8')
            emit({'selected_run_id': run['run_id'], 'state': run['state']})
            return 0
        if op == 'watch':
            run = direct.get_run(_selected_run_id())
            emit(_follow_with_auto_analysis(run['run_id']))
            return 0
        if op == 'runs':
            emit({'runs': direct.list_runs()})
            return 0
        if op == 'status':
            emit(direct.get_run(_selected_run_id()))
            return 0
        if op == 'pause':
            run = direct.get_run(_selected_run_id())
            emit(direct.pause_run(run['run_id']))
            return 0
        if op == 'resume':
            run = direct.get_run(_selected_run_id())
            emit(direct.resume_run(run['run_id']))
            return 0
        if op == 'cancel':
            run = direct.get_run(_selected_run_id())
            emit(direct.cancel_run(run['run_id']))
            return 0
        if op == 'reconcile':
            run = direct.get_run(_selected_run_id())
            emit(direct.reconcile_run(run['run_id'], action=args.action, reason=args.reason))
            return 0
        if op == 'logs':
            run = direct.get_run(_selected_run_id())
            if args.follow:
                emit(direct.watch_run(run['run_id'], on_log=lambda s, txt: emit({'stream': s, 'text': txt})))
                return 0
            logs = []
            for att in run.get('attempts', []):
                logs.append({
                    'attempt_id': att['attempt_id'],
                    'phase': att['phase'],
                    'stream': args.stream,
                    'log': direct.read_logs(run['run_id'], att['attempt_id'], stream=args.stream),
                })
            emit({'run_id': run['run_id'], 'state': run['state'], 'attempts': logs})
            return 0
        if op == 'analyze':
            decision = direct.analyze_once(
                run_id=args.run_id,
                analysis_id=args.analysis_id,
                consumer=args.consumer,
            )
            emit(decision or {'status': 'NO_PENDING_ANALYSES'})
            return 0

    raise ValueError('Unsupported direct plugin command')
