"""Offline adoption/release/prerequisite tests; no OS installers or hardware."""
import hashlib
import importlib.util
import json
from pathlib import Path
import sqlite3
import subprocess
from types import SimpleNamespace

import pytest

ROOT=Path(__file__).resolve().parents[1]


@pytest.fixture
def modules(monkeypatch):
    monkeypatch.syspath_prepend(str(ROOT/'apps/agent-monitor'))
    import recovery,prerequisites
    spec=importlib.util.spec_from_file_location('monitor_recovery_tests',ROOT/'apps/agent-monitor/manage.py')
    manager=importlib.util.module_from_spec(spec);spec.loader.exec_module(manager)
    return manager,recovery,prerequisites


def gui_runtime(runtime,state='PAUSED',contract='bsp-upgrade-integration-v1'):
    runtime.mkdir(parents=True,exist_ok=True)
    db=runtime/'gui/runs.db';db.parent.mkdir()
    with sqlite3.connect(db) as c:
        c.execute('CREATE TABLE meta(key TEXT,value TEXT)');c.execute("INSERT INTO meta VALUES('schema_version','1')")
        c.execute('CREATE TABLE runs(id TEXT,data TEXT)')
        c.execute('INSERT INTO runs VALUES(?,?)',('run',json.dumps({'id':'run','state':state,'attempts':[],
            'integration':{'contract_version':contract,'retry_policy':'fail-stop-analysis-v1'}})))
    return db


def installed(manager,home,monkeypatch,*releases):
    for release in releases:
        path=home/'releases'/release;path.mkdir(parents=True)
        (path/'source.txt').write_text('fixed '+release)
    monkeypatch.setattr(manager,'verify',lambda path:{'release':Path(path).name})
    monkeypatch.setattr(manager,'valid_environment',lambda path:True)


def test_offline_compatible_adoption_cas_backup_and_state_preservation(modules,tmp_path,monkeypatch):
    manager,recovery,_=modules;home=tmp_path/'home';runtime=tmp_path/'existing';release='a'*64
    db=gui_runtime(runtime);config=runtime/'settings.json';config.write_text('{"preserved":true}')
    manager.bind_runtime(home,runtime);installed(manager,home,monkeypatch,release)
    monkeypatch.setattr(manager.subprocess,'Popen',lambda *a,**k:pytest.fail('adoption launched a process'))
    report=manager.inspect_runtime(home)
    assert report['adoptable'] is True and report['compatible'] is True
    with pytest.raises(RuntimeError,match='INSPECTION_CHANGED'):manager.adopt_runtime(home,release,'0'*64)
    adopted=manager.adopt_runtime(home,release,report['revision'])
    assert adopted['state']=='ADOPTED' and adopted['started'] is False
    backup=Path(adopted['backup']['path']);assert backup.is_dir()
    with sqlite3.connect(backup/'gui/runs.db') as c:
        assert json.loads(c.execute('SELECT data FROM runs').fetchone()[0])['state']=='PAUSED'
    assert (backup/'settings.json').read_bytes()==config.read_bytes()
    with sqlite3.connect(db) as c: assert json.loads(c.execute('SELECT data FROM runs').fetchone()[0])['state']=='PAUSED'
    assert manager.current(home)['release']==release
    with pytest.raises(RuntimeError,match='ADOPTION_BLOCKED'):manager.adopt_runtime(home,release,report['revision'])


@pytest.mark.parametrize('state,contract',[('UNKNOWN','bsp-upgrade-integration-v1'),('RUNNING','bsp-upgrade-integration-v1'),('PAUSED','future-contract')])
def test_adoption_never_bypasses_unknown_live_or_unknown_contract(modules,tmp_path,monkeypatch,state,contract):
    manager,_,_=modules;home=tmp_path/'home';runtime=tmp_path/'existing';release='a'*64
    db=gui_runtime(runtime,state,contract);manager.bind_runtime(home,runtime);installed(manager,home,monkeypatch,release)
    report=manager.inspect_runtime(home)
    assert report['adoptable'] is False
    with pytest.raises(RuntimeError,match='ADOPTION_BLOCKED'):manager.adopt_runtime(home,release,report['revision'])
    assert not (home/'current.json').exists() and not (home/'backups').exists()
    with sqlite3.connect(db) as c:assert json.loads(c.execute('SELECT data FROM runs').fetchone()[0])['state']==state


def test_inspection_respects_original_worker_ownership(modules,tmp_path):
    manager,_,_=modules;home=tmp_path/'home';runtime=tmp_path/'existing'
    gui_runtime(runtime);manager.bind_runtime(home,runtime)
    with manager.lock(runtime/'worker.lock'):
        with pytest.raises(RuntimeError):manager.inspect_runtime(home)
    assert not (home/'current.json').exists()


def reserved_runtime(runtime):
    db = gui_runtime(runtime)
    with sqlite3.connect(db) as connection:
        run = json.loads(connection.execute('SELECT data FROM runs').fetchone()[0])
        run.update(simulation=True, lease_token='PRIVATE_TOKEN', connection_snapshot={'host': 'private.company'})
        run['attempts'] = [{'state': 'ERROR', 'terminated': False, 'process_ref': 'PRIVATE_PROCESS'}]
        connection.execute('UPDATE runs SET data=?', (json.dumps(run),))
        connection.execute('CREATE TABLE reservations(resource TEXT PRIMARY KEY, run_id TEXT, token TEXT)')
        connection.executemany('INSERT INTO reservations VALUES(?,?,?)', [
            ('private.company:board:one', 'run', 'PRIVATE_TOKEN'),
            ('private.company:com:one', 'run', 'PRIVATE_TOKEN'),
            ('private.company:board:missing', 'missing-run', 'OTHER_TOKEN'),
        ])
    return db


def test_t254_reservation_diagnosis_counts_owners_and_resources_without_private_data(modules, tmp_path):
    manager, recovery, _ = modules
    home, runtime = tmp_path / 'home', tmp_path / 'PRIVATE_RUNTIME'
    db = reserved_runtime(runtime)
    manager.bind_runtime(home, runtime)
    before = db.read_bytes()
    report = manager.diagnose_runtime(home)
    assert report['adoptable'] is False
    assert report['unresolved'] == {'HELD_RESERVATIONS': 1, 'ATTEMPT_UNCONFIRMED': 1}
    assert report['reservations'] == {'verified': True, 'resources': 3,
        'owner_states': {'PAUSED': 1, 'OWNER_MISSING': 1}, 'execution_modes': {'mock': 1},
        'unconfirmed_attempts': 1, 'preservable_resources': 0,
        'blockers': {'ATTEMPT_UNCONFIRMED': 2, 'OWNER_MISSING': 1}}
    text = json.dumps(report) + recovery.diagnostic_text(report)
    for private in ('PRIVATE', 'private.company', 'missing-run', str(runtime)):
        assert private not in text
    assert db.read_bytes() == before
    assert not (home / 'current.json').exists()


