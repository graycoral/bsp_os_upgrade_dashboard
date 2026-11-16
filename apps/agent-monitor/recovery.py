"""Offline runtime inspection and consistent backups; never imports an executor."""
from contextlib import ExitStack, contextmanager, closing
from collections import Counter
import hashlib
import json
from pathlib import Path
import shutil
import sqlite3

GUI_CONTRACTS = {'bsp-upgrade-integration-v1'}
RETRY_POLICIES = {None, 'initial-pass-else-two-of-three-v1', 'fail-stop-analysis-v1'}
ACTIVE = {'RUNNING', 'DISPATCHING', 'CANCEL_REQUESTED', 'UNKNOWN'}
RUN_STATES = ACTIVE | {'QUEUED', 'PAUSED', 'PAUSE_REQUESTED', 'COMPLETED', 'CANCELLED'}


def reservation_summary(connection):
    owners, modes = Counter(), Counter()
    unconfirmed = 0
    resources = connection.execute('SELECT COUNT(*) FROM reservations').fetchone()[0]
    if not resources:
        return {'resources': 0, 'owner_states': {}, 'execution_modes': {}, 'unconfirmed_attempts': 0}
    rows = connection.execute('SELECT DISTINCT r.run_id, t.data FROM reservations r '
                              'LEFT JOIN runs t ON t.id=r.run_id')
    for _, data in rows:
        if data is None:
            owners['OWNER_MISSING'] += 1
            continue
        run = json.loads(data)
        state = run.get('state')
        owners[state if isinstance(state, str) and state in RUN_STATES else 'OTHER'] += 1
        simulation = run.get('simulation')
        mode = 'UNSPECIFIED'
        if simulation is True: mode = 'mock'
        elif simulation is False: mode = 'hardware'
        modes[mode] += 1
        unconfirmed += sum(attempt.get('terminated') is False or
                           (attempt.get('state') in ACTIVE and attempt.get('terminated') is not True)
                           for attempt in run.get('attempts', []))
    return {'resources': resources, 'owner_states': dict(owners), 'execution_modes': dict(modes),
            'unconfirmed_attempts': unconfirmed}


def diagnostic_summary(report):
    """Shareable counts only; no paths, IDs, resource names, tokens or log text."""
    owners, modes = Counter(), Counter()
    resources = unconfirmed = 0
    for item in report.get('reservation_summaries', []):
        owners.update(item['owner_states'])
        modes.update(item['execution_modes'])
        resources += item['resources']
        unconfirmed += item['unconfirmed_attempts']
    return {'adoptable': report['adoptable'], 'compatible': report['compatible'],
            'issues': dict(Counter(item['code'] for item in report['issues'])),
            'unresolved': dict(Counter(item.get('code') or item['state'] for item in report['unresolved'])),
            'live_states': dict(Counter(item['state'] for item in report['live_states'])),
            'reservations': {'verified': not any(item['code'] == 'DATABASE_UNREADABLE' for item in report['issues']),
                             'resources': resources, 'owner_states': dict(owners),
                             'execution_modes': dict(modes), 'unconfirmed_attempts': unconfirmed}}


def diagnostic_text(summary):
    reservations = summary['reservations']
    lines = ['이관 검사 · ' + ('가능' if summary['adoptable'] else '보류')]
    for label, key in [('형식·계약 문제', 'issues'), ('미해결 항목', 'unresolved'), ('실행 상태', 'live_states')]:
        counts = ', '.join(f'{code} {count}' for code, count in sorted(summary[key].items())) or '없음'
        lines.append(f'{label} · {counts}')
    owners = ', '.join(f'{state} {count}' for state, count in sorted(reservations['owner_states'].items())) or '없음'
    modes = ', '.join(f'{mode} {count}' for mode, count in sorted(reservations['execution_modes'].items())) or '없음'
    if reservations['verified']:
        lines.extend([f'예약 자원 · {reservations["resources"]}개 / 예약 세션 · {owners}',
                      f'예약 실행 방식 · {modes}', f'종료 미확인 시도 · {reservations["unconfirmed_attempts"]}개'])
    else:
        lines.append('예약 상세 · DB 내용을 확인할 수 없습니다.')
    if reservations['resources']:
        lines.append('예약 해제는 해당 세션의 취소·종료 확인 절차로 처리합니다.')
    if not summary['adoptable']:
        lines.append('복구 지원에는 위 상태 코드와 건수를 사용하세요.')
    return '\n'.join(lines)


def file_hash(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream,'sha256').hexdigest()


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


