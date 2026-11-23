import {toDiagramModel} from '../adapters/dashboard';
import {freezeDeep, jobFixture, moduleFixture, scaleFixture, stage, stageNames} from './fixtures';
const {test, expect} = require('./runtime.cjs');
const adapt = (job: unknown) => toDiagramModel(job, {contextKey: 'demo:job-A'});
const first = (job: unknown) => adapt(job).groups[0].modules[0];

test('T-144 persisted groups and ids survive duplicate names; malformed groups stay unassigned', () => {
  const a = moduleFixture('A', 'boot', {name: '동명 IP'}), b = moduleFixture('B', 'main', {name: '동명 IP'});
  const model = adapt(jobFixture([a, b, moduleFixture('C', 'unknown')]));
  expect(model.groups.map(g => g.modules.map(m => m.id))).toEqual([['A'], ['B']]);
  expect(model.unassigned.map(m => m.id)).toEqual(['C']);
  expect(model.unassigned[0].diagnostics.join(' ')).toMatch(/그룹/);
  expect(adapt(null).groups.every(g => g.modules.length === 0)).toBe(true);
  expect(adapt(jobFixture([])).unassigned).toEqual([]);
});

test('T-145 first incomplete stage is waiting, not running; code/build completion is conjunctive', () => {
  const m = moduleFixture();
  m.stages.analysis = stage('SUCCEEDED'); m.stages.design = stage('SUCCEEDED');
  m.stages.code = stage('SUCCEEDED'); m.current_stage = 'build';
  let view = first(jobFixture([m]));
  expect(view.runningStages).toEqual([]); expect(view.activity).toBe('waiting');
  expect(view.stages.map(s => s.label)).toEqual(['요구사항분석', '설계', '구현', '검증', 'Test']);
  expect(view.stages[2].parts.map(p => p.id)).toEqual(['code', 'build']);
  expect(view.stages[2].complete).toBe(false); expect(view.summary).toMatch(/빌드/);
  m.stages.build = stage('FAILED'); view = first(jobFixture([m]));
  expect(view.activity).toBe('failed'); expect(view.stages[2].complete).toBe(false);
  m.stages.build = stage('SUCCEEDED'); expect(first(jobFixture([m])).stages[2].complete).toBe(true);
  m.stages.code = stage('SUCCEEDED', {validity: 'STALE'});
  expect(first(jobFixture([m])).stages[2].complete).toBe(false);
});

test('T-145 active work survives paused/blocked_reason and multiple running stages are preserved', () => {
  const m = moduleFixture();
  m.stages.analysis = stage('RUNNING', {blocked_reason: '신규 배정 일시 중지'});
  m.stages.design = stage('RUNNING');
  const view = first(jobFixture([m], {paused: true}));
  expect(view.activity).toBe('running'); expect(view.runningStages).toEqual(['analysis', 'design']);
  expect(view.detail).toMatch(/후속 배정/); expect(view.diagnostics.join(' ')).toMatch(/복수/);
});

for (const [status, activity] of [['CANCEL_REQUESTED', 'transition'], ['DISPATCHING', 'transition'], ['UNKNOWN', 'unknown'], ['CANCELLED', 'failed']] as const) {
  test(`T-145 ${status} stops normal execution flow`, () => {
    const m = moduleFixture(); m.stages.analysis = stage(status);
    const view = first(jobFixture([m]));
    expect(view.activity).toBe(activity); expect(view.runningStages).toEqual([]);
    expect(view.stages[0].complete).toBe(false);
  });
}

test('T-145 N/A and 100 percent never manufacture completion or server boot gate', () => {
  const m = moduleFixture('A', 'boot', {progress: {percent: 100}});
  for (const name of stageNames) m.stages[name] = stage('SUCCEEDED');
  m.stages.device_test = stage('NOT_APPLICABLE', {exclusion_reason: '서버 제외 사유'});
  const model = adapt(jobFixture([m], {boot_ready: false}));
  expect(model.bootReady).toBe(false); expect(model.groups[0].modules[0].activity).not.toBe('complete');
  expect(model.groups[0].modules[0].stages[4].parts[0].detail).toBe('서버 제외 사유');
});

