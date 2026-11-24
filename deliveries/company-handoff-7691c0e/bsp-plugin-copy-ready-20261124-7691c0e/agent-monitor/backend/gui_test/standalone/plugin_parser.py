"""Standard-library argument schema shared by the launcher and dispatchers."""
import argparse
from pathlib import Path


class StrictParser(argparse.ArgumentParser):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, allow_abbrev=False, **kwargs)


def command_parser(*, direct=False):
    parser = StrictParser(prog='/bsp-upgrade')
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
    test.add_argument('operation', choices=['list', 'preview', 'run', 'runs', 'select', 'status', 'watch', 'logs', 'pause', 'resume', 'cancel', 'reconcile', 'analyze'] + (['prepare', 'send'] if direct else []))
    test.add_argument('run_id', nargs='?'); test.add_argument('--installer'); test.add_argument('--pattern', action='append')
    test.add_argument('--tc-root', type=Path); test.add_argument('--module')
    test.add_argument('--flash-profile')
    if direct:
        test.add_argument('--build')
        test.add_argument('--file', type=Path)
        test.add_argument('--flash', action='store_true', help='퓨징 요청에 저장한 BAT와 프로파일 사용')
    test.add_argument('--follow', action='store_true'); test.add_argument('--no-follow', action='store_true')
    test.add_argument('--stream', default='stdout'); test.add_argument('--action', default='MARK_ABORTED'); test.add_argument('--reason', default='')
    test.add_argument('--report', action='store_true'); test.add_argument('--consumer')
    test.add_argument('--requeue', action='store_true'); test.add_argument('--analysis-id')
    if direct:
        connect.add_argument('--read-only', action='store_true', help='Observe without writing to Windows')
        connect.add_argument('--no-provision', action='store_true', help='Require a preinstalled Python environment')
        for subcommand in (connect, status, test):
            subcommand.add_argument('--json', action='store_true', help='Versioned UTF-8 JSON lines for observation')
    return parser


def parse_direct_args(argv):
    parser = command_parser(direct=True)
    args = parser.parse_args(argv)
    machine = getattr(args, 'json', False)
    if machine and not (args.command == 'status'
                        or (args.command == 'connect' and args.watch and not args.operation)
                        or (args.command == 'test' and args.operation in {'status', 'watch'})):
        parser.error('--json is supported for status, connect --watch, test status and test watch')
    if args.command == 'connect' and (args.read_only or args.no_provision) and (not args.watch or args.operation):
        parser.error('--read-only and --no-provision require connect --watch')
    return args


def module_parser():
    parser = StrictParser(prog='modules')
    sub = parser.add_subparsers(dest='operation', required=True)
    commands = [sub.add_parser('list'), sub.add_parser('publish')]
    for op in commands:
        op.add_argument('--runtime-id')
        op.add_argument('--package-version')
    commands[1].add_argument('--file', type=Path, required=True)
    commands[1].add_argument('--expected-version', type=int, required=True)
    return parser
