import { test, expect, type Page } from '../../apps/web/node_modules/@playwright/test';
import { createServer, type Server } from 'node:http';
import { readFileSync } from 'node:fs';
import path from 'node:path';

// Serve the actual built App on an isolated ephemeral port. Every API request is
// intercepted below; this suite never reads or changes a user's running service.
const root = path.resolve(process.cwd(), '../..');
const dist = path.join(root, 'apps/web/dist');
let server: Server;
let origin: string;
test.beforeAll(async () => {
  server = createServer((req, res) => {
    const relative = new URL(req.url || '/', 'http://fixture').pathname;
    const file = path.resolve(dist, relative === '/' ? 'index.html' : `.${relative}`);
    if (!file.startsWith(dist + path.sep)) { res.writeHead(403).end(); return; }
    try {
      const type = file.endsWith('.js') ? 'text/javascript' : file.endsWith('.css') ? 'text/css' : 'text/html';
      res.writeHead(200, { 'Content-Type': type }); res.end(readFileSync(file));
    } catch { res.writeHead(404).end(); }
  });
  await new Promise<void>(resolve => server.listen(0, '127.0.0.1', resolve));
  const address = server.address();
  if (!address || typeof address === 'string') throw new Error('Fixture HTTP server did not start.');
  origin = `http://127.0.0.1:${address.port}`;
});
test.afterAll(async () => { if (server) await new Promise<void>((resolve, reject) => server.close(e => e ? reject(e) : resolve())); });

type Data = Record<string, any>;
function profile(): Data {
  return { execution: 'demo', runner: 'native', workspace: '/fixture/work', source_revision: '',
    old_base: '', vendor_tree: '', new_base: '', host: '', account: '', tool_paths: { claude: '', opencode: '', codex: '' },
    disabled_tools: [], models: {}, role_instructions: {}, agent_instructions: '', agents: { claude: [], opencode: [], codex: [] },
    build_argv: [], build_command: '', artifact_path: '', build_env_script: '', verification_command: '', integration_command: '',
    module_report_version: 2, orchestration: { enabled: true, timeout_seconds: 120, max_calls: 20, max_stale_replans: 2, auto_retry_limit: 0 },
    command_result_path: '.bsp-dashboard/results/{job_id}/{attempt_id}/{stage}.json',
    modules: [{ name: 'Fixture BSP', group: 'boot', target_paths: [] }], max_analysis: 3, timeout_seconds: 900,
    jira_mode: 'direct', jira_url: '', jira_project: '', jira_auth_env: 'BSP_JIRA_TOKEN', jira_api_version: '2',
    mcp_name: '', mcp_scope: 'project', mcp_argv: [], jira_issue_type: 'Task', jira_fields: {} };
}
function job(id = 'job-a', title = 'Fixture job'): Data {
  const progress = { done: 0, total: 1, percent: 0 };
  const stages = Object.fromEntries(['analysis', 'design', 'code', 'build', 'verification', 'device_test'].map(name =>
    [name, { status: name === 'analysis' ? 'FAILED' : 'PENDING', validity: 'UNVERIFIED', required_cases: ['boot'],
      attempts: [], result: null, blocked_reason: 'Fixture gate', can_retry: false }]));
  return { id, title, version: 10, plan_version: 1, confirmed_plan: null, source_revision: 'fixture-source', fingerprint: 'fixture-fingerprint',
    execution: 'demo', mode: 'linux', profile: profile(), session: { id: 'session', status: 'SIMULATED' },
    paused: false, state: 'ANALYZING', health: 'OK', boot_ready: false, updated_at: '2026-11-06T00:00:00Z',
    overall: progress, progress: Object.fromEntries(['analysis', 'implementation', 'verification', 'build', 'test'].map(n => [n, progress])),
    modules: [{ id: 'module-a', name: 'Fixture BSP', group: 'boot', stages, progress, current_stage: 'analysis', changes: [], can_demo_complete: false }],
    decisions: [], prompts: [], integration: { status: 'PENDING' }, final_review: null };
}
function summary(): Data {
  return { enabled: true, legacy_report: false, health: { status: 'OK' }, execution_version: 10,
    limits: { used_runs: 1, max_runs_per_job: 20, max_stale_replans: 2, auto_retry_limit: 0 },
    runs: [{ id: 'run-a', status: 'SUCCEEDED', base_state_version: 10, plan_version: 1,
      response: { summary: 'A proposal is available; module execution has not succeeded.' } }],
    proposals: [{ id: 'proposal-a', run_id: 'run-a', kind: 'RETRY', status: 'RECORDED', reason: 'Use supplied missing input.',
      target: { module_ids: ['module-a'], stage: 'analysis' }, data: { changed_approach: 'Use verified header.' }, evidence_refs: [] }],
    candidates: [{ id: 'candidate-a', status: 'OPEN', question: 'Choose compatibility behavior.', report_id: 'report-a',
      affected_module_ids: ['module-a'], affected_stages: ['design'], blocking: true,
      options: ['upstream', 'shim'], recommendation: 'upstream' }],
    holds: [{ id: 'hold-a', candidate_id: 'candidate-a', status: 'ACTIVE', module_ids: ['module-a'], stages: ['design'], reason: 'Choose compatibility behavior.' }] };
}

