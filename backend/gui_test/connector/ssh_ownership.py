"""Durable SSH process generations for one connector runtime, independent of UI state."""
import json
import os
import re

from ..execution import launch


def endpoint(cfg, ssh_port, remote_port):
    server = str(cfg.get('server') or '').strip()
    account = str(cfg.get('account') or '').strip()
    key = cfg.get('ssh_key') or ''
    if (not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9.:-]*', server)
            or not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_.-]*', account)
            or not isinstance(key, str) or '\0' in key):
        raise ValueError('Invalid SSH endpoint')
    return {'server': server, 'account': account, 'ssh_port': launch._port(ssh_port),
            'remote_runner_port': launch._port(remote_port), 'ssh_key': key.strip()}


def read(runtime):
    runtime = launch._plain_path(runtime)
    profile = os.path.normcase(str(runtime))
    data = launch._read(runtime / 'ssh-ownership.json')
    if data is launch._MISSING:
        return {'version': 1, 'runtime': profile, 'last_endpoint': None, 'owners': []}
    if (not isinstance(data, dict) or data.get('version') != 1 or data.get('runtime') != profile
            or set(data) != {'version', 'runtime', 'last_endpoint', 'owners'}
            or not isinstance(data['owners'], list)):
        raise ValueError('Invalid SSH ownership record for this profile')
    for record in data['owners']:
        if not isinstance(record, dict) or set(record) != {'process', 'endpoint', 'forward'}:
            raise ValueError('Invalid recorded SSH process')
        if record['forward'] not in ('-R', '-L', None):
            raise ValueError('Invalid recorded SSH forwarding type')
        launch._identity(record['process'])
    for item in [data['last_endpoint'], *(r['endpoint'] for r in data['owners'])]:
        if item is None:
            continue
        if not isinstance(item, dict) or set(item) != {'server', 'account', 'ssh_key', 'ssh_port', 'remote_runner_port'}:
            raise ValueError('Invalid recorded SSH endpoint')
        if endpoint(item, item['ssh_port'], item['remote_runner_port']) != item:
            raise ValueError('Invalid recorded SSH endpoint')
    return data


def update(runtime, *, target=None, processes=(), forward='-R'):
    """Called under the tunnel lock, or after force-stop verifies the lock was released."""
    previous = read(runtime)
    owners = [r for r in previous['owners']
              if launch.process_identity(r['process']['pid']) == r['process']]
    for process in processes:
        if process and not any(r['process'] == process for r in owners):
            owners.append({'process': launch._identity(process), 'endpoint': target, 'forward': forward})
    current = dict(previous, owners=owners, last_endpoint=target or previous['last_endpoint'])
    if current != previous:
        if len(json.dumps(current)) >= 16384:
            raise ValueError('SSH ownership record exceeds receipt size limit')
        launch._atomic_json_write(runtime / 'ssh-ownership.json', current)
    return current


def preserve_previous(runtime):
    """Adopt still-live identities from v2 before the first new status write."""
    status = launch._read(runtime / 'ssh-tunnel.json')
    processes = []
    if status is not launch._MISSING:
        launch._validate_ssh_tunnel(status)
        for process in (status['transport'], status['dashboard_transport']):
            if process and launch.process_identity(process['pid']) == process:
                processes.append(process)
    # v2 did not record the SSH server. Never infer it from a later configuration.
    update(runtime, processes=processes, forward=None)


def matching_reverse_pid(ownership, target):
    for entry in ownership['owners']:
        saved = entry['endpoint']
        if entry['forward'] != '-R' or not saved:
            continue
        if any(saved[k] != target[k] for k in ('server', 'account', 'ssh_port', 'remote_runner_port')):
            continue
        proc = entry['process']
        if launch.process_identity(proc['pid']) == proc:
            return proc['pid']
    return None
