"""Bounded, non-interactive subprocesses; never return raw credential-bearing output."""
import os
import signal
import subprocess
import tempfile
import time
import hashlib
from pathlib import Path
from uuid import uuid4
from backend.adapters.receipts import ProcessVerification, verify_receipt
from dataclasses import dataclass


@dataclass
class ProcessResult:
    code: int | None
    stdout: bytes = b''
    stderr: bytes = b''
    error: str = ''
    unknown: bool = False
    process_receipt: dict | None = None


def run_process(argv, *, cwd, timeout, stdin=b'', env=None, limit=4_194_304, launch_context=None, receipt_sink=None):
    if launch_context is not None or receipt_sink is not None:
        return _run_receipted(argv, cwd=cwd, timeout=timeout, stdin=stdin, env=env, limit=limit,
                              launch_context=launch_context, receipt_sink=receipt_sink)
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


def _run_receipted(argv, *, cwd, timeout, stdin, env, limit, launch_context, receipt_sink):
    from backend.adapters.receipts import durable_receipt, launch_receipt, verify_receipt
    context = dict(launch_context or {})
    context.setdefault('launch_id', str(uuid4()))
    # A receipt sink is called outside DB transactions. The runtime must persist an
    # intent nonce before entering this function and treat a missing receipt as UNKNOWN.
    root = Path(cwd).resolve()
    folder = Path(context.get('receipt_dir') or root / '.bsp-dashboard' / 'results' / 'receipts' / context['launch_id']).resolve()
    if not folder.is_relative_to(root) or folder == root:
        return ProcessResult(None, error='Receipt path must be inside the workspace.', unknown=True)
    receipt = None
    def publish(value):
        digest = durable_receipt(folder / 'process.json', value)
        result = value | {'receipt_sha256': digest, 'receipt_path': str((folder / 'process.json').relative_to(root))}
        if receipt_sink:
            receipt_sink(result)
        return result
    with tempfile.TemporaryFile() as out, tempfile.TemporaryFile() as err, tempfile.TemporaryFile() as inp:
        inp.write(stdin)
        inp.seek(0)
        try:
            p = subprocess.Popen(argv, stdin=inp, stdout=out, stderr=err, cwd=cwd, env=env, start_new_session=True)
        except OSError:
            return ProcessResult(None, error='Process launch failed.')
        try:
            receipt = publish(launch_receipt(p.pid, context))
        except Exception:
            # The spawn-to-receipt gap is never represented as a normal failure.
            try:
                p.kill()
                p.wait(timeout=2)
            except (OSError, subprocess.TimeoutExpired):
                pass
            return ProcessResult(p.poll(), error='Process identity receipt could not be durably recorded.', unknown=True)
        deadline = time.monotonic() + timeout
        problem = ''
        while p.poll() is None:
            if time.monotonic() >= deadline:
                problem = 'Process timeout.'
            elif os.fstat(out.fileno()).st_size + os.fstat(err.fileno()).st_size > limit:
                problem = 'Process output limit exceeded.'
            if problem:
                verification = verify_receipt(receipt)
                if verification.state != 'ALIVE':
                    return ProcessResult(p.poll(), error='Cannot verify process identity before termination.', unknown=True, process_receipt=receipt)
                try:
                    if os.name == 'posix':
                        os.killpg(receipt['group_id'], signal.SIGKILL)
                    else:
                        # No durable Windows descendant proof: UNKNOWN is retained.
                        p.kill()
                except (OSError, PermissionError):
                    return ProcessResult(p.poll(), error='Process termination could not be established.', unknown=True, process_receipt=receipt)
                break
            time.sleep(.02)
        try:
            p.wait(timeout=3)
        except subprocess.TimeoutExpired:
            return ProcessResult(p.poll(), error='Process termination wait timed out.', unknown=True, process_receipt=receipt)
        verification = verify_receipt(receipt)
        # Short kernel cleanup races may settle, but never turn ambiguity into success.
        if verification.state == 'ALIVE' and os.name == 'posix':
            time.sleep(.02)
            verification = verify_receipt(receipt)
        out.seek(0)
        err.seek(0)
        stdout, stderr = out.read(limit + 1), err.read(limit + 1)
        if len(stdout) + len(stderr) > limit:
            problem = problem or 'Process output limit exceeded.'
            stdout, stderr = stdout[:limit], stderr[:max(0, limit - min(len(stdout), limit))]
        try:
            outputs = {}
            for name, raw in (('stdout', stdout), ('stderr', stderr)):
                path = folder / (name + '.bin')
                path.parent.mkdir(parents=True, exist_ok=True)
                temporary = path.with_suffix('.tmp')
                with temporary.open('wb') as stream:
                    stream.write(raw)
                    stream.flush()
                    os.fsync(stream.fileno())
                os.replace(temporary, path)
                outputs[name] = {'path': str(path.relative_to(root)), 'sha256': hashlib.sha256(raw).hexdigest(), 'size': len(raw)}
            terminal = {key: value for key, value in receipt.items() if key not in {'receipt_sha256', 'receipt_path'}}
            terminal.update(phase='TERMINATED' if verification.state == 'TERMINATED' else 'UNKNOWN',
                            finished_at=time.time(), exit_code=p.returncode, verification=verification.evidence,
                            outputs=outputs, error=problem)
            receipt = publish(terminal)
        except Exception:
            return ProcessResult(p.returncode, error='Terminal receipt could not be durably recorded.', unknown=True, process_receipt=receipt)
        if verification.state != 'TERMINATED':
            return ProcessResult(p.returncode, error='Complete process-group termination is unverified.', unknown=True, process_receipt=receipt)
        return ProcessResult(p.returncode, stdout, stderr, problem, process_receipt=receipt)
