"""Fresh plugin setup uses common profile APIs, without SSH/COM/fastboot execution."""
import copy
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import sqlite3
import sys

from fastapi.testclient import TestClient
import pytest

from backend.gui_test.connector import shared_control
from backend.gui_test.connector.settings import Settings
from backend.gui_test.core.integration_profiles import (IntegrationProfiles, FlashProfile, FlashPatch,
                                                       merge_flash_patch, profile_revision)
from backend.gui_test.core.models import TestError, digest
from backend.gui_test.execution.host import Host
from backend.gui_test.runtime import make_manager
from backend.gui_test.standalone.integration import create_app

BASE='/api/v1/gui-test/live/integration'
PROFILES=BASE+'/profiles'
SERVICE={'X-Bsp-Service':'plugin'}
BOARD={'board_id':'board-a','host':'TEST-PC','com':'COM7'}
COMMAND={'single':['python','{tc_path}','{com_a}'], 'dual':['python','{tc_path}','{com_a}','{com_b}']}


def flash(tmp_path):
    executable=tmp_path/'fastboot.exe';executable.touch()
    return {'enabled':True,'fastboot':str(executable),'batch_sha256':'a'*64,
            'success_marker':'ALL IMAGES OK','failure_markers':['FAILED','fastboot: error:'],
            'boards':{'board-a':{'com':'COM7','serial':'board-serial','lkshell_prompt':'lkshell>',
                                 'boot_marker':'login :','login_prompt':'login :',
                                 'observer':{'port':'COM41','rx_only_confirmed':True,'control_lines_isolated':True,
                                             'panic_signatures':['Kernel panic'],'boot_signatures':['BOOT START'],
                                             'login_markers':['login :']}}}}


def app_for(tmp_path):
    return create_app(tmp_path,start_worker=False)


def desired_application(manager,runner_id):
    value=manager.shared_settings.connector_application()
    return {'expected_revision':value['revision'],'runner_id':runner_id}


def test_plugin_can_create_validate_list_select_command_on_blank_install(tmp_path):
    app=app_for(tmp_path)
    with TestClient(app,client=('127.0.0.1',1000),headers=SERVICE) as client:
        assert client.get(PROFILES+'/commands').json()=={'commands':[]}
        normalized=client.post(PROFILES+'/commands/validate',json=COMMAND)
        assert normalized.status_code==200 and normalized.json()['revision']==digest(COMMAND)
        created=client.put(PROFILES+'/commands/company-tc',json=COMMAND|{'expected_revision':None})
        assert created.status_code==200,created.text
        profile=created.json()
        assert client.get(PROFILES+'/commands/company-tc').json()['revision']==profile['revision']
        settings=client.get(BASE+'/settings').json()
        selected=client.post(PROFILES+'/commands/company-tc/select',json={
            'expected_settings_revision':settings['revision'],'revision':profile['revision']})
        assert selected.status_code==200,selected.text
        assert selected.json()['integration']['command_profile']=='company-tc'
        assert selected.json()['integration']['command_revision']==profile['revision']
        # The new setup surface does not authorize legacy execution/saved writes.
        assert client.put('/api/v1/gui-test/live/saved/command',json={'name':'bypass','data':COMMAND}).status_code==403
        assert app.state.manager.store.all()==[]


def test_command_overwrite_is_atomic_cas_and_selection_rejects_stale_revision(tmp_path):
    manager=make_manager(tmp_path,'integration');profiles=IntegrationProfiles(manager)
    first=profiles.save_command('tc',COMMAND)
    with pytest.raises(TestError) as duplicate:profiles.save_command('tc',COMMAND)
    assert duplicate.value.code=='PROFILE_CHANGED'
    def save(option):
        value=copy.deepcopy(COMMAND);value['single'].append(option)
        try:return profiles.save_command('tc',value|{'expected_revision':first['revision']})['revision']
        except TestError as error:return error.code
    with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(save,['--one','--two']))
    assert results.count('PROFILE_CHANGED')==1
    with pytest.raises(TestError) as stale:
        profiles.select('command','tc',{'expected_settings_revision':manager.shared_settings.read()['revision'],'revision':first['revision']})
    assert stale.value.code=='COMMAND_CHANGED'
    # The prior public Manager.save_document interface remains source compatible.
    assert manager.save_document('command','legacy',COMMAND)['revision']==digest(COMMAND)


