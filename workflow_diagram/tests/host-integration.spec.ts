import {jobFixture, moduleFixture, stage} from './fixtures';
const {test, expect} = require('./runtime.cjs');
const {startAppServer} = require('./app-server.cjs');
let host: any;
test.beforeAll(async () => {host = await startAppServer();});
test.afterAll(async () => {await host?.close();});

async function mockHost(page: any, options: {onlyAInitially?: boolean} = {}) {
  const m = moduleFixture('A-IP'); m.stages.analysis = stage('RUNNING');
  const a = jobFixture([m], {id: 'A', title: 'Synthetic A'});
  const b = jobFixture([moduleFixture('B-IP', 'main')], {id: 'B', title: 'Synthetic B'});
  const state = {a, b, eventsFail: false, pending: false, conflict: false, conflictSent: false,
    gets: [] as string[], posts: [] as any[], creations: [] as any[], createdB: false, held: [] as any[], unexpected: [] as string[]};
  await page.addInitScript(() => localStorage.setItem('bsp-job', 'A'));
  await page.route('**/api/**', async route => {
    const request = route.request(); const url = new URL(request.url()); const pathname = url.pathname;
    const json = (value: any, status = 200) => route.fulfill({status, contentType: 'application/json', body: JSON.stringify(value)});
    if (pathname === '/api/v1/config') return json({profile: null});
    if (pathname === '/api/v1/jobs') {
      if (request.method() === 'POST') {state.creations.push(request.postDataJSON()); state.createdB = true; return json({job_id: 'B'}, 201);}
      state.gets.push('list'); return json(options.onlyAInitially && !state.createdB ? [a] : [a, b]);
    }
    const action = pathname.match(/^\/api\/v1\/jobs\/(A|B)\/actions\/(.+)$/);
    if (action) {
      state.posts.push({id: action[1], name: action[2], key: request.headers()['idempotency-key'], body: request.postDataJSON()});
      if (state.conflict && !state.conflictSent) {state.conflictSent = true; return json({code: 'VERSION_CONFLICT', message: 'synthetic conflict'}, 409);}
      return json({accepted: true});
    }
    const snapshot = pathname.match(/^\/api\/v1\/jobs\/(A|B)$/);
    if (snapshot) {
      state.gets.push(snapshot[1]);
      if (state.pending || state.conflictSent && state.conflict) {state.held.push({route, id: snapshot[1]}); return;}
      return json(snapshot[1] === 'A' ? a : b);
    }
    if (/\/jobs\/(A|B)\/events$/.test(pathname)) return json(state.eventsFail ? {message: 'events unavailable'} : [], state.eventsFail ? 503 : 200);
    // GUI Test route fixtures are explicit empty data; they do not launch anything.
    if (/\/gui-test\//.test(pathname) || /\/gui_test\//.test(pathname)) {
      if (pathname.endsWith('/capabilities')) return json({execution: 'mock', max_parallel: 1, features: {}});
      if (pathname.endsWith('/catalog')) return json({tests: [], source: null});
      return json([]);
    }
    state.unexpected.push(pathname); return json({message: 'unconfigured mock endpoint'}, 404);
  });
  await page.goto(host.url);
  await expect(page.getByRole('navigation').getByRole('button', {name: '대시보드', exact: true})).toBeVisible();
  return state;
}
const diagram = async (page: any) => {
  await page.getByRole('navigation').getByRole('button', {name: '다이어그램', exact: true}).click();
  await expect(page.getByTestId('workflow-diagram')).toBeVisible();
};

test('T-146 events-only failure cannot mark accepted snapshot offline; same version refresh recovers freshness', async ({page}) => {
  const state = await mockHost(page); await diagram(page);
  state.eventsFail = true;
  const before = state.gets.length;
  await expect.poll(() => state.gets.length, {timeout: 5000}).toBeGreaterThan(before);
  await expect(page.getByTestId('workflow-diagram')).toContainText('상태 조회됨');
  await expect(page.getByTestId('wd-module-A-IP')).toContainText('진행 중');
  expect(state.posts).toEqual([]);
});

