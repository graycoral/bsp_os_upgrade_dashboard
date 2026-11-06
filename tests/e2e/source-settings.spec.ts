import { test, expect, type Page } from '../../apps/web/node_modules/@playwright/test';
import { createServer, type Server } from 'node:http';
import { readFileSync } from 'node:fs';
import path from 'node:path';

// Static production UI with a complete intercepted API. No remote repositories,
// runner, board, model, or user runtime is contacted by these tests.
let server: Server, origin: string;
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
const commits = ['a'.repeat(40), 'b'.repeat(40)];
const refs = [{ name: 'release/main', ref: 'refs/heads/release/main', commit: commits[0] },
  { name: 'board/feature', ref: 'refs/heads/board/feature', commit: commits[1] }];
const tc = (name: string) => ({ id: name + '.py', path: name + '.py', name, kind: 'Single', timeout: 30, content_hash: name });
async function fixture(page: Page, options: { disconnected?: boolean; registered?: boolean; live?: boolean } = {}) {
  const state: Data = { version: 1, active: { kind: options.registered ? 'server-folder' : 'legacy',
    location: options.registered ? '/srv/current' : '', ref: null, commit: null, inspection_id: null,
    snapshot_id: options.registered ? 'original-snapshot' : null, source_revision: options.registered ? 'source-original' : null } };
  const execution = { ready: !options.disconnected, code: options.disconnected ? 'RUNNER_UNAVAILABLE' : 'READY',
    reason: options.disconnected ? 'Fixture runner unavailable; catalog remains readable' : '' };
  const control = { state, catalog: { branch: 'legacy', revision: 'source-original', tests: [tc('boot'), tc('second')] },
    writes: [] as Data[], unexpected: [] as string[], inspections: new Map<string, Data>(),
    suites: [{ name: 'Old source suite', revision: 'suite-old', source_revision: 'source-original',
      tc_ids: ['boot.py'], tc_hashes: { 'boot.py': 'boot' }, tc_repeats: {}, cycles: 2 }],
    inspectGate: null as Promise<void> | null, applyGate: null as Promise<void> | null, failApply: false };
  await page.route('**/api/v1/**', async route => {
    const req = route.request(), raw = new URL(req.url()).pathname.replace('/api/v1', ''), api = raw.replace('/gui-test/live', '/gui-test');
    const send = (json: unknown, status = 200) => route.fulfill({ status, json });
    if (req.method() === 'GET') {
      if (api === '/jobs') return send([]);
      if (api === '/config') return send({ version: 1, profile: null });
      if (api === '/gui-test/source') return send({ ...state, execution });
      if (api === '/gui-test/catalog') return send(control.catalog);
      if (api === '/gui-test/capabilities') return send({ mode: 'dashboard', simulation: !options.live, hardware: false, branches: ['legacy'] });
      if (api === '/gui-test/boards') return send({ boards: [{ host: 'demo-windows', board_id: 'demo-board-a', com: 'COM3' }] });
      if (api === '/gui-test/ports') return send({ ports: [] });
      if (api === '/gui-test/saved/suite') return send(control.suites);
      if (api === '/gui-test/runs' || api === '/gui-test/demo/jobs' || /\/saved\/(profile|command)$/.test(api)) return send([]);
    }
    if (req.method() === 'POST' && api === '/gui-test/source/inspect') {
      const body = req.postDataJSON(); control.writes.push({ api: raw, body });
      const inspection = { inspection_id: `inspection-${control.inspections.size + 1}`, ...body,
        repository: body.kind === 'git-url', refs: body.kind === 'git-url' ? refs : [],
        default_ref: body.kind === 'git-url' ? refs[0].ref : null, inspected_at: '2026-11-06T00:00:00Z' };
      control.inspections.set(inspection.inspection_id, inspection);
      if (control.inspectGate) await control.inspectGate;
      try { return await send(inspection); } catch { return; } // Input changes may abort this request.
    }
    if (req.method() === 'PUT' && api === '/gui-test/source') {
      const body = req.postDataJSON(); control.writes.push({ api: raw, body });
      if (control.applyGate) await control.applyGate;
      if (control.failApply) return send({ message: 'Source version changed; inspect again', code: 'VERSION_CONFLICT' }, 409);
      const inspection = control.inspections.get(body.inspection_id)!;
      if (!inspection || body.expected_version !== state.version) return send({ message: 'Stale source', code: 'VERSION_CONFLICT' }, 409);
      state.version++;
      state.active = { kind: inspection.kind, location: inspection.location, ref: body.ref, commit: refs.find(item => item.ref === body.ref)?.commit || null,
        inspection_id: inspection.inspection_id, snapshot_id: 'next-snapshot', source_revision: 'source-next' };
      control.catalog = { branch: body.ref || 'folder', revision: 'source-next', tests: [tc('replacement')] };
      if (inspection.kind === 'legacy') {
        state.active = { kind: 'legacy', location: '', ref: null, commit: null, inspection_id: null, snapshot_id: null, source_revision: null };
        control.catalog = { branch: 'legacy', revision: 'source-original', tests: [tc('boot'), tc('second')] };
      }
      return send({ ...state, execution, catalog: control.catalog });
    }
    if (req.method() === 'POST' && api === '/gui-test/preflight') {
      control.writes.push({ api: raw, body: req.postDataJSON() }); return send({ ok: true, checks: ['Fixture only'] });
    }
    control.unexpected.push(`${req.method()} ${raw}`); return send({ message: 'Unexpected fixture request' }, 501);
  });
  await page.goto(origin + (options.live ? '/?guiExecution=live&tab=gui-test' : '/'));
  return control;
}
async function navigate(page: Page, name: string) {
  await page.getByRole('navigation').getByRole('link', { name, exact: true }).click();
}
async function sourceSettings(page: Page, global = false) {
  await navigate(page, global ? '환경 설정' : 'Test 현황');
  if (!global) {
    const settings = page.getByRole('button', { name: '연결 및 실행 설정', exact: true });
    if (await settings.getAttribute('aria-expanded') !== 'true') await settings.click();
  }
  const source = page.getByRole('button', { name: '소스 설정', exact: true });
  if (await source.getAttribute('aria-expanded') !== 'true') await source.click();
  await expect(page.getByRole('region', { name: '현재 적용된 TC 소스', exact: true })).toBeVisible();
}
async function inspect(page: Page, kind: 'git-url' | 'server-folder', location: string) {
  await page.getByRole('combobox', { name: 'TC 소스 유형', exact: true }).selectOption(kind);
  await page.getByRole('textbox', { name: 'TC 소스 위치', exact: true }).fill(location);
  await page.getByRole('button', { name: '소스 확인', exact: true }).click();
  await expect(page.getByRole('button', { name: '소스 적용', exact: true })).toBeEnabled();
}