def test_t254_doctor_uses_requested_runtime_without_installing_or_launching(modules, tmp_path, monkeypatch, capsys):
    manager, _, prerequisites = modules
    home, runtime = tmp_path / 'home', tmp_path / 'existing'
    reserved_runtime(runtime)
    monkeypatch.setattr(prerequisites, 'prepare', lambda *a, **k: pytest.fail('doctor installed tools'))
    monkeypatch.setattr(manager.subprocess, 'Popen', lambda *a, **k: pytest.fail('doctor launched process'))
    assert manager.main(['doctor', '--home', str(home), '--runtime', str(runtime)]) == 0
    captured = capsys.readouterr()
    assert json.loads(captured.out)['reservations']['resources'] == 3
    assert 'PAUSED 1' in captured.err and '종료 미확인 시도 · 1개' in captured.err
    assert not (home / 'runtime-location.json').exists()


def test_t254_start_prints_private_safe_diagnosis_when_first_adoption_is_blocked(modules, tmp_path, monkeypatch):
    manager, _, _ = modules
    home, runtime = tmp_path / 'home', tmp_path / 'PRIVATE_RUNTIME'
    reserved_runtime(runtime)
    manager.bind_runtime(home, runtime)
    monkeypatch.setattr(manager, 'prepare', lambda *a: {'state': 'UPDATE_PENDING'})
    monkeypatch.setattr(manager.subprocess, 'Popen', lambda *a, **k: pytest.fail('unverified runtime started'))
    with pytest.raises(RuntimeError) as error:
        manager.start(home)
    assert 'HELD_RESERVATIONS 1' in str(error.value)
    assert 'PAUSED 1' in str(error.value)
    assert 'bash run.sh doctor' in str(error.value)
    assert 'PRIVATE' not in str(error.value) and 'private.company' not in str(error.value)


def test_t254_doctor_respects_worker_lock_and_saved_runtime(modules, tmp_path):
    manager, _, _ = modules
    home, runtime = tmp_path / 'home', tmp_path / 'existing'
    reserved_runtime(runtime)
    manager.bind_runtime(home, runtime)
    with pytest.raises(ValueError): manager.diagnose_runtime(home, tmp_path / 'wrong')
    with manager.lock(runtime / 'worker.lock'):
        with pytest.raises(RuntimeError): manager.diagnose_runtime(home)


def test_t254_doctor_reports_unreadable_reservations_as_unverified(modules, tmp_path):
    manager, recovery, _ = modules
    home, runtime = tmp_path / 'home', tmp_path / 'existing'
    db = reserved_runtime(runtime)
    manager.bind_runtime(home, runtime)
    with sqlite3.connect(db) as connection:
        connection.execute('UPDATE runs SET data=?', ('PRIVATE_INVALID_JSON',))
    report = manager.diagnose_runtime(home)
    assert report['adoptable'] is False and report['reservations']['verified'] is False
    assert report['issues']['DATABASE_UNREADABLE'] == 1
    assert '예약 상세 · DB 내용을 확인할 수 없습니다.' in recovery.diagnostic_text(report)
    assert 'PRIVATE' not in json.dumps(report)


def test_t254_diagnosis_skips_snapshot_hashes_and_cannot_supply_adoption_revision(modules, tmp_path, monkeypatch):
    manager, recovery, _ = modules
    home, runtime = tmp_path / 'home', tmp_path / 'existing'
    reserved_runtime(runtime)
    (runtime / 'large-snapshot.bin').write_bytes(b'fixture')
    manager.bind_runtime(home, runtime)
    monkeypatch.setattr(recovery, 'file_hash', lambda path: pytest.fail('diagnosis hashed snapshot'))
    monkeypatch.setattr(recovery, 'digest', lambda value: pytest.fail('diagnosis hashed DB rows'))
    report = recovery.inspect(runtime, include_revision=False)
    assert 'revision' not in report
    assert manager.diagnose_runtime(home)['reservations']['resources'] == 3


def paused_hardware_runtime(runtime):
    db = reserved_runtime(runtime)
    with sqlite3.connect(db) as connection:
        connection.execute("DELETE FROM reservations WHERE run_id='missing-run'")
        run = json.loads(connection.execute('SELECT data FROM runs').fetchone()[0])
        run.update(simulation=False, integration=None)
        run['attempts'][0]['terminated'] = True
        connection.execute('UPDATE runs SET data=?', (json.dumps(run),))
    return db


def test_t254_start_adopts_verified_paused_hardware_reservations_with_backup(modules, tmp_path, monkeypatch):
    manager, _, _ = modules
    home, runtime, release = tmp_path / 'home', tmp_path / 'existing', 'a' * 64
    db = paused_hardware_runtime(runtime)
    manager.bind_runtime(home, runtime)
    installed(manager, home, monkeypatch, release)
    target = home / 'releases' / release
    before = db.read_bytes()
    report = manager.inspect_runtime(home)
    assert report['adoptable'] is True
    assert manager.diagnose_runtime(home)['reservations']['preservable_resources'] == 2
    assert manager.has_work(runtime)  # Shutdown/update still require settled work.

    def prepare(*args):
        assert manager.activate(home, release, target)
        return {'state': 'REUSED', 'release': release, 'path': str(target)}

    launched = []
    monkeypatch.setattr(manager, 'prepare', prepare)
    monkeypatch.setattr(manager.subprocess, 'Popen', lambda argv, **kw: launched.append(argv) or SimpleNamespace(poll=lambda: None))
    monkeypatch.setattr(manager, 'status', lambda path: {'state': 'READY'})
    assert manager.start(home, port=0)['state'] == 'READY'
    assert len(launched) == 1 and '_serve' in launched[0]
    assert db.read_bytes() == before
    receipt = manager.read(home / 'runtime-adoption.json')
    assert receipt['automatic'] is True
    with sqlite3.connect(Path(receipt['backup']['path']) / 'gui/runs.db') as connection:
        assert connection.execute('SELECT COUNT(*) FROM reservations').fetchone()[0] == 2
        saved = json.loads(connection.execute('SELECT data FROM runs').fetchone()[0])
        assert saved['state'] == 'PAUSED' and saved['simulation'] is False
    assert manager.current(home)['release'] == release
    assert manager.activate(home, release, target)
    assert len(list((home / 'backups').iterdir())) == 1
    assert not manager.activate(home, 'b' * 64, home / 'other-release')


@pytest.mark.parametrize('case', ['running', 'unknown', 'unterminated', 'missing-proof', 'token', 'orphan',
                                  'lease', 'batch', 'pending-batch', 'future-contract', 'mode'])
