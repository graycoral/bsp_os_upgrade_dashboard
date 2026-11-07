"""Opt-in T-211/212/216 real Windows ZIP relocation/edit/repack smoke.

Run with a host Python: python tests/editable_runner_smoke.py --zip <built.zip>
No SSH, COM, boards or model calls. All children use the bundled Python.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.request import build_opener, ProxyHandler, Request
import uuid
import zipfile


def actual_host_smoke(root, work, report, env, outcomes):
    """Real bundled Host.main/Uvicorn; identity only, no TC/COM/SSH access."""
    external_python = Path(sys.executable).resolve()
    assert not external_python.is_relative_to(root)
    source = work / 'empty TC source'
    source.mkdir()
    runtime = work / 'isolated host runtime'
    runtime.mkdir()
    config = work / 'host-fixture.json'
    config.write_text(json.dumps({'source_root': str(source), 'python': str(external_python),
        'boards': [{'host': 'fixture-host', 'board_id': 'fixture', 'com': 'COM254', 'node': 'fixture'}]}), encoding='utf-8')
    python = str(root / 'runtime/python.exe')
    owner_file = work / 'owner-identity.json'
    child_env = dict(env, GUI_TEST_RUNNER_TOKEN='fixture-host-token-' + 'a' * 48)
    identity_code = ('import json; from pathlib import Path; '
        'from backend.gui_test.execution.launch import process_identity; '
        f'Path({str(owner_file)!r}).write_text(json.dumps(process_identity({os.getpid()})))')
    with (report / 'host-owner.stdout.log').open('wb') as out, (report / 'host-owner.stderr.log').open('wb') as err:
        result = subprocess.run([python, '-B', '-X', 'utf8', '-c', identity_code], env=child_env,
                                cwd=work, stdout=out, stderr=err, timeout=15)
    assert result.returncode == 0
    owner = json.loads(owner_file.read_text())
    # Only add deterministic graceful shutdown and a trap against accidental COM
    # enumeration; Host.main, socket handoff, lifespan and HTTP auth remain real.
    harness = '''
import sys,threading,time
from pathlib import Path
import uvicorn
from serial.tools import list_ports
def forbidden(*a,**k): raise RuntimeError('Smoke must not access COM or TC')
list_ports.comports=forbidden
stop=Path(sys.argv.pop(1))
original=uvicorn.Server.run
def run(server,*a,**k):
    def monitor():
        while not stop.exists(): time.sleep(.025)
        server.should_exit=True
    threading.Thread(target=monitor,daemon=True).start()
    return original(server,*a,**k)
uvicorn.Server.run=run
from backend.gui_test.execution.host import Host,main
Host.catalog=forbidden
main(sys.argv[1:])
'''
    opener = build_opener(ProxyHandler({}))
    children = []
    def start(name, port, fallback):
        nonce = uuid.uuid4().hex
        receipt = runtime / ('launch-' + nonce + '.json')
        stop = work / (name + '.stop')
        args = [python, '-B', '-X', 'utf8', '-c', harness, str(stop), '--config', str(config),
                '--runtime', str(runtime), '--port', str(port), '--launch-id', nonce,
                '--startup-receipt', str(receipt), '--owner-pid', str(owner['pid']),
                '--owner-created', owner['creation_time']]
        if fallback: args.append('--allow-port-fallback')
        out = (report / (name + '.stdout.log')).open('wb')
        err = (report / (name + '.stderr.log')).open('wb')
        child = subprocess.Popen(args, env=child_env, cwd=work, stdout=out, stderr=err)
        children.append((child, stop, out, err))
        return child, receipt
    try:
        with socket.socket() as occupied:
            occupied.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
            occupied.bind(('127.0.0.1', 0))
            occupied.listen()
            preferred = occupied.getsockname()[1]
            child, receipt = start('actual-host', preferred, True)
            deadline = time.monotonic() + 20
            identity = None
            while time.monotonic() < deadline:
                assert child.poll() is None, 'Host exited before authenticated readiness'
                if receipt.exists():
                    startup = json.loads(receipt.read_text(encoding='utf-8'))
                    try:
                        url = f'http://127.0.0.1:{startup["runner_port"]}/v1/identity'
                        request = Request(url, headers={'Authorization': 'Bearer ' + child_env['GUI_TEST_RUNNER_TOKEN']})
                        with opener.open(request, timeout=.5) as response:
                            identity = json.loads(response.read())
                        break
                    except (OSError, URLError): pass
                time.sleep(.05)
            assert identity and identity['runner_id'] == startup['runner_id']
            assert startup['runner']['pid'] == child.pid and startup['owner'] == owner
            assert startup['runner_port'] != preferred
            try:
                opener.open(Request(url), timeout=2)
                raise AssertionError('Host accepted an unauthenticated request')
            except HTTPError as error:
                assert error.code == 401
            # A second actual Host may bind but its lifespan must fail the same
            # runtime's final ProcessLock and must never become a second service.
            with socket.socket() as probe:
                probe.bind(('127.0.0.1', 0))
                second_port = probe.getsockname()[1]
            duplicate, _ = start('actual-host-duplicate', second_port, False)
            assert duplicate.wait(timeout=15) != 0
            with opener.open(request, timeout=2) as response:
                assert json.loads(response.read())['runner_id'] == startup['runner_id']
            outcomes.append({'name': 'actual-host-socket-auth-final-lock', 'exit_code': 0,
                             'runner_port': startup['runner_port']})
    finally:
        for child, stop, out, err in reversed(children):
            stop.touch()
            try: child.wait(timeout=12)
            except subprocess.TimeoutExpired:
                child.kill()
                child.wait(timeout=5)
                raise AssertionError('Fixture Host failed graceful shutdown')
            finally:
                out.close()
                err.close()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--zip', required=True, type=Path)
    parser.add_argument('--work-root', type=Path, default=Path('C:/Temp/rq61-tests-short'))
    parser.add_argument('--report-dir', required=True, type=Path)
    parser.add_argument('--actual-host', action='store_true', help='Also run bundled Host/Uvicorn identity-only smoke')
    args = parser.parse_args(argv)
    if os.name != 'nt':
        parser.error('This acceptance smoke requires Windows x64.')
    report = args.report_dir.resolve()
    report.mkdir(parents=True, exist_ok=False)
    work = args.work_root.resolve() / ('한글 Runner space ' + uuid.uuid4().hex[:8])
    work.mkdir(parents=True)
    archive = args.zip.resolve()
    original_sha = hashlib.sha256(archive.read_bytes()).hexdigest()
    outcomes = []
    env = dict(os.environ)
    env['PATH'] = str(Path(os.environ['SystemRoot']) / 'System32')
    poison = work / 'wrong external Python path'
    (poison / 'scripts').mkdir(parents=True)
    (poison / 'scripts/__init__.py').write_text("raise RuntimeError('PYTHONPATH leaked')\n")
    env['PYTHONPATH'] = str(poison)
    env['GUI_TEST_RUNNER_TOKEN'] = 'fixture-only-not-a-real-token'

    def run(root, name, arguments):
        executable = root / 'runtime/python.exe'
        with (report / (name + '.stdout.log')).open('wb') as out, (report / (name + '.stderr.log')).open('wb') as err:
            completed = subprocess.run([str(executable), '-B', '-X', 'utf8', *arguments], cwd=work,
                                       env=env, stdout=out, stderr=err, timeout=120)
        outcomes.append({'name': name, 'exit_code': completed.returncode})
        if completed.returncode:
            raise AssertionError(f'{name} exited {completed.returncode}; see {report}')

    try:
        first = work / '압축 해제 first'
        with zipfile.ZipFile(archive) as z:
            z.extractall(first)
        # Accept a single documented top-level folder as well as a flat archive.
        if not (first / 'bundle.json').is_file():
            candidates = list(first.glob('*/bundle.json'))
            assert len(candidates) == 1, 'cannot find unique bundle root'
            first = candidates[0].parent
        moved = work / '이동 relocated'
        shutil.move(str(first), moved)
        for tool in ('python', 'py', 'pip'):
            assert shutil.which(tool, path=env['PATH']) is None, f'{tool} unexpectedly on smoke PATH'
        run(moved, 'help', ['-m', 'scripts.setup_runtime', '--help'])
        run(moved, 'imports', ['-c',
            'import fastapi,uvicorn,pydantic,serial,sqlite3; '
            'from backend.gui_test.execution.bundle import runtime_mode; '
            'assert runtime_mode()=="editable"'])
        if args.actual_host:
            actual_host_smoke(moved, work, report, env, outcomes)
        baseline = json.loads((moved / 'build-info.json').read_text(encoding='utf-8'))
        source = moved / 'src/scripts/setup_ports.py'
        with source.open('a', encoding='utf-8') as stream:
            stream.write('\nRQ61_EDIT_PROBE = "edited-after-extract"\n')
        run(moved, 'edited-source', ['-c',
            'from scripts.setup_ports import RQ61_EDIT_PROBE; '
            'assert RQ61_EDIT_PROBE=="edited-after-extract"'])
        repacked = work / '새 전달 repacked.zip'
        run(moved, 'cacheless-repack', ['-m', 'scripts.build_editable_runner', 'repack',
                                      '--bundle-root', str(moved), '--output', str(repacked)])
        second = work / '두번째 reextract'
        with zipfile.ZipFile(repacked) as z:
            z.extractall(second)
        if not (second / 'bundle.json').is_file():
            second = next(second.glob('*/bundle.json')).parent
        run(second, 'repacked-edit', ['-c',
            'from scripts.setup_ports import RQ61_EDIT_PROBE; '
            'assert RQ61_EDIT_PROBE=="edited-after-extract"'])
        info = json.loads((second / 'build-info.json').read_text(encoding='utf-8'))
        assert info['original_source_hashes'] == baseline['original_source_hashes']
        assert info['parent_bundle_id'] == baseline['bundle_id'] and info['modified'] is True
        assert info['immutable_hashes'] == baseline['immutable_hashes']
        assert not list(second.rglob('*.pyc')), 'bytecode can obscure source edit behavior'
        assert hashlib.sha256(archive.read_bytes()).hexdigest() == original_sha
        outcomes.append({'name': 'relocate-edit-repack-provenance', 'exit_code': 0})
        return 0
    finally:
        (report / 'results.json').write_text(json.dumps({'work_root': str(work), 'checks': outcomes}, indent=2), encoding='utf-8')


if __name__ == '__main__':
    raise SystemExit(main())