test('T-146 permanent pending times out, releases refresh lock, rejects late response and recovers', async ({page}) => {
  const state = await mockHost(page); await diagram(page); state.pending = true;
  await expect.poll(() => state.held.length, {timeout: 5000}).toBeGreaterThan(0);
  const firstCount = state.held.length;
  await expect(page.getByTestId('workflow-diagram')).toContainText('조회 실패', {timeout: 8000});
  await expect.poll(() => state.held.length, {timeout: 6500}).toBeGreaterThan(firstCount);
  state.pending = false;
  for (const held of state.held.splice(0)) await held.route.fulfill({status: 200, contentType: 'application/json', body: JSON.stringify({...state.a, version: 99})}).catch(() => {});
  await expect(page.getByTestId('workflow-diagram')).toContainText('상태 조회됨', {timeout: 8000});
  expect(state.posts).toEqual([]);
});

test('T-144 T-146 A → B → A rejects stale snapshots without leaking expanded state', async ({page}) => {
  const state = await mockHost(page); await diagram(page);
  await page.getByTestId('wd-toggle-A-IP').click(); state.pending = true;
  await expect.poll(() => state.held.length, {timeout: 5000}).toBeGreaterThan(0);
  const select = page.getByRole('combobox', {name: '업그레이드 작업 선택'});
  await select.selectOption('B'); state.pending = false;
  for (const held of state.held.splice(0)) await held.route.fulfill({status: 200, contentType: 'application/json', body: JSON.stringify(state.a)}).catch(() => {});
  await expect(page.getByTestId('wd-module-B-IP')).toBeVisible({timeout: 7000});
  await expect(page.getByTestId('wd-module-A-IP')).toHaveCount(0);
  await select.selectOption('A'); await expect(page.getByTestId('wd-toggle-A-IP')).toBeVisible({timeout: 7000});
  await expect(page.getByTestId('wd-toggle-A-IP')).toHaveAttribute('aria-expanded', 'false');
  expect(state.posts).toEqual([]);
});

test('T-146 command VERSION_CONFLICT recovery for A cannot replace B selection or retarget command', async ({page}) => {
  const state = await mockHost(page); state.conflict = true;
  await page.getByRole('button', {name: '일시 중지', exact: true}).click();
  await expect.poll(() => state.conflictSent).toBe(true);
  await expect.poll(() => state.held.length).toBeGreaterThan(0);
  await page.getByRole('combobox', {name: '업그레이드 작업 선택'}).selectOption('B');
  state.conflict = false;
  for (const held of state.held.splice(0)) await held.route.fulfill({status: 200, contentType: 'application/json', body: JSON.stringify({...state.a, version: 8})}).catch(() => {});
  await diagram(page); await expect(page.getByTestId('wd-module-B-IP')).toBeVisible({timeout: 8000});
  await expect(page.getByTestId('wd-module-A-IP')).toHaveCount(0);
  expect(state.posts.every(p => p.id === 'A' && p.name === 'pause')).toBe(true);
  expect(new Set(state.posts.map(p => p.key)).size).toBe(1);
});