@pytest.mark.parametrize('bad',[
    {'single':['cmd.exe','/c','{tc_path}','{com_a}'],'dual':COMMAND['dual']},
    {'single':['python','-c','{tc_path}','{com_a}'],'dual':COMMAND['dual']},
    {'single':['python','{tc_path}','{com_a}','{bad}'],'dual':COMMAND['dual']},
])
def test_shared_command_save_never_expands_windows_command_allowlist(tmp_path,bad):
    profiles=IntegrationProfiles(make_manager(tmp_path,'integration'))
    with pytest.raises(TestError):profiles.save_command('unsafe',bad)
    assert profiles.commands()=={'commands':[]}


def test_flash_named_patch_preserves_legacy_profiles_and_checks_local_cas(tmp_path):
    supplied=FlashProfile.model_validate(flash(tmp_path)).model_dump(exclude_none=True)
    old={'profiles':{'legacy':{'enabled':True,'console_preflash_steps':[{'command':'approved-old'}],
                               'credential_environment':'OLD_REF'}},'max_bundle_bytes':987654}
    patch={'profiles':{'plugin':supplied},'expected_revisions':{'plugin':None}}
    merged=merge_flash_patch(old,patch,[BOARD],tmp_path/'runtime')
    assert merged['profiles']['legacy']==old['profiles']['legacy'] and merged['max_bundle_bytes']==987654
    assert merged['profiles']['plugin']==supplied and old['profiles'].keys()=={'legacy'}
    assert merge_flash_patch(merged,patch,[BOARD],tmp_path/'runtime')==merged  # replay after crash
    changed=copy.deepcopy(merged);changed['profiles']['plugin']['success_marker']='LOCAL EDIT'
    with pytest.raises(TestError) as conflict:merge_flash_patch(changed,patch,[BOARD],tmp_path/'runtime')
    assert conflict.value.code=='FLASH_PROFILE_CHANGED'


@pytest.mark.parametrize('change',[
    {'fastboot':'C:/Windows/System32/cmd.exe'}, {'batch_sha256':'wrong'},
    {'console_preflash_steps':[{'command':'erase all'}]}, {'failure_markers':[]},
    {'boards':{'board-a':{'com':'COM7','serial':'serial','lkshell_prompt':'fast','boot_marker':'login','login_prompt':'login'}}},
])
def test_public_flash_schema_rejects_arbitrary_steps_tools_and_incomplete_trust(tmp_path,change):
    with pytest.raises(ValueError):FlashProfile.model_validate(flash(tmp_path)|change)


def test_windows_flash_save_checks_files_and_board_identity_before_atomic_write(tmp_path):
    settings=Settings(tmp_path/'windows')
    settings.save({'_setup':{'server':'linux.local','account':'tester'},'boards':[BOARD],
                   'serial_transport':'native','flashing':{'profiles':{'plugin':flash(tmp_path)},'expected_revisions':{'plugin':None}}})
    before=settings.path.read_bytes();saved=settings.read()['flashing']['profiles']['plugin']
    invalid=copy.deepcopy(saved);invalid['boards']['board-a']['com']='COM99'
    with pytest.raises(TestError) as mismatch:
        settings.save({'flashing':{'profiles':{'plugin':invalid},'expected_revisions':{'plugin':profile_revision('plugin',saved)}}})
    assert mismatch.value.code=='FLASH_NOT_CONFIGURED' and settings.path.read_bytes()==before
    missing=copy.deepcopy(saved);missing['fastboot']=str(tmp_path/'missing/fastboot.exe')
    with pytest.raises(TestError):settings.save({'flashing':{'profiles':{'plugin':missing},'expected_revisions':{'plugin':profile_revision('plugin',saved)}}})
    assert settings.path.read_bytes()==before


def test_desired_flash_applied_only_when_exact_started_host_hash_matches(tmp_path,monkeypatch):
    home=tmp_path/'windows';settings=Settings(home)
    settings.save({'_setup':{'server':'linux.local','account':'tester'},'boards':[BOARD], 'serial_transport':'native'})
    profile=FlashProfile.model_validate(flash(tmp_path)).model_dump(exclude_none=True)
    app={'runner_id':'a'*32,'desired_revision':'b'*64,'settings':{'flashing':{'profiles':{'plugin':profile},'expected_revisions':{'plugin':None}}}}
    shared_control.remember_desired(home,app,app['runner_id'])
    local=json.loads(shared_control.pending_file(home).read_text());local['state']='SAVED'
    shared_control.pending_file(home).write_text(json.dumps(local))
    settings.save({'flashing':app['settings']['flashing']})
    sent=[];monkeypatch.setattr(shared_control,'request',lambda home,path,method,value:sent.append(value))
    inventory={'runner_id':app['runner_id'],'host_busy':False,'reserved':False,'boards':[BOARD],
               'configuration_fields':{'flashing_profiles':{'plugin':'0'*64}}}
    shared_control.acknowledge(home,app,inventory)
    assert sent[-1]['state']=='BLOCKED'
    inventory['configuration_fields']['flashing_profiles']['plugin']=digest(profile)
    shared_control.acknowledge(home,app,inventory)
    assert sent[-1]['state']=='APPLIED' and sent[-1]['applied_revision']==digest(app['settings'])