@contextmanager
def offline_locks(runtime, lock):
    """Same ownership locks as production workers; no DB or execution mutation."""
    runtime = Path(runtime)
    with ExitStack() as stack:
        stack.enter_context(lock(runtime / 'worker.lock'))
        for path in sorted(runtime.glob('**/runs.db')):
            stack.enter_context(lock(path.with_suffix('.lock')))
        yield


def inspect(runtime, *, include_revision=True):
    runtime = Path(runtime).resolve()
    report = {'runtime': str(runtime), 'supported_contracts': sorted(GUI_CONTRACTS),
              'databases': [], 'files': {}, 'issues': [], 'unresolved': [], 'live_states': [],
              'reservation_summaries': []}
    for path in sorted(runtime.rglob('*')) if runtime.exists() else []:
        if path.is_symlink():
            report['issues'].append({'path': path.relative_to(runtime).as_posix(), 'code': 'SYMLINK'})
            continue
        if not path.is_file() or path.suffix in {'.lock', '.db-wal', '.db-shm'} or path.name.endswith(('-wal', '-shm')):
            continue
        name = path.relative_to(runtime).as_posix()
        if path.suffix != '.db':
            if include_revision:
                report['files'][name] = file_hash(path)
            continue
        try:
            with closing(sqlite3.connect(f'{path.as_uri()}?mode=ro', uri=True)) as c:
                c.execute('BEGIN')
                tables = {r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'")}
                version = c.execute("SELECT value FROM meta WHERE key='schema_version'").fetchone() if 'meta' in tables else None
                supported = {'1', '2'} if path.name == 'dashboard.db' else {'1'}
                if path.name in {'dashboard.db', 'runs.db'} and (not version or version[0] not in supported):
                    report['issues'].append({'path': name, 'code': 'SCHEMA_UNSUPPORTED'})
                database = {'path': name, 'schema_version': version[0] if version else None}
                if include_revision:
                    rows = {}
                    for table in sorted(tables):
                        if table.startswith('sqlite_'): continue
                        # Table names come only from SQLite metadata and are quoted.
                        quoted = '"' + table.replace('"', '""') + '"'
                        values = c.execute('SELECT * FROM ' + quoted).fetchall()
                        rows[table] = sorted([list(row) for row in values], key=lambda r: json.dumps(r, sort_keys=True, default=str))
                    database['content_revision'] = digest(rows)
                report['databases'].append(database)
                if 'runs' in tables:
                    for row in c.execute('SELECT data FROM runs'):
                        run = json.loads(row[0]); identity = run.get('id', '?'); integration = run.get('integration') or {}
                        if integration and integration.get('contract_version') not in GUI_CONTRACTS:
                            report['issues'].append({'path': name, 'id': identity, 'code': 'GUI_CONTRACT_UNSUPPORTED'})
                        policies = ([run['execution_policy']] if 'execution_policy' in run else []) + ([integration['retry_policy']] if 'retry_policy' in integration else [])
                        if any(policy not in RETRY_POLICIES for policy in policies):
                            report['issues'].append({'path': name, 'id': identity, 'code': 'RETRY_POLICY_UNSUPPORTED'})
                        if len(policies)>1 and policies[0]!=policies[1]:
                            report['issues'].append({'path': name, 'id': identity, 'code': 'RETRY_POLICY_CONFLICT'})
                        states = {run.get('state')} | {a.get('state') for a in run.get('attempts', [])}
                        current = run.get('state')
                        if current in ACTIVE:
                            report['live_states'].append({'path': name, 'id': identity, 'state': current})
                        if current == 'UNKNOWN' or any(a.get('state') == 'UNKNOWN' for a in run.get('attempts', []) if a.get('terminated') is not True):
                            report['unresolved'].append({'path': name, 'id': identity, 'code': 'UNKNOWN'})
                if 'jobs' in tables:
                    for row in c.execute('SELECT data FROM jobs'):
                        job = json.loads(row[0]); identity = job.get('id', '?')
                        if job.get('profile', {}).get('module_report_version', 1) not in {1, 2}:
                            report['issues'].append({'path': name, 'id': identity, 'code': 'MODULE_CONTRACT_UNSUPPORTED'})
                        if not isinstance(job.get('modules'), list) or not isinstance(job.get('profile'), dict):
                            report['issues'].append({'path': name, 'id': identity, 'code': 'BSP_LAYOUT_UNSUPPORTED'})
                        integration_state=job.get('integration',{}).get('status')
                        if integration_state in ACTIVE:
                            item={'path':name,'id':identity,'stage':'integration','state':integration_state}
                            report['live_states'].append(item)
                            if integration_state=='UNKNOWN':report['unresolved'].append(item)
                        if job.get('session',{}).get('status') in {'CONNECTING','NEEDS_RECONCILIATION','UNKNOWN'}:
                            report['unresolved'].append({'path':name,'id':identity,'code':'SESSION_UNRESOLVED'})
                        for module in job.get('modules', []):
                            for stage, value in module.get('stages', {}).items():
                                if value.get('status') in ACTIVE:
                                    item = {'path': name, 'id': identity, 'stage': stage, 'state': value['status']}
                                    report['live_states'].append(item)
                                    if value['status'] == 'UNKNOWN': report['unresolved'].append(item)
                if 'orchestration_runs' in tables:
                    for row in c.execute("SELECT id,status FROM orchestration_runs WHERE status IN ('RUNNING','UNKNOWN')"):
                        report['unresolved'].append({'path':name,'id':row[0],'code':'ORCHESTRATION_'+row[1]})
                for table in ('reservations', 'leases', 'coordinator_lanes'):
                    if table in tables and c.execute('SELECT 1 FROM '+table+' LIMIT 1').fetchone():
                        report['unresolved'].append({'path': name, 'code': 'HELD_'+table.upper()})
                if 'reservations' in tables:
                    report['reservation_summaries'].append(reservation_summary(c))
                if 'launch_receipts' in tables:
                    for row in c.execute('SELECT data FROM launch_receipts'):
                        value = json.loads(row[0]); phase = (value.get('process_receipt') or {}).get('phase')
                        if phase in {'UNKNOWN', 'LAUNCHED'} or value.get('status') in {'INTENT', 'STARTED', 'UNKNOWN'} and phase != 'TERMINATED':
                            report['unresolved'].append({'path': name, 'id': value.get('id'), 'code': 'PROCESS_UNRESOLVED'})
        except (OSError, ValueError, TypeError, AttributeError, sqlite3.Error) as exc:
            report['issues'].append({'path': name, 'code': 'DATABASE_UNREADABLE', 'error': type(exc).__name__})
    report['compatible'] = not report['issues']
    report['adoptable'] = report['compatible'] and not report['unresolved'] and not report['live_states']
    return report | {'revision': digest(report)} if include_revision else report


def backup(runtime, destination):
    """SQLite backup includes committed WAL bytes; every other file stays local."""
    runtime, destination = Path(runtime).resolve(), Path(destination).resolve()
    if destination.is_relative_to(runtime) or destination.exists():
        raise ValueError('Backup must be a new directory outside runtime')
    destination.mkdir(parents=True, mode=0o700)
    hashes = {}
    for path in sorted(runtime.rglob('*')):
        if path.is_symlink(): raise ValueError('Runtime symlinks require explicit operator review')
        if not path.is_file() or path.suffix == '.lock' or path.name.endswith(('-wal', '-shm')): continue
        name = path.relative_to(runtime).as_posix(); target = destination / name
        target.parent.mkdir(parents=True, exist_ok=True)
        if path.suffix == '.db':
            with closing(sqlite3.connect(f'{path.as_uri()}?mode=ro', uri=True)) as source, closing(sqlite3.connect(target)) as output:
                source.backup(output)
                # A standalone backup must not depend on a retained WAL file.
                output.execute('PRAGMA journal_mode=DELETE')
        else:
            shutil.copyfile(path, target)
        target.chmod(0o600)
        hashes[name] = file_hash(target)
    (destination / 'BACKUP.json').write_text(json.dumps({'runtime': str(runtime), 'files': hashes}, indent=2) + '\n')
    (destination / 'BACKUP.json').chmod(0o600)
    return {'path': str(destination), 'files': len(hashes), 'revision': digest(hashes)}


def release_references(runtime):
    """Retain source releases named by historical runtime receipts/snapshots."""
    import re
    found = set()
    def scan(value):
        if isinstance(value, dict):
            for key, item in value.items():
                if key in {'release', 'source_release', 'managed_release', 'package_release'} and isinstance(item,str) and re.fullmatch('[a-f0-9]{64}',item):
                    found.add(item)
                scan(item)
        elif isinstance(value,list):
            for item in value: scan(item)
    runtime = Path(runtime)
    for path in runtime.rglob('*') if runtime.exists() else []:
        if path.is_symlink(): raise ValueError('Runtime symlink prevents safe release cleanup')
        if not path.is_file(): continue
        if path.suffix == '.json': scan(json.loads(path.read_text(encoding='utf-8-sig')))
        elif path.suffix == '.db':
            with closing(sqlite3.connect(f'{path.resolve().as_uri()}?mode=ro',uri=True)) as c:
                for row in c.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall():
                    quoted='"'+row[0].replace('"','""')+'"'
                    columns={r[1] for r in c.execute('PRAGMA table_info('+quoted+')')}
                    if 'data' in columns:
                        for value in c.execute('SELECT data FROM '+quoted): scan(json.loads(value[0]))
    return found
