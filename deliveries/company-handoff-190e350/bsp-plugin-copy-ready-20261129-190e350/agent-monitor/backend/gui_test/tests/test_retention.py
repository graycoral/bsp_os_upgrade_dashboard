"""Temporary-directory retention safety; never cleans the user's runtime."""
import json
import os
from pathlib import Path
import sqlite3
import threading
import time
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from backend.gui_test.core.manager import Manager
from backend.gui_test.core.models import TestError
from backend.gui_test.core.store import Store
from backend.gui_test.core.retention import (StorageSettings, StoragePolicy, collect,
    collect_trees, snapshot_lock, connector_sync)
from backend.gui_test.execution import retention as windows

OLD = time.time() - 30 * 86400


def tree(root, identity, size=16):
    path = root / identity
    path.mkdir(parents=True)
    (path / 'data').write_bytes(b'x' * size)
    os.utime(path / 'data', (OLD, OLD))
    os.utime(path, (OLD, OLD))
    return path


def doc(store, kind, name, value):
    with store.transaction() as c: c.execute('INSERT INTO documents VALUES(?,?,?)', (kind, name, json.dumps(value)))


def run(store, name, value):
    with store.transaction() as c: c.execute('INSERT INTO runs VALUES(?,?)', (name, json.dumps(value)))


def policy(store, **values):
    settings = StorageSettings(store)
    current = settings.read()
    return settings.save({k:v for k,v in current.items() if k != 'revision'} | values | {'expected_revision':current['revision']})


def test_linux_retains_current_active_paused_unknown_failed_and_prepared(tmp_path):
    manager = Manager(Store(tmp_path / 'state.db'))
    paths = {str(i): tree(manager.sources.snapshots, f'{i:064x}') for i in range(1, 10)}
    doc(manager.store, 'source-state', 'active', {'active': {'snapshot_id':paths['1'].name}})
    for i, state in [(2,'RUNNING'), (3,'PAUSED'), (4,'UNKNOWN'), (5,'COMPLETED')]:
        run(manager.store, str(i), {'state':state,'overall_result':'FAIL' if i==5 else 'INCOMPLETE', 'source_snapshot':{'snapshot_id':paths[str(i)].name}})
    doc(manager.store, 'integration-preparation','ready', {'state':'READY','expires_at':time.time()+10,'receipt':{'source_directory':str(paths['6'])}})
    doc(manager.store, 'integration-preparation','expired', {'state':'READY','expires_at':OLD,'receipt':{'source_directory':str(paths['7'])}})
    run(manager.store,'8', {'state':'COMPLETED','overall_result':'PASS','source_snapshot':{'snapshot_id':paths['8'].name}})
    run(manager.store,'9', {'state':'COMPLETED','overall_result':'PASS','source_snapshot':{'snapshot_id':paths['9'].name},'attempts':[{'state':'FAIL'}]})
    policy(manager.store,max_bytes=1)
    preview = collect(manager,dry_run=True)
    assert set(preview['candidates']) == {str(paths['7']),str(paths['8'])}
    assert all(p.exists() for p in paths.values())
    report = collect(manager,dry_run=False)
    assert report['protected_bytes']==7*16 and report['over_budget']
    assert not paths['7'].exists() and not paths['8'].exists()
    assert len(manager.store.all())==6  # No run/evidence records are pruned.
    assert StorageSettings(manager.store).report()['deleted_bytes']==32


def test_age_budget_disabled_grace_and_links(tmp_path):
    root=tmp_path/'cache'
    old=tree(root,'a'*64)
    recent=tree(root,'b'*64)
    os.utime(recent,None)
    outside=tree(tmp_path/'external','keep')
    (root/('c'*64)).symlink_to(outside, target_is_directory=True)
    unknown=tree(root,'not-a-cache')
    value=StoragePolicy(max_bytes=1).model_dump()
    disabled=collect_trees([(root,'[a-f0-9]{64}')],set(),value|{'enabled':False},dry_run=False)
    assert disabled['deleted']==[]
    report=collect_trees([(root,'[a-f0-9]{64}')],set(),value,dry_run=False)
    assert report['deleted']==[str(old)] and report['over_budget']
    assert recent.exists() and outside.exists() and unknown.exists()
    assert not report['measurement_complete']


def test_collector_does_not_race_producer_reference_window(tmp_path):
    manager=Manager(Store(tmp_path/'state.db'))
    path=tree(manager.sources.snapshots,'a'*64)
    entered=threading.Event(); release=threading.Event()
    def producer():
        with snapshot_lock(tmp_path):
            with snapshot_lock(tmp_path):  # Nested source/apply/start operations.
                entered.set(); release.wait(5)
                doc(manager.store,'source-state','active',{'snapshot_id':path.name})
    thread=threading.Thread(target=producer); thread.start()
    try:
        assert entered.wait(3)
        assert collect(manager,dry_run=False)['skipped_reason']=='SNAPSHOT_BUSY'
    finally: release.set(); thread.join(5)
    assert collect(manager,dry_run=False)['deleted']==[] and path.exists()


