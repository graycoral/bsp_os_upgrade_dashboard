/** Fixed, synthetic snapshots. No BSP, ACON, device or application database access. */
export const stageNames = ['analysis', 'design', 'code', 'build', 'verification', 'device_test'] as const;
export function stage(status = 'PENDING', extra: Record<string, unknown> = {}) {
  return {status, validity: 'CURRENT', blocked_reason: null, attempts: [], required_cases: [], ...extra};
}
export function moduleFixture(id = 'ip-1', group = 'boot', extra: Record<string, unknown> = {}) {
  return {id, name: `IP ${id}`, group, current_stage: 'analysis', progress: {done: 0, total: 6, percent: 0},
    stages: Object.fromEntries(stageNames.map(name => [name, stage()])), ...extra};
}
export function jobFixture(modules = [moduleFixture()], extra: Record<string, unknown> = {}) {
  return {id: 'job-A', execution: 'demo', version: 7, updated_at: '2000-01-01T00:00:00Z', paused: false,
    modules, boot_ready: false, plan_version: 1, confirmed_plan: null, state: 'ANALYZING',
    title: 'Synthetic job A', profile: {workspace: '/synthetic'}, source_revision: 'synthetic-revision',
    decisions: [], prompts: [], integration: {status: 'PENDING'}, final_review: null, session: {status: 'READY'},
    progress: Object.fromEntries(['analysis', 'implementation', 'verification', 'build', 'test'].map(key => [key, {done: 0, total: 1, percent: 0}])),
    groups: {boot: {percent: 0}, main: {percent: 0}}, overall: {done: 0, total: 6, percent: 0}, ...extra};
}
export function scaleFixture(withHistory = false) {
  return jobFixture(Array.from({length: 100}, (_, i) => {
    const m = moduleFixture(`ip-${i}`, i < 20 ? 'boot' : 'main', {name: `${i.toString().padStart(3, '0')}-` + '가'.repeat(76)});
    m.stages.analysis = stage(i % 7 === 0 ? 'FAILED' : 'RUNNING');
    if (withHistory) for (const s of Object.values(m.stages)) {
      s.attempts = Array.from({length: 8}, (_, n) => ({id: `attempt-${n}`, status: 'FAILED',
        log: 'synthetic log '.repeat(64), evidence: {hash: 'a'.repeat(64)},
        automation: {phase: 'COMPLETED', report: {cases: Array.from({length: 12}, (_, c) => ({id: `tc-${c}`, result: 'PASS'}))}}}));
    }
    return m;
  }));
}

export function freezeDeep<T>(input: T): T {
  if (input && typeof input === 'object' && !Object.isFrozen(input)) {
    Object.freeze(input);
    Object.values(input).forEach(freezeDeep);
  }
  return input;
}

/** Explicit read-only GUI source contract; never registers or runs a source. */
export function legacySourceFixture() {
  return {version:0,active:{kind:'legacy',location:'',ref:null,commit:null,inspection_id:null,snapshot_id:null,source_revision:null},
    execution:{ready:true,reason:null,code:'READY'}};
}

/** Existing O1 read endpoints also load on overview/decisions in display fixtures. */
export function inactiveOrchestrationFixture(version=1) {
  return {enabled:false,legacy_report:true,execution_version:version,health:{status:'DISABLED'},limits:{},
    runs:[],proposals:[],candidates:[],holds:[],pagination:{}};
}