def test_full_fresh_profile_setup_pins_flash_command_and_runs_mocked_tc(tmp_path,monkeypatch):
    server=tmp_path/'server';home=tmp_path/'windows';settings=Settings(home)
    settings.save({'_setup':{'server':'linux.local','account':'tester'},'boards':[BOARD],
                   'serial_transport':'native','python':sys.executable})
    host=Host(settings.read(),home/'runtime',ports=lambda:['COM7'])
    current=[host]
    app=app_for(server);manager=app.state.manager
    registration={'runner_id':host.identity,'inventory':host.inventory()}
    monkeypatch.setattr(manager.runner.registry,'read',lambda:registration)
    monkeypatch.setattr(manager.runner,'inventory',lambda:current[0].inventory()|{'fresh':True})
    monkeypatch.setattr(manager.runner,'integration_profile',lambda name:current[0].flashing.profile_info(name))
    try:
        with TestClient(app,client=('127.0.0.1',1000),headers=SERVICE) as client:
            command=client.put(PROFILES+'/commands/company-tc',json=COMMAND).json()
            central=client.get(BASE+'/settings').json()
            response=client.post(PROFILES+'/commands/company-tc/select',json={'expected_settings_revision':central['revision'],'revision':command['revision']})
            assert response.status_code==200,response.text
            desired=client.put(PROFILES+'/flash/plugin',json=desired_application(manager,host.identity)|{'profile':flash(tmp_path)})
            assert desired.status_code==200,desired.text
            desired=desired.json();assert desired['state']=='PENDING'
            shared_control.remember_desired(home,desired,host.identity)
            host.close();shared_control.apply_pending(home)
            replacement=Host(settings.read(),home/'runtime',ports=lambda:['COM7']);current[0]=replacement
            registration['inventory']=replacement.inventory()
            def receipt(home,path,method,value):
                response=client.post(BASE+'/'+path,json=value)
                assert response.status_code==200,response.text
                return response.json()
            monkeypatch.setattr(shared_control,'request',receipt)
            shared_control.acknowledge(home,desired,replacement.inventory())
            assert manager.shared_settings.connector_application()['state']=='APPLIED'
            listed=client.get(PROFILES+'/flash').json();selected=listed['profiles'][0]
            central=client.get(BASE+'/settings').json()
            flash_selected=client.post(PROFILES+'/flash/plugin/select',json={'expected_settings_revision':central['revision'],'revision':selected['applied_revision']})
            assert flash_selected.status_code==200,flash_selected.text
            central=flash_selected.json();value=central['integration']
            value.update(installer_roots=[str(tmp_path/'images')],source_roots=[str(tmp_path/'tc')],tc_root=str(tmp_path/'tc'))
            changed=client.put(BASE+'/settings',json={'expected_revision':central['revision'],'integration':value,
                'timeouts':{key:value for key,value in central['timeouts'].items() if key!='revision'}})
            assert changed.status_code==200,changed.text
            tests=[{'id':'case','path':'case.py','name':'case','kind':'Single','timeout':600,'after':[],
                    'disabled_reason':'','content_hash':'fixture'}]
            manager.integration.preparer=lambda request,config:{'catalog':{'revision':'fixed','metadata_revision':'fixed','tests':tests},'tests':tests}
            monkeypatch.setattr(manager.runner,'begin_integration',lambda *args:{'state':'READY','id':'fixture-batch','terminated':True})
            monkeypatch.setattr(manager.boards,'verify',lambda *args:None)
            accepted=client.post(BASE+'/runs',headers={'Idempotency-Key':'fresh'},json={
                'installer_path':str(tmp_path/'images/install.bat'),'tc_patterns':['*.py']})
            assert accepted.status_code==202,accepted.text
            run=accepted.json();assert run['command_snapshot']['revision']==command['revision']
            assert run['integration']['config']['flash_profile_revision']==selected['applied_revision']
            manager.integration.prepare_run(run['id'])
            claim=manager.claim(run['id']);assert claim and claim['tc']['id']=='case'
            manager.emit(run['id'],claim['attempt']['id'],'stdout','Test Result: PASS\n')
            manager.finish(claim,{'exit_code':0,'terminated':True})
            assert manager.get(run['id'])['results']['case']=='PASS'
    finally:
        current[0].close()