def test_policy_validation_cas_and_pending_sync(tmp_path):
    manager=Manager(Store(tmp_path/'state.db'))
    initial=StorageSettings(manager.store).read()
    assert initial['enabled'] and initial['max_age_seconds']==604800 and initial['max_bytes']==20*1024**3
    assert connector_sync(manager)['state']=='LOCAL_DEFAULT'
    value=policy(manager.store,max_age_seconds=3600)
    assert value['revision']!=initial['revision']
    with pytest.raises(TestError,match='changed'):
        StorageSettings(manager.store).save({k:v for k,v in initial.items() if k!='revision'}|{'expected_revision':initial['revision']})
    with pytest.raises(ValidationError): StoragePolicy(enabled='false')
    assert connector_sync(manager)['state']=='SYNC_PENDING'


def host(tmp_path):
    value=SimpleNamespace(runtime=tmp_path,db=tmp_path/'executions.db',lock=threading.RLock())
    with sqlite3.connect(value.db) as c:
        c.executescript('CREATE TABLE runner_meta(key TEXT PRIMARY KEY,value TEXT);CREATE TABLE jobs(id TEXT PRIMARY KEY,fingerprint TEXT,data TEXT);CREATE TABLE batches(id TEXT PRIMARY KEY,fingerprint TEXT,data TEXT);')
    return value


def job(host, identity, **values):
    value={'id':identity,'state':'DONE','terminated':True,'exit_code':0,'stdout':'Test Result: PASS','stderr':'','source_snapshot_id':'f'*64}|values
    with sqlite3.connect(host.db) as c: c.execute('INSERT INTO jobs VALUES(?,?,?)',(identity,'hash',json.dumps(value)))
    return value


def test_windows_pass_only_cleanup_preserves_failed_unknown_held_and_receipts(tmp_path):
    runner=host(tmp_path)
    passed=tree(tmp_path/'snapshots','1'*32)
    failed=tree(tmp_path/'snapshots','2'*32)
    unknown=tree(tmp_path/'snapshots','3'*32)
    held=tree(tmp_path/'batch-snapshots','4'*32)
    source=tree(tmp_path/'source-snapshots','f'*64)
    installer=tree(tmp_path/'installer-snapshots','e'*64)
    receipts=tmp_path/'installer-transfers';receipts.mkdir()
    receipt=receipts/(installer.name+'.json');receipt.write_text('{"state":"READY"}')
    partial=receipts/'resumable.partial';partial.write_bytes(b'keep')
    job(runner,passed.name)
    job(runner,failed.name,stdout='Test Result: FAIL')
    job(runner,unknown.name,state='UNKNOWN',terminated=False)
    with sqlite3.connect(runner.db) as c:
        c.execute('INSERT INTO batches VALUES(?,?,?)',(held.name,'hash',json.dumps({'id':held.name,'state':'READY'})))
    preview=windows.collect(runner,dry_run=True)
    assert set(preview['candidates'])=={str(passed),str(installer)} and receipt.exists()
    actual=windows.collect(runner,dry_run=False)
    assert set(actual['deleted'])==set(preview['candidates'])
    assert all(p.exists() for p in [failed,unknown,held,source,partial]) and not receipt.exists()
    with sqlite3.connect(runner.db) as c: assert c.execute('SELECT count(*) FROM jobs').fetchone()[0]==3


def test_windows_publication_and_gc_share_lock_and_refresh_grace(tmp_path):
    runner=host(tmp_path)
    path=tree(tmp_path/'source-snapshots','a'*64)
    def publish(): return {'snapshot_id':path.name}
    windows.publish(runner,publish)
    assert windows.collect(runner,dry_run=False)['deleted']==[]
    assert path.exists()


