import { test, expect, type Page } from '../../apps/web/node_modules/@playwright/test';
import { createServer, type Server } from 'node:http';
import { readFileSync } from 'node:fs';
import path from 'node:path';
import { editCommand, editConnection, expandTestDetails, selectTestSetting } from './settings-controls';

// Only static assets come from this server. All API requests are intercepted,
// including unexpected writes, so these tests cannot invoke tools or hardware.
let server: Server;
let origin: string;
test.beforeAll(async () => {
  const dist = path.resolve(process.cwd(), 'dist');
  server = createServer((req, res) => {
    const pathname = new URL(req.url || '/', 'http://fixture').pathname;
    const file = path.resolve(dist, pathname === '/' ? 'index.html' : '.' + pathname);
    if (!file.startsWith(dist + path.sep)) { res.writeHead(403).end(); return; }
    try {
      res.writeHead(200, { 'Content-Type': file.endsWith('.js') ? 'text/javascript' : file.endsWith('.css') ? 'text/css' : 'text/html' });
      res.end(readFileSync(file));
    } catch { res.writeHead(404).end(); }
  });
  await new Promise<void>(resolve => server.listen(0, '127.0.0.1', resolve));
  const address = server.address();
  if (!address || typeof address === 'string') throw Error('Static fixture server did not start');
  origin = `http://127.0.0.1:${address.port}`;
});
test.afterAll(async () => { if (server) await new Promise<void>((resolve, reject) => server.close(e => e ? reject(e) : resolve())); });

type Data = Record<string, any>;
function profile(): Data {
  return { execution: 'demo', runner: 'native', workspace: '/fixture/work', source_revision: '',
    old_base: '', vendor_tree: '', new_base: '', host: '', account: '', tool_paths: {}, disabled_tools: [], models: {},
    role_instructions: {}, agent_instructions: '', agents: { claude: [], opencode: [], codex: [] },
    build_argv: [], build_command: '', artifact_path: '', build_env_script: '', verification_command: '', integration_command: '',
    module_report_version: 1, orchestration: { enabled: false, timeout_seconds: 120, max_calls: 20, max_stale_replans: 2, auto_retry_limit: 0 },
    command_result_path: '.bsp-dashboard/results/{job_id}/{attempt_id}/{stage}.json',
    modules: [{ name: 'Fixture BSP', group: 'boot', target_paths: [] }], max_analysis: 3, timeout_seconds: 900,
    jira_mode: 'direct', jira_url: '', jira_project: '', jira_auth_env: 'BSP_JIRA_TOKEN', jira_api_version: '2',
    mcp_name: '', mcp_scope: 'project', mcp_argv: [], jira_issue_type: 'Task', jira_fields: {} };
}
async function fixture(page: Page, options: { capabilitiesReady?: Promise<void>; savedRun?: Data } = {}) {
  const state = { config: { version: 1, profile: profile() }, writes: [] as Data[], unexpected: [] as string[],
    reads: [] as string[], saved: { profile: [] as Data[], suite: [] as Data[], command: [] as Data[] } };
  await page.route('**/api/v1/**', async route => {
    const req = route.request(), url = new URL(req.url()), api = url.pathname.replace('/api/v1', '');
    const send = (json: unknown, status = 200) => route.fulfill({ status, json });
    const gui = api.replace('/gui-test/live', '/gui-test');
    if (req.method() === 'GET') {
      state.reads.push(api);
      if (api === '/config') return send(state.config);
      if (api === '/jobs') return send([]);
      if (gui === '/gui-test/source/request-settings') return send({ catalog_timeout_seconds: 100 });
      if (gui === '/gui-test/source') return send({ version: 0, active: { kind: 'legacy', location: '', ref: null, commit: null,
        inspection_id: null, snapshot_id: null, source_revision: null }, execution: { ready: true, reason: '', code: 'READY' } });
      if (gui === '/gui-test/capabilities') {
        await options.capabilitiesReady;
        return send({ mode: 'dashboard', simulation: true, hardware: false, branches: ['demo/main', 'draft/branch'] });
      }
      if (gui === '/gui-test/catalog') return send({ revision: 'source-1', branch: 'demo/main', tests: [
        { id: 'boot.py', name: 'boot', path: 'boot.py', kind: 'Single', timeout: 30, content_hash: 'a'.repeat(64) },
        { id: 'pair.py', name: 'pair', path: 'pair.py', kind: 'Dual', timeout: 30, content_hash: 'b'.repeat(64) }] });
      if (gui === '/gui-test/boards') return send({ boards: [
        { host: 'demo-windows', board_id: 'demo-board-a', com: 'COM3' }, { host: 'demo-windows', board_id: 'demo-board-b', com: 'COM4' }] });
      if (gui === '/gui-test/ports') return send({ ports: [] });
      if (gui === '/gui-test/runs') return send(options.savedRun ? [options.savedRun] : []);
      if (options.savedRun && gui === '/gui-test/runs/' + options.savedRun.id) return send(options.savedRun);
      if (options.savedRun && gui === '/gui-test/runs/' + options.savedRun.id + '/events') return send([]);
      if (gui === '/gui-test/demo/jobs') return send([]);
      const saved = gui.match(/^\/gui-test\/saved\/(profile|suite|command)$/);
      if (saved) return send(state.saved[saved[1] as keyof typeof state.saved]);
    }
    if (req.method() === 'PUT' && api === '/config') {
      const body = req.postDataJSON(); state.writes.push({ api, body });
      if (body.version !== state.config.version) return send({ message: 'Version conflict' }, 409);
      state.config = { version: state.config.version + 1, profile: body.profile }; return send(state.config);
    }
    const saved = gui.match(/^\/gui-test\/saved\/(profile|suite|command)$/);
    if (req.method() === 'PUT' && saved) {
      const body = req.postDataJSON(), value = { ...body.data, name: body.name, revision: 'saved-1' };
      state.writes.push({ api, body });
      const list = state.saved[saved[1] as keyof typeof state.saved];
      list.splice(0, list.length, ...list.filter(item => item.name !== body.name), value); return send(value);
    }
    if (req.method() === 'POST' && gui === '/gui-test/preflight') {
      state.writes.push({ api, body: req.postDataJSON() }); return send({ ok: true, simulation: true, checks: ['Fixture only'] });
    }
    if (options.savedRun && req.method() === 'POST' && gui === '/gui-test/runs/' + options.savedRun.id + '/heartbeat') return send({ ok: true });
    state.unexpected.push(`${req.method()} ${api}`);
    return send({ message: 'Unexpected fixture request; no operation performed' }, 501);
  });
  await page.goto(origin);
  await expect(page.getByRole('heading', { name: 'OS 업그레이드 대시보드', exact: true })).toBeVisible();
  return state;
}
async function navigate(page: Page, name: string) {
  await page.getByRole('navigation').getByRole('link', { name, exact: true }).click();
}
async function expand(page: Page, title: string) {
  const button = page.getByRole('button', { name: title, exact: true });
  if (await button.getAttribute('aria-expanded') === 'false') await button.click();
}
async function globalSettings(page: Page) {
  await navigate(page, '환경 설정');
  await page.getByRole('button', { name: '환경 설정 모두 펼치기', exact: true }).click();
}
async function localTestSettings(page: Page) {
  await navigate(page, 'Test 현황');
  await expand(page, '연결 및 실행 설정');
  await expand(page, 'Test 설정');
}

