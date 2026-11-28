"""Persistent analysis with fake providers and bounded local read-only programs."""
import json
import sys
import time
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from backend.gui_test.core.models import TestError,digest
from backend.gui_test.runtime import make_manager
from backend.gui_test.core.worker import Worker
from backend.gui_test.standalone.analysis_runtime import (
    attach, RuntimeAnalysis, AdapterCommand, context, invoke, pinned, save_settings, settings)
from backend.gui_test.standalone.plugin_client import PluginClient
from backend.gui_test.tests.test_core import start
from backend.gui_test.tests.test_failure_analysis import fail,verifier


def command(tmp_path,role):
    script=tmp_path/(role+'.py');script.write_text('# fixture\n')
    return pinned([sys.executable,str(script),'{request_file}'])


def test_flash_failure_context_includes_bounded_redacted_evidence_without_tc_attempt(tmp_path):
    from backend.gui_test.tests.test_plugin_integration_service import rig as fixture
    manager, service, _, request, _, _ = fixture.__wrapped__(tmp_path)
    run = service.start('flash-evidence', 'bsp-upgrade', request)
    service.record_batch(run['id'], {'id': 'f' * 32, 'state': 'FAILED', 'phase': 'BOOT',
        'terminated': True, 'reason': 'BOOT_TIMEOUT', 'lease_token': 'hidden-lease',
        'flashes': [{'result': {'stdout': 'x' * 20000 + '\nfastboot init success',
                               'stderr': 'password=hidden-password\nboot timed out',
                               'console': ['old'] * 40 + ['waiting for login']}}]})
    item = manager.analysis.claim('bsp-upgrade', 'test')
    payload = context(item)
    assert payload['attempts'] == []
    batch = payload['integration']['batch']
    assert batch['phase'] == 'BOOT' and batch['terminated'] is True
    result = batch['flashes'][0]['result']
    assert result['stdout'].endswith('fastboot init success')
    assert result['console'][-1] == 'waiting for login'
    assert len(result['console']) == 32 and payload['integration_evidence_truncated'] is True
    encoded = json.dumps(payload)
    assert 'hidden-lease' not in encoded and 'hidden-password' not in encoded
    assert item['evidence_refs'] == payload['analysis']['evidence_refs']


def test_analysis_truncation_cannot_expose_long_credential_tail(tmp_path):
    manager = make_manager(tmp_path, 'standalone')
    run = fail(manager, start(manager))
    item = manager.analysis.claim('bsp-upgrade', 'test')
    selected = next(a for a in item['run']['attempts'] if a['id'] == item['attempt_id'])
    selected['stdout'] = 'password=' + 'private-data' * 4000
    selected['stderr'] = 'Bearer ' + 'credential' * 4000
    payload = json.dumps(context(item))
    assert 'private-data' not in payload and 'credential' not in payload


def test_existing_worker_automatically_diagnoses_failure_without_claiming_remediation(tmp_path):
    manager=attach(make_manager(tmp_path,'standalone'),tmp_path)
    run=fail(manager,start(manager))
    worker=Worker(manager)
    try:
        worker.tick()
        worker.analysis_pending.result(timeout=5)
        current=manager.get(run['id'])
        assert current['failure_analysis']['status']=='HOLD' and current['failure_analysis']['latched']
        assert current['attempts']==run['attempts'] and manager.claim(run['id']) is None
        assert manager.analysis_runtime.status()['state']=='HOLD'
        assert current['failure_analysis']['cause_key'].startswith('fail-')
    finally: worker.close()


def test_registered_command_analyzer_and_independent_verifier_complete_retry(tmp_path):
    manager=attach(make_manager(tmp_path,'standalone'),tmp_path)
    original=fail(manager,start(manager))
    cfg={'mode':'command','analyzer':command(tmp_path,'analyze'),'verifier':command(tmp_path,'verify')}
    save_settings(tmp_path,cfg)
    seen=[]
    def execute(command,request,home):
        seen.append(request)
        assert 'lease_token' not in json.dumps(request)
        if request['contract']=='failure-analysis-v1':
            item=request['analysis']
            return {'base_revision':item['evidence_revision'],'cause_key':'fixed-fixture','cause_summary':'fixture',
                    'remediation_summary':'verified repair','evidence_refs':item['evidence_refs'],
                    'remediation_refs':['repair:fixture'],'action':'RETRY'}
        return verifier(request['run'],request['analysis'],request['result'])
    manager.analysis_runtime.executor=execute
    receipt=manager.analysis_runtime.tick()
    assert receipt['status']=='RETRY_READY' and len(seen)==2
    assert manager.claim(original['id'])['attempt']['slot_index']==0


def test_unavailable_adapter_keeps_durable_lease_for_restart_and_does_not_leak_output(tmp_path):
    manager=attach(make_manager(tmp_path,'standalone'),tmp_path)
    run=fail(manager,start(manager))
    save_settings(tmp_path,{'mode':'command','analyzer':command(tmp_path,'analyze')})
    manager.analysis_runtime.executor=lambda *a: (_ for _ in ()).throw(ValueError('password=private-detail'))
    manager.analysis_runtime.tick()
    assert manager.get(run['id'])['failure_analysis']['status']=='LEASED'
    assert manager.analysis_runtime.status()['code']=='ANALYSIS_ADAPTER_INVALID'
    assert 'private-detail' not in json.dumps(manager.analysis_runtime.status())
    reopened=attach(make_manager(tmp_path,'standalone'),tmp_path)
    reopened.analysis.clock=lambda:time.time()+601
    item=reopened.analysis.claim('bsp-upgrade','new-consumer')
    assert item['id']==run['failure_analysis']['request_id'] and item['deliveries']==2