@pytest.mark.parametrize('transport',['native','proxy'])
def test_public_profile_reaches_actual_prepare_batch_validation(tmp_path,monkeypatch,transport):
    import hashlib
    from backend.gui_test.core.models import uid
    from backend.gui_test.execution.installer_snapshots import freeze_installer
    home=tmp_path/'windows';settings=Settings(home)
    settings.save({'_setup':{'server':'linux.local','account':'tester'},'boards':[BOARD],
                   'serial_transport':transport,'python':sys.executable})
    old=Host(settings.read(),home/'runtime',ports=lambda:['COM7']);runner=old.identity;old.close()
    images=tmp_path/'images';images.mkdir();(images/'install.bat').write_text('rem reviewed installer fixture')
    (images/'image.bin').write_bytes(b'fixture image')
    supplied=flash(tmp_path);supplied['batch_sha256']=hashlib.sha256((images/'install.bat').read_bytes()).hexdigest()
    if transport=='proxy':
        supplied['boards']['board-a']['observer'].pop('port')
        supplied['boards']['board-a']['observer']['rx_only_confirmed']=False
        supplied['boards']['board-a']['observer']['control_lines_isolated']=False
    app=app_for(tmp_path/'server');manager=app.state.manager
    monkeypatch.setattr(manager.runner.registry,'read',lambda:{'runner_id':runner,'inventory':{'boards':[BOARD]}})
    monkeypatch.setattr(manager.runner,'inventory',lambda:{'runner_id':runner,'fresh':True,'flash_profile_revisions':{}})
    with TestClient(app,client=('127.0.0.1',1000),headers=SERVICE) as client:
        saved=client.put(PROFILES+'/flash/plugin',json=desired_application(manager,runner)|{'profile':supplied})
        assert saved.status_code==200,saved.text
        shared_control.remember_desired(home,saved.json(),runner);shared_control.apply_pending(home)
    host=Host(settings.read(),home/'runtime',ports=lambda:['COM7'])
    calls=[];monkeypatch.setattr(host.flashing,'prepare',lambda item:calls.append(item['id']))
    if host.multiplexers:
        from types import SimpleNamespace
        # Inject a connected proxy port; no serial endpoint is opened.
        host.multiplexers.ports['board-a'].port=SimpleNamespace(close=lambda:None)
    try:
        installer=freeze_installer(str(images/'install.bat'),[str(images)],host.runtime/'installer-snapshots')
        parent=host.batches.reserve({'id':uid(),'runner_id':runner,'request_id':'profile-prepare','connection':{'a':BOARD}})
        request={'id':uid(),'token':parent['token'],'epoch':parent['epoch'],'profile':'plugin',
                 'profile_revision':host.flashing.profile_info('plugin')['revision'],'snapshot_id':installer['snapshot_id'],
                 'manifest':installer,'connection':{'a':BOARD},'source_revision':'fixed-fixture'}
        accepted=host.flashing.start_prepare(parent['id'],request)
        for thread in host.threads:thread.join(timeout=1)
        assert accepted['phase']=='PREPARING' and calls==[request['id']]
        assert accepted['profile']['boards']['board-a']['observer']['login_markers']==['login :']
    finally:host.close()


def test_missing_or_invalid_observer_is_rejected_before_saving_profile(tmp_path):
    supplied=flash(tmp_path);supplied['boards']['board-a'].pop('observer')
    with pytest.raises(ValueError):FlashProfile.model_validate(supplied)
    supplied=flash(tmp_path);supplied['boards']['board-a']['observer']['login_markers']=['different prompt']
    with pytest.raises(ValueError):FlashProfile.model_validate(supplied)
    supplied=flash(tmp_path);supplied['boards']['board-a']['observer']['panic_signatures']=['한'*400]
    with pytest.raises(ValueError):FlashProfile.model_validate(supplied)