def test_pending_remote_policy_retries_pins_identity_and_does_not_overwrite_defaults(tmp_path):
    manager=Manager(Store(tmp_path/'state.db'))
    directory=tmp_path/'remote'; directory.mkdir()
    remote_host=host(directory); remote_host.identity='a'*32
    class Remote:
        fail=False
        def request(self,path,method='GET',data=None):
            if self.fail: raise TestError('offline','RUNNER_UNAVAILABLE')
            if path=='/identity': return {'runner_id':remote_host.identity,'storage_retention_v1':True}
            if path=='/storage-policy' and method=='GET': return windows.read_policy(remote_host)
            assert data['expected_runner_id']==remote_host.identity
            return windows.save_policy(remote_host,data)
    manager.runner=Remote()
    assert connector_sync(manager)['state']=='LOCAL_DEFAULT'
    policy(manager.store,max_bytes=1024)
    manager.runner.fail=True
    assert connector_sync(manager)['state']=='SYNC_PENDING'
    manager.runner.fail=False
    assert connector_sync(manager)['state']=='APPLIED'
    assert windows.read_policy(remote_host)['max_bytes']==1024
    assert windows.read_policy(remote_host)['origin']=='plugin'
    current=windows.read_policy(remote_host)
    with pytest.raises(TestError,match='identity'):
        windows.save_policy(remote_host,{k:current[k] for k in StoragePolicy.model_fields}|{'expected_revision':current['revision'],'expected_runner_id':'b'*32})


def test_storage_policy_file_validates_cas_and_worker_integration(tmp_path):
    from backend.gui_test.core.retention import main
    from backend.gui_test.core.worker import Worker
    manager=Manager(Store(tmp_path/'state.db'))
    path=tmp_path/'policy.json'
    main(['--database',str(manager.store.path),'export',str(path)])
    value=json.loads(path.read_text());value['max_bytes']=1234
    path.write_text(json.dumps(value))
    main(['--database',str(manager.store.path),'apply',str(path)])
    assert StorageSettings(manager.store).read()['max_bytes']==1234
    with pytest.raises(TestError,match='changed'):
        main(['--database',str(manager.store.path),'apply',str(path)])
    candidate=tree(manager.sources.snapshots,'a'*64)
    worker=Worker(manager)
    try:
        worker.tick()
        worker.storage_pending.result(timeout=10)
        assert not candidate.exists()
    finally: worker.close()


def test_storage_api_requires_principal_and_supports_dry_run(tmp_path):
    from fastapi import FastAPI
    from fastapi.responses import JSONResponse
    from fastapi.testclient import TestClient
    from backend.gui_test.api.storage import create_router
    manager=Manager(Store(tmp_path/'state.db'))
    app=FastAPI()
    @app.middleware('http')
    async def principal(request,call_next):
        if request.headers.get('x-test-principal'): request.state.gui_principal='test'
        return await call_next(request)
    @app.exception_handler(TestError)
    async def error(request,exc): return JSONResponse({'code':exc.code},status_code=exc.status)
    app.include_router(create_router(manager))
    client=TestClient(app);url='/api/v1/gui-test/live/integration'
    current=client.get(url+'/storage-policy').json()
    payload={k:current[k] for k in StoragePolicy.model_fields}|{'expected_revision':current['revision'],'max_bytes':1}
    assert client.put(url+'/storage-policy',json=payload).status_code==403
    assert client.put(url+'/storage-policy',json=payload,headers={'x-test-principal':'yes'}).status_code==200
    path=tree(manager.sources.snapshots,'a'*64)
    response=client.post(url+'/storage-cleanup',json={'dry_run':True},headers={'x-test-principal':'yes'})
    assert response.status_code==200 and response.json()['candidates']==[str(path)] and path.exists()
    assert response.json()['connector_cleanup']['state']=='UNAVAILABLE'



def test_connector_qt_policy_edits_and_preview_share_central_adapter(tmp_path):
    os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
    from PySide6.QtWidgets import QApplication
    from backend.gui_test.connector.preview import MockConnector
    from backend.gui_test.connector.shared_settings_ui import StorageSettingsPanel
    app=QApplication.instance() or QApplication([])
    class Owner:
        adapter=MockConnector(tmp_path)
        errors=[]
        def operation(self,fn,done=None):
            value=fn()
            if done: done(value)
        def show_error(self,value): self.errors.append(value)
    owner=Owner(); panel=StorageSettingsPanel(owner)
    try:
        panel.save(); assert owner.errors
        panel.reload(); panel.hours.setValue(24); panel.gib.setValue(2);panel.save()
        assert owner.adapter.storage_policy()['max_age_seconds']==86400
        assert owner.adapter.storage_policy()['max_bytes']==2*1024**3
        panel.preview(); assert '서버:' in panel.status.text() and '커넥터:' in panel.status.text()
        # A response arriving during an edit may not overwrite the visible edit.
        generation=panel.generation; panel.hours.setValue(48)
        panel.accept(owner.adapter.storage_policy(),generation)
        assert panel.hours.value()==48
    finally: panel.close();panel.deleteLater();app.processEvents()


