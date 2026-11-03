"""Opt-in, durable Windows flash/test pipeline. No hardware defaults are guessed."""
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import sqlite3
import subprocess
import threading
import time

from pydantic import Field
from gui_test.core.models import StrictModel, Connection, CommandTemplate, TestError, digest, now
from gui_test.core.results import parse_result
from gui_test.adapters.runner import validate_command_template, validate_windows_command, resolve_argv
from gui_test.execution.source import snapshot
from gui_test.execution.process import ProcessTree
from gui_test.execution.capture import Capture


class FlashRequest(StrictModel):
    id: str = Field(pattern=r'^[a-f0-9]{32}$')
    runner_id: str = Field(pattern=r'^[a-f0-9]{32}$')
    profile: str = Field(pattern=r'^[A-Za-z0-9_.-]{1,80}$')
    bundle: str = Field(min_length=1, max_length=512)
    manifest: dict
    source_revision: str = Field(min_length=1, max_length=256)
    connection: Connection
    template: CommandTemplate
    cases: dict[str, list[str]]
    tests: list[dict]
    baseline: dict


class UnknownHardware(TestError):
    pass


def relative(value):
    if not isinstance(value, str) or not value or '\\' in value or ':' in value:
        raise TestError('Expected a relative POSIX bundle path', 'IMAGE_PATH')
    p = PurePosixPath(value)
    if p.is_absolute() or any(x in {'', '.', '..'} for x in value.split('/')):
        raise TestError('Invalid bundle path', 'IMAGE_PATH')
    # Also exclude Windows device names, streams, shell metacharacters and aliases.
    if any(not re.fullmatch(r'[A-Za-z0-9_ .-]+', x) or x.endswith((' ', '.')) or
           x.split('.')[0].upper() in {'CON', 'PRN', 'AUX', 'NUL', *('COM'+str(i) for i in range(10)), *('LPT'+str(i) for i in range(10))}
           for x in p.parts):
        raise TestError('Unsupported bundle filename', 'IMAGE_PATH')
    return p


def contained(root, value):
    p = root
    for part in relative(value).parts:
        p = p / part
        if p.is_symlink() or (hasattr(p, 'is_junction') and p.is_junction()):
            raise TestError('Links are not allowed in image paths', 'IMAGE_PATH')
    if not p.resolve().is_relative_to(root.resolve()):
        raise TestError('Image path escaped its root', 'IMAGE_PATH')
    return p


def validate_manifest(manifest):
    if set(manifest) != {'schema_version', 'batch', 'files'} or type(manifest['schema_version']) is not int or manifest['schema_version'] != 1:
        raise TestError('Build artifact must be a flash manifest v1', 'IMAGE_MANIFEST')
    files = manifest['files']
    if not isinstance(files, dict) or not 2 <= len(files) <= 500:
        raise TestError('Manifest needs batch plus image files (maximum 500)', 'IMAGE_MANIFEST')
    if len({k.casefold() for k in files}) != len(files):
        raise TestError('Case-insensitive image filename collision', 'IMAGE_MANIFEST')
    for name, sha in files.items():
        relative(name)
        if not isinstance(sha, str) or not re.fullmatch('[a-f0-9]{64}', sha):
            raise TestError('Every image file requires SHA256', 'IMAGE_MANIFEST')
    batch = manifest['batch']
    if not isinstance(batch, str) or batch not in files or Path(batch).suffix.lower() != '.bat':
        raise TestError('Manifest must identify its batch file', 'IMAGE_MANIFEST')