async function expectSettingsOnly(page: Page) {
  const settings = page.locator('#gui-test-settings');
  await expect(settings.getByRole('button', { name: 'Test 설정', exact: true })).toBeVisible();
  // The retained workspace remains mounted, but none of its TC operations or
  // execution surfaces belong in Environment settings, even with every fold open.
  for (const selector of ['.gt-intro', '.gt-demo', '.gt-workspace-toolbar', '#gt-catalog-panel',
    '#gt-results-view', '.gt-order-preview', '.gt-controls', '.gt-run-progress']) {
    await expect(settings.locator(selector)).toBeHidden();
  }
  await expect(settings.getByRole('heading', { name: 'Test cases', exact: true })).toBeHidden();
  await expect(settings.getByLabel('TC 검색', { exact: true })).toBeHidden();
  await expect(settings.getByLabel('선택 boot', { exact: true })).toBeHidden();
  await expect(settings.getByLabel('선택 pair', { exact: true })).toBeHidden();
  await expect(settings.getByRole('separator', { name: 'TC 검색 패널 너비' })).toBeHidden();
  await expect(settings.getByLabel('Run 이력', { exact: true })).toBeHidden();
  await expect(settings.getByRole('button', { name: 'Preflight 검사', exact: true })).toBeHidden();
  await expect(settings.getByRole('button', { name: '테스트 시작', exact: true })).toBeHidden();
  await expect(settings.getByLabel('TC 판정 진행률', { exact: true })).toBeHidden();
  await expect(settings.getByLabel('결과 상세', { exact: true })).toBeHidden();
}

