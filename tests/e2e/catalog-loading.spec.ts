import { test, expect, type Page } from '../../apps/web/node_modules/@playwright/test';
import { createServer, type Server } from 'node:http';
import { readFileSync } from 'node:fs';
import path from 'node:path';

// T-193: deterministic deferred HTTP fixtures; no live runner or board traffic.
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
  if (!address || typeof address === 'string') throw Error('Fixture server failed');
  origin = `http://127.0.0.1:${address.port}`;
});
test.afterAll(async () => { if (server) await new Promise<void>(resolve => server.close(() => resolve())); });

function deferred() {
  let resolve!: () => void;
  const promise = new Promise<void>(done => { resolve = done; });
  return { promise, resolve };
}
const catalog = (name = 'boot') => ({ branch: 'demo/main', revision: 'source-' + name, tests: [
  { id: name + '.py', path: name + '.py', name, kind: 'Single', timeout: 30, content_hash: name },
] });
async function fixture(page: Page, initialPending = false) {
  const control = { seconds: 100, writes: [] as number[], requests: 0, unexpected: [] as string[],
    pending: initialPending ? deferred() : null, fail: false, catalog: catalog() };
  await page.route('**/api/v1/**', async route => {
    const req = route.request();
    const api = new URL(req.url()).pathname.replace('/api/v1', '').replace('/gui-test/live', '/gui-test');
    const send = (json: unknown, status = 200) => route.fulfill({ status, json });
    if (api === '/gui-test/source/request-settings') {
      if (req.method() === 'PUT') {
        const value = req.postDataJSON().catalog_timeout_seconds;
        if (!Number.isInteger(value) || value < 1 || value > 600) return send({ message: 'Invalid timeout' }, 422);
        control.writes.push(value); control.seconds = value;
      }
      return send({ catalog_timeout_seconds: control.seconds });
    }
    if (req.method() === 'GET') {
      if (api === '/jobs') return send([]);
      if (api === '/config') return send({ version: 1, profile: null });
      if (api === '/gui-test/source') return send({ version: 0,
        active: { kind: 'legacy', location: '', ref: null, commit: null, inspection_id: null, snapshot_id: null, source_revision: null },
        execution: { ready: true, code: 'READY', reason: '' } });
      if (api === '/gui-test/capabilities') return send({ mode: 'dashboard', simulation: true, hardware: false, branches: ['demo/main'] });
      if (api === '/gui-test/boards') return send({ boards: [{ host: 'fixture', board_id: 'board-a', com: 'COM3' }] });
      if (api === '/gui-test/ports') return send({ ports: [] });
      if (api === '/gui-test/catalog') {
        control.requests++;
        const gate = control.pending, snapshot = control.catalog, fail = control.fail;
        if (gate) await gate.promise;
        try { return await send(fail ? { message: 'Catalog fixture timed out', code: 'TC_CATALOG_TIMEOUT' } : snapshot, fail ? 504 : 200); }
        catch { return; } // Deactivation intentionally aborts deferred requests.
      }
      if (api === '/gui-test/runs' || api === '/gui-test/demo/jobs' || /\/saved\/(suite|profile|command)$/.test(api)) return send([]);
    }
    control.unexpected.push(`${req.method()} ${api}`);
    return send({ message: 'Unexpected fixture request' }, 501);
  });
  await page.goto(origin);
  await navigate(page, 'Test 현황');
  return control;
}
async function navigate(page: Page, name: string) {
  await page.getByRole('navigation').getByRole('link', { name, exact: true }).click();
}
async function settings(page: Page, global = false) {
  await navigate(page, global ? '환경 설정' : 'Test 현황');
  if (!global) {
    const button = page.getByRole('button', { name: '연결 및 실행 설정', exact: true });
    if (await button.getAttribute('aria-expanded') !== 'true') await button.click();
  }
  const source = page.getByRole('button', { name: '소스 설정', exact: true });
  if (await source.getAttribute('aria-expanded') !== 'true') await source.click();
}