def test_t254_automatic_adoption_rejects_unverified_reservations(modules, tmp_path, monkeypatch, case):
    manager, _, _ = modules
    home, runtime, release = tmp_path / 'home', tmp_path / 'existing', 'a' * 64
    db = paused_hardware_runtime(runtime)
    manager.bind_runtime(home, runtime)
    installed(manager, home, monkeypatch, release)
    with sqlite3.connect(db) as connection:
        run = json.loads(connection.execute('SELECT data FROM runs').fetchone()[0])
        if case == 'running': run['state'] = 'RUNNING'
        elif case == 'unknown': run['attempts'][0]['state'] = 'UNKNOWN'
        elif case == 'unterminated': run['attempts'][0]['terminated'] = False
        elif case == 'missing-proof': run['attempts'][0].pop('terminated')
        elif case == 'token': connection.execute("UPDATE reservations SET token='other-owner'")
        elif case == 'orphan': connection.execute("UPDATE reservations SET run_id='missing-run'")
        elif case == 'lease':
            connection.execute('CREATE TABLE leases(id TEXT)')
            connection.execute("INSERT INTO leases VALUES('active')")
        elif case in {'batch', 'pending-batch', 'future-contract'}:
            run['integration'] = {'contract_version': 'bsp-upgrade-integration-v1', 'phase': 'TESTING',
                                  'batch': {'state': 'READY'}}
            if case == 'batch': run['integration']['batch']['state'] = 'RUNNING'
            if case == 'pending-batch': run['integration']['pending_terminal_state'] = 'CANCELLED'
            if case == 'future-contract': run['integration']['contract_version'] = 'future'
        elif case == 'mode': run.pop('simulation')
        connection.execute('UPDATE runs SET data=?', (json.dumps(run),))
    before = db.read_bytes()
    assert manager.inspect_runtime(home)['adoptable'] is False
    assert not manager.activate(home, release, home / 'releases' / release)
    assert db.read_bytes() == before
    assert not (home / 'current.json').exists() and not (home / 'backups').exists()


@pytest.mark.parametrize('meta', [
    None,
    {'phase': 'PREPARING'},
    {'phase': 'FAILED'},
    {'phase': 'TESTING', 'batch': {'state': 'READY'}},
    {'phase': 'FAILED', 'batch': {'state': 'FAILED', 'terminated': True}},
    {'phase': 'DONE', 'batch': {'state': 'DONE', 'not_started': True}},
])
def test_t254_supported_paused_batch_receipts_preserve_reservations(modules, tmp_path, meta):
    manager, _, _ = modules
    runtime = tmp_path / 'existing'
    db = paused_hardware_runtime(runtime)
    with sqlite3.connect(db) as connection:
        run = json.loads(connection.execute('SELECT data FROM runs').fetchone()[0])
        run['attempts'] = []
        run['integration'] = dict(meta, contract_version='bsp-upgrade-integration-v1') if meta else None
        connection.execute('UPDATE runs SET data=?', (json.dumps(run),))
    manager.bind_runtime(tmp_path / 'home', runtime)
    assert manager.inspect_runtime(tmp_path / 'home')['adoptable'] is True


@pytest.mark.parametrize('failure', ['backup', 'pointer'])
def test_t254_failed_automatic_adoption_keeps_paused_runtime_and_can_retry(modules, tmp_path, monkeypatch, failure):
    manager, recovery, _ = modules
    home, runtime, release = tmp_path / 'home', tmp_path / 'existing', 'a' * 64
    db = paused_hardware_runtime(runtime)
    manager.bind_runtime(home, runtime)
    installed(manager, home, monkeypatch, release)
    before = db.read_bytes()
    with monkeypatch.context() as patch:
        if failure == 'backup':
            def failed_backup(*args):
                raise OSError('backup failed')
            patch.setattr(recovery, 'backup', failed_backup)
        else:
            original = manager.atomic
            def atomic(path, value):
                if Path(path).name == 'current.json': raise OSError('pointer failed')
                return original(path, value)
            patch.setattr(manager, 'atomic', atomic)
        with pytest.raises(OSError): manager.activate(home, release, home / 'releases' / release)
    assert not (home / 'current.json').exists()
    assert db.read_bytes() == before
    assert manager.activate(home, release, home / 'releases' / release)


def test_t254_paused_reservation_adoption_honors_worker_lock_and_revision(modules, tmp_path, monkeypatch):
    manager, _, _ = modules
    home, runtime, release = tmp_path / 'home', tmp_path / 'existing', 'a' * 64
    db = paused_hardware_runtime(runtime)
    manager.bind_runtime(home, runtime)
    installed(manager, home, monkeypatch, release)
    report = manager.inspect_runtime(home)
    with manager.lock(runtime / 'worker.lock'):
        assert not manager.activate(home, release, home / 'releases' / release)
    assert not (home / 'current.json').exists()
    with sqlite3.connect(db) as connection:
        connection.execute("UPDATE reservations SET token='different-owner'")
    with pytest.raises(RuntimeError, match='INSPECTION_CHANGED'):
        manager.adopt_runtime(home, release, report['revision'])
    assert not (home / 'current.json').exists() and not (home / 'backups').exists()


def test_sqlite_backup_copies_committed_wal_without_checkpointing_source(modules,tmp_path):
    _,recovery,_=modules;runtime=tmp_path/'runtime';runtime.mkdir();db=runtime/'data.db'
    with sqlite3.connect(db) as writer:
        writer.execute('PRAGMA journal_mode=WAL');writer.execute('CREATE TABLE values_kept(value TEXT)')
        writer.execute("INSERT INTO values_kept VALUES('committed-wal')");writer.commit()
        assert Path(str(db)+'-wal').exists()
        result=recovery.backup(runtime,tmp_path/'backup')
        with sqlite3.connect(Path(result['path'])/'data.db') as copied:
            assert copied.execute('SELECT value FROM values_kept').fetchone()[0]=='committed-wal'
    assert not (tmp_path/'backup/data.db-wal').exists()


def test_rollback_checks_environment_and_preserves_runtime_and_previous(modules,tmp_path,monkeypatch):
    manager,_,_=modules;home=tmp_path/'home';a,b='a'*64,'b'*64
    installed(manager,home,monkeypatch,a,b);manager.bind_runtime(home)
    manager.atomic(home/'current.json',{'release':b,'path':str(home/'releases'/b),'previous':{'release':a,'path':str(home/'releases'/a)}})
    marker=manager.runtime_path(home)/'kept.json';marker.parent.mkdir();marker.write_text('{"kept":true}')
    assert manager.rollback(home)['release']==a and marker.read_text()=='{"kept":true}'
    assert manager.current(home)['previous']['release']==b
    monkeypatch.setattr(manager,'has_work',lambda runtime:True)
    with pytest.raises(RuntimeError,match='ROLLBACK_BLOCKED'):manager.rollback(home,b)
    monkeypatch.setattr(manager,'has_work',lambda runtime:False)
    monkeypatch.setattr(manager,'valid_environment',lambda path:False)
    with pytest.raises(RuntimeError,match='검증된 설치'):manager.rollback(home,b)


