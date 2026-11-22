"""Portable, nonsecret first-connection exchange. Linux remains TC path authority."""
from datetime import datetime, timezone
import json
import ipaddress
import os
import tempfile
from uuid import uuid4
from pathlib import Path
from typing import Literal

from pydantic import Field, ValidationError, model_validator
from .models import StrictModel, TestError

FORMAT = 'gui-test-connector-bootstrap-v1'
FORMAT_V2 = 'gui-test-connector-bootstrap-v2'
MAX_BYTES = 8192


def _validate_reachable_host(server):
    # The plugin must supply a Windows-reachable host, never its own loopback.
    if server.lower().rstrip('.') in {'localhost', 'localhost.localdomain'}:
        raise ValueError('Supply the explicit Windows-reachable Linux host')
    try:
        address = ipaddress.ip_address(server)
    except ValueError:
        if ':' in server or all(c in '0123456789.' for c in server) or any(
                not label or len(label) > 63 or label.startswith('-') or label.endswith('-')
                for label in server.rstrip('.').split('.')):
            raise ValueError('Invalid Linux hostname')
    else:
        mapped = getattr(address, 'ipv4_mapped', None)
        if (address.is_loopback or address.is_unspecified or address.is_multicast or address.is_link_local or
                mapped is not None and (mapped.is_loopback or mapped.is_unspecified)):
            raise ValueError('Supply the explicit Windows-reachable Linux host')
    return server


class ConnectorEndpoint(StrictModel):
    server: str = Field(strict=True, min_length=1, max_length=253, pattern=r'^[A-Za-z0-9][A-Za-z0-9.:-]*$')
    account: str = Field(strict=True, min_length=1, max_length=80, pattern=r'^[A-Za-z_][A-Za-z0-9_.-]*$')
    ssh_port: int = Field(strict=True, ge=1, le=65535)
    remote_dashboard_port: int = Field(strict=True, ge=1, le=65535)

    @model_validator(mode='after')
    def reachable_host(self):
        _validate_reachable_host(self.server)
        return self


class ConnectorSshEndpoint(StrictModel):
    server: str = Field(strict=True, min_length=1, max_length=253, pattern=r'^[A-Za-z0-9][A-Za-z0-9.:-]*$')
    account: str = Field(strict=True, min_length=1, max_length=80, pattern=r'^[A-Za-z_][A-Za-z0-9_.-]*$')
    ssh_port: int = Field(strict=True, default=22, ge=1, le=65535)

    @model_validator(mode='after')
    def reachable_host(self):
        _validate_reachable_host(self.server)
        return self


class ConnectorEndpointV2(ConnectorSshEndpoint):
    remote_runner_port: int = Field(strict=True, default=8771, ge=1, le=65535)
    remote_dashboard_port: int | None = Field(strict=True, default=None, ge=1, le=65535)

    @model_validator(mode='after')
    def distinct_ports(self):
        if self.remote_dashboard_port is not None and self.remote_runner_port == self.remote_dashboard_port:
            raise ValueError('remote_runner_port and remote_dashboard_port must differ')
        return self


class ServiceIdentity(StrictModel):
    runtime_id: str = Field(strict=True, min_length=1, max_length=160, pattern=r'^[A-Za-z0-9_.-]+$')
    package_version: str = Field(strict=True, min_length=1, max_length=80, pattern=r'^[A-Za-z0-9_.+-]+$')


class ConnectorBootstrap(StrictModel):
    format: Literal['gui-test-connector-bootstrap-v1']
    endpoint: ConnectorEndpoint
    identity: ServiceIdentity


class ConnectorBootstrapV2(StrictModel):
    format: Literal['gui-test-connector-bootstrap-v2'] = FORMAT_V2
    endpoint: ConnectorEndpointV2
    expected_runner_id: str | None = Field(default=None, pattern=r'^[a-f0-9]{32}$')
    issued_at: str = Field(strict=True, min_length=1, max_length=64)


def parse_bootstrap(value):
    if isinstance(value, (ConnectorBootstrap, ConnectorBootstrapV2)):
        return value
    if isinstance(value, dict) and value.get('format') == FORMAT_V2:
        return ConnectorBootstrapV2.model_validate(value)
    return ConnectorBootstrap.model_validate(value)


def build_bootstrap_v2(*, server, account, ssh_port=22, remote_runner_port=8771,
                       remote_dashboard_port=None, expected_runner_id=None, issued_at=None):
    return ConnectorBootstrapV2(
        format=FORMAT_V2,
        endpoint=ConnectorEndpointV2(
            server=server,
            account=account,
            ssh_port=ssh_port,
            remote_runner_port=remote_runner_port,
            remote_dashboard_port=remote_dashboard_port,
        ),
        expected_runner_id=expected_runner_id,
        issued_at=issued_at or datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z'),
    ).model_dump()


def plain_path(path):
    path = Path(path).expanduser().absolute()
    if any(part.is_symlink() for part in (path, *path.parents)):
        raise ValueError('Bootstrap paths must not contain symbolic links')
    return path


def load_profile(path):
    path = plain_path(path)
    if not path.is_file():
        raise ValueError('Bootstrap JSON file required')
    with path.open('rb') as stream:
        data = stream.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        raise ValueError('Bootstrap profile is too large')
    def unique(pairs):
        value = {}
        for key, item in pairs:
            if key in value:
                raise ValueError('Duplicate bootstrap field')
            value[key] = item
        return value
    try:
        return parse_bootstrap(json.loads(data.decode('utf-8-sig'), object_pairs_hook=unique))
    except ValidationError:
        # ValidationError includes raw attacker inputs. Keep rejected key bytes,
        # passwords and command strings out of launcher diagnostics and logs.
        raise ValueError('Invalid connection profile schema; use a fresh plugin export') from None


def verify_service(profile, health):
    value = parse_bootstrap(profile)
    if isinstance(value, ConnectorBootstrapV2):
        return
    if any(health.get(key) != expected for key, expected in value.identity.model_dump().items()):
        raise TestError('Linux service identity differs from the imported connection profile', 'SERVICE_IDENTITY_MISMATCH', 409)


def service_headers(profile):
    try:
        value = parse_bootstrap(profile)
    except ValidationError:
        raise ValueError('Saved connection profile is malformed') from None
    if isinstance(value, ConnectorBootstrapV2):
        return {'X-Bsp-Service': 'plugin'}
    return {'X-Bsp-Service': 'plugin', 'X-Bsp-Runtime-Id': value.identity.runtime_id,
            'X-Bsp-Package-Version': value.identity.package_version}


def write_profile(path, value):
    """Package-local atomic export; usable without any repository host scripts."""
    value = parse_bootstrap(value)
    path = plain_path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    data = (json.dumps(value.model_dump(), ensure_ascii=False, indent=2) + '\n').encode('utf-8')
    fd, name = tempfile.mkstemp(prefix=path.name + '.', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(data); stream.flush(); os.fsync(stream.fileno())
        plain_path(path)
        if path.exists():
            backup = path.with_name(path.name + '.' + uuid4().hex + '.bak')
            with backup.open('xb') as stream:
                stream.write(path.read_bytes()); stream.flush(); os.fsync(stream.fileno())
            if os.name != 'nt': backup.chmod(0o600)
        os.replace(name, path)
    finally:
        if os.path.exists(name): os.unlink(name)
    return value.model_dump()