test('T-180 source location and inspected real refs share one global/local editor', async ({ page }) => {
  const control = await fixture(page);
  await sourceSettings(page, true);
  await inspect(page, 'git-url', 'https://github.example.invalid/team/tc.git');
  const branch = page.getByRole('combobox', { name: 'TC 소스 브랜치', exact: true });
  await expect(branch.locator('option')).toHaveText(refs.map(item => item.name));
  await branch.selectOption(refs[1].ref);
  const editor = await page.getByRole('textbox', { name: 'TC 소스 위치', exact: true }).elementHandle();
  await sourceSettings(page);
  await expect(branch).toHaveValue(refs[1].ref);
  await expect(page.getByRole('textbox', { name: 'TC 소스 위치', exact: true })).toHaveValue('https://github.example.invalid/team/tc.git');
  expect(await editor!.evaluate(el => el === document.querySelector('[aria-label="TC 소스 위치"]'))).toBe(true);
  await page.getByRole('textbox', { name: 'TC 소스 위치', exact: true }).fill('https://gerrit.example.invalid/other/tc');
  await sourceSettings(page, true);
  await expect(page.getByRole('textbox', { name: 'TC 소스 위치', exact: true })).toHaveValue('https://gerrit.example.invalid/other/tc');
  await expect(branch).toHaveCount(0);
  await expect(page.getByRole('button', { name: '소스 적용', exact: true })).toBeDisabled();
  expect(control.writes.filter(write => write.api.endsWith('/source'))).toHaveLength(0);
  expect(control.unexpected).toEqual([]);
});

