"""Bounded, non-interactive subprocesses; never return raw credential-bearing output."""
import os
import signal
import subprocess
import tempfile
import time
from dataclasses import dataclass


@dataclass
class ProcessResult:
    code: int | None
    stdout: bytes = b''
    stderr: bytes = b''
    error: str = ''
    unknown: bool = False


def run_process(argv, *, cwd, timeout, stdin=b'', env=None, limit=4_194_304):
    with tempfile.TemporaryFile() as out, tempfile.TemporaryFile() as err, tempfile.TemporaryFile() as inp:
        inp.write(stdin); inp.seek(0)
        try:
            p = subprocess.Popen(argv, stdin=inp, stdout=out, stderr=err, cwd=cwd,
                                 env=env, start_new_session=True)
        except OSError:
            return ProcessResult(None, error='실행 파일 또는 작업 폴더를 확인하세요.')
        deadline = time.monotonic() + timeout
        problem = ''
        while p.poll() is None:
            if time.monotonic() >= deadline:
                problem = '실행 시간 초과'
            elif os.fstat(out.fileno()).st_size + os.fstat(err.fileno()).st_size > limit:
                problem = '출력 크기 제한 초과'
            if problem:
                break
            time.sleep(.02)
        # Normal foreground CLI exit is already observed. Do not signal its reaped PID/PGID.
        if p.poll() is None:
            try:
                os.killpg(p.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            except PermissionError:
                # Cannot establish that all children stopped: caller must retain its lease.
                try:
                    p.kill()
                    p.wait(timeout=1)
                except (OSError, subprocess.TimeoutExpired):
                    pass
                return ProcessResult(p.poll(), error='프로세스 그룹 종료를 확인할 수 없습니다. 수동 상태 확인이 필요합니다.', unknown=True)
        p.wait()
        if os.fstat(out.fileno()).st_size + os.fstat(err.fileno()).st_size > limit:
            problem = problem or '출력 크기 제한 초과'
        if problem:
            return ProcessResult(p.returncode, error=problem)
        out.seek(0); err.seek(0)
        return ProcessResult(p.returncode, out.read(limit), err.read(limit))