function collectionPage(rows: Data[], search = new URLSearchParams()): Data {
  const limit = Math.min(100, Math.max(1, Number(search.get('limit') || 50)));
  const before = search.get('before') ? Number(search.get('before')) : Infinity;
  const withCursors = rows.map((row, index) => ({ ...row, cursor: index + 1 }));
  const items = withCursors.filter(row => row.cursor < before).slice(-limit);
  return { items, limit, total: rows.length, next_cursor: items.length && items[0].cursor > 1 ? items[0].cursor : null };
}

function summaryMetadata(source: Data): Data {
  const result: Data = { ...source, pagination: {} };
  for (const collection of ['runs', 'proposals', 'candidates', 'holds']) {
    const page = collectionPage(source[collection]);
    result[collection] = page.items.map((row: Data) => {
      const { data, evidence_refs, history, request, transport, ...metadata } = row;
      return metadata;
    });
    result.pagination[collection] = { limit: page.limit, next_cursor: page.next_cursor, total: page.total };
  }
  return result;
}

async function fixture(page: Page, configure?: (state: Data) => void) {
  const state: Data = { jobs: [job()], config: { version: 1, profile: profile() }, summary: summary(),
    actions: [], reads: [], reports: [{ report_id: 'report-a', stage: 'analysis', sha256: 'a'.repeat(64), disposition: 'APPLIED' }],
    report: { wire_result: { summary: '<img src=x onerror="window.__unsafe=1"><script>window.__unsafe=1</script>' } } };
  configure?.(state);
  await page.route('**/api/v1/**', async route => {
    const request = route.request(), url = new URL(request.url()), api = url.pathname.replace('/api/v1', '');
    const send = (body: unknown, status = 200) => route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) });
    if (request.method() === 'GET') {
      state.reads.push(api);
      if (api === '/config') return send(state.config);
      if (api === '/jobs') return send(state.jobs.map((j: Data) => ({ id: j.id, title: j.title })));
      if (/\/events$/.test(api)) return send([]);
      const detail = api.match(/\/orchestration\/(proposals|candidates)\/([^/]+)$/);
      if (detail) {
        const stored = state.summary[detail[1]].find((row: Data) => row.id === decodeURIComponent(detail[2]));
        return stored ? send(stored) : send({ message: 'Stored fixture detail not found.' }, 404);
      }
      if (/\/reports\/[^/]+$/.test(api)) return send(state.report);
      const collection = api.match(/\/orchestration\/(runs|proposals|candidates|holds)$/);
      if (collection) {
        const rows = state.summary[collection[1]].map((row: Data) => {
          const { data, evidence_refs, history, request, transport, ...metadata } = row;
          return metadata;
        });
        return send(collectionPage(rows, url.searchParams));
      }
      if (/\/reports$/.test(api)) return send(collectionPage(state.reports, url.searchParams));
      if (/\/orchestration$/.test(api)) {
        if (state.delaySummary && api.includes('/job-a/')) await state.delaySummary;
        return send(summaryMetadata(api.includes('/job-b/') ? { ...summary(), proposals: [], candidates: [], holds: [] } : state.summary));
      }
      const selected = state.jobs.find((j: Data) => api === `/jobs/${j.id}`);
      if (selected) return send(selected);
    }
    if (request.method() === 'PUT' && api === '/config') {
      state.config = { ...request.postDataJSON(), version: state.config.version + 1 };
      return send(state.config);
    }
    if (request.method() === 'POST' && api.includes('/actions/')) {
      const body = request.postDataJSON(); state.actions.push({ api, body, headers: request.headers() });
      if (state.conflict) return send({ message: 'Execution version changed.', code: 'VERSION_CONFLICT' }, 409);
      if (api.endsWith('/apply-proposal')) {
        state.summary.proposals[0].status = 'APPLIED'; state.summary.proposals[0].result = { status: 'APPLIED', reason: 'Retry accepted.' };
        return send({ status: 'APPLIED', reason: 'Retry accepted.' });
      }
      if (api.endsWith('/reconcile-run')) return send({ status: 'UNKNOWN', process_status: 'UNKNOWN' });
      return send({ version: 10 });
    }
    return send({ message: `Unexpected fixture API request: ${request.method()} ${api}` }, 501);
  });
  await page.goto(origin);
  await expect(page.getByRole('heading', { name: 'OS 업그레이드 대시보드', exact: true })).toBeVisible();
  return state;
}
async function panel(page: Page, proposalCount = 1) {
  const region = page.getByRole('region', { name: '작업 오케스트레이션', exact: true });
  await region.locator(':scope > details > summary').click();
  await expect(region.getByText(`저장된 제안 (${proposalCount})`, { exact: true })).toBeVisible();
  return region;
}