def test_flash_discovery_is_explicit_readonly_and_retains_ambiguous_serials(tmp_path,monkeypatch):
    settings=Settings(tmp_path/'windows')
    supplied=FlashProfile.model_validate(flash(tmp_path)).model_dump(exclude_none=True)
    settings.save({'_setup':{'server':'linux.local','account':'tester'},'boards':[BOARD],'serial_transport':'native',
                   'flashing':{'profiles':{'plugin':supplied},'expected_revisions':{'plugin':None}}})
    config=settings.read();config['flashing']['profiles']['legacy']=dict(supplied,credential_environment='PRIVATE_ENV_REF',
        console_preflash_steps=[{'command':'approved private procedure'}])
    config['flashing']['profiles']['legacy']['boards']['board-a']['observer']['redact_values']=['secret-not-exported']
    host=Host(config,settings.home/'runtime',ports=lambda:['COM7']);calls=[]
    monkeypatch.setattr(host.flashing.io,'devices',lambda value:calls.append(value['fastboot']) or ['serial-a','serial-b'])
    before=settings.path.read_bytes()
    try:
        metadata=host.flash_setup(False)
        assert calls==[] and metadata['devices'] is None and metadata['fastboot']['path']==str(Path(supplied['fastboot']).resolve())
        legacy=next(p for p in metadata['profiles'] if p['name']=='legacy')
        assert legacy['revision']==profile_revision('legacy',config['flashing']['profiles']['legacy'])
        assert 'credential_environment' in legacy['advanced_fields'] and 'PRIVATE_ENV_REF' not in str(metadata)
        assert 'secret-not-exported' not in str(metadata)
        found=host.flash_setup(True)
        assert found['devices']==['serial-a','serial-b'] and len(calls)==1
        assert settings.path.read_bytes()==before  # No serial/COM autoassignment.
        monkeypatch.setattr(host,'safe_to_stop',lambda:False)
        with pytest.raises(TestError) as busy:host.flash_setup(True)
        assert busy.value.code=='CONNECTOR_BUSY' and len(calls)==1
    finally:host.close()


def test_remote_flash_discovery_works_before_tc_python_and_checks_identity(tmp_path):
    import httpx
    from backend.gui_test.adapters.windows_remote import WindowsRemote
    calls=[];runner='a'*32
    def transport(request):
        calls.append(request)
        if request.url.path.endswith('/identity'):
            return httpx.Response(200,json={'runner_id':runner,'flash_profile_setup_v1':True,'tc_python_configured_v1':False})
        return httpx.Response(200,json={'runner_id':runner,'fastboot':{'path':'C:/tools/fastboot.exe'},'devices':['one','two']})
    with httpx.Client(transport=httpx.MockTransport(transport)) as client:
        remote=WindowsRemote('http://127.0.0.1:9888',client=client)
        result=remote.flash_setup(True)
    assert result['devices']==['one','two'] and len(calls)==2
    assert calls[-1].url.params['discover_devices']=='true' and calls[-1].extensions['timeout']['read']==15


def test_nested_advanced_profile_edits_are_explicitly_rejected_and_preserved(tmp_path):
    from backend.gui_test.core.integration_profiles import flash_setup_metadata
    old=FlashProfile.model_validate(flash(tmp_path)).model_dump(exclude_none=True)
    old['boards']['board-a']['login_steps']=[{'command':'trusted login procedure'}]
    old['boards']['board-a']['observer']['redact_values']=['private-redaction-value']
    old['boards']['board-a']['observer']['rotate_bytes']=123456
    supplied=FlashProfile.model_validate(flash(tmp_path)).model_dump(exclude_none=True)
    supplied['flash_timeout']=1200.0
    config={'profiles':{'trusted':copy.deepcopy(old)}}
    metadata=flash_setup_metadata(config)['profiles'][0]
    assert metadata['advanced_fields']==['boards.board-a.login_steps','boards.board-a.observer.redact_values','boards.board-a.observer.rotate_bytes']
    assert 'private-redaction-value' not in str(metadata)
    with pytest.raises(TestError) as advanced:
        merge_flash_patch(config,{'profiles':{'trusted':supplied},'expected_revisions':{'trusted':profile_revision('trusted',old)}},[BOARD],tmp_path/'runtime')
    assert advanced.value.code=='FLASH_PROFILE_ADVANCED'
    assert advanced.value.diagnostic['unsupported_fields']==metadata['advanced_fields']
    assert config['profiles']['trusted']==old