def test_release_cleanup_retains_current_previous_and_runtime_history_pins(modules,tmp_path,monkeypatch):
    manager,_,_=modules;home=tmp_path/'home';a,b,c,d='a'*64,'b'*64,'c'*64,'d'*64
    installed(manager,home,monkeypatch,a,b,c,d);manager.bind_runtime(home)
    manager.atomic(home/'current.json',{'release':a,'path':str(home/'releases'/a),'previous':{'release':b,'path':str(home/'releases'/b)}})
    runtime=manager.runtime_path(home);runtime.mkdir();(runtime/'history.json').write_text(json.dumps({'source_release':c}))
    plan=manager.cleanup_releases(home,keep=0)
    assert plan['state']=='PLANNED' and plan['removed']==[d]
    assert (home/'releases'/d).exists()
    assert manager.cleanup_releases(home,apply=True,keep=0)['state']=='CLEANED'
    assert not (home/'releases'/d).exists()
    assert all((home/'releases'/release).exists() for release in (a,b,c))
    with manager.lock(home/'service.lock'):
        with pytest.raises(RuntimeError):manager.cleanup_releases(home,apply=True,keep=0)


def test_public_tools_reuse_never_runs_installer_and_missing_tools_plan_fixed_argv(modules,tmp_path):
    _,_,prerequisites=modules;calls=[]
    def detector(**kwargs):return {'platform':'linux','tools':{'python':'/python','ssh':'/ssh'},'missing':[]}
    result=prerequisites.prepare(tmp_path,apply=True,detector=detector,run=lambda *a,**k:pytest.fail('installed existing tools'))
    assert result['state']=='REUSED'
    missing=lambda **kwargs:{'platform':'linux','tools':{'python':'/python','ssh':None},'missing':['ssh']}
    result=prerequisites.prepare(tmp_path,detector=missing,which=lambda name:'/usr/bin/'+name if name in {'apt-get','sudo'} else None,root=False)
    assert result['commands']==[['/usr/bin/sudo','-n','/usr/bin/apt-get','install','-y','openssh-client']]
    assert not list(tmp_path.iterdir())


def test_public_tools_apply_rechecks_and_reports_package_failure(modules,tmp_path):
    _,_,prerequisites=modules;states=iter([{'platform':'linux','tools':{'ssh':None},'missing':['ssh']},
                                       {'platform':'linux','tools':{'ssh':'/ssh'},'missing':[]}]);calls=[]
    def run(argv,**kwargs):calls.append(argv);assert kwargs['shell'] is False;return SimpleNamespace(returncode=0)
    result=prerequisites.prepare(tmp_path,apply=True,detector=lambda **kwargs:next(states),
                                which=lambda name:'/bin/'+name if name=='apt-get' else None,run=run,root=True)
    assert result['state']=='PREPARED' and len(calls)==1
    result=prerequisites.prepare(tmp_path,apply=True,detector=lambda **kwargs:{'platform':'linux','missing':['ssh']},
                                which=lambda name:'/bin/'+name if name=='apt-get' else None,run=lambda *a,**k:SimpleNamespace(returncode=7),root=True)
    assert result['state']=='BLOCKED' and result['reason']=='PACKAGE_INSTALL_FAILED'


def signed_input(tmp_path,artifacts):
    manifest=tmp_path/'supplied.json';manifest.write_text(json.dumps({'format':'agent-monitor-supplied-artifacts-v1','artifacts':artifacts}))
    signature=tmp_path/'supplied.sig';signature.write_text('signature')
    keyring=tmp_path/'trusted.gpg';keyring.write_text('trusted-key')
    return manifest,signature,keyring


def test_supplied_requirements_are_signature_hash_and_offline_locked_before_any_install(modules,tmp_path):
    _,_,prerequisites=modules;requirements=tmp_path/'company.txt';requirements.write_text('company-tc==1.0 --hash=sha256:'+'a'*64+'\n')
    manifest,signature,keyring=signed_input(tmp_path,[{'path':requirements.name,'kind':'tc-requirements','sha256':hashlib.sha256(requirements.read_bytes()).hexdigest()}])
    wheelhouse=tmp_path/'wheels';wheelhouse.mkdir();calls=[]
    def run(argv,**kwargs):calls.append(argv);return SimpleNamespace(returncode=0)
    which=lambda name:'/bin/gpgv' if name=='gpgv' else None
    planned=prerequisites.install_supplied(manifest,signature,keyring,tmp_path/'home',wheelhouse=wheelhouse,run=run,which=which)
    assert planned['state']=='PLANNED' and len(calls)==1 and calls[0][0]=='/bin/gpgv'
    pip=planned['commands'][-1];assert '--no-index' in pip and '--require-hashes' in pip and '--no-deps' in pip
    with pytest.raises(ValueError,match='signature'):
        prerequisites.install_supplied(manifest,signature,keyring,tmp_path/'home',wheelhouse=wheelhouse,
                                      run=lambda *a,**k:SimpleNamespace(returncode=1),which=which)
    requirements.write_text('--index-url https://private.invalid\ncompany-tc==1.0\n')
    with pytest.raises(ValueError,match='hash mismatch'):
        prerequisites.install_supplied(manifest,signature,keyring,tmp_path/'home',wheelhouse=wheelhouse,run=run,which=which)


@pytest.mark.parametrize('python_present',[True,False])
def test_linux_bootstrap_installs_only_missing_public_components(tmp_path,python_present):
    import os
    tools=tmp_path/'bin';tools.mkdir();capture=tmp_path/'commands'
    def executable(name,text):
        path=tools/name;path.write_text('#!/bin/sh\n'+text+'\n');path.chmod(0o755)
    executable('uname','printf Linux')
    executable('id','printf 0')
    if python_present:executable('python3','exit 0')
    executable('apt-get','printf "%s\\n" "$@" > "$CAPTURE"\nprintf "#!/bin/sh\\nexit 0\\n" > "$BOOTSTRAP_BIN/ssh"\n/bin/chmod +x "$BOOTSTRAP_BIN/ssh"\nprintf "#!/bin/sh\\nexit 0\\n" > "$BOOTSTRAP_BIN/python3"\n/bin/chmod +x "$BOOTSTRAP_BIN/python3"')
    result=subprocess.run(['/bin/sh',str(ROOT/'scripts/bootstrap-prerequisites.sh')],
                          env=dict(os.environ,PATH=str(tools),CAPTURE=str(capture),BOOTSTRAP_BIN=str(tools)),capture_output=True,text=True)
    assert result.returncode==0,result.stderr
    installed=capture.read_text().splitlines()
    assert installed==(['install','-y','openssh-client'] if python_present else ['install','-y','python3','python3-venv','openssh-client'])


