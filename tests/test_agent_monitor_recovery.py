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