async function expectSettingsWidth(page: Page) {
  const layout = page.locator('#gui-test-settings .gt-layout');
  const main = page.locator('#gui-test-settings .gt-main');
  const layoutBox = await layout.boundingBox(), mainBox = await main.boundingBox();
  expect(layoutBox).not.toBeNull(); expect(mainBox).not.toBeNull();
  expect(Math.abs(mainBox!.x - layoutBox!.x)).toBeLessThanOrEqual(1);
  expect(Math.abs(mainBox!.width - layoutBox!.width)).toBeLessThanOrEqual(1);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
}

test('T-169 BSP global and contextual settings retain the same drafts, including invalid JSON', async ({ page }) => {
  const state = await fixture(page);
  await globalSettings(page);
  await expectSettingsOnly(page);
  await page.getByLabel('Linux 호스트', { exact: true }).fill('draft.internal');
  await page.getByLabel('도구 연결 방식', { exact: true }).selectOption('bridge');
  const invalid = '["unfinished"';
  // The inline validation description is inside the label, so invalid input
  // adds text to its accessible name. Keep identifying the same field by name.
  await page.getByRole('textbox', { name: /^claude 실행 배열/ }).fill(invalid);
  await navigate(page, '대시보드');
  await expand(page, '대시보드 관련 설정');
  await expect(page.getByLabel('Linux 호스트', { exact: true })).toHaveValue('draft.internal');
  await expect(page.getByRole('textbox', { name: /^claude 실행 배열/ })).toHaveValue(invalid);
  await page.getByLabel('Linux 호스트', { exact: true }).fill('local.internal');
  await navigate(page, '사람 검토 · Jira');
  await expand(page, 'Jira 관련 설정');
  // The local Jira surface excludes unrelated BSP sections.
  await expect(page.getByLabel('Linux 호스트', { exact: true })).toBeHidden();
  await globalSettings(page);
  await expect(page.getByLabel('Linux 호스트', { exact: true })).toHaveValue('local.internal');
  await expect(page.getByRole('textbox', { name: /^claude 실행 배열/ })).toHaveValue(invalid);
  expect(state.writes).toEqual([]); expect(state.unexpected).toEqual([]);
});

test('T-170 global settings hides an existing Run and preserves its selected report on return', async ({ page }) => {
  // A recorded result exercises hidden progress, controls and report state;
  // no run is created and no tool or hardware can be invoked by this fixture.
  const savedRun = { id: 'retained-run', version: 1, state: 'COMPLETED', overall_result: 'PASS',
    controller: 'other-session', simulation: true, source_revision: 'source-1', tests: [], attempts: [], results: {},
    progress: { percent: 100, done: 2, total: 2, counts: { PASS: 2 } },
    sync: { status: 'SYNCED', reason: 'Retained report evidence' }, connection_snapshot: {},
    started_at: '2026-11-06T00:00:00Z', ended_at: '2026-11-06T00:01:00Z' };
  const state = await fixture(page, { savedRun });
  await navigate(page, 'Test 현황');
  await page.getByLabel('Run 이력', { exact: true }).selectOption(savedRun.id);
  await expect(page.getByLabel('TC 판정 진행률', { exact: true })).toBeVisible();
  await page.getByRole('tab', { name: '결과 리포트', exact: true }).click();
  await expect(page.getByText('Retained report evidence', { exact: true })).toBeVisible();
  await globalSettings(page);
  await expectSettingsOnly(page);
  await expect(page.getByRole('button', { name: '일시 정지', exact: true })).toBeHidden();
  await expect(page.getByRole('button', { name: '테스트 중단', exact: true })).toBeHidden();
  await expect(page.getByRole('tab', { name: '결과 리포트', exact: true })).toBeHidden();
  await navigate(page, 'Test 현황');
  await expect(page.getByLabel('Run 이력', { exact: true })).toHaveValue(savedRun.id);
  await expect(page.getByRole('tab', { name: '결과 리포트', exact: true })).toHaveAttribute('aria-selected', 'true');
  await expect(page.getByText('Retained report evidence', { exact: true })).toBeVisible();
  await expect(page.getByLabel('TC 판정 진행률', { exact: true })).toHaveAttribute('value', '2');
  expect(state.writes).toEqual([]); expect(state.unexpected).toEqual([]);
});