def test_windows_bootstrap_has_signed_installer_and_offline_requirements_contract():
    script=(ROOT/'scripts/bootstrap-prerequisites.ps1').read_text()
    assert "Winget-Package 'Python.Python.3.13'" in script and "Winget-Package 'Google.PlatformTools'" in script
    assert "Get-AuthenticodeSignature" in script and "SignerCertificate.Thumbprint" in script
    assert "OpenSSH.Client~~~~0.0.1.0" in script
    assert "--require-hashes" in script and "--no-index" in script and "--no-deps" in script
    assert "Start-Service" not in script and "fastboot devices" not in script and "ssh " not in script


def test_supplied_package_receipt_cannot_reuse_deleted_environment(modules,tmp_path):
    import shutil
    _,_,prerequisites=modules;requirements=tmp_path/'company.txt';requirements.write_text('company-tc==1.0 --hash=sha256:'+'a'*64+'\n')
    manifest,signature,keyring=signed_input(tmp_path,[{'path':requirements.name,'kind':'tc-requirements','sha256':hashlib.sha256(requirements.read_bytes()).hexdigest()}])
    wheels=tmp_path/'wheels';wheels.mkdir();home=tmp_path/'home';calls=[]
    def run(argv,**kwargs):
        calls.append(argv)
        if argv[1:3]==['-m','venv']:
            python=Path(argv[3])/('Scripts/python.exe' if __import__('os').name=='nt' else 'bin/python')
            python.parent.mkdir(parents=True,exist_ok=True);python.touch()
        return SimpleNamespace(returncode=0)
    which=lambda name:'/bin/gpgv' if name=='gpgv' else None
    first=prerequisites.install_supplied(manifest,signature,keyring,home,wheelhouse=wheels,apply=True,run=run,which=which)
    assert first['state']=='INSTALLED'
    calls.clear()
    assert prerequisites.install_supplied(manifest,signature,keyring,home,wheelhouse=wheels,apply=True,run=run,which=which)['state']=='REUSED'
    assert not any('pip' in argv for argv in calls)
    shutil.rmtree(home/'supplied-tc-environment');calls.clear()
    repaired=prerequisites.install_supplied(manifest,signature,keyring,home,wheelhouse=wheels,apply=True,run=run,which=which)
    assert repaired['state']=='INSTALLED' and any(argv[1:3]==['-m','venv'] for argv in calls)
    assert any('pip' in argv for argv in calls)


def test_supplied_same_version_corruption_reinstalls_with_fixed_offline_hashes(modules,tmp_path):
    _,_,prerequisites=modules;requirements=tmp_path/'company.txt';requirements.write_text('company-tc==1.0 --hash=sha256:'+'a'*64+'\n')
    manifest,signature,keyring=signed_input(tmp_path,[{'path':requirements.name,'kind':'tc-requirements','sha256':hashlib.sha256(requirements.read_bytes()).hexdigest()}])
    home=tmp_path/'home';wheels=tmp_path/'wheels';wheels.mkdir();calls=[]
    def run(argv,**kwargs):
        calls.append(argv)
        if argv[1:3]==['-m','venv']:
            python=Path(argv[3])/('Scripts/python.exe' if __import__('os').name=='nt' else 'bin/python')
            python.parent.mkdir(parents=True,exist_ok=True);python.touch()
        return SimpleNamespace(returncode=0)
    which=lambda name:'/bin/gpgv' if name=='gpgv' else None
    prerequisites.install_supplied(manifest,signature,keyring,home,wheelhouse=wheels,apply=True,run=run,which=which)
    calls.clear();healthy_checks=0
    def damaged_then_repaired(argv,**kwargs):
        nonlocal healthy_checks
        if '-I' in argv:
            healthy_checks+=1;calls.append(argv)
            assert '-S' in argv  # Do not execute package .pth startup hooks.
            return SimpleNamespace(returncode=1 if healthy_checks==1 else 0)
        return run(argv,**kwargs)
    result=prerequisites.install_supplied(manifest,signature,keyring,home,wheelhouse=wheels,apply=True,run=damaged_then_repaired,which=which)
    pip=next(argv for argv in calls if 'pip' in argv)
    assert '--force-reinstall' in pip and '--require-hashes' in pip and '--no-index' in pip
    assert result['state']=='INSTALLED' and healthy_checks==2


def test_cleanup_only_recognizes_owned_abandoned_stages_and_binding_avoids_releases(modules,tmp_path):
    manager,_,_=modules;home=tmp_path/'home';manager.bind_runtime(home)
    owned=home/'.install-owned';owned.mkdir();manager.atomic(owned/'INSTALL_STAGE.json',{'format':'agent-monitor-install-stage-v1','path':str(owned)})
    unknown=home/'.install-unknown';unknown.mkdir();(unknown/'keep').write_text('unverified')
    plan=manager.cleanup_releases(home,keep=0)
    assert plan['staging_removed']==['.install-owned'] and owned.exists()
    manager.cleanup_releases(home,apply=True,keep=0)
    assert not owned.exists() and (unknown/'keep').is_file()
    fresh=tmp_path/'fresh-home'
    with pytest.raises(ValueError,match='분리'):manager.bind_runtime(fresh,fresh/'releases'/'runtime')


@pytest.mark.parametrize('top,inner,expected',[
    ('future-policy',None,'RETRY_POLICY_UNSUPPORTED'),
    ('fail-stop-analysis-v1','initial-pass-else-two-of-three-v1','RETRY_POLICY_CONFLICT'),
    ('fail-stop-analysis-v1','future-policy','RETRY_POLICY_UNSUPPORTED'),
])
def test_adoption_uses_actual_general_execution_policy_and_rejects_conflicts(modules,tmp_path,top,inner,expected):
    manager,recovery,_=modules;runtime=tmp_path/'runtime';db=gui_runtime(runtime)
    with sqlite3.connect(db) as c:
        run=json.loads(c.execute('SELECT data FROM runs').fetchone()[0]);run['execution_policy']=top
        if inner is None:run.pop('integration')
        else:run['integration']['retry_policy']=inner
        c.execute('UPDATE runs SET data=?',(json.dumps(run),))
    report=recovery.inspect(runtime)
    assert report['compatible'] is False and report['adoptable'] is False
    assert expected in {item['code'] for item in report['issues']}


def test_supplied_cli_apply_respects_running_supervisor_before_private_install(modules,tmp_path,monkeypatch):
    manager,_,prerequisites=modules;home=tmp_path/'home';manager.bind_runtime(home)
    monkeypatch.setattr(prerequisites,'prepare',lambda *a,**k:{'state':'REUSED'})
    monkeypatch.setattr(prerequisites,'install_supplied',lambda *a,**k:pytest.fail('private installer ran while active'))
    with manager.lock(home/'service.lock'):
        assert manager.main(['tools','--home',str(home),'--apply','--artifact-manifest',str(tmp_path/'company.json')])==1