@pytest.mark.parametrize('phase',['scan','delete'])
def test_slow_linux_filesystem_does_not_hold_writer_lock(tmp_path,monkeypatch,phase):
    from backend.gui_test.core import retention
    manager=Manager(Store(tmp_path/'state.db'))
    tree(manager.sources.snapshots,'a'*64)
    entered=threading.Event();release=threading.Event()
    original=retention._measure
    def slow(path):
        if path.name.startswith('.retention-')==(phase=='delete'):
            entered.set();assert release.wait(5)
        return original(path)
    monkeypatch.setattr(retention,'_measure',slow)
    errors=[]
    def cleanup():
        try: collect(manager,dry_run=False)
        except Exception as exc: errors.append(exc)
    thread=threading.Thread(target=cleanup);thread.start()
    try:
        assert entered.wait(3)
        with sqlite3.connect(manager.store.path,timeout=.2) as c:
            c.execute('BEGIN IMMEDIATE')
            c.execute("INSERT INTO meta VALUES('concurrent-emission','retained')")
    finally:release.set();thread.join(5)
    assert not errors


@pytest.mark.parametrize('phase',['scan','delete','publish'])
def test_slow_windows_filesystem_does_not_hold_control_or_writer_lock(tmp_path,monkeypatch,phase):
    from backend.gui_test.core import retention
    runner=host(tmp_path); tree(tmp_path/'source-snapshots','a'*64)
    entered=threading.Event();release=threading.Event()
    original=retention._measure
    def slow(path):
        if path.name.startswith('.retention-')==(phase=='delete'):
            entered.set();assert release.wait(5)
        return original(path)
    monkeypatch.setattr(retention,'_measure',slow)
    def publication():
        entered.set();assert release.wait(5)
        return {'snapshot_id':'a'*64}
    errors=[]
    def cleanup():
        try:
            if phase=='publish': windows.publish(runner,publication)
            else: windows.collect(runner,dry_run=False)
        except Exception as exc: errors.append(exc)
    thread=threading.Thread(target=cleanup);thread.start()
    try:
        assert entered.wait(3)
        assert runner.lock.acquire(timeout=.2)
        try:
            with sqlite3.connect(runner.db,timeout=.2) as c:
                c.execute('BEGIN IMMEDIATE')
                c.execute("INSERT INTO runner_meta VALUES('concurrent-status','retained')")
        finally:runner.lock.release()
    finally:release.set();thread.join(5)
    assert not errors


def test_candidate_changed_after_scan_is_revalidated(tmp_path,monkeypatch):
    from backend.gui_test.core import retention
    manager=Manager(Store(tmp_path/'state.db'))
    candidate=tree(manager.sources.snapshots,'a'*64)
    original=retention.scan_trees
    def scan(roots):
        result=original(roots)
        doc(manager.store,'source-state','active',{'snapshot_id':candidate.name})
        return result
    monkeypatch.setattr(retention,'scan_trees',scan)
    assert collect(manager,dry_run=False)['deleted']==[]
    assert candidate.exists()


def test_snapshot_lock_excludes_another_process(tmp_path):
    import subprocess
    import sys
    from backend.gui_test.execution.launch import LaunchLock
    # The other process represents a second plugin/monitor API worker.
    code="from backend.gui_test.core.retention import snapshot_lock; import sys\ntry:\n with snapshot_lock(sys.argv[1],blocking=False): sys.exit(2)\nexcept BlockingIOError: sys.exit(0)\n"
    with LaunchLock(tmp_path/'snapshot-retention.lock'):
        result=subprocess.run([sys.executable,'-c',code,str(tmp_path)],capture_output=True,timeout=10)
    assert result.returncode==0,result.stderr.decode()


def test_shutdown_awaits_inflight_windows_cleanup(tmp_path,monkeypatch):
    import asyncio
    runner=host(tmp_path)
    started=threading.Event();release=threading.Event();finished=threading.Event()
    def slow_collect(*args,**kwargs):
        started.set();assert release.wait(5);finished.set()
    monkeypatch.setattr(windows,'collect',slow_collect)
    async def check():
        task=asyncio.create_task(windows.maintain(runner))
        assert await asyncio.to_thread(started.wait,3)
        task.cancel()
        await asyncio.sleep(.02)
        assert not task.done()  # Process lock may not be released yet.
        release.set()
        with pytest.raises(asyncio.CancelledError): await task
        assert finished.is_set()
    asyncio.run(check())


def test_large_backlog_is_quarantined_in_bounded_batches(tmp_path):
    manager=Manager(Store(tmp_path/'state.db'))
    for index in range(40): tree(manager.sources.snapshots,f'{index:064x}')
    report=collect(manager,dry_run=False)
    assert len(report['deleted'])==32 and report['batch_limited']
    assert len(list(manager.sources.snapshots.iterdir()))==8
    assert len(collect(manager,dry_run=False)['deleted'])==8