test('T-170 GUI nested editors and TC repeats survive global/local navigation in both directions', async ({ page }) => {
  const state = await fixture(page);
  await localTestSettings(page);
  await page.getByText('현재 실행 순서 확인', { exact: true }).click();
  await page.getByRole('button', { name: 'pair 위로 이동', exact: true }).click();
  await expect.poll(() => page.locator('[aria-label="TC 실행 순서"] > li').evaluateAll(rows => rows.map(row => row.getAttribute('data-order-id')))).toEqual(['pair.py', 'boot.py']);
  await globalSettings(page);
  await expectSettingsOnly(page);
  await localTestSettings(page);
  // Reordering and the open preview are retained in the original CaseTree.
  await expect(page.getByRole('button', { name: 'boot 위로 이동', exact: true })).toBeVisible();
  await expect.poll(() => page.locator('[aria-label="TC 실행 순서"] > li').evaluateAll(rows => rows.map(row => row.getAttribute('data-order-id')))).toEqual(['pair.py', 'boot.py']);
  await editCommand(page);
  await page.getByLabel('실행 명령 이름', { exact: true }).fill('Unsaved command');
  await page.getByLabel('Single 실행 명령', { exact: true }).fill('python\nunsaved.py\n{com_a}');
  await editConnection(page);
  await page.getByLabel('프로파일 이름', { exact: true }).fill('Unsaved connection');
  await selectTestSetting(page, 'suite');
  await page.getByLabel('Suite 이름', { exact: true }).fill('Unsaved suite');
  await selectTestSetting(page, 'basic');
  await page.getByLabel('전체 목록 반복 횟수', { exact: true }).selectOption('3');
  await page.getByRole('checkbox', { name: '수동 보드 / COM 입력', exact: true }).check();
  await page.getByLabel('Board A com', { exact: true }).fill('COM19');
  await page.getByLabel('선택 pair', { exact: true }).uncheck();
  await page.getByRole('button', { name: 'boot 실행 횟수 설정', exact: true }).click();
  await page.getByLabel('boot 실행 횟수', { exact: true }).fill('4');
  // Identity checks catch an editor remount even if a subset of draft values
  // happened to be copied into a second form.
  const commandNode = await page.getByLabel('Single 실행 명령', { exact: true }).elementHandle();
  await globalSettings(page);
  await editCommand(page);
  await expect(page.getByLabel('실행 명령 이름', { exact: true })).toHaveValue('Unsaved command');
  await editConnection(page);
  await expect(page.getByLabel('프로파일 이름', { exact: true })).toHaveValue('Unsaved connection');
  await expect(page.getByLabel('Board A com', { exact: true })).toHaveValue('COM19');
  await selectTestSetting(page, 'suite');
  await expect(page.getByLabel('Suite 이름', { exact: true })).toHaveValue('Unsaved suite');
  await expectSettingsOnly(page);
  await expect(page.getByLabel('boot 실행 횟수', { exact: true })).toBeHidden();
  expect(await commandNode!.evaluate(el => el === document.querySelector('[aria-label="Single 실행 명령"]'))).toBe(true);
  await editCommand(page);
  await page.getByLabel('Single 실행 명령', { exact: true }).fill('python\nglobal-draft.py');
  await selectTestSetting(page, 'basic');
  await page.getByLabel('전체 목록 반복 횟수', { exact: true }).selectOption('5');
  await navigate(page, '실행 기록');
  await localTestSettings(page);
  await editCommand(page);
  await expect(page.getByLabel('Single 실행 명령', { exact: true })).toHaveValue('python\nglobal-draft.py');
  await selectTestSetting(page, 'basic');
  await expect(page.getByLabel('전체 목록 반복 횟수', { exact: true })).toHaveValue('5');
  await expect(page.getByLabel('선택 pair', { exact: true })).not.toBeChecked();
  await expect(page.getByLabel('boot 실행 횟수', { exact: true })).toHaveValue('4');
  expect(await commandNode!.evaluate(el => el === document.querySelector('[aria-label="Single 실행 명령"]'))).toBe(true);
  expect(state.writes).toEqual([]); expect(state.unexpected).toEqual([]);
});

