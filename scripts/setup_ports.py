"""Strict, standard-library-only setup port profile and precedence rules."""
import json
import os
from pathlib import Path
import tempfile


DEFAULT_PORTS = {'runner_port': 8771, 'dashboard_port': 8766,
                 'remote_runner_port': 8771, 'remote_dashboard_port': 8766}


def validate_port(value):
    if type(value) is not int or not 1 <= value <= 65535:
        raise ValueError('포트는 1~65535 사이의 정수여야 합니다.')
    return value


def reject_links(path):
    path = Path(path).absolute()
    if any(item.is_symlink() for item in (path, *path.parents)):
        raise ValueError('포트 프로파일 경로에 링크를 사용할 수 없습니다.')


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('포트 프로파일에 중복 필드가 있습니다.')
        result[key] = value
    return result


def validate_ports(ports):
    required = set(DEFAULT_PORTS)
    if not isinstance(ports, dict) or not required <= set(ports) <= required | {'ssh_port'}:
        raise ValueError('포트 프로파일 필드가 올바르지 않습니다.')
    for value in ports.values():
        validate_port(value)
    if ports['runner_port'] == ports['dashboard_port']:
        raise ValueError('--port와 --dashboard-port는 서로 달라야 합니다.')
    if ports['remote_runner_port'] == ports['remote_dashboard_port']:
        raise ValueError('--remote-runner-port와 --remote-dashboard-port는 서로 달라야 합니다.')
    return dict(ports)


class PortsProfile:
    def __init__(self, path):
        self.path = Path(path)

    def read(self):
        reject_links(self.path)
        try:
            raw = self.path.read_text(encoding='utf-8-sig')
        except FileNotFoundError:
            return {}
        value = json.loads(raw, object_pairs_hook=unique_object)
        if (not isinstance(value, dict) or set(value) != {'version', 'ports'} or
                type(value['version']) is not int or value['version'] != 1):
            raise ValueError('포트 프로파일 버전 또는 형식이 올바르지 않습니다.')
        return validate_ports(value['ports'])

    def resolve(self, overrides, saved_ssh_port=None):
        saved = self.read()
        values, origins = {}, {}
        for key, default in {**DEFAULT_PORTS, 'ssh_port': 22}.items():
            if overrides.get(key) is not None:
                values[key], origins[key] = validate_port(overrides[key]), 'CLI'
            elif key in saved:
                values[key], origins[key] = saved[key], 'profile'
            elif key == 'ssh_port' and saved_ssh_port is not None:
                values[key], origins[key] = validate_port(saved_ssh_port), '_setup.ssh_port'
            else:
                values[key], origins[key] = default, 'default'
        return validate_ports(values), origins

    def save(self, ports):
        ports = validate_ports(ports)
        reject_links(self.path)
        # A corrupted existing profile must be repaired deliberately, not overwritten.
        self.read()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, temporary = tempfile.mkstemp(prefix=self.path.name + '.', dir=self.path.parent)
        try:
            with os.fdopen(fd, 'w', encoding='utf-8', newline='\n') as stream:
                json.dump({'version': 1, 'ports': ports}, stream, ensure_ascii=False, indent=2)
                stream.write('\n')
                stream.flush()
                os.fsync(stream.fileno())
            reject_links(self.path)
            os.replace(temporary, self.path)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)
        return ports
