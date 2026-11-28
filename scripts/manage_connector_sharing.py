#!/usr/bin/env python3
"""Provision shared Windows execution on the board host as its local operator."""
import argparse
import csv
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.gui_test.core.models import TestError
from backend.gui_test.execution.sharing import SharedHost, TASK_ID
from backend.gui_test.standalone.server import ProcessLock


def write_credential(path, value):
    """Publish a separate transfer file without overwriting or exposing credentials."""
    path = path.expanduser().absolute()
    fd, name = tempfile.mkstemp(prefix='.sharing-credential-', dir=path.parent)
    temp = Path(name)
    try:
        if os.name == 'nt':
            # Restrict the DACL while the file is still empty. Processes from
            # other Windows logins never receive the transferable plaintext.
            result = subprocess.run(['whoami', '/user', '/fo', 'csv', '/nh'], check=True,
                                    capture_output=True, text=True)
            _, sid = next(csv.reader(result.stdout.splitlines()))
            if not sid.startswith('S-1-'):
                raise OSError('Cannot identify the local Windows operator')
            subprocess.run(['icacls', str(temp), '/inheritance:r', '/grant:r', '*' + sid + ':(F)'],
                           check=True, capture_output=True)
        with os.fdopen(fd, 'wb', closefd=False) as output:
            output.write((json.dumps(value, ensure_ascii=False) + '\n').encode('utf-8'))
            output.flush()
            os.fsync(output.fileno())
        os.close(fd)
        fd = None
        if os.name == 'nt':
            os.rename(temp, path)  # Windows rename fails if the destination exists.
        else:
            os.link(temp, path)
        return path
    finally:
        if fd is not None:
            os.close(fd)
        temp.unlink(missing_ok=True)


