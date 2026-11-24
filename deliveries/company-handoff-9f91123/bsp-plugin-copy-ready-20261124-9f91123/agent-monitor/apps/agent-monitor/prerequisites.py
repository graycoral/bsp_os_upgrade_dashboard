"""Explicit OS package-manager preparation and signed supplied artifacts.

Detection is inert. apply=True is an installer action; it never starts SSH,
connects to a board, runs TC code or guesses private vendor package names.
"""
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time

PACKAGES = {
    'apt-get': ['python3', 'python3-venv', 'openssh-client'],
    'dnf': ['python3', 'python3-pip', 'openssh-clients'],
    'pacman': ['python', 'python-pip', 'openssh'],
}
SOURCES = ['https://learn.microsoft.com/windows/package-manager/winget/install',
           'https://learn.microsoft.com/windows-server/administration/openssh/openssh_install_firstuse',
           'https://developer.android.com/tools/releases/platform-tools']


def python_path(which=shutil.which, run=subprocess.run):
    if (3, 11) <= sys.version_info[:2] < (3, 14): return sys.executable
    for name in ('python3.13', 'python3.12', 'python3.11', 'python3'):
        path = which(name)
        if path and run([path, '-c', 'import sys;raise SystemExit(not ((3,11)<=sys.version_info[:2]<(3,14)))'],
                        stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode == 0:
            return path
    return None


def detect(*, platform=None, which=None, run=None):
    platform, which, run = platform or sys.platform, which or shutil.which, run or subprocess.run
    tools = {'python': python_path(which, run), 'ssh': which('ssh')}
    if platform == 'win32': tools['fastboot'] = which('fastboot')
    return {'platform': platform, 'tools': tools, 'missing': [name for name, path in tools.items() if not path]}


def prepare(home, apply=False, *, platform=None, which=None, run=None, detector=None, root=None):
    which, run = which or shutil.which, run or subprocess.run
    state = (detector or detect)(platform=platform, which=which, run=run)
    if not state['missing']: return state | {'state': 'REUSED', 'commands': []}
    commands = []
    if state['platform'] == 'win32':
        script = Path(__file__).resolve().parents[2] / 'scripts/bootstrap-prerequisites.ps1'
        powershell = which('powershell.exe') or which('pwsh')
        if not powershell: return state | {'state': 'BLOCKED', 'reason': 'POWERSHELL_UNAVAILABLE', 'commands': []}
        commands = [[powershell, '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', str(script)]]
    elif state['platform'].startswith('linux'):
        manager = next((name for name in PACKAGES if which(name)), None)
        if not manager: return state | {'state': 'BLOCKED', 'reason': 'PACKAGE_MANAGER_UNSUPPORTED', 'commands': []}
        is_root = os.geteuid() == 0 if root is None else root
        prefix = [] if is_root else [which('sudo') or 'sudo', '-n']
        names = PACKAGES[manager]
        if state['missing'] == ['ssh']: names = [names[-1]]
        install = [which(manager), *(['install', '-y'] if manager != 'pacman' else ['-S', '--needed', '--noconfirm']), *names]
        commands = [prefix + install]
    else:
        return state | {'state': 'BLOCKED', 'reason': 'PLATFORM_UNSUPPORTED', 'commands': []}
    if not apply: return state | {'state': 'PLANNED', 'commands': commands}
    home = Path(home); home.mkdir(parents=True, exist_ok=True)
    log = home / ('tools-' + str(time.time_ns()) + '.log')
    with log.open('wb') as stream:
        for argv in commands:
            result = run(argv, stdin=subprocess.DEVNULL, stdout=stream, stderr=stream, shell=False)
            if result.returncode:
                return state | {'state': 'BLOCKED', 'reason': 'PACKAGE_INSTALL_FAILED', 'log': str(log), 'commands': commands}
    after = (detector or detect)(platform=platform, which=which, run=run)
    return after | {'state': 'PREPARED' if not after['missing'] else 'BLOCKED',
                    'reason': '' if not after['missing'] else 'TOOLS_STILL_UNAVAILABLE', 'log': str(log), 'commands': commands}


def supplied_path(root, name):
    path = Path(name)
    if not isinstance(name, str) or path.is_absolute() or '..' in path.parts or '\\' in name:
        raise ValueError('Supplied artifact paths must be relative to the signed manifest')
    value = root / path
    if any(p.is_symlink() for p in [value, *value.parents]) or not value.resolve().is_relative_to(root):
        raise ValueError('Supplied artifact links/escapes are not allowed')
    return value



def healthy_supplied_python(python,pins,run):
    if not Path(python).is_file(): return False
    # Read installed metadata/RECORD bytes only; never import a company's TC.
    check = """import base64,hashlib,importlib.metadata as m,json,re,sys
from pathlib import Path
pins=json.loads(sys.argv[1]);root=Path(sys.argv[2]).resolve()
paths=[root/'Lib/site-packages',root/'lib'/('python'+str(sys.version_info.major)+'.'+str(sys.version_info.minor))/'site-packages']
canonical=lambda s:re.sub(r'[-_.]+','-',s).lower()
dists={canonical(d.metadata['Name']):d for d in m.distributions(path=[str(p) for p in paths])}
for name,version in pins.items():
 d=dists[canonical(name)]
 assert d.version==version and d.files
 for entry in d.files:
  if entry.hash is None: continue
  path=Path(d.locate_file(entry));assert path.resolve().is_relative_to(root) and path.is_file()
  actual=base64.urlsafe_b64encode(hashlib.new(entry.hash.mode,path.read_bytes()).digest()).rstrip(b'=').decode()
  assert actual==entry.hash.value
"""
    try:
        return run([str(python),'-I','-S','-c',check,json.dumps(pins),str(Path(python).parent.parent)],stdin=subprocess.DEVNULL,
                   stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,shell=False).returncode==0
    except (OSError,subprocess.SubprocessError): return False

def install_supplied(manifest, signature, keyring, home, *, wheelhouse=None, apply=False, run=None, which=None):
    run, which = run or subprocess.run, which or shutil.which
    manifest = Path(manifest).resolve()
    if not signature or not keyring: raise ValueError('Detached signature and trusted keyring are required')
    gpgv = which('gpgv')
    if not gpgv: raise RuntimeError('gpgv is required to verify supplied artifacts')
    if run([gpgv, '--keyring', str(Path(keyring).resolve()), str(Path(signature).resolve()), str(manifest)],
           stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, shell=False).returncode:
        raise ValueError('Supplied manifest signature is invalid')
    value = json.loads(manifest.read_text())
    if value.get('format') != 'agent-monitor-supplied-artifacts-v1' or not isinstance(value.get('artifacts'), list):
        raise ValueError('Unsupported supplied artifact manifest')
    commands = [];health_checks=[];drivers=False
    for item in value['artifacts']:
        path = supplied_path(manifest.parent, item['path'])
        with path.open('rb') as stream:
            actual_hash=hashlib.file_digest(stream,'sha256').hexdigest()
        if actual_hash != item.get('sha256'):
            raise ValueError('Supplied artifact hash mismatch')
        kind = item.get('kind')
        if kind == 'driver-deb':
            drivers=True
            executable = which('dpkg')
            if not executable or path.suffix != '.deb': raise ValueError('A .deb and dpkg host are required')
            commands.append([executable, '-i', str(path)])
        elif kind == 'driver-rpm':
            drivers=True
            executable = which('rpm')
            if not executable or path.suffix != '.rpm': raise ValueError('An .rpm and rpm host are required')
            commands.append([executable, '-Uvh', str(path)])
        elif kind == 'tc-requirements':
            if wheelhouse is None or not Path(wheelhouse).is_dir(): raise ValueError('An explicit offline wheelhouse is required')
            text = path.read_text().replace('\\\n', ' ')
            lines = [line.strip() for line in text.splitlines() if line.strip() and not line.lstrip().startswith('#')]
            if not lines or any(not re.fullmatch(r'[A-Za-z0-9_.-]+==[A-Za-z0-9_.+!-]+(?:\s+--hash=sha256:[a-f0-9]{64})+', line) for line in lines):
                raise ValueError('TC requirements must pin every package with SHA256 hashes and contain no pip directives/URLs')
            environment = Path(home).resolve() / 'supplied-tc-environment'
            python = environment / ('Scripts/python.exe' if os.name == 'nt' else 'bin/python')
            pins={line.split('==',1)[0]:line.split('==',1)[1].split()[0] for line in lines}
            health_checks.append((python,pins))
            if not python.exists(): commands.append([sys.executable, '-m', 'venv', str(environment)])
            commands.append([str(python), '-m', 'pip', 'install', '--require-hashes', '--no-deps', '--force-reinstall', '--no-index',
                             '--find-links', str(Path(wheelhouse).resolve()), '-r', str(path)])
        else:
            raise ValueError('Unsupported supplied artifact kind')
    identity = hashlib.sha256(manifest.read_bytes() + Path(signature).read_bytes() + Path(keyring).read_bytes()).hexdigest()
    receipt = Path(home) / 'supplied-artifacts.json'
    if (receipt.exists() and json.loads(receipt.read_text()).get('revision') == identity and not drivers and
            all(healthy_supplied_python(python,pins,run) for python,pins in health_checks)):
        return {'state': 'REUSED', 'revision': identity, 'commands': []}
    if not apply: return {'state': 'PLANNED', 'revision': identity, 'commands': commands}
    receipt.parent.mkdir(parents=True, exist_ok=True)
    log = receipt.parent / ('supplied-' + str(time.time_ns()) + '.log')
    with log.open('wb') as stream:
        for argv in commands:
            if argv[0] in {which('dpkg'), which('rpm')} and hasattr(os, 'geteuid') and os.geteuid() != 0:
                argv = [which('sudo') or 'sudo', '-n', *argv]
            if run(argv, stdin=subprocess.DEVNULL, stdout=stream, stderr=stream, shell=False).returncode:
                raise RuntimeError('Supplied installation failed; inspect ' + str(log))
    if not all(healthy_supplied_python(python,pins,run) for python,pins in health_checks):
        raise RuntimeError('Supplied package verification failed; previous receipt was preserved')
    receipt.write_text(json.dumps({'revision': identity, 'manifest': str(manifest), 'log': str(log)}, indent=2) + '\n')
    return {'state': 'INSTALLED', 'revision': identity, 'log': str(log), 'commands': commands,
            'company_hardware_acceptance': 'NOT_RUN'}