test('T-148 REG-0035 identical clock windows have identical polling counts despite repeated tab roundtrips', async ({page}) => {
  const clockStart = new Date('2026-11-03T00:00:00Z');
  await page.clock.install({time: clockStart}); await page.clock.pauseAt(clockStart);
  const state = await mockHost(page);
  const nav = page.getByRole('navigation');
  const count = () => state.gets.filter(x => x === 'list').length;
  async function windowRequests(roundtrips: boolean) {
    const before = count(); // Includes the first tab entry; never capture after clicking it.
    for (let tick = 0; tick < 4; tick++) {
      if (roundtrips) {
        await diagram(page);
        if (tick === 0) await page.getByTestId('wd-toggle-A-IP').click();
        await nav.getByRole('button', {name: '대시보드', exact: true}).click();
      }
      await page.clock.runFor(1800);
      await expect.poll(count).toBeGreaterThanOrEqual(before + tick + 1);
      // Let the intercepted snapshot/events promise chain settle while fake time stays paused.
      await page.waitForTimeout(100);
    }
    await page.waitForTimeout(100);
    return count() - before;
  }
  const baseline = await windowRequests(false);
  const diagramCount = await windowRequests(true);
  expect(baseline).toBe(4); expect(diagramCount).toBe(baseline);
  for (const name of ['사람 검토 · Jira', '실행 기록', '환경 설정', '대시보드']) {
    await nav.getByRole('button', {name, exact: true}).click();
    await expect(nav.getByRole('button', {name, exact: true})).toHaveClass(/active/);
  }
  await diagram(page); await expect(page.getByTestId('wd-toggle-A-IP')).toHaveAttribute('aria-expanded', 'true');
  expect(state.posts).toEqual([]); expect(state.unexpected).toEqual([]);
  console.log('T-148 REG-0035 host_request_counts', JSON.stringify({windowMs: 7200, roundtrips: 4, baseline, diagramCount, snapshotGets: state.gets.length}));
});

test('T-146 REG-0034 creating B while A is selected switches snapshot boundary and subsequent command target', async ({page}) => {
  const state = await mockHost(page, {onlyAInitially: true});
  const select = page.getByRole('combobox', {name: '업그레이드 작업 선택'});
  await expect(select).toHaveValue('A');
  await page.getByRole('button', {name: '새 업그레이드', exact: true}).click();
  await page.getByRole('dialog').getByLabel('작업 이름', {exact: true}).fill('Synthetic B created');
  await page.getByRole('dialog').getByRole('button', {name: '분석 시작', exact: true}).click();
  await expect(page.getByRole('dialog')).toHaveCount(0);
  await expect(select).toHaveValue('B', {timeout: 7000});
  await diagram(page);
  await expect(page.getByTestId('wd-module-B-IP')).toBeVisible({timeout: 7000});
  await expect(page.getByTestId('wd-module-A-IP')).toHaveCount(0);
  await page.getByRole('navigation').getByRole('button', {name: '대시보드', exact: true}).click();
  await page.getByRole('button', {name: '일시 중지', exact: true}).click();
  await expect.poll(() => state.posts.length).toBe(1);
  expect(state.posts[0].id).toBe('B'); expect(state.posts[0].name).toBe('pause');
  expect(state.creations).toHaveLength(1); expect(state.creations[0].title).toBe('Synthetic B created');
});

test('T-144 REG-0034 inactive A → B → A resets expansion while same-task tab roundtrip preserves it', async ({page}) => {
  const state = await mockHost(page); await diagram(page);
  await page.getByTestId('wd-toggle-A-IP').click();
  await expect(page.getByTestId('wd-toggle-A-IP')).toHaveAttribute('aria-expanded', 'true');
  const overview = page.getByRole('navigation').getByRole('button', {name: '대시보드', exact: true});
  await overview.click(); await diagram(page);
  await expect(page.getByTestId('wd-toggle-A-IP')).toHaveAttribute('aria-expanded', 'true');
  await overview.click();
  const select = page.getByRole('combobox', {name: '업그레이드 작업 선택'});
  await select.selectOption('B'); await expect(select).toHaveValue('B');
  await expect(page.locator('.summary')).toContainText('Synthetic B', {timeout: 7000});
  await select.selectOption('A'); await expect(page.locator('.summary')).toContainText('Synthetic A', {timeout: 7000});
  await diagram(page);
  await expect(page.getByTestId('wd-toggle-A-IP')).toHaveAttribute('aria-expanded', 'false');
  await expect(page.getByTestId('wd-stages-A-IP')).toHaveCount(0);
  expect(state.posts).toEqual([]);
});