def local_mutation(host, port, route, payload):
    import httpx

    token = host.admin.load(readonly=True)
    base = f'http://127.0.0.1:{port}'
    with host.connect() as db:
        expected = db.execute("SELECT value FROM runner_meta WHERE key='identity'").fetchone()[0]
    try:
        with httpx.Client(timeout=5, trust_env=False, follow_redirects=False) as http:
            identity = http.get(base + '/v1/identity')
            if identity.status_code != 200 or identity.json().get('runner_id') != expected:
                raise ValueError('Local port does not identify the requested Windows Host')
            response = http.post(base + route, json=payload, headers={'Authorization': 'Bearer ' + token})
    except httpx.HTTPError:
        raise ValueError('Could not reach the requested Windows-local Host') from None
    if response.status_code != 200:
        result = response.json()
        raise TestError(result.get('message', 'Local Host rejected the operation'), result.get('code', 'SHARING_ERROR'))
    return response.json()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime', type=Path, required=True, help='Directory containing executions.db')
    parser.add_argument('--host-port', type=int, help='Actual Windows-local Host port for online revoke or handoff')
    commands = parser.add_subparsers(dest='command', required=True)
    commands.add_parser('enable', help='Enable shared mode with the Host process stopped and board idle')
    status = commands.add_parser('status', help='Show local shared mode and Runner identity')
    status.add_argument('--run-id', help='Show the current Run owner and epoch before handoff')
    for role in ('account', 'service'):
        issue = commands.add_parser('issue-' + role)
        issue.add_argument('name')
        issue.add_argument('--output', type=Path, required=True, help='New private credential transfer file')
        commands.add_parser('revoke-' + role).add_argument('name')
    monitor = commands.add_parser('approve-monitor')
    monitor.add_argument('--account', required=True)
    monitor.add_argument('--monitor-id', required=True)
    monitor.add_argument('--ssh-profile', required=True)
    monitor.add_argument('--monitor-port', type=int, required=True)
    monitor.add_argument('--output', type=Path, help='New private Monitor credential file (required on first approval)')
    handoff = commands.add_parser('handoff')
    handoff.add_argument('--run-id', required=True)
    handoff.add_argument('--task-id', required=True)
    handoff.add_argument('--expected-epoch', type=int, required=True)
    args = parser.parse_args(argv)
    if args.host_port is not None and not 1 <= args.host_port <= 65535:
        parser.error('Host port must be from 1 to 65535')
    host = SharedHost(args.runtime.expanduser().resolve())
    if not host.db.is_file():
        parser.error('Initialize this execution Host before provisioning shared mode')
    try:
        if args.command == 'enable':
            with ProcessLock(host.runtime / 'runner.lock'):
                host.init_schema()
                with host.connect() as db:
                    db.execute('BEGIN IMMEDIATE')
                    host.enable(db)
            print('Shared mode enabled')
        elif args.command == 'status':
            with host.connect() as db:
                runner = db.execute("SELECT value FROM runner_meta WHERE key='identity'").fetchone()[0]
                result = {'runner_id': runner, 'sharing_mode': host.mode(db)}
                if args.run_id:
                    if not TASK_ID.fullmatch(args.run_id) or result['sharing_mode'] != 'shared':
                        raise ValueError('Run ownership status requires shared mode and a valid Run ID')
                    row = db.execute(
                        'SELECT r.run_id,r.state,o.task_id,o.monitor_id,t.account,COALESCE(o.epoch,0) AS ownership_epoch '
                        'FROM connector_runs r LEFT JOIN sharing_run_owners o USING(run_id) '
                        'LEFT JOIN sharing_tasks t USING(task_id) WHERE r.run_id=?', (args.run_id,),
                    ).fetchone()
                    if not row:
                        raise ValueError('Run not found')
                    result['run'] = dict(row)
                print(json.dumps(result))
        else:
            with host.connect() as db:
                if host.mode(db) != 'shared':
                    raise ValueError('Enable shared mode first')
            if args.command.startswith('issue-'):
                path = None
                try:
                    with host.connect() as db:
                        db.execute('BEGIN IMMEDIATE')
                        value = host.issue(db, args.command.removeprefix('issue-'), args.name)
                        path = write_credential(args.output, value)
                except BaseException:
                    if path:
                        path.unlink(missing_ok=True)
                    raise
                print('Credential file written to ' + str(path))
            elif args.command == 'approve-monitor':
                path = None
                try:
                    with host.connect() as db:
                        db.execute('BEGIN IMMEDIATE')
                        value = host.approve_monitor(db, args.account, args.monitor_id, args.ssh_profile,
                                                     args.monitor_port, issue_key=args.output is not None)
                        if value:
                            path = write_credential(args.output, value)
                except BaseException:
                    if path:
                        path.unlink(missing_ok=True)
                    raise
                print('Monitor approved; credential file written to ' + str(path) if path else 'Monitor approved')
            elif args.command.startswith('revoke-'):
                role = args.command.removeprefix('revoke-')
                if args.host_port:
                    local_mutation(host, args.host_port, '/v1/sharing/principals/revoke', {'role': role, 'name': args.name})
                else:
                    with ProcessLock(host.runtime / 'runner.lock'), host.connect() as db:
                        db.execute('BEGIN IMMEDIATE')
                        host.revoke(db, role, args.name)
                print('Credential revoked')
            else:
                payload = {'expected_epoch': args.expected_epoch, 'task_id': args.task_id}
                if not TASK_ID.fullmatch(args.run_id):
                    raise ValueError('Invalid Run ID')
                if args.host_port:
                    result = local_mutation(host, args.host_port, '/v1/sharing/runs/' + args.run_id + '/handoff', payload)
                else:
                    with ProcessLock(host.runtime / 'runner.lock'), host.connect() as db:
                        db.execute('BEGIN IMMEDIATE')
                        result = host.handoff(db, args.run_id, **payload)
                print(json.dumps(result))
    except TestError as exc:
        parser.exit(1, exc.message + '\n')
    except (ValueError, RuntimeError, FileExistsError) as exc:
        parser.exit(1, str(exc) + '\n')
    except (OSError, sqlite3.Error, subprocess.SubprocessError):
        parser.exit(1, 'Could not complete local provisioning. Check the runtime and credential file permissions.\n')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