test('T-193 initial loading animates until settled and preserves initial auto-selection', async ({ page }, testInfo) => {
  const state = await fixture(page, true);
  try {
    const loading = page.getByRole('status').filter({ hasText: 'TC 목록을 읽는 중…' });
    await expect(loading).toBeVisible();
    await expect(loading).toHaveAttribute('aria-busy', 'true');
    const spinner = loading.locator('.gt-catalog-spinner');
    expect(await spinner.evaluate(el => getComputedStyle(el).animationName)).not.toBe('none');
    await page.screenshot({ path: testInfo.outputPath('catalog-loading.png'), fullPage: true });
    await page.emulateMedia({ reducedMotion: 'reduce' });
    await expect.poll(() => spinner.evaluate(el => getComputedStyle(el).animationName)).toBe('none');
    await expect(loading).toBeVisible();
    await settings(page);
    await expect(page.getByLabel('TC 목록 조회 제한 시간(초)', { exact: true })).toBeEditable();
    state.pending!.resolve(); state.pending = null;
    await expect(loading).toHaveCount(0);
    await expect(page.getByLabel('선택 boot', { exact: true })).toBeChecked();
    expect(state.requests).toBe(1);
    expect(state.unexpected).toEqual([]);
  } finally { state.pending?.resolve(); }
});

test('T-193 timeout draft survives global/local views and saves only explicitly across reload', async ({ page }) => {
  const state = await fixture(page);
  await settings(page);
  const input = page.getByLabel('TC 목록 조회 제한 시간(초)', { exact: true });
  const save = page.getByRole('button', { name: '조회 제한 시간 저장', exact: true });
  await expect(input).toHaveValue('100');
  await input.fill('173');
  await settings(page, true);
  await expect(input).toHaveValue('173');
  await settings(page);
  await expect(input).toHaveValue('173');
  expect(state.writes).toEqual([]);
  for (const value of ['0', '601', '1.5', '']) {
    await input.fill(value);
    await save.click();
    expect(state.writes).toEqual([]);
  }
  await input.fill('173'); await save.click();
  await expect.poll(() => state.writes).toEqual([173]);
  await page.reload(); await settings(page);
  await expect(input).toHaveValue('173');
  expect(state.unexpected).toEqual([]);
});

test('T-193 failed manual refresh retains TC choice and releases loading for retry', async ({ page }) => {
  const state = await fixture(page);
  await expect(page.getByLabel('선택 boot', { exact: true })).toBeChecked();
  await page.getByLabel('선택 boot', { exact: true }).uncheck();
  await settings(page);
  state.pending = deferred(); state.fail = true;
  try {
    const refresh = page.getByRole('button', { name: /TC 갱신/ });
    await refresh.click();
    await expect(page.getByText('TC 목록을 읽는 중…', { exact: true })).toBeVisible();
    await expect(refresh).toBeDisabled();
    await expect.poll(() => state.requests).toBe(2);
    state.pending.resolve(); state.pending = null;
    await expect(page.getByText('TC 목록을 읽는 중…', { exact: true })).toHaveCount(0);
    await expect(page.getByText('Catalog fixture timed out', { exact: false })).toBeVisible();
    await expect(page.getByLabel('선택 boot', { exact: true })).not.toBeChecked();
    await settings(page);
    await expect(page.getByLabel('TC 목록 조회 제한 시간(초)', { exact: true })).toBeEditable();
    state.fail = false;
    await page.getByRole('button', { name: 'TC 목록 다시 조회', exact: true }).click();
    await expect.poll(() => state.requests).toBe(3);
    await expect(page.getByText('Catalog fixture timed out', { exact: false })).toHaveCount(0);
    expect(state.unexpected).toEqual([]);
  } finally { state.pending?.resolve(); }
});

test('T-193 deactivation discards a late catalog result before a fresh request', async ({ page }) => {
  const state = await fixture(page, true);
  const old = state.pending!;
  try {
    await expect.poll(() => state.requests).toBe(1);
    await navigate(page, '대시보드');
    state.catalog = catalog('replacement'); state.pending = null;
    old.resolve();
    await navigate(page, 'Test 현황');
    await expect(page.getByLabel('선택 replacement', { exact: true })).toBeVisible();
    await expect(page.getByLabel('선택 boot', { exact: true })).toHaveCount(0);
    await expect(page.getByText('TC 목록을 읽는 중…', { exact: true })).toHaveCount(0);
    expect(state.unexpected).toEqual([]);
  } finally { old.resolve(); }
});