test('T-145 manual and same-attempt automation preserve actual Test result', () => {
  const m = moduleFixture(); m.current_stage = 'device_test';
  m.stages.device_test = stage('WAITING_INPUT');
  expect(first(jobFixture([m])).stages[4].parts[0].detail).toMatch(/수동 PASS\/FAIL/);
  m.stages.device_test = stage('WAITING_INPUT', {automation_blocked: '이미지 누락'});
  expect(first(jobFixture([m])).stages[4].parts[0].detail).toMatch(/자동 준비 대기.*이미지 누락/);
  // Match backend/worker/hardware.py prepare(): FlashRequest.id and baseline.attempt_id.
  m.stages.device_test = stage('RUNNING', {attempts: [{id: 'current'}], automation: {payload: {id: 'current', baseline: {attempt_id: 'current'}}, phase: 'COMPLETED'}});
  let view = first(jobFixture([m]));
  expect(view.stages[4].complete).toBe(false); expect(view.stages[4].parts[0].detail).toMatch(/자동 실행 종료/);
  m.stages.device_test = stage('RUNNING', {attempts: [{id: 'current'}], automation: {payload: {id: 'old', baseline: {attempt_id: 'old'}}, phase: 'FLASHING'}});
  view = first(jobFixture([m])); expect(view.stages[4].parts[0].detail).not.toMatch(/퓨징/);
});

test('T-145 server percent falls unchanged; unreported and out-of-range remain unknown', () => {
  const m = moduleFixture();
  m.progress = {percent: 83}; expect(first(jobFixture([m])).percent).toBe(83);
  m.progress = {percent: 16}; expect(first(jobFixture([m])).percent).toBe(16);
  for (const percent of [null, undefined, -1, 101, NaN, '60']) {
    m.progress = {percent}; expect(first(jobFixture([m])).percent).toBeNull();
  }
});

test('T-145 malformed stages and duplicate ids have diagnostics and no fabricated activity', () => {
  const m = moduleFixture(); delete m.stages.build; m.stages.code = stage('FUTURE_STATUS');
  let view = first(jobFixture([m]));
  expect(view.stages[2].parts.map(p => p.status)).toEqual(['UNKNOWN', 'UNKNOWN']);
  expect(view.diagnostics.length).toBeGreaterThanOrEqual(2);
  const duplicate = moduleFixture(m.id); duplicate.stages.analysis = stage('RUNNING');
  const views = adapt(jobFixture([m, duplicate])).groups[0].modules;
  expect(new Set(views.map(v => v.key)).size).toBe(2);
  expect(views.every(v => v.activity === 'unknown' && v.runningStages.length === 0)).toBe(true);
});

test('T-148 pure projection excludes secrets, logs, entire histories and keeps existing aggregates untouched', () => {
  const raw = scaleFixture(true); raw.secret = 'NEVER_COPY_SECRET'; raw.profile = {token: 'NEVER_COPY_TOKEN'};
  raw.progress = {implementation: {percent: 13}};
  const before = JSON.stringify(raw); freezeDeep(raw);
  const model = adapt(raw); const serialized = JSON.stringify(model);
  expect(JSON.stringify(raw)).toBe(before);
  expect(serialized).not.toMatch(/NEVER_COPY|synthetic log|attempt-7|automation/);
  expect(raw.progress.implementation.percent).toBe(13);
  expect(model.groups.flatMap(g => g.modules)).toHaveLength(100);
  const timings: number[] = [];
  for (let i = 0; i < 20; i++) {const start = performance.now(); adapt(raw); timings.push(performance.now() - start);}
  console.log('T-148 adapter_ms', JSON.stringify({max: Math.max(...timings), samples: timings}));
  expect(Math.max(...timings)).toBeLessThanOrEqual(100);
});