class SerialConsole:
    """Read throughout flashing so an early boot marker is not lost."""
    def __init__(self, config):
        import serial
        self.port = serial.Serial(port=config['com'], baudrate=config['baudrate'], timeout=.2,
                                  write_timeout=2, bytesize=8, parity='N', stopbits=1)
        self.port.reset_input_buffer()
        self.ending = {'cr': b'\r', 'lf': b'\n', 'crlf': b'\r\n'}[config['line_ending']]
        self.buffer = bytearray()
        self.lock = threading.Lock()
        self.closed = threading.Event()
        self.failed = False
        self.thread = threading.Thread(target=self.read, daemon=True)
        self.thread.start()

    def read(self):
        try:
            while not self.closed.is_set():
                with self.lock:
                    data = self.port.read(1024)
                    self.buffer.extend(data)
                    del self.buffer[:-65536]
                time.sleep(.001)
        except Exception:
            self.failed = True

    def command(self, value):
        with self.lock:
            # Exclude bytes read before the command from its readiness check.
            self.port.reset_input_buffer()
            self.buffer.clear()
            self.port.write(value.encode('ascii') + self.ending)
            self.port.flush()

    def wait(self, marker, timeout):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if self.failed:
                raise TestError('Console disconnected; readiness was not established', 'CONSOLE_LOST')
            with self.lock:
                if marker.encode('utf-8') in self.buffer:
                    return
            time.sleep(.05)
        raise TestError('Console readiness marker timed out', 'CONSOLE_TIMEOUT')

    def close(self):
        self.closed.set()
        self.thread.join(timeout=1)
        self.port.close()