def test_supplied_install_stops_if_public_prerequisite_failed(modules,tmp_path,monkeypatch):
    manager,_,prerequisites=modules;home=tmp_path/'home'
    monkeypatch.setattr(prerequisites,'prepare',lambda *a,**k:{'state':'BLOCKED','reason':'PACKAGE_INSTALL_FAILED'})
    monkeypatch.setattr(prerequisites,'install_supplied',lambda *a,**k:pytest.fail('continued after prerequisite failure'))
    assert manager.main(['tools','--home',str(home),'--apply','--artifact-manifest',str(tmp_path/'company.json')])==1


@pytest.mark.parametrize('integration,session',[('UNKNOWN','READY'),('SUCCEEDED','NEEDS_RECONCILIATION')])
def test_adoption_rejects_bsp_integration_and_session_unknown(modules,tmp_path,integration,session):
    _,recovery,_=modules;runtime=tmp_path/'runtime';runtime.mkdir()
    with sqlite3.connect(runtime/'dashboard.db') as c:
        c.execute('CREATE TABLE meta(key TEXT,value TEXT)');c.execute("INSERT INTO meta VALUES('schema_version','2')")
        c.execute('CREATE TABLE jobs(data TEXT)')
        c.execute('INSERT INTO jobs VALUES(?)',(json.dumps({'id':'bsp','profile':{'module_report_version':1},
            'modules':[],'integration':{'status':integration},'session':{'status':session}}),))
    report=recovery.inspect(runtime)
    assert report['adoptable'] is False and report['unresolved']


def reset_fixture(manager, home):
    from backend.gui_test.core.store import Store as GuiStore
    from backend.storage.store import Store as BspStore
    from backend.gui_test.connector.registry import ConnectorRegistry
    runtime = manager.bind_runtime(home, home.parent/'existing')
    gui = GuiStore(runtime/'gui/runs.db')
    with gui.transaction() as connection:
        run = {'id':'run', 'state':'PAUSED', 'simulation':False, 'lease_token':'owner',
               'attempts':[{'state':'ERROR', 'terminated':True}], 'integration':None}
        connection.execute('INSERT INTO runs VALUES(?,?)', ('run', json.dumps(run)))
        connection.executemany('INSERT INTO reservations VALUES(?,?,?)',
                               [('board','run','owner'), ('console','run','owner')])
        connection.execute("INSERT INTO events(run_id,type,data,at) VALUES('run','FAIL','{}','now')")
        connection.execute("INSERT INTO commands VALUES('old-key','hash','{}')")
        connection.execute("INSERT INTO outbox VALUES('run','{}')")
        for kind in ['profile','suite','command','shared-settings','source-state','storage-policy','execution-timeouts',
                     'failure-analysis','integration-preparation','deleted-run','analysis-runtime']:
            connection.execute('INSERT INTO documents VALUES(?,?,?)', (kind,'current','{}'))
    bsp = BspStore(runtime/'dashboard.db')
    with bsp.transaction() as connection:
        connection.execute("INSERT INTO config VALUES(1,7,'{\"port\":8765}')")
        connection.execute('INSERT INTO jobs VALUES(?,?,?)', ('job',1,json.dumps({'id':'job','modules':[], 'profile':{}})))
        connection.execute("INSERT INTO events(job_id,type,data,created_at) VALUES('job','created','{}','now')")
    registry = ConnectorRegistry(runtime)
    with registry.connection() as connection:
        connection.execute("INSERT INTO registration VALUES(1,'{\"runner_id\":\"windows\"}')")
        connection.execute("INSERT INTO connector_errors(event_id,data) VALUES('old-error','{}')")
    (runtime/'gui-test.json').write_text('{"runner":"registered"}')
    return runtime, gui, bsp


def test_t254_bulk_reset_preserves_settings_and_backs_up_all_records(modules, tmp_path):
    manager, _, _ = modules
    home = tmp_path/'home'
    runtime, gui, bsp = reset_fixture(manager, home)
    assert manager.main(['reset','--home',str(home),'--runtime',str(runtime)]) == 0
    receipt = manager.read(home/'runtime-reset.json')
    assert receipt['state'] == 'RESET' and receipt['settings_preserved']
    with gui.connection() as connection:
        for table in ['runs','reservations','commands','events','outbox']:
            assert connection.execute('SELECT COUNT(*) FROM '+table).fetchone()[0] == 0
        kinds = {row[0] for row in connection.execute('SELECT kind FROM documents')}
        assert kinds == {'profile','suite','command','shared-settings','source-state','storage-policy','execution-timeouts'}
    with bsp.connection() as connection:
        assert connection.execute('SELECT COUNT(*) FROM jobs').fetchone()[0] == 0
        assert tuple(connection.execute('SELECT * FROM config').fetchone()) == (1,7,'{"port":8765}')
    with sqlite3.connect(runtime/'connector-registry.db') as connection:
        assert connection.execute('SELECT COUNT(*) FROM registration').fetchone()[0] == 1
        assert connection.execute('SELECT COUNT(*) FROM connector_errors').fetchone()[0] == 0
    backup = Path(receipt['backup']['path'])
    with sqlite3.connect(backup/'gui/runs.db') as connection:
        assert connection.execute('SELECT COUNT(*) FROM reservations').fetchone()[0] == 2
        assert connection.execute('SELECT COUNT(*) FROM runs').fetchone()[0] == 1
    assert (backup/'gui-test.json').read_bytes() == (runtime/'gui-test.json').read_bytes()
    assert not manager.has_work(runtime)
    manager.require_reset_complete(home)


@pytest.mark.parametrize('failure', ['active','unknown','batch','token','analysis','schema','worker'])
def test_t254_reset_refuses_unresolved_execution_before_backup(modules, tmp_path, failure):
    manager, _, _ = modules
    home = tmp_path/'home'
    runtime, gui, _ = reset_fixture(manager, home)
    with gui.transaction() as connection:
        run = gui.get(connection,'run')
        if failure == 'active': run['state'] = 'RUNNING'
        if failure == 'unknown': run['attempts'][0]['terminated'] = False
        if failure == 'batch': run['integration'] = {'contract_version':'bsp-upgrade-integration-v1','phase':'PREPARING','batch':{'state':'RUNNING'}}
        if failure == 'token': run['lease_token'] = 'different'
        if failure == 'analysis': connection.execute("UPDATE documents SET data='{\"status\":\"LEASED\"}' WHERE kind='failure-analysis'")
        if failure == 'schema': connection.execute('CREATE TABLE future_schema(value TEXT)')
        connection.execute('UPDATE runs SET data=?', (json.dumps(run),))
    if failure == 'worker':
        with manager.lock(runtime/'worker.lock'), pytest.raises(RuntimeError): manager.reset_runtime(home)
    else:
        with pytest.raises(RuntimeError, match='RESET_BLOCKED'): manager.reset_runtime(home)
    assert len(gui.all()) == 1
    assert not (home/'backups').exists()
    assert not (home/'runtime-reset.json').exists()