test('T-84 proposal acceptance remains distinct from actual module success, and raw reports are escaped', async ({ page }) => {
  const state = await fixture(page);
  const region = await panel(page);
  expect(state.reads.some((read: string) => read === '/jobs/job-a/reports/report-a')).toBe(false);
  expect(state.reads.some((read: string) => /\/orchestration\/(proposals|candidates)\//.test(read))).toBe(false);
  expect(state.actions).toHaveLength(0);
  await region.getByText('저장된 제안 (1)', { exact: true }).click();
  await expect(region.getByText('제안 접수 · RECORDED', { exact: true })).toBeVisible();
  expect(state.reads.includes('/jobs/job-a/orchestration/proposals/proposal-a')).toBe(false);
  await region.getByText('제안 내용 · 근거 참조', { exact: true }).click();
  await expect(region.getByLabel('제안 내용 · 근거 참조 proposal-a', { exact: true })).toContainText('Use verified header.');
  expect(state.reads.includes('/jobs/job-a/orchestration/proposals/proposal-a')).toBe(true);
  const apply = region.getByRole('button', { name: '저장된 제안 적용 요청', exact: true });
  await expect(apply).toBeEnabled(); await apply.press('Enter');
  await expect(region.getByText('명령 적용 · APPLIED', { exact: true })).toBeVisible();
  expect(state.actions).toHaveLength(1);
  expect(state.actions[0].body).toEqual({ expected_version: 10, data: { proposal_id: 'proposal-a' } });
  expect(state.actions[0].headers['idempotency-key']).toBeTruthy();
  expect(state.jobs[0].modules[0].stages.analysis.status).toBe('FAILED');
  await expect(page.getByRole('row').filter({ has: page.getByRole('button', { name: /Fixture BSP 선행 그룹/ }) })).toContainText('실패');
  await region.getByText('모듈 보고서 (1)', { exact: true }).click();
  await region.locator('summary').filter({ hasText: /^보고서 report-a/ }).click();
  const raw = region.getByLabel('보고서 report-a 원문과 정규화 사실');
  await expect(raw).toContainText('<script>');
  expect(state.reads.some((read: string) => read === '/jobs/job-a/reports/report-a')).toBe(true);
  await expect(raw.locator('script,img')).toHaveCount(0);
  expect(await page.evaluate(() => (window as any).__unsafe)).toBeUndefined();
});

test('T-73 T-84 stale proposals stay disabled and 409 does not blindly retry a command', async ({ page }) => {
  const state = await fixture(page, s => { s.summary.runs[0].base_state_version = 9; });
  const region = await panel(page);
  await region.getByText('저장된 제안 (1)', { exact: true }).click();
  await expect(region.getByRole('button', { name: '저장된 제안 적용 요청' })).toBeDisabled();
  expect(state.actions).toHaveLength(0);
  state.summary.runs[0].base_state_version = 10;
  state.conflict = true;
  await page.reload();
  const fresh = await panel(page);
  await fresh.getByText('저장된 제안 (1)', { exact: true }).click();
  await fresh.getByRole('button', { name: '저장된 제안 적용 요청' }).click();
  await expect(fresh.getByRole('alert')).toContainText('최신 상태를 다시 조회');
  expect(state.actions).toHaveLength(1);
  expect(state.reads.filter((p: string) => p === '/jobs/job-a').length).toBeGreaterThan(1);
});

test('T-82 T-84 UNKNOWN reconciliation sends only the stored run ID; no client termination declaration', async ({ page }) => {
  const state = await fixture(page, s => { s.summary.runs[0].status = 'UNKNOWN'; s.summary.health.status = 'UNKNOWN'; });
  const region = await panel(page);
  await region.getByText('조정 호출 이력 (1)', { exact: true }).click();
  await region.getByRole('button', { name: '서버에서 실행 상태 확인', exact: true }).press('Enter');
  await expect(region.getByRole('status')).toContainText('상태 확인 필요');
  expect(state.actions[0].body.data).toEqual({ run_id: 'run-a' });
  expect(JSON.stringify(state.actions[0].body)).not.toMatch(/pid|terminated|kill/);
  await region.getByLabel('새 재계획 요청').fill('Read current evidence.');
  await expect(region.getByRole('button', { name: '재계획 요청 기록' })).toBeDisabled();
});

test('T-79 T-84 candidate classification requires a reason and preserves explicit hold state', async ({ page }) => {
  const state = await fixture(page);
  await page.getByRole('navigation').getByRole('link', { name: '사람 검토 · Jira', exact: true }).click();
  const region = page.getByRole('region', { name: '판단 후보와 범위 대기' });
  await region.getByText('판단 후보 (1)', { exact: true }).click();
  expect(state.reads.includes('/jobs/job-a/orchestration/candidates/candidate-a')).toBe(false);
  await region.getByText('판단 후보 전체 내용 · 이력', { exact: true }).click();
  await expect(region.getByLabel('판단 후보 전체 내용 · 이력 candidate-a', { exact: true })).toContainText('upstream');
  expect(state.actions).toHaveLength(0);
  await region.getByText('후보 분류 · 사유 기록', { exact: true }).click();
  await expect(region.getByRole('button', { name: '후보 분류 저장' })).toBeDisabled();
  await region.getByLabel('판단 후보 분류', { exact: true }).selectOption('ORDINARY_FAILURE');
  await region.getByLabel('분류 · 제외 사유', { exact: true }).fill('The captured failure is an ordinary missing-header error.');
  await region.getByRole('button', { name: '후보 분류 저장', exact: true }).press('Enter');
  await expect(region.getByRole('status')).toContainText('요청을 기록');
  expect(state.actions[0].body.data).toEqual({ candidate_id: 'candidate-a', classification: 'ORDINARY_FAILURE',
    reason: 'The captured failure is an ordinary missing-header error.' });
  await region.getByText('범위 대기 (1)', { exact: true }).click();
  await expect(region.getByText('대기 적용 중 · ACTIVE', { exact: true })).toBeVisible();
  expect(state.actions).toHaveLength(1);
});

test('T-83 T-84 saved orchestration settings apply to future jobs and retain existing job contract', async ({ page }) => {
  const state = await fixture(page, s => { s.jobs[0].profile.module_report_version = 1; s.jobs[0].profile.orchestration.enabled = false; });
  await page.getByRole('navigation').getByRole('link', { name: '환경 설정', exact: true }).click();
  await page.getByLabel('모듈 보고 계약', { exact: true }).selectOption('2');
  await page.getByLabel('자동 작업 조정', { exact: true }).selectOption('enabled');
  await page.getByText('조정 한도 · 명령 결과 경로', { exact: true }).click();
  await page.locator('[name="orchestration_max_calls"]').fill('7');
  await page.locator('[name="orchestration_auto_retry_limit"]').fill('1');
  await page.getByRole('button', { name: '설정 저장', exact: true }).click();
  await expect(page.getByRole('status')).toContainText('설정을 저장');
  expect(state.config.profile.orchestration.max_calls).toBe(7);
  expect(state.config.profile.orchestration.auto_retry_limit).toBe(1);
  expect(state.jobs[0].profile.module_report_version).toBe(1);
  expect(state.jobs[0].profile.orchestration.enabled).toBe(false);
  expect(state.actions).toHaveLength(0);
});

test('T-84 delayed summary for a previous job cannot populate the newly selected job', async ({ page }) => {
  let release!: () => void;
  const delayed = new Promise<void>(resolve => { release = resolve; });
  const state = await fixture(page, s => { s.jobs.push(job('job-b', 'Second fixture job')); s.delaySummary = delayed; });
  await page.getByLabel('업그레이드 작업 선택', { exact: true }).selectOption('job-b');
  const region = await panel(page, 0);
  await expect(region.getByText('저장된 제안 (0)', { exact: true })).toBeVisible();
  release();
  await expect(page.getByRole('heading', { name: 'Second fixture job', exact: true })).toBeVisible();
  await expect(region.getByText('저장된 제안 (1)', { exact: true })).toHaveCount(0);
  expect(state.actions).toHaveLength(0);
});