def test_external_provider_leaves_request_unclaimed_and_config_is_cas(tmp_path):
    manager=attach(make_manager(tmp_path,'standalone'),tmp_path)
    run=fail(manager,start(manager))
    receipt=save_settings(tmp_path,{'mode':'external'})
    manager.analysis_runtime.tick()
    assert manager.get(run['id'])['failure_analysis']['status']=='PENDING'
    with pytest.raises(TestError):save_settings(tmp_path,{'mode':'builtin'},'stale')
    assert save_settings(tmp_path,{'mode':'builtin'},receipt['revision'])['mode']=='builtin'


def test_configuration_change_during_callback_cannot_apply_old_advice(tmp_path):
    manager=attach(make_manager(tmp_path,'standalone'),tmp_path)
    run=fail(manager,start(manager))
    saved=save_settings(tmp_path,{'mode':'command','analyzer':command(tmp_path,'analyze')})
    def execute(*args):
        save_settings(tmp_path,{'mode':'external'},saved['revision'])
        item=args[1]['analysis']
        return {'base_revision':item['evidence_revision'],'cause_key':'changed','cause_summary':'fixture',
                'remediation_summary':'','evidence_refs':item['evidence_refs'],'remediation_refs':[],'action':'HOLD'}
    manager.analysis_runtime.executor=execute
    manager.analysis_runtime.tick()
    assert manager.get(run['id'])['failure_analysis']['status']=='LEASED'
    assert manager.analysis_runtime.status()['code']=='ANALYSIS_CONFIG_CHANGED'


def test_bounded_command_executes_only_pinned_program_and_cleans_private_context(tmp_path):
    script=tmp_path/'read_request.py'
    script.write_text('import json,sys\nv=json.load(open(sys.argv[1]));print(json.dumps({"seen":v["value"]}))\n')
    cfg=AdapterCommand.model_validate(pinned([sys.executable,str(script),'{request_file}']))
    assert invoke(cfg,{'value':'fixture'},tmp_path/'private')=={'seen':'fixture'}
    assert not list((tmp_path/'private').iterdir())
    script.write_text('raise Exception("changed")')
    with pytest.raises(TestError,match='changed'):invoke(cfg,{},tmp_path/'private')


@pytest.mark.parametrize('body', ['print("x"*300000)', 'import time;time.sleep(30)'])
def test_timeout_and_excessive_output_do_not_become_analysis_result(tmp_path,body):
    script=tmp_path/'bad.py';script.write_text(body)
    cfg=AdapterCommand.model_validate(pinned([sys.executable,str(script),'{request_file}'])|{'timeout_seconds':1})
    with pytest.raises(TestError): invoke(cfg,{},tmp_path/'private')
    assert not list((tmp_path/'private').iterdir())


def test_real_bootstrap_wires_runtime_verifier_and_api_preserves_it(tmp_path):
    from backend.api.main import create_app
    manager=make_manager(tmp_path/'plain','integration')
    assert isinstance(manager.analysis_worker,RuntimeAnalysis)
    app=create_app(tmp_path/'full')
    assert app.state.gui_live_manager.analysis.verifier is not None
    with TestClient(app,client=('127.0.0.1',1200)) as client:
        response=client.get('/api/v1/gui-test/live/integration/analyses/runtime',headers={'X-Bsp-Service':'plugin'})
        assert response.status_code==200 and response.json()['state']=='WAITING'


def test_plugin_client_accepts_actual_64_character_analysis_identity(tmp_path):
    from backend.gui_test.standalone.integration import create_app,ServiceRegistry
    from backend.gui_test.core.integration import IntegrationService
    manager=make_manager(tmp_path,'standalone');IntegrationService(manager,{})
    run=fail(manager,start(manager));analysis_id=run['failure_analysis']['request_id']
    assert len(analysis_id)==64
    app=create_app(tmp_path,manager=manager,start_worker=False)
    with TestClient(app,client=('127.0.0.1',1200)) as transport:
        identity=ServiceRegistry(manager,tmp_path,'bsp-upgrade').snapshot(False)
        client=PluginClient('http://127.0.0.1',expected_identity={k:identity[k] for k in ('runtime_id','package_version')},client=transport)
        assert client.analysis(analysis_id)['id']==analysis_id
        item=client.claim_analysis()['analysis']
        result={'base_revision':item['evidence_revision'],'cause_key':'fixture','cause_summary':'fixture',
                'remediation_summary':'','evidence_refs':item['evidence_refs'],'remediation_refs':[],'action':'HOLD'}
        assert client.submit_analysis(analysis_id,{'lease_token':item['lease_token'],'result':result})['status']=='HOLD'


def test_full_host_health_preserves_process_identity(tmp_path, monkeypatch):
    from backend.api.main import create_app
    from fastapi.testclient import TestClient
    monkeypatch.setenv('BSP_INSTANCE_ID','isolated-fixture-process')
    with TestClient(create_app(tmp_path),client=('127.0.0.1',1200)) as client:
        result=client.get('/api/v1/health')
        assert result.status_code==200
        response=result.json()
        assert response['instance_id']=='isolated-fixture-process'
        assert response['service_instance_id'] != response['instance_id']
