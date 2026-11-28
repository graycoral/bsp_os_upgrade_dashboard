"""Read the install credential and sign purpose-bound Monitor challenges."""
import hashlib
import hmac
import json
import os
import re
import stat

CHALLENGE = re.compile(r'[a-f0-9]{64}')
TOKEN = re.compile(r'[A-Za-z0-9_-]{32,128}')


def load_monitor_credential(path, monitor_id):
    try:
        flags = os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0) | getattr(os, 'O_NONBLOCK', 0)
        with os.fdopen(os.open(path, flags), 'rb') as source:
            info = os.fstat(source.fileno())
            if not stat.S_ISREG(info.st_mode) or (os.name == 'posix' and (
                    info.st_uid != os.geteuid() or stat.S_IMODE(info.st_mode) & 0o077)):
                raise ValueError('credential is not owner-only')
            data = source.read(4097)
        if len(data) > 4096:
            raise ValueError('credential is too large')
        value = json.loads(data)
        if (not isinstance(value, dict) or set(value) != {'schema_version', 'monitor_id', 'token', 'runner_id'}
                or type(value.get('schema_version')) is not int or value['schema_version'] != 1
                or value.get('monitor_id') != monitor_id or not isinstance(value.get('token'), str)
                or not TOKEN.fullmatch(value['token']) or not isinstance(value.get('runner_id'), str)
                or not re.fullmatch(r'[a-f0-9]{32}', value['runner_id'])):
            raise ValueError('invalid credential')
        return value
    except (OSError, TypeError, ValueError):
        raise ValueError('The shared Monitor requires an owner-only credential for this installation.') from None


def load_monitor_token(path, monitor_id):
    return load_monitor_credential(path, monitor_id)['token']


def monitor_proof(token, monitor_id, challenge):
    return hmac.new(token.encode(), f'bsp-monitor-v1:{monitor_id}:{challenge}'.encode(), hashlib.sha256).hexdigest()


def redeem_proof(token, monitor_id, ticket):
    return hmac.new(token.encode(), f'bsp-monitor-redeem-v1:{monitor_id}:{ticket}'.encode(), hashlib.sha256).hexdigest()