test('T-181 late inspection cannot overwrite edited location and failed apply preserves active catalog', async ({ page }) => {
  const control = await fixture(page, { registered: true });
  let release!: () => void;
  control.inspectGate = new Promise<void>(resolve => { release = resolve; });
  try {
    await sourceSettings(page);
    await page.getByRole('combobox', { name: 'TC 소스 유형', exact: true }).selectOption('git-url');
    await page.getByRole('textbox', { name: 'TC 소스 위치', exact: true }).fill('https://github.example.invalid/old/tc');
    await page.getByRole('button', { name: '소스 확인', exact: true }).click();
    await expect.poll(() => control.writes.length).toBe(1);
    await page.getByRole('textbox', { name: 'TC 소스 위치', exact: true }).fill('/srv/new-draft');
    release(); control.inspectGate = null;
    await expect(page.getByRole('button', { name: '소스 적용', exact: true })).toBeDisabled();
    await expect(page.getByRole('combobox', { name: 'TC 소스 브랜치', exact: true })).toHaveCount(0);
    await inspect(page, 'server-folder', '/srv/new-draft');
    control.failApply = true;
    await page.getByRole('button', { name: '소스 적용', exact: true }).click();
    await expect(page.getByRole('alert').filter({ hasText: 'Source version changed' })).toBeVisible();
    await expect(page.getByRole('region', { name: '현재 적용된 TC 소스', exact: true })).toContainText('/srv/current');
    await expect(page.getByLabel('선택 boot', { exact: true })).toBeChecked();
    expect(control.catalog.revision).toBe('source-original'); expect(control.state.version).toBe(1);
    expect(control.unexpected).toEqual([]);
  } finally { release(); }
});

test('T-182 folder apply locks input, replaces catalog, resets execution drafts and retains command draft', async ({ page }) => {
  const control = await fixture(page);
  await sourceSettings(page);
  await page.getByRole('button', { name: '설정 모두 펼치기', exact: true }).click();
  await page.getByLabel('전체 목록 반복 횟수', { exact: true }).fill('3');
  await page.getByLabel('Suite 이름', { exact: true }).fill('Old source suite draft');
  await page.getByLabel('Single 실행 명령', { exact: true }).fill('python\nkeep-draft.py\n{com_a}');
  const command = await page.getByLabel('Single 실행 명령', { exact: true }).elementHandle();
  await page.getByRole('button', { name: '← 결과로 돌아가기', exact: true }).click();
  // Editing command text makes it dirty, so first verify source-apply selection
  // resets independently of a successful Preflight.
  await sourceSettings(page);
  await inspect(page, 'server-folder', '/srv/plain tests');
  await expect(page.getByRole('combobox', { name: 'TC 소스 브랜치', exact: true })).toHaveCount(0);
  let release!: () => void;
  control.applyGate = new Promise<void>(resolve => { release = resolve; });
  try {
    await page.getByRole('button', { name: '소스 적용', exact: true }).click();
    await expect(page.getByRole('textbox', { name: 'TC 소스 위치', exact: true })).toBeDisabled();
    await expect(page.getByRole('combobox', { name: 'TC 소스 유형', exact: true })).toBeDisabled();
    release();
    await expect(page.getByRole('region', { name: '현재 적용된 TC 소스', exact: true })).toContainText('/srv/plain tests');
    await expect(page.getByLabel('선택 boot', { exact: true })).toHaveCount(0);
    await expect(page.getByLabel('선택 replacement', { exact: true })).not.toBeChecked();
    await expect(page.getByLabel('전체 목록 반복 횟수', { exact: true })).toHaveValue('1');
    await expect(page.getByLabel('Single 실행 명령', { exact: true })).toHaveValue('python\nkeep-draft.py\n{com_a}');
    expect(await command!.evaluate(el => el === document.querySelector('[aria-label="Single 실행 명령"]'))).toBe(true);
    const apply = control.writes.find(write => write.api.endsWith('/source'))!;
    expect(apply.body).toEqual({ inspection_id: expect.any(String), ref: null, expected_version: 1 });
    expect(control.unexpected).toEqual([]);
  } finally { release(); }
});

