"""Private Linux credential and task state for the shared direct connector."""
import contextlib
import json
import os
from pathlib import Path
import re
import secrets
import stat
import tempfile
import uuid


SHARING_CAPABILITY = 'multi-plugin-ownership-v1'
ID = re.compile(r'[0-9a-f]{32}')
SECRET = re.compile(r'[A-Za-z0-9_-]{32,128}')
MONITOR_ID = re.compile(r'[A-Za-z0-9][A-Za-z0-9_.@-]{0,127}')


class SharingError(ValueError):
    def __init__(self, message, code='INVALID_SHARING_STATE'):
        super().__init__(message)
        self.code = code


def valid_id(value):
    return isinstance(value, str) and bool(ID.fullmatch(value))


def valid_secret(value):
    return isinstance(value, str) and bool(SECRET.fullmatch(value))


def valid_monitor_id(value):
    return isinstance(value, str) and bool(MONITOR_ID.fullmatch(value))


def private_directory(path):
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    info = path.lstat()
    if (not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077):
        raise SharingError('Sharing state directories must be owned by the Linux account and private.')
    return path


def private_json(path):
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    except FileNotFoundError:
        raise
    except OSError:
        raise SharingError('The private state file could not be opened.') from None
    with os.fdopen(fd, 'rb') as stream:
        info = os.fstat(stream.fileno())
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077):
            raise SharingError('Sharing state files must be regular, account-owned, and private.')
        try:
            data = stream.read(64 * 1024 * 1024 + 1)
            if len(data) > 64 * 1024 * 1024:
                raise ValueError('State size exceeded')
            value = json.loads(data, object_pairs_hook=_unique_object)
        except (ValueError, UnicodeError):
            raise SharingError('The private state file is invalid.') from None
    if not isinstance(value, dict):
        raise SharingError('The private state file is invalid.')
    return value


def _unique_object(items):
    value = dict(items)
    if len(value) != len(items):
        raise ValueError('Duplicate private state field')
    return value


def write_private_json(path, value):
    fd, temp = tempfile.mkstemp(dir=path.parent, prefix='.write-')
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as stream:
            json.dump(value, stream, ensure_ascii=False, allow_nan=False)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp, path)
        sync_directory(path.parent)
    finally:
        Path(temp).unlink(missing_ok=True)


def sync_directory(path):
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


@contextlib.contextmanager
def state_lock(directory, name):
    import fcntl

    fd = os.open(directory / name, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW | os.O_NONBLOCK, 0o600)
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
            raise SharingError('Sharing state lock must be owned by the Linux account and private.')
        fcntl.flock(fd, fcntl.LOCK_EX)
        yield
    finally:
        os.close(fd)


def credential_fields(value):
    if (set(value) != {'schema_version', 'account', 'token', 'runner_id'}
            or type(value['schema_version']) is not int or value['schema_version'] != 1
            or not valid_secret(value['token']) or not valid_id(value['runner_id'])
            or not isinstance(value['account'], str) or not 1 <= len(value['account']) <= 160
            or not value['account'].isprintable()):
        raise SharingError('Use the private account credential issued by the Windows Host.', 'INVALID_SHARING_CREDENTIAL')
    return value


def transport_options(socket=None, owner_uid=None, trust_protected_loopback=False):
    if socket is not None:
        path = Path(socket).expanduser()
        uid = os.getuid() if owner_uid is None else owner_uid
        if (trust_protected_loopback or not path.is_absolute() or '..' in path.parts
                or type(uid) is not int or uid < 0):
            raise SharingError('Use an absolute private reverse SSH socket and its trusted owner UID.', 'INVALID_SHARED_TRANSPORT')
        return {'kind': 'unix', 'socket': str(path), 'owner_uid': uid}
    if owner_uid is not None:
        raise SharingError('A socket owner UID requires a private reverse SSH socket.', 'INVALID_SHARED_TRANSPORT')
    return {'kind': 'protected-tcp'} if trust_protected_loopback else None


def transport_args(transport):
    if transport['kind'] == 'protected-tcp':
        return ['--trust-protected-loopback']
    return ['--sharing-host-socket', transport['socket'], '--sharing-host-socket-owner-uid', str(transport['owner_uid'])]


def read_transport(value):
    if value == {'kind': 'protected-tcp'}:
        return value
    if isinstance(value, dict) and set(value) == {'kind', 'socket', 'owner_uid'} and value['kind'] == 'unix':
        if isinstance(value['socket'], str) and type(value['owner_uid']) is int:
            return transport_options(value['socket'], value['owner_uid'])
    raise SharingError('Import the account with a private socket or operator-protected endpoint.', 'SHARED_TRANSPORT_REQUIRED')


