import {aconConnection, diagramActivity, snapshotHealth} from '../web/presentation';
import {toDiagramModel} from '../adapters/dashboard';
import {jobFixture, moduleFixture, stage} from './fixtures';
const {test, expect} = require('./runtime.cjs');

test('T-146 ACON scope, provider timestamp and expiry are independent of API health', () => {
  const api = {status: 'ready' as const, receivedAt: 50000, receivedMonoMs: 10, staleAfterMs: 5400, needsConfirmation: false, detail: ''};
  expect(snapshotHealth(api, 11).fresh).toBe(true);
  expect(aconConnection(undefined, 'A', 'IP', 1000).tone).toBe('gray');
  const common = {provider: 'synthetic', jobId: 'A', scope: 'job' as const, state: 'connected' as const, observedAt: 900, expiresAt: 1200};
  expect(aconConnection([common], 'A', 'IP', 1000).label).toBe('공통 연결');
  expect(aconConnection([common], 'B', 'IP', 1000).fresh).toBe(false);
  expect(aconConnection([common], 'A', 'IP', 1200).label).toMatch(/만료/);
  expect(aconConnection([{...common, observedAt: 1100}], 'A', 'IP', 1000).fresh).toBe(false);
  const explicit = {...common, scope: 'module' as const, moduleId: 'IP', state: 'disconnected' as const};
  expect(aconConnection([common, explicit], 'A', 'IP', 1000).tone).toBe('red');
  expect(aconConnection([common, explicit], 'A', 'OTHER', 1000).label).toBe('공통 연결');
  expect(aconConnection([{...common, provider: ''}], 'A', 'IP', 1000).fresh).toBe(false);
});

test('T-147 general analysis runs without opening prerequisite edge; failed peer does not suppress boot work', () => {
  const boot = moduleFixture('boot'), failed = moduleFixture('failed'), main = moduleFixture('main', 'main');
  main.stages.analysis = stage('RUNNING'); failed.stages.analysis = stage('FAILED');
  let model = toDiagramModel(jobFixture([boot, failed, main]), {contextKey: 'A'});
  expect(diagramActivity(model, true)).toEqual({boot: false, main: false});
  boot.stages.analysis = stage('RUNNING');
  model = toDiagramModel(jobFixture([boot, failed, main]), {contextKey: 'A'});
  expect(diagramActivity(model, true)).toEqual({boot: true, main: false});
  main.stages.analysis = stage('SUCCEEDED'); main.stages.design = stage('RUNNING');
  model = toDiagramModel(jobFixture([boot, failed, main], {boot_ready: false}), {contextKey: 'A'});
  expect(diagramActivity(model, true).main).toBe(false); expect(model.diagnostics.join(' ')).toMatch(/불일치/);
  model = toDiagramModel(jobFixture([boot, failed, main], {boot_ready: true}), {contextKey: 'A'});
  expect(diagramActivity(model, true).main).toBe(true);
  expect(diagramActivity(model, false)).toEqual({boot: false, main: false});
});

test('T-147 cancelled, cancel-requested, unknown and waiting modules have no active paths', () => {
  for (const status of ['CANCELLED', 'CANCEL_REQUESTED', 'UNKNOWN', 'WAITING_INPUT', 'DISPATCHING', 'PENDING']) {
    const boot = moduleFixture('boot'), main = moduleFixture('main', 'main');
    boot.stages.analysis = stage(status); main.stages.design = stage(status);
    const model = toDiagramModel(jobFixture([boot, main], {boot_ready: true}), {contextKey: 'A'});
    expect(diagramActivity(model, true)).toEqual({boot: false, main: false});
  }
});