test('T-182 disconnected live source remains inspectable with catalog visible and execution blocked', async ({ page }) => {
  const control = await fixture(page, { registered: true, disconnected: true, live: true });
  await sourceSettings(page);
  await expect(page.getByLabel('선택 boot', { exact: true })).toBeVisible();
  await expect(page.getByRole('region', { name: '현재 적용된 TC 소스', exact: true })).toContainText('Fixture runner unavailable');
  await page.getByRole('button', { name: '← 결과로 돌아가기', exact: true }).click();
  await expect(page.getByRole('button', { name: 'Preflight 검사', exact: true })).toBeDisabled();
  await expect(page.getByRole('button', { name: '테스트 시작', exact: true })).toBeDisabled();
  expect(control.writes).toEqual([]); expect(control.unexpected).toEqual([]);
});

test('T-182 applying source invalidates passed Preflight and rejects the previous source Suite', async ({ page }) => {
  const control = await fixture(page);
  await sourceSettings(page);
  await page.getByRole('button', { name: '설정 모두 펼치기', exact: true }).click();
  await page.getByLabel('Suite 불러오기', { exact: true }).selectOption({ label: 'Old source suite' });
  await page.getByRole('button', { name: '← 결과로 돌아가기', exact: true }).click();
  await page.getByRole('button', { name: 'Preflight 검사', exact: true }).click();
  await expect(page.getByRole('button', { name: '테스트 시작', exact: true })).toBeEnabled();
  await sourceSettings(page, true);
  await inspect(page, 'server-folder', '/srv/new generation');
  await page.getByRole('button', { name: '소스 적용', exact: true }).click();
  await expect(page.getByLabel('선택 replacement', { exact: true })).not.toBeChecked();
  await page.getByLabel('Suite 불러오기', { exact: true }).selectOption({ label: 'Old source suite' });
  await expect(page.getByRole('alert').filter({ hasText: 'Suite 소스 또는 TC가 변경됐습니다' })).toBeVisible();
  await expect(page.getByLabel('선택 replacement', { exact: true })).not.toBeChecked();
  await page.getByLabel('선택 replacement', { exact: true }).check();
  await navigate(page, 'Test 현황');
  await expect(page.getByRole('button', { name: '테스트 시작', exact: true })).toBeDisabled();
  await page.getByRole('button', { name: 'Preflight 검사', exact: true }).click();
  await expect(page.getByRole('button', { name: '테스트 시작', exact: true })).toBeEnabled();
  const checks = control.writes.filter(write => write.api.endsWith('/preflight'));
  expect(checks).toHaveLength(2);
  expect(checks[0].body.suite_revision).toBe('suite-old');
  expect(checks[1].body).toMatchObject({ source_revision: 'source-next', suite_revision: '', tc_ids: ['replacement.py'], cycles: 1 });
  expect(control.unexpected).toEqual([]);
});

test('T-180 registered source explicitly reverts to legacy while preserving location draft', async ({ page }) => {
  const control = await fixture(page, { registered: true });
  await sourceSettings(page);
  const kind = page.getByRole('combobox', { name: 'TC 소스 유형', exact: true });
  const location = page.getByRole('textbox', { name: 'TC 소스 위치', exact: true });
  await location.fill('/srv/keep-unsaved-location');
  await kind.selectOption('legacy');
  await expect(location).toBeDisabled();
  await kind.selectOption('server-folder');
  await expect(location).toHaveValue('/srv/keep-unsaved-location');
  await kind.selectOption('legacy');
  await page.getByRole('button', { name: '소스 확인', exact: true }).click();
  await expect(page.getByRole('button', { name: '소스 적용', exact: true })).toBeEnabled();
  await page.getByRole('button', { name: '소스 적용', exact: true }).click();
  await expect(page.getByRole('region', { name: '현재 적용된 TC 소스', exact: true })).toContainText('기존 설정 · Legacy');
  await expect(page.getByLabel('TC 브랜치', { exact: true })).toBeVisible();
  await expect(page.getByLabel('선택 boot', { exact: true })).not.toBeChecked();
  expect(control.writes[0].body).toEqual({ kind: 'legacy', location: '' });
  expect(control.writes[1].body).toEqual({ inspection_id: expect.any(String), ref: null, expected_version: 1 });
  expect(control.unexpected).toEqual([]);
});