class FlashService:
    def __init__(self, host, config, io=None):
        self.host, self.config = host, config
        self.io = io or self
        self.console = SerialConsole

    def profile(self, req):
        profile = self.config.get('profiles', {}).get(req.profile)
        if not profile or profile.get('enabled') is not True:
            raise TestError('Flash profile is not enabled', 'FLASH_NOT_CONFIGURED')
        required = ('image_root', 'fastboot', 'batch_sha256', 'success_marker', 'boards')
        if any(not profile.get(k) for k in required):
            raise TestError('Flash profile is incomplete', 'FLASH_NOT_CONFIGURED')
        if not isinstance(profile['success_marker'], str) or not profile['success_marker'].strip():
            raise TestError('Explicit batch success marker required', 'FLASH_NOT_CONFIGURED')
        markers = profile.get('failure_markers', ['FAILED', 'fastboot: error:'])
        if not isinstance(markers, list) or not markers or any(not isinstance(m, str) or not m.strip() for m in markers):
            raise TestError('Explicit nonempty failure markers required', 'FLASH_NOT_CONFIGURED')
        if profile['batch_sha256'] != req.manifest['files'][req.manifest['batch']]:
            raise TestError('Batch is not the reviewed registered version', 'BATCH_CHANGED')
        selected = [req.connection.a] + ([req.connection.b] if req.connection.b else [])
        serials = []
        for board in selected:
            if board.model_dump() not in self.host.configured_boards:
                raise TestError('Board identity mismatch', 'BOARD_MISMATCH')
            cfg = profile['boards'].get(board.board_id, {})
            if (cfg.get('com') != board.com or type(cfg.get('baudrate')) is not int or cfg['baudrate'] <= 0 or
                    cfg.get('line_ending') not in {'cr', 'lf', 'crlf'} or
                    any(not isinstance(cfg.get(k), str) or not cfg[k].strip() for k in ('lkshell_prompt', 'boot_marker', 'serial'))):
                raise TestError('Console/fastboot identity and readiness configuration required', 'FLASH_NOT_CONFIGURED')
            if not re.fullmatch(r'[A-Za-z0-9_.-]{1,160}', cfg['serial']):
                raise TestError('Invalid fastboot serial', 'FLASH_NOT_CONFIGURED')
            serials.append(cfg['serial'])
        if len(set(serials)) != len(serials):
            raise TestError('Fastboot serials must be distinct', 'BOARD_MISMATCH')
        for field, default in [('console_timeout', 120), ('fastboot_timeout', 60), ('flash_timeout', 1800), ('boot_timeout', 180)]:
            value = profile.get(field, default)
            if type(value) not in (int, float) or not 1 <= value <= 7200:
                raise TestError('Invalid flash timeout', 'FLASH_NOT_CONFIGURED')
        limit = profile.get('max_bundle_bytes', 64 * 1024**3)
        if type(limit) is not int or not 1 <= limit <= 1024**4:
            raise TestError('Invalid image staging byte limit', 'FLASH_NOT_CONFIGURED')
        root = Path(profile['image_root']).resolve(strict=True)
        if self.host.runtime.is_relative_to(root) or root.is_relative_to(self.host.runtime):
            raise TestError('Image root and runtime must be separate', 'IMAGE_PATH')
        if not Path(profile['fastboot']).is_absolute() or not Path(profile['fastboot']).is_file():
            raise TestError('Configure an absolute fastboot executable', 'FLASH_NOT_CONFIGURED')
        return json.loads(json.dumps(profile))

    def start(self, payload):
        req = FlashRequest.model_validate(payload)
        value = req.model_dump(); fingerprint = digest(value)
        with self.host.lock, sqlite3.connect(self.host.db) as c:
            if req.runner_id != self.host.identity:
                raise TestError('Windows runner identity changed', 'RUNNER_CHANGED')
            previous = c.execute('SELECT fingerprint,data FROM jobs WHERE id=?', (req.id,)).fetchone()
            if previous:
                if previous[0] != fingerprint:
                    raise TestError('Pipeline ID reused with different content', 'IDEMPOTENCY_CONFLICT')
                return json.loads(previous[1])
            if any(json.loads(r[0])['state'] in {'RUNNING', 'UNKNOWN'} for r in c.execute('SELECT data FROM jobs')):
                raise TestError('Windows host is reserved', 'RESERVATION_CONFLICT')
            validate_manifest(req.manifest)
            profile = self.profile(req)
            template = validate_command_template(req.template.model_dump())
            validate_windows_command(template)
            if not req.cases or len(req.cases) > 100 or any(not ids or len(ids) != len(set(ids)) for ids in req.cases.values()):
                raise TestError('Map each required case to distinct TC IDs', 'CASE_MAPPING')
            ids = list(dict.fromkeys(t for group in req.cases.values() for t in group))
            if len(ids) > 100:
                raise TestError('At most 100 TC per hardware pipeline', 'CASE_MAPPING')
            item = {'id': req.id, 'kind': 'flash-test', 'request_hash': fingerprint, 'source_revision': req.source_revision,
                    'state': 'RUNNING', 'phase': 'PREPARING', 'terminated': False, 'exit_code': None,
                    'started_at': now(), 'events': [], 'tests': [], 'flashes': [], 'request': value,
                    'profile': profile, 'reason': ''}
            c.execute('INSERT INTO jobs VALUES(?,?,?)', (req.id, fingerprint, json.dumps(item)))
            c.commit()  # Durable reservation BEFORE any file copy or device command.
            thread = threading.Thread(target=self.execute, args=(item,), daemon=False)
            self.host.threads.append(thread)
            thread.start()
            return item

    def update(self, item, phase, message):
        item['phase'] = phase
        item['events'].append({'at': now(), 'phase': phase, 'message': message})
        self.host.save(item)

    def copy_bundle(self, req, profile, destination):
        root = Path(profile['image_root']).resolve(strict=True)
        source = contained(root, req.bundle)
        destination.mkdir(parents=True, exist_ok=False)
        size = 0
        for name in req.manifest['files']:
            info = contained(source, name).stat()
            if not stat.S_ISREG(info.st_mode):
                raise TestError('Image entries must be regular files', 'IMAGE_PATH')
            size += info.st_size
        limit = profile.get('max_bundle_bytes', 64 * 1024**3)
        if size > limit or shutil.disk_usage(destination).free < size + 64 * 1024**2:
            raise TestError('Insufficient image staging capacity', 'IMAGE_SPACE')
        copied = 0
        for name, sha in req.manifest['files'].items():
            src = contained(source, name)
            target = destination / name
            target.parent.mkdir(parents=True, exist_ok=True)
            h = hashlib.sha256()
            with src.open('rb') as inp, target.open('xb') as out:
                if not stat.S_ISREG(os.fstat(inp.fileno()).st_mode):
                    raise TestError('Image changed to a non-regular file', 'IMAGE_PATH')
                for chunk in iter(lambda: inp.read(1024 * 1024), b''):
                    copied += len(chunk)
                    if copied > limit:
                        raise TestError('Image grew beyond staging capacity', 'IMAGE_SPACE')
                    h.update(chunk); out.write(chunk)
            if h.hexdigest() != sha:
                raise TestError('Image snapshot hash mismatch', 'IMAGE_CHANGED')

    def run(self, argv, cwd, timeout, flashing=False, env=None):
        tree = None
        try:
            tree = ProcessTree(argv, cwd, subprocess.PIPE, subprocess.PIPE, env=env)
            capture = Capture(tree.process.stdout, tree.process.stderr, limit=65536)
            deadline = time.monotonic() + timeout
            while not tree.stopped():
                if time.monotonic() >= deadline or capture.snapshot()[1]:
                    stopped = tree.stop()
                    if flashing or not stopped:
                        raise UnknownHardware('Execution interrupted; board state needs reconciliation', 'HARDWARE_UNKNOWN')
                    raise TestError('TC timeout or output limit', 'TC_EXECUTION')
                time.sleep(.05)
            if not capture.drain():
                raise UnknownHardware('Process output termination unverified', 'HARDWARE_UNKNOWN')
            texts, overflow = capture.snapshot()
            if overflow:
                raise TestError('Output limit exceeded', 'OUTPUT_LIMIT')
            return {**texts, 'exit_code': tree.process.poll(), 'terminated': True}
        except BaseException as exc:
            try: stopped = tree is None or tree.stop()
            except Exception: stopped = False
            if tree is not None and (not stopped or flashing):
                raise UnknownHardware('Process termination or flashed state requires reconciliation', 'HARDWARE_UNKNOWN') from exc
            raise
        finally:
            if tree: tree.close()

    def devices(self, profile):
        result = self.run([profile['fastboot'], 'devices'], self.host.runtime, 10)
        if result['exit_code'] != 0:
            raise TestError('Fastboot discovery failed', 'FASTBOOT_DISCOVERY')
        return [line.split()[0] for line in result['stdout'].splitlines() if len(line.split()) >= 2 and line.split()[1] == 'fastboot']

    def flash(self, profile, cfg, directory, batch):
        if os.name != 'nt':
            raise TestError('Physical flashing requires Windows', 'WINDOWS_REQUIRED')
        # Fixed local batch name, no caller-provided shell string or arguments.
        # Reviewed batch must honor ANDROID_SERIAL and propagate all flashing failures.
        command = str(Path(os.environ['SystemRoot']) / 'System32' / 'cmd.exe')
        local_batch = directory / batch
        return self.run([command, '/d', '/c', local_batch.name], local_batch.parent,
                        profile.get('flash_timeout', 1800), flashing=True,
                        env={'ANDROID_SERIAL': cfg['serial'], 'BSP_FASTBOOT': profile['fastboot']})

    def execute(self, item):
        req = FlashRequest.model_validate(item['request']); profile = item['profile']
        try:
            directory = self.host.runtime / 'flash-snapshots' / req.id
            images = directory / 'images'
            self.copy_bundle(req, profile, images)
            catalog = snapshot(self.host.root, directory / 'tc', self.host.metadata, req.source_revision)
            selected_ids = list(dict.fromkeys(t for ids in req.cases.values() for t in ids))
            selected = []
            for identity in selected_ids:
                tc = next((t for t in catalog['tests'] if t['id'] == identity and not t['disabled_reason']), None)
                if not tc or any(dep not in selected_ids[:selected_ids.index(identity)] for dep in tc.get('after', [])):
                    raise TestError('Invalid TC selection/order/dependency', 'CASE_MAPPING')
                argv = resolve_argv(req.template.model_dump()[tc['kind'].lower()], tc, req.connection.model_dump())
                argv[0], argv[1] = self.host.python, str(directory / 'tc' / tc['path'])
                selected.append((tc, argv))
            if [tc for tc, _ in selected] != req.tests:
                raise TestError('Pinned TC/parser metadata mismatch', 'SOURCE_CHANGED')
            self.host.verify(req.connection.model_dump())
            for board in [req.connection.a] + ([req.connection.b] if req.connection.b else []):
                cfg = profile['boards'][board.board_id]
                self.update(item, 'ENTERING_LKSHELL', board.board_id)
                console = self.io.console(cfg)
                try:
                    console.command('reboot lkshell')
                    console.wait(cfg['lkshell_prompt'], profile.get('console_timeout', 120))
                    self.update(item, 'ENTERING_FASTBOOT', board.board_id)
                    console.command('fast')
                finally:
                    console.close()
                deadline = time.monotonic() + profile.get('fastboot_timeout', 60)
                while True:
                    devices = self.io.devices(profile)
                    if devices == [cfg['serial']]: break
                    if devices and devices != [cfg['serial']]:
                        raise TestError('Unexpected or multiple fastboot targets', 'BOARD_MISMATCH')
                    if time.monotonic() >= deadline:
                        raise TestError('Target did not enter fastboot', 'FASTBOOT_TIMEOUT')
                    time.sleep(.2)
                self.update(item, 'FLASHING', board.board_id)
                console = self.io.console(cfg)
                try:
                    result = self.io.flash(profile, cfg, images, req.manifest['batch'])
                    text = result['stdout'] + '\n' + result['stderr']
                    markers = profile.get('failure_markers', ['FAILED', 'fastboot: error:'])
                    success = result['terminated'] and result['exit_code'] == 0 and profile['success_marker'] in text and not any(m.casefold() in text.casefold() for m in markers)
                    item['flashes'].append({'board': board.model_dump(), 'serial': cfg['serial'], 'manifest_hash': digest(req.manifest), 'result': result, 'success': success})
                    self.host.save(item)
                    if not success: raise TestError('Batch did not provide verified success', 'FLASH_FAILED')
                    self.update(item, 'WAITING_BOOT', board.board_id)
                    console.wait(cfg['boot_marker'], profile.get('boot_timeout', 180))
                    item['flashes'][-1]['boot_ready'] = True
                    self.host.save(item)
                finally:
                    console.close()  # Release the console before any TC opens COM.
            self.host.verify(req.connection.model_dump())
            for tc, argv in selected:
                if len(json.dumps(item).encode()) > 900000:
                    raise TestError('Pipeline evidence limit reached', 'OUTPUT_LIMIT')
                self.update(item, 'TESTING', tc['id'])
                result = self.io.run(argv, directory / 'tc', tc['timeout'])
                state, reason, _ = parse_result(result['stdout'], result['stderr'], result['exit_code'], terminated=result['terminated'], **tc.get('parser', {}))
                item['tests'].append({'tc_id': tc['id'], 'state': state, 'reason': reason, 'argv': argv, 'parser': tc.get('parser', {}), **result})
                self.host.save(item)
                if state not in {'PASS', 'FAIL'}:
                    raise TestError('TC result is incomplete', 'TC_EXECUTION')
            states = {t['tc_id']: t['state'] for t in item['tests']}
            item['cases'] = {case: 'PASS' if all(states[t] == 'PASS' for t in ids) else 'FAIL' for case, ids in req.cases.items()}
            item.update(outcome='SUCCEEDED' if all(v == 'PASS' for v in item['cases'].values()) else 'FAILED',
                        state='DONE', terminated=True)
            self.update(item, 'COMPLETED', 'Flash, boot readiness and mapped TC results recorded')
        except UnknownHardware as exc:
            item.update(state='UNKNOWN', outcome='UNKNOWN', terminated=False, reason=exc.code)
            self.update(item, 'UNKNOWN', exc.message)
        except Exception as exc:
            item.update(state='DONE', outcome='FAILED', terminated=True, reason=exc.code if isinstance(exc, TestError) else 'PIPELINE_ERROR')
            self.update(item, 'FAILED', exc.message if isinstance(exc, TestError) else 'Pipeline failed; inspect configuration and hardware')
        finally:
            item['ended_at'] = now()
            self.host.save(item)
