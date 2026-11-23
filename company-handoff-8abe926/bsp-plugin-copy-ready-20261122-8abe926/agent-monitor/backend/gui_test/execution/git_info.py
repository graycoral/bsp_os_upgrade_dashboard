"""Bounded, read-only Git metadata for the configured TC source directory."""
from datetime import datetime, timezone
import os
from pathlib import Path
import re
import shutil
import subprocess
import threading
import time
from urllib.parse import urlsplit, urlunsplit


TIMEOUT_SECONDS = 2.0
MAX_OUTPUT_BYTES = 8192


class _GitReadError(Exception):
    def __init__(self, status):
        self.status = status


def _environment():
    # A runner may inherit a developer shell's Git overrides. They must never
    # redirect a TC source query to another repository or inject configuration.
    env = {key: value for key, value in os.environ.items() if not key.upper().startswith('GIT_')}
    env.update(GIT_CONFIG_NOSYSTEM='1', GIT_CONFIG_GLOBAL=os.devnull,
               GIT_TERMINAL_PROMPT='0', GIT_OPTIONAL_LOCKS='0', LC_ALL='C', LANG='C')
    return env


def _run_git(executable, root, args, deadline, env):
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise _GitReadError('timeout')
    try:
        process = subprocess.Popen(
            [executable, '--no-pager', '-c', 'core.fsmonitor=false', '-C', str(root), *args],
            stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            shell=False, env=env, cwd=root,
            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    except FileNotFoundError:
        raise _GitReadError('git_unavailable') from None
    except OSError:
        raise _GitReadError('error') from None

    output = [bytearray(), bytearray()]
    lock = threading.Lock()
    invalid = threading.Event()

    def stop():
        try:
            process.kill()
        except OSError:
            pass

    def read(pipe, index):
        try:
            while chunk := pipe.read(4096):
                with lock:
                    if sum(map(len, output)) + len(chunk) > MAX_OUTPUT_BYTES:
                        invalid.set()
                        stop()
                        return
                    output[index].extend(chunk)
        except (OSError, ValueError):
            invalid.set()
            stop()

    readers = [threading.Thread(target=read, args=(pipe, index), daemon=True)
               for index, pipe in enumerate((process.stdout, process.stderr))]
    for reader in readers:
        reader.start()
    try:
        try:
            process.wait(timeout=max(0.001, deadline - time.monotonic()))
        except subprocess.TimeoutExpired:
            stop()
            try:
                process.wait(timeout=0.1)
            except subprocess.TimeoutExpired:
                pass
            raise _GitReadError('timeout') from None
        for reader in readers:
            reader.join(timeout=max(0.001, min(0.1, deadline - time.monotonic())))
        if any(reader.is_alive() for reader in readers):
            raise _GitReadError('timeout')
        if invalid.is_set():
            raise _GitReadError('error')
        return process.returncode, *(bytes(value).decode('utf-8', errors='replace').strip() for value in output)
    finally:
        for pipe, reader in zip((process.stdout, process.stderr), readers):
            if not reader.is_alive():
                pipe.close()


def _remote(value):
    """Return a recognized origin without credentials or URL parameters."""
    if not value or len(value) > 4096 or any(ord(char) < 32 or ord(char) == 127 for char in value):
        return None
    try:
        if '://' in value:
            parts = urlsplit(value)
            if parts.scheme.lower() not in {'http', 'https', 'ssh', 'git', 'file'}:
                return None
            host = parts.hostname
            if parts.scheme.lower() != 'file' and not host:
                return None
            if host and ':' in host:
                host = '[' + host + ']'
            port = parts.port
            authority = (host or '') + (':' + str(port) if port is not None else '')
            return urlunsplit((parts.scheme.lower(), authority, parts.path, '', ''))
        # Git's SCP syntax has no scheme: user@host:path. Remove its user too.
        match = re.fullmatch(r'(?:[^@/:]+@)?(\[[0-9a-fA-F:]+\]|[A-Za-z0-9.-]+):([^\\].*)', value)
        if match and len(match[1]) > 1 and not match[2].startswith(':'):
            path = re.split(r'[?#]', match[2], maxsplit=1)[0]
            return match[1] + ':' + path if path else None
    except (ValueError, UnicodeError):
        pass
    return None


def inspect_git(source_root):
    """Observe Git HEAD; never use it as the executable TC snapshot revision."""
    result = {'status': 'error', 'source_path': None, 'repository_path': None,
              'remote': None, 'branch': None, 'commit': None, 'detached': None,
              'checked_at': datetime.now(timezone.utc).isoformat()}
    deadline = time.monotonic() + TIMEOUT_SECONDS
    try:
        root = Path(source_root).resolve(strict=True)
        result['source_path'] = str(root)
        if not root.is_dir():
            return result
        env = _environment()
        executable = shutil.which('git', path=env.get('PATH'))
        if not executable:
            result['status'] = 'git_unavailable'
            return result
        code, repository, error = _run_git(executable, root, ['rev-parse', '--show-toplevel'], deadline, env)
        if code:
            result['status'] = ('not_repository' if 'not a git repository' in error.casefold()
                                or 'must be run in a work tree' in error.casefold() else 'error')
            return result
        if (not repository or not Path(repository).is_absolute() or
                not root.is_relative_to(Path(repository).resolve(strict=True))):
            return result
        result['repository_path'] = repository
        code, branch, _ = _run_git(executable, root, ['symbolic-ref', '--quiet', '--short', 'HEAD'], deadline, env)
        if code not in (0, 1) or (code == 0 and (not branch or len(branch) > 1024 or
                                                any(ord(char) < 32 or ord(char) == 127 for char in branch))):
            return result
        result.update(branch=branch if code == 0 else None, detached=code == 1)
        code, commit, _ = _run_git(executable, root, ['rev-parse', '--verify', 'HEAD'], deadline, env)
        if code == 0 and re.fullmatch(r'(?:[0-9a-fA-F]{40}|[0-9a-fA-F]{64})', commit):
            result.update(status='available', commit=commit.lower())
        elif code and result['branch'] is not None:
            result['status'] = 'unborn'
        else:
            return result
        code, remote, _ = _run_git(executable, root,
                                  ['config', '--local', '--no-includes', '--get', 'remote.origin.url'], deadline, env)
        if code not in (0, 1):
            result['status'] = 'error'
            return result
        result['remote'] = _remote(remote) if code == 0 else None
    except _GitReadError as exc:
        result['status'] = exc.status
    except (OSError, TypeError, ValueError):
        # No raw Git output, origin or exception text crosses the API boundary.
        result['status'] = 'error'
    return result