test('T-171 pending view mode is shared, stays unapplied through navigation, and applies with reload', async ({ page }) => {
  const state = await fixture(page);
  await globalSettings(page);
  await selectTestSetting(page, 'view');
  await page.getByRole('combobox', { name: 'Test 현황 보기 모드', exact: true }).selectOption('live');
  expect(new URL(page.url()).searchParams.get('guiExecution')).not.toBe('live');
  await localTestSettings(page);
  await selectTestSetting(page, 'view');
  await expect(page.getByRole('combobox', { name: 'Test 현황 보기 모드', exact: true })).toHaveValue('live');
  await expect(page.getByRole('button', { name: '보기 모드 적용', exact: true })).toBeEnabled();
  await page.getByRole('combobox', { name: 'Test 현황 보기 모드', exact: true }).selectOption('default');
  await globalSettings(page);
  await selectTestSetting(page, 'view');
  await expect(page.getByRole('button', { name: '보기 모드 적용', exact: true })).toBeDisabled();
  await page.getByRole('combobox', { name: 'Test 현황 보기 모드', exact: true }).selectOption('live');
  await page.getByRole('button', { name: '보기 모드 적용', exact: true }).click();
  await expect(page).toHaveURL(/guiExecution=live/);
  await selectTestSetting(page, 'view');
  await expect(page.getByRole('combobox', { name: 'Test 현황 보기 모드', exact: true })).toHaveValue('live');
  expect(await page.evaluate(() => localStorage.getItem('gui-execution-view'))).toBe('live');
  expect(state.writes).toEqual([]); expect(state.unexpected).toEqual([]);
});

test('T-172 one compact Test section uses the same category editor and safe defaults in both tabs', async ({ page }, testInfo) => {
  const state = await fixture(page);
  await globalSettings(page);
  await page.setViewportSize({ width: 1360, height: 900 });
  const category = page.getByRole('combobox', { name: 'Test 설정 항목', exact: true });
  const panel = page.locator('#gt-settings-view [data-settings-section="test"]');
  await expect(category).toHaveValue('basic');
  await expect(category.locator('option')).toHaveText(['기본 연결·실행', 'TC 소스', '실행 명령', 'Suite', '보기 모드']);
  await expect(page.locator('#gt-settings-view .gt-settings-toggle:visible')).toHaveCount(1);
  await expect(page.getByLabel('전체 목록 반복 횟수', { exact: true })).toHaveValue('1');
  await expect(page.getByLabel('Board A', { exact: true })).toHaveValue('demo-board-a');
  await expect(page.getByLabel('프로파일 이름', { exact: true })).toBeHidden();
  await expect(page.getByLabel('Single 실행 명령', { exact: true })).toBeHidden();
  const basicNode = await category.elementHandle();
  expect((await panel.boundingBox())!.height).toBeLessThan(640);
  await panel.screenshot({ path: testInfo.outputPath('global-compact-basic.png') });
  await selectTestSetting(page, 'source');
  await expect(page.getByLabel('TC 소스 유형', { exact: true })).toHaveValue('legacy');
  await expect(page.getByLabel('TC 소스 위치', { exact: true })).toBeDisabled();
  await expect(page.getByRole('button', { name: '소스 적용', exact: true })).toBeDisabled();
  await expandTestDetails(page, '조회 고급 설정');
  await expect(page.getByLabel('TC 목록 조회 제한 시간 선택', { exact: true })).toHaveValue('100');
  await expect(page.getByLabel('TC 목록 조회 제한 시간(초)', { exact: true })).toBeHidden();
  await selectTestSetting(page, 'basic');
  await page.getByLabel('전체 목록 반복 횟수', { exact: true }).selectOption('37');
  await localTestSettings(page);
  await expect(category).toHaveValue('basic');
  await expect(page.getByLabel('전체 목록 반복 횟수', { exact: true })).toHaveValue('37');
  expect(await basicNode!.evaluate(el => el === document.querySelector('[aria-label="Test 설정 항목"]'))).toBe(true);
  await panel.screenshot({ path: testInfo.outputPath('local-compact-basic.png') });
  // Hidden category fields stay out of keyboard navigation while retaining DOM identity.
  await category.focus();
  for (let i = 0; i < 8; i++) {
    await page.keyboard.press('Tab');
    expect(await page.evaluate(() => {
      const node = document.activeElement as HTMLElement;
      return node.getClientRects().length > 0 && !node.closest('[hidden]');
    })).toBe(true);
  }
  await page.setViewportSize({ width: 375, height: 900 });
  await panel.screenshot({ path: testInfo.outputPath('local-compact-mobile.png') });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await globalSettings(page);
  await expectSettingsOnly(page); await expectSettingsWidth(page);
  await expect(page.getByLabel('전체 목록 반복 횟수', { exact: true })).toHaveValue('37');
  await panel.screenshot({ path: testInfo.outputPath('global-compact-mobile.png') });
  expect(state.writes).toEqual([]); expect(state.unexpected).toEqual([]);
});