@pytest.mark.parametrize('failure', ['backup','second_db','receipt'])
def test_t254_interrupted_reset_retries_with_original_backup(modules, tmp_path, monkeypatch, failure):
    manager, recovery, _ = modules
    home = tmp_path/'home'
    runtime, gui, bsp = reset_fixture(manager, home)
    original_clear = recovery.clear_runtime_records
    original_atomic = manager.atomic
    with monkeypatch.context() as patch:
        if failure == 'backup':
            patch.setattr(recovery,'backup',lambda *args: (_ for _ in ()).throw(OSError('disk full')))
        elif failure == 'second_db':
            def interrupted(runtime, plan):
                original_clear(runtime, plan[:1])
                raise OSError('interrupted')
            patch.setattr(recovery,'clear_runtime_records',interrupted)
        else:
            def atomic(path, value):
                if Path(path).name == 'runtime-reset.json' and value['state'] == 'RESET': raise OSError('receipt failed')
                original_atomic(path,value)
            patch.setattr(manager,'atomic',atomic)
        with pytest.raises(OSError): manager.reset_runtime(home)
    receipt = manager.read(home/'runtime-reset.json')
    if failure == 'backup':
        assert receipt is None and len(gui.all()) == 1
    else:
        assert receipt['state'] == 'RESET_PENDING'
        with pytest.raises(RuntimeError, match='RESET_PENDING'): manager.start(home)
        with pytest.raises(RuntimeError, match='RESET_PENDING'): manager.serve(home,8765)
    result = manager.reset_runtime(home)
    assert result['state'] == 'RESET' and not gui.all()
    if receipt: assert result['backup'] == receipt['backup']
    with sqlite3.connect(Path(result['backup']['path'])/'gui/runs.db') as connection:
        assert connection.execute('SELECT COUNT(*) FROM runs').fetchone()[0] == 1


def test_t254_reset_pending_rejects_modified_backup(modules, tmp_path, monkeypatch):
    manager, recovery, _ = modules
    home = tmp_path/'home'
    reset_fixture(manager, home)
    with monkeypatch.context() as patch:
        patch.setattr(recovery,'clear_runtime_records',lambda *args: (_ for _ in ()).throw(OSError('interrupted')))
        with pytest.raises(OSError): manager.reset_runtime(home)
    receipt = manager.read(home/'runtime-reset.json')
    (Path(receipt['backup']['path'])/'gui-test.json').write_text('changed')
    with pytest.raises(RuntimeError, match='백업 검증'): manager.reset_runtime(home)


@pytest.mark.parametrize('blocked', [False, True])
def test_t254_reset_uses_supervisor_stop_and_waits_for_ownership(modules, tmp_path, monkeypatch, blocked):
    manager, _, _ = modules
    home = tmp_path/'home'
    reset_fixture(manager, home)
    manager.atomic(home/'service.json', {'instance':'current'})
    running = True
    monkeypatch.setattr(manager,'cancel_reset_sessions',lambda service: None)
    monkeypatch.setattr(manager,'active',lambda home: running)
    def stop(home):
        nonlocal running
        if blocked: manager.atomic(home/'stop-result.json',{'instance':'current','state':'BLOCKED','reason':'active work'})
        else: running = False
    monkeypatch.setattr(manager,'stop',stop)
    if blocked:
        with pytest.raises(RuntimeError, match='active work'): manager.reset_runtime(home)
        assert manager.read(home/'runtime-reset.json')['state'] == 'RESET_DRAINING'
    else:
        assert manager.reset_runtime(home)['state'] == 'RESET'


def test_t254_reset_checks_unreserved_flash_batch_ownership(modules, tmp_path):
    manager, _, _ = modules
    home = tmp_path/'home'
    _, gui, _ = reset_fixture(manager, home)
    with gui.transaction() as connection:
        run = gui.get(connection,'run')
        run['integration'] = {'contract_version':'bsp-upgrade-integration-v1','phase':'TESTING','batch':{'state':'READY'}}
        connection.execute('DELETE FROM reservations')
        connection.execute('UPDATE runs SET data=?',(json.dumps(run),))
    with pytest.raises(RuntimeError,match='이미지 설치 예약'): manager.reset_runtime(home)
    with gui.transaction() as connection:
        run['integration']['batch_released'] = True
        connection.execute('UPDATE runs SET data=?',(json.dumps(run),))
    assert manager.reset_runtime(home)['state'] == 'RESET'


def test_t254_root_reset_command_with_synthetic_runtime(modules, tmp_path):
    manager, _, _ = modules
    home = tmp_path/'home'
    runtime, gui, _ = reset_fixture(manager, home)
    result = subprocess.run(['bash',str(ROOT/'run.sh'),'reset','--home',str(home),'--runtime',str(runtime)],
                            cwd=tmp_path, capture_output=True, text=True, timeout=15)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)['state'] == 'RESET'
    assert '초기화 완료' in result.stderr
    assert not gui.all()


def test_t254_reset_cancel_failure_reuses_pre_cancellation_backup(modules, tmp_path, monkeypatch):
    manager, _, _ = modules
    home = tmp_path/'home'
    runtime, gui, _ = reset_fixture(manager, home)
    manager.atomic(home/'service.json', {'instance':'fixture'})
    running = True
    calls = 0
    monkeypatch.setattr(manager,'active',lambda home: running)
    def cancel(service):
        nonlocal calls
        calls += 1
        if calls == 1:
            with gui.transaction() as connection:
                run = gui.get(connection,'run')
                run['state'] = 'CANCELLED'
                connection.execute('UPDATE runs SET data=?',(json.dumps(run),))
                connection.execute('DELETE FROM reservations')
            raise RuntimeError('connection lost after cancellation')
    def stop(home):
        nonlocal running
        running = False
    monkeypatch.setattr(manager,'cancel_reset_sessions',cancel)
    monkeypatch.setattr(manager,'stop',stop)
    with pytest.raises(RuntimeError, match='connection lost'): manager.reset_runtime(home)
    receipt = manager.read(home/'runtime-reset.json')
    assert receipt['state'] == 'RESET_DRAINING'
    with pytest.raises(RuntimeError, match='RESET_PENDING'): manager.start(home)
    result = manager.reset_runtime(home)
    assert result['backup'] == receipt['backup']
    assert len(list((home/'backups').iterdir())) == 1
    with sqlite3.connect(Path(result['backup']['path'])/'gui/runs.db') as connection:
        assert json.loads(connection.execute('SELECT data FROM runs').fetchone()[0])['state'] == 'PAUSED'
        assert connection.execute('SELECT COUNT(*) FROM reservations').fetchone()[0] == 2