class SharingState:
    def __init__(self, state_dir, port):
        self.root = Path(state_dir).expanduser().absolute() / 'sharing'
        self.endpoint = self.root / str(port)
        self.account_file = self.endpoint / 'account.json'

    def _directories(self):
        if not hasattr(os, 'getuid'):
            raise SharingError('Shared plugin credentials require a Linux account.')
        private_directory(self.root)
        private_directory(self.endpoint)

    def configured(self):
        # A dangling link or an inaccessible path is a corrupt configuration.
        # Fail closed instead of accidentally using the legacy client.
        try:
            self.account_file.lstat()
        except FileNotFoundError:
            for path in (self.root, self.endpoint):
                if path.is_symlink():
                    raise SharingError('Sharing state directory links are not permitted.')
            return False
        return True

    def configuration(self):
        if not self.configured():
            raise SharingError('Import the Windows Host account credential for this connector port.', 'SHARING_CREDENTIAL_REQUIRED')
        self._directories()
        record = private_json(self.account_file)
        transport = read_transport(record.pop('transport', None))
        return credential_fields(record), transport

    def credential(self):
        return self.configuration()[0]

    def import_credential(self, source, transport=None):
        try:
            value = credential_fields(private_json(Path(source).expanduser()))
        except FileNotFoundError:
            raise SharingError('The supplied credential file is missing.', 'INVALID_SHARING_CREDENTIAL') from None
        self._directories()
        with state_lock(self.endpoint, '.account.lock'):
            if self.configured():
                existing, former_transport = self.configuration()
                if transport is None:
                    transport = former_transport
                if (existing['account'], existing['runner_id']) != (value['account'], value['runner_id']):
                    raise SharingError('Use a separate --state-dir for a different account or Windows Host.', 'SHARING_SCOPE_CHANGED')
            transport = read_transport(transport)
            write_private_json(self.account_file, value | {'transport': transport})
        return {'state': 'IMPORTED', 'account': value['account'], 'runner_id': value['runner_id']}

    def task_directory(self, task_id):
        if not valid_id(task_id):
            raise SharingError('Task IDs must be 32 lowercase hexadecimal digits.', 'INVALID_TASK_ID')
        self._directories()
        return private_directory(self.endpoint / task_id)

    def task(self, task_id):
        path = self.task_directory(task_id) / 'task.json'
        try:
            value = private_json(path)
        except FileNotFoundError:
            raise SharingError('The selected task has not been created in this state directory.', 'TASK_NOT_FOUND') from None
        if (set(value) != {'task_id', 'task_key', 'project', 'monitor_id'} or value['task_id'] != task_id
                or not valid_secret(value['task_key']) or not valid_monitor_id(value['monitor_id'])
                or not isinstance(value['project'], str) or not 1 <= len(value['project']) <= 1024
                or not value['project'].isprintable()):
            raise SharingError('The private task record is invalid.')
        return value

    def create_task(self, task_id, project, monitor_id):
        if not valid_monitor_id(monitor_id):
            raise SharingError('Enter the approved Agent Monitor installation ID.', 'INVALID_MONITOR_ID')
        if not isinstance(project, str) or not 1 <= len(project) <= 1024 or not project.strip() or not project.isprintable():
            raise SharingError('Enter a nonempty project label of up to 1024 characters.', 'INVALID_PROJECT')
        task_id = task_id or uuid.uuid4().hex
        task = self.task_directory(task_id)
        with state_lock(task, '.task.lock'):
            if (task / 'task.json').exists() or (task / 'task.json').is_symlink():
                existing = self.task(task_id)
                if (existing['project'], existing['monitor_id']) != (project, monitor_id):
                    raise SharingError('The task ID already has a different project or Monitor.', 'TASK_CONFLICT')
                return existing
            value = {'task_id': task_id, 'task_key': secrets.token_urlsafe(32), 'project': project, 'monitor_id': monitor_id}
            write_private_json(task / 'task.json', value)
            return value

    def tasks(self):
        self._directories()
        result = []
        for path in sorted(self.endpoint.iterdir()):
            if valid_id(path.name) and (path / 'task.json').is_file():
                result.append(public_task(self.task(path.name)))
        return result


def public_task(task):
    return {key: task[key] for key in ('task_id', 'project', 'monitor_id')}