test('T-172 folds support keyboard, retain drafts, persist on reload, and fit narrow screens', async ({ page }) => {
  await fixture(page); await globalSettings(page);
  await page.setViewportSize({ width: 1440, height: 1000 });
  await expectSettingsOnly(page);
  await expectSettingsWidth(page);
  // Configuration editors remain available and editable without the TC workspace.
  await selectTestSetting(page, 'view');
  await expect(page.getByRole('combobox', { name: 'Test 현황 보기 모드', exact: true })).toBeEnabled();
  await selectTestSetting(page, 'source');
  await page.getByLabel('TC 소스 유형', { exact: true }).selectOption('server-folder');
  await page.getByLabel('TC 소스 위치', { exact: true }).fill('/srv/settings-only-draft');
  await editConnection(page);
  await page.getByLabel('프로파일 이름', { exact: true }).fill('Settings-only connection');
  await editCommand(page);
  await page.getByLabel('Single 실행 명령', { exact: true }).fill('python\nsettings-only.py');
  await selectTestSetting(page, 'basic');
  await page.getByLabel('전체 목록 반복 횟수', { exact: true }).selectOption('7');
  await selectTestSetting(page, 'suite');
  await page.getByLabel('Suite 이름', { exact: true }).fill('Settings-only suite');
  const section = page.getByRole('button', { name: '실행 환경', exact: true });
  await section.focus(); await section.press('Enter');
  await expect(section).toHaveAttribute('aria-expanded', 'false');
  await expect(page.getByLabel('Linux 호스트', { exact: true })).toBeHidden();
  await section.press('Space'); await expect(section).toHaveAttribute('aria-expanded', 'true');
  await page.getByRole('button', { name: '환경 설정 모두 접기', exact: true }).click();
  await expect(section).toHaveAttribute('aria-expanded', 'false');
  await expect(page.getByRole('button', { name: 'Test 설정', exact: true })).toHaveAttribute('aria-expanded', 'false');
  await page.reload(); await navigate(page, '환경 설정');
  await expect(section).toHaveAttribute('aria-expanded', 'false');
  await page.getByRole('button', { name: '환경 설정 모두 펼치기', exact: true }).click();
  await expect(section).toHaveAttribute('aria-expanded', 'true');
  await expect(page.getByRole('button', { name: 'Test 설정', exact: true })).toHaveAttribute('aria-expanded', 'true');
  await page.setViewportSize({ width: 375, height: 900 });
  await expect(page.getByRole('button', { name: '설정 저장', exact: true })).toBeVisible();
  await expectSettingsOnly(page);
  await expectSettingsWidth(page);
});

test('T-173 saving reveals and focuses invalid fields hidden by folding or local scope', async ({ page }) => {
  const state = await fixture(page), errors: string[] = [];
  page.on('console', msg => { if (msg.type() === 'error') errors.push(msg.text()); });
  page.on('pageerror', error => errors.push(error.message));
  await globalSettings(page);
  await page.getByLabel('도구 연결 방식', { exact: true }).selectOption('bridge');
  const invalid = page.getByRole('textbox', { name: /^claude 실행 배열/ });
  await invalid.fill('[broken JSON');
  await page.getByRole('button', { name: '환경 설정 모두 접기', exact: true }).click();
  await navigate(page, '사람 검토 · Jira'); await expand(page, 'Jira 관련 설정');
  await page.getByRole('button', { name: '설정 저장', exact: true }).click();
  await expect(invalid).toBeVisible(); await expect(invalid).toBeFocused();
  await expect(invalid).toHaveValue('[broken JSON');
  await expect(page.getByRole('navigation').getByRole('link', { name: '환경 설정', exact: true })).toHaveAttribute('aria-current', 'page');
  await invalid.fill('[]');
  await expand(page, '구조화 보고 · 작업 오케스트레이션');
  const limits = page.getByText('조정 한도 · 명령 결과 경로', { exact: true });
  await limits.click();
  const numeric = page.locator('[name="orchestration_max_calls"]');
  await numeric.fill('0'); await limits.click();
  await page.getByRole('button', { name: '환경 설정 모두 접기', exact: true }).click();
  await page.getByRole('button', { name: '저장 후 환경 점검', exact: true }).click();
  await expect(numeric).toBeVisible(); await expect(numeric).toBeFocused();
  expect(state.writes).toEqual([]); expect(state.unexpected).toEqual([]);
  expect(errors.filter(error => /not focusable|invalid form control/i.test(error))).toEqual([]);
});