def test_t254_reset_http_checks_running_service_identity(modules, monkeypatch):
    manager, _, _ = modules
    service = {'instance':'expected', 'release':'a', 'runtime':'/fixture', 'port':12345}
    monkeypatch.setattr(manager,'health',lambda port:{'managed_instance':'other'})
    monkeypatch.setattr(manager.urllib.request,'build_opener',lambda *args: pytest.fail('Contacted unowned API'))
    with pytest.raises(RuntimeError, match='소유권'): manager.reset_request(service,'/api/v1/gui-test/runs')


def test_t254_reset_refuses_session_that_started_after_inspection(modules, monkeypatch):
    manager, _, _ = modules
    def request(service, path, payload=None, controller=None):
        assert payload is None, 'Running session was cancelled automatically'
        return [{'id':'run','state':'PAUSED'}] if path.endswith('/runs') else {'id':'run','state':'RUNNING'}
    monkeypatch.setattr(manager,'reset_request',request)
    with pytest.raises(RuntimeError,match='종료가 확인되지'): manager.cancel_reset_sessions({})


@pytest.mark.parametrize('activity', ['jira','prompt','attempt','lease','process'])
def test_t254_live_bsp_archive_refuses_unresolved_execution(modules, tmp_path, activity):
    manager, recovery, _ = modules
    home = tmp_path/'home'
    runtime, _, bsp = reset_fixture(manager, home)
    with bsp.transaction() as connection:
        job = bsp.get(connection,'job')
        if activity == 'jira': job['decisions'] = [{'sync_status':'SENDING'}]
        if activity == 'prompt': job['prompts'] = [{'status':'RUNNING'}]
        if activity == 'attempt': job['modules'] = [{'stages':{'build':{'status':'FAILED','attempts':[{'status':'UNKNOWN'}]}}}]
        if activity == 'lease': connection.execute("INSERT INTO leases VALUES('linux-write','attempt','owner')")
        if activity == 'process':
            receipt = {'id':'launch','status':'SUCCEEDED','process_receipt':{}}
            connection.execute('INSERT INTO launch_receipts VALUES(?,?,?,?,?,?,?)',
                               ('launch','job','owner','stage','nonce','SUCCEEDED',json.dumps(receipt)))
        connection.execute('UPDATE jobs SET data=?',(json.dumps(job),))
    destination = tmp_path/'archive'
    destination.mkdir()
    with pytest.raises(RuntimeError,match='RESET_BLOCKED'):
        recovery.archive_idle_records(runtime,destination,lambda result:pytest.fail('Unsafe archive recorded'))
    assert len(bsp.all()) == 1 and not list(destination.iterdir())


def test_t254_bsp_archive_blocks_concurrent_claim_until_records_are_removed(modules, tmp_path):
    from concurrent.futures import ThreadPoolExecutor
    import threading
    from backend.domain.engine import Engine
    from backend.domain.policy import Conflict
    from backend.settings import Profile
    from backend.storage.store import Store
    _, recovery, _ = modules
    runtime = tmp_path/'runtime'
    engine = Engine(Store(runtime/'dashboard.db'), runtime/'artifacts')
    identity = engine.create('new', Profile().model_dump(),'fixture','linux')['job_id']
    module_id = engine.store.snapshot(identity)['modules'][0]['id']
    backups = tmp_path/'backups'
    backups.mkdir()
    started = threading.Event()
    finished = threading.Event()
    future = None
    with ThreadPoolExecutor(max_workers=1) as pool:
        def claim():
            started.set()
            try: return engine.claim(identity,module_id,'analysis','contender')
            finally: finished.set()
        def recorded(receipt):
            nonlocal future
            with sqlite3.connect(Path(receipt['path'])/'dashboard.db') as connection:
                assert connection.execute('SELECT COUNT(*) FROM jobs').fetchone()[0] == 1
            future = pool.submit(claim)
            assert started.wait(2)
            assert not finished.wait(.05), 'Scheduler bypassed the archive write lock'
        assert recovery.archive_idle_records(runtime,backups,recorded) == 1
        with pytest.raises(Conflict): future.result(timeout=3)
    assert engine.store.all() == []


@pytest.mark.parametrize('failure', ['receipt','second_commit'])
def test_t254_bsp_archive_failure_and_retry_preserve_backups(modules, tmp_path, monkeypatch, failure):
    from backend.storage.store import Store
    manager, recovery, _ = modules
    home = tmp_path/'home'
    runtime, _, bsp = reset_fixture(manager, home)
    second = Store(runtime/'legacy/demo-dashboard.db')
    with second.transaction() as connection:
        connection.execute('INSERT INTO jobs VALUES(?,?,?)',('second',1,json.dumps({'id':'second','modules':[],'profile':{}})))
    manager.atomic(home/'service.json', {'instance':'fixture'})
    running = True
    monkeypatch.setattr(manager,'active',lambda home:running)
    monkeypatch.setattr(manager,'cancel_reset_sessions',lambda service:None)
    def stop(home):
        nonlocal running
        running = False
    monkeypatch.setattr(manager,'stop',stop)
    original_atomic = manager.atomic
    original_connect = sqlite3.connect
    with monkeypatch.context() as patch:
        if failure == 'receipt':
            def atomic(path,value):
                if value.get('pre_stop_archives'): raise OSError('archive receipt failed')
                original_atomic(path,value)
            patch.setattr(manager,'atomic',atomic)
        else:
            class Connection:
                def __init__(self, connection): self.connection = connection
                def __getattr__(self, name): return getattr(self.connection,name)
                def commit(self): raise sqlite3.OperationalError('commit interrupted')
            def connect(path,*args,**kwargs):
                connection = original_connect(path,*args,**kwargs)
                return Connection(connection) if str(path).endswith('legacy/demo-dashboard.db?mode=rw') else connection
            patch.setattr(recovery.sqlite3,'connect',connect)
        with pytest.raises((OSError,RuntimeError)): manager.reset_runtime(home)
    assert manager.read(home/'runtime-reset.json')['state'] == 'RESET_DRAINING'
    if failure == 'receipt': assert len(bsp.all()) == 1
    else: assert bsp.all() == []
    assert len(second.all()) == 1
    result = manager.reset_runtime(home)
    assert result['state'] == 'RESET' and bsp.all() == [] and second.all() == []
    with original_connect(Path(result['backup']['path'])/'dashboard.db') as connection:
        assert connection.execute('SELECT COUNT(*) FROM jobs').fetchone()[0] == 1
    for archive in result['pre_stop_archives']:
        assert (Path(archive['path'])/'BACKUP.json').is_file()