test('T-173 background settings error reveals its category and advanced retry without a write', async ({ page }) => {
  const state = await fixture(page);
  let fail = true;
  await page.route('**/api/v1/gui-test/source/request-settings', async route => {
    if (!fail) return route.fallback();
    return route.fulfill({ status: 503, json: { message: 'Fixture request settings unavailable' } });
  });
  await globalSettings(page);
  await expect(page.getByRole('combobox', { name: 'Test 설정 항목', exact: true })).toHaveValue('source');
  await expect(page.getByRole('alert').filter({ hasText: 'Fixture request settings unavailable' })).toBeVisible();
  const retry = page.getByRole('button', { name: '조회 설정 다시 확인', exact: true });
  await expect(retry).toBeVisible();
  fail = false; await retry.click();
  await expect(page.getByRole('alert').filter({ hasText: 'Fixture request settings unavailable' })).toHaveCount(0);
  await expect(page.getByLabel('TC 목록 조회 제한 시간 선택', { exact: true })).toHaveValue('100');
  expect(state.writes).toEqual([]); expect(state.unexpected).toEqual([]);
});

test('T-174 saves from either BSP surface persist and GUI edits invalidate Preflight without global save', async ({ page }) => {
  const state = await fixture(page);
  await globalSettings(page);
  await page.getByLabel('Linux 호스트', { exact: true }).fill('global-saved.internal');
  await page.getByRole('button', { name: '설정 저장', exact: true }).click();
  await expect.poll(() => state.config.profile.host).toBe('global-saved.internal');
  await navigate(page, '대시보드'); await expand(page, '대시보드 관련 설정');
  await expect(page.getByLabel('Linux 호스트', { exact: true })).toHaveValue('global-saved.internal');
  await page.getByLabel('Linux 호스트', { exact: true }).fill('local-saved.internal');
  await page.getByRole('button', { name: '설정 저장', exact: true }).click();
  await expect.poll(() => state.config.profile.host).toBe('local-saved.internal');
  await page.reload(); await globalSettings(page);
  await expect(page.getByLabel('Linux 호스트', { exact: true })).toHaveValue('local-saved.internal');
  await navigate(page, 'Test 현황');
  await page.getByRole('button', { name: 'Preflight 검사', exact: true }).click();
  await expect(page.getByRole('button', { name: '테스트 시작', exact: true })).toBeEnabled();
  await globalSettings(page);
  await selectTestSetting(page, 'basic');
  await page.getByLabel('전체 목록 반복 횟수', { exact: true }).selectOption('2');
  await navigate(page, 'Test 현황');
  await expect(page.getByRole('button', { name: '테스트 시작', exact: true })).toBeDisabled();
  expect(state.writes.filter(write => write.api === '/config')).toHaveLength(2);
  expect(state.writes.filter(write => /preflight$/.test(write.api))).toHaveLength(1);
  expect(state.unexpected).toEqual([]);
});

test('T-175 named GUI saves stay separate from BSP save and reload through the other settings surface', async ({ page }) => {
  const state = await fixture(page);
  await globalSettings(page);
  await editCommand(page);
  await page.getByLabel('실행 명령 이름', { exact: true }).fill('Shared command');
  await page.getByLabel('Single 실행 명령', { exact: true }).fill('python\nshared.py\n{com_a}');
  await editConnection(page);
  await page.getByLabel('프로파일 이름', { exact: true }).fill('Shared connection');
  // BSP save must not silently save any GUI editor.
  await page.getByRole('button', { name: '설정 저장', exact: true }).click();
  await expect.poll(() => state.writes.length).toBe(1);
  expect(state.saved.command).toEqual([]); expect(state.saved.profile).toEqual([]);
  await selectTestSetting(page, 'command');
  await page.getByRole('button', { name: '명령 저장 / 수정', exact: true }).click();
  await expect(page.getByLabel('저장된 실행 명령', { exact: true })).toHaveValue('Shared command');
  await editConnection(page);
  await page.getByRole('button', { name: '프로파일 저장', exact: true }).click();
  await expect.poll(() => state.saved.profile.length).toBe(1);
  await page.reload(); await localTestSettings(page);
  await editCommand(page);
  await expect(page.getByLabel('저장된 실행 명령', { exact: true })).toHaveValue('Shared command');
  await expect(page.getByLabel('Single 실행 명령', { exact: true })).toHaveValue('python\nshared.py\n{com_a}');
  await editConnection(page);
  const connections = page.getByLabel('연결 프로파일 불러오기', { exact: true });
  await expect(connections.getByRole('option', { name: 'Shared connection', exact: true })).toHaveCount(1);
  await connections.selectOption({ label: 'Shared connection' });
  await editCommand(page);
  await page.getByLabel('실행 명령 이름', { exact: true }).fill('Saved locally');
  await page.getByRole('button', { name: '명령 저장 / 수정', exact: true }).click();
  await expect(page.getByLabel('저장된 실행 명령', { exact: true })).toHaveValue('Saved locally');
  await page.reload(); await globalSettings(page);
  await selectTestSetting(page, 'command');
  await expect(page.getByLabel('저장된 실행 명령', { exact: true })).toHaveValue('Saved locally');
  expect(state.writes.filter(write => write.api === '/config')).toHaveLength(1);
  expect(state.writes.filter(write => /saved\/command$/.test(write.api))).toHaveLength(2);
  expect(state.unexpected).toEqual([]);
});

test('T-170 delayed GUI initialization completes across hidden navigation and polls only while active', async ({ page }) => {
  await page.clock.install();
  let capabilityResponses = 0;
  page.on('response', response => {
    if (new URL(response.url()).pathname === '/api/v1/gui-test/capabilities' && response.status() === 200) capabilityResponses++;
  });
  let release!: () => void;
  const capabilitiesReady = new Promise<void>(resolve => { release = resolve; });
  const state = await fixture(page, { capabilitiesReady });
  try {
    await globalSettings(page);
    await expect.poll(() => state.reads.filter(api => api === '/gui-test/capabilities').length).toBe(1);
    await navigate(page, '실행 기록');
    release();
    // Navigate while initialization is pending. Aborting the inactive read and
    // retrying it on return is legitimate; only one successful initialization
    // may load the catalog and update the retained instance.
    await localTestSettings(page);
    await expect(page.getByLabel('선택 boot', { exact: true })).toBeChecked();
    await selectTestSetting(page, 'command');
    await expect(page.getByRole('button', { name: '명령 저장 / 수정', exact: true })).toBeEnabled();
    await editConnection(page);
    await page.getByLabel('프로파일 이름', { exact: true }).fill('Delayed retained draft');
    await navigate(page, '실행 기록');
    const hiddenReads = state.reads.filter(api => api.startsWith('/gui-test/')).length;
    await page.clock.runFor(2100);
    expect(state.reads.filter(api => api.startsWith('/gui-test/'))).toHaveLength(hiddenReads);
    await globalSettings(page);
    await editConnection(page);
    await expect(page.getByLabel('프로파일 이름', { exact: true })).toHaveValue('Delayed retained draft');
    const activeReads = state.reads.filter(api => api === '/gui-test/runs').length;
    await page.clock.runFor(1400);
    await expect.poll(() => state.reads.filter(api => api === '/gui-test/runs').length).toBeGreaterThan(activeReads);
    expect(capabilityResponses).toBe(1);
    expect(state.reads.filter(api => api === '/gui-test/catalog')).toHaveLength(1);
    expect(state.unexpected).toEqual([]);
  } finally { release(); }
});

test('T-172 folding remains usable when preference storage fails and shared editors have unique IDs', async ({ page }) => {
  await page.addInitScript(() => {
    const read = Storage.prototype.getItem, write = Storage.prototype.setItem;
    Storage.prototype.getItem = function (key: string) {
      if (key.startsWith('gui-settings-panel:')) throw new DOMException('Preference reads blocked', 'SecurityError');
      return read.call(this, key);
    };
    Storage.prototype.setItem = function (key: string, value: string) {
      if (key.startsWith('gui-settings-panel:')) throw new DOMException('Preference writes blocked', 'QuotaExceededError');
      return write.call(this, key, value);
    };
  });
  const errors: string[] = [];
  page.on('pageerror', error => errors.push(error.message));
  const state = await fixture(page); await globalSettings(page);
  await editConnection(page);
  await page.getByLabel('프로파일 이름', { exact: true }).fill('Storage-independent draft');
  const duplicateIds = () => page.evaluate(() => {
    const ids = Array.from(document.querySelectorAll('[id]'), el => el.id);
    return ids.filter((id, index) => ids.indexOf(id) !== index);
  });
  expect(await duplicateIds()).toEqual([]);
  await page.getByRole('button', { name: '환경 설정 모두 접기', exact: true }).click();
  const panel = page.getByRole('button', { name: 'Test 설정', exact: true });
  await expect(panel).toHaveAttribute('aria-expanded', 'false');
  await panel.focus(); await panel.press('Space');
  await expect(panel).toHaveAttribute('aria-expanded', 'true');
  await localTestSettings(page);
  await editConnection(page);
  await expect(page.getByLabel('프로파일 이름', { exact: true })).toHaveValue('Storage-independent draft');
  expect(await duplicateIds()).toEqual([]);
  expect(errors).toEqual([]); expect(state.unexpected).toEqual([]);
});
