import {jobFixture, moduleFixture, stage} from './fixtures';
const {test, expect} = require('./runtime.cjs');
const {startAppServer} = require('./app-server.cjs');
let host: any;

test.beforeAll(async () => {host = await startAppServer();});
test.afterAll(async () => {await host?.close();});

/** Route-only display fixture: never starts a worker or touches a saved job. */
async function overview(page: any, state = 'RUNNING') {
  const boot = moduleFixture('boot', 'boot', {name: 'Bootloader', progress: {done: 6, total: 6, percent: 100}, current_stage: null});
  for (const name of Object.keys(boot.stages)) boot.stages[name] = stage('SUCCEEDED');
  const ethernet = moduleFixture('ethernet', 'main', {name: 'Ethernet'});
  ethernet.stages.analysis = stage('RUNNING');
  const camera = moduleFixture('camera', 'main', {name: 'Camera'});
  camera.stages.analysis = stage('FAILED', {blocked_reason: 'Synthetic analysis failure'});
  const job = jobFixture([boot, ethernet, camera], {
    id: 'overview-fixture', fingerprint: 'synthetic-fingerprint', state,
    title: 'Synthetic BSP OS upgrade with a long reviewable project title',
    source_revision: 'synthetic-source-revision-with-a-long-unbroken-reference',
    profile: {workspace: '/synthetic/workspaces/long-unbroken-project-directory-for-responsive-review'},
    overall: {done: 7, total: 19, percent: 37},
    progress: {
      analysis: {done: 3, total: 3, percent: 100},
      implementation: {done: 1, total: 6, percent: 17},
      verification: {done: 0, total: 3, percent: 0},
      build: {done: 1, total: 3, percent: 33},
      test: {done: 0, total: 0, percent: null},
    },
  });
  const unexpected: string[] = [];
  await page.addInitScript(() => localStorage.setItem('bsp-job', 'overview-fixture'));
  await page.route('**/api/**', async (route: any) => {
    const request = route.request(), pathname = new URL(request.url()).pathname;
    let body: unknown;
    if (request.method() !== 'GET') unexpected.push(`${request.method()} ${pathname}`);
    else if (pathname === '/api/v1/config') body = {profile: null};
    else if (pathname === '/api/v1/jobs') body = [job];
    else if (pathname === '/api/v1/jobs/overview-fixture') body = job;
    else if (pathname === '/api/v1/jobs/overview-fixture/events') body = [];
    else unexpected.push(pathname);
    await route.fulfill({status: body === undefined ? 404 : 200, contentType: 'application/json', body: JSON.stringify(body ?? {message: 'Unexpected fixture request'})});
  });
  await page.goto(host.url);
  await expect(page.getByRole('heading', {name: '모듈별 진행 상황 3'})).toBeVisible();
  return unexpected;
}

test('overview preserves server aggregates, N/A, status counts and keyboard module controls', async ({page}) => {
  const unexpected = await overview(page);
  await expect(page.locator('.avatar')).toHaveCount(0);
  await expect(page.locator('.topbar').getByText('장비 테스트', {exact: true})).toHaveCount(0);
  for (const label of ['ENGINEERING WORKSPACE', 'WORKSPACE', 'UPGRADE CONTROL ROOM']) {
    await expect(page.getByText(label, {exact: true})).toHaveCount(0);
  }
  const cards = page.locator('.progress-grid > .progress-card');
  await expect(cards).toHaveCount(5);
  const values = [
    ['요구사항 분석', '100%', '3 / 3 완료'], ['구현', '17%', '1 / 6 완료'],
    ['검증', '0%', '0 / 3 완료'], ['빌드', '33%', '1 / 3 완료'], ['테스트', '해당 없음', '0 / 0 완료'],
  ];
  for (let i = 0; i < values.length; i++) {
    for (const text of values[i]) await expect(cards.nth(i)).toContainText(text);
  }
  await expect(cards.last()).not.toContainText('0%');
  await expect(page.locator('.overall')).toContainText('37%');
  await expect(page.locator('.overall')).toContainText('7 / 19 필수 작업 완료');
  await expect(page.locator('.legend')).toContainText('진행 1');
  await expect(page.locator('.legend')).toContainText('완료 1');
  await expect(page.locator('.legend')).toContainText('실패 1');
  const colors = await cards.locator('.bar > i').evaluateAll((bars: HTMLElement[]) => bars.map(bar => getComputedStyle(bar).backgroundColor));
  expect(new Set(colors).size).toBe(1);
  await expect(page.getByRole('button', {name: '일시 중지', exact: true})).toBeEnabled();
  await expect(page.getByRole('button', {name: '새 업그레이드', exact: true})).toBeVisible();

  await page.getByRole('button', {name: '나머지 모듈', exact: true}).click();
  await expect(page.locator('.module-toggle')).toHaveCount(2);
  const search = page.getByRole('textbox', {name: '모듈 검색', exact: true});
  await search.fill('eThEr');
  await expect(page.locator('.module-toggle')).toHaveCount(1);
  const toggle = page.locator('.module-toggle');
  await expect(toggle).toContainText('Ethernet');
  await toggle.focus(); await page.keyboard.press('Enter');
  await expect(toggle).toHaveAttribute('aria-expanded', 'true');
  const detail = page.locator('#' + await toggle.getAttribute('aria-controls'));
  await expect(detail).toBeVisible();
  await page.keyboard.press('Space');
  await expect(toggle).toHaveAttribute('aria-expanded', 'false');
  await expect(detail).toHaveCount(0);
  await search.fill('no-matching-module');
  await expect(page.getByText('검색 결과가 없습니다.', {exact: true})).toBeVisible();
  await search.fill('');
  await page.getByRole('button', {name: '부트로더 선행', exact: true}).click();
  await expect(page.locator('.module-toggle')).toHaveCount(1);
  await expect(page.locator('.module-toggle')).toContainText('Bootloader');
  await page.getByRole('button', {name: '전체 모듈', exact: true}).click();
  await expect(page.locator('.module-toggle')).toHaveCount(3);
  expect(unexpected).toEqual([]);
});

test('overview fits narrow screens and keeps a compact five-stage desktop strip', async ({page}, testInfo: any) => {
  const unexpected = await overview(page);
  for (const width of [320, 375, 414, 768, 1280]) {
    await page.setViewportSize({width, height: 1000});
    const cards = page.locator('.progress-grid > .progress-card');
    for (let i = 0; i < 5; i++) await expect(cards.nth(i)).toBeVisible();
    await expect(page.getByRole('textbox', {name: '모듈 검색', exact: true})).toBeVisible();
    const dimensions = await page.evaluate(() => ({page: document.documentElement.scrollWidth, viewport: window.innerWidth}));
    expect(dimensions.page, `page overflow at ${width}px`).toBeLessThanOrEqual(dimensions.viewport + 1);
    for (const selector of ['.summary-source', '.summary-workspace']) {
      const value = page.locator(selector);
      await expect(value).toBeVisible();
      const bounds = await value.evaluate((element: HTMLElement) => {
        const summary = element.closest('.summary')!.getBoundingClientRect();
        const range = document.createRange(); range.selectNodeContents(element);
        return {summary: {left: summary.left, right: summary.right, top: summary.top, bottom: summary.bottom},
          text: Array.from(range.getClientRects(), r => ({left: r.left, right: r.right, top: r.top, bottom: r.bottom})),
          scrollWidth: element.scrollWidth, clientWidth: element.clientWidth};
      });
      expect(bounds.text.length, `${selector} rendered text at ${width}px`).toBeGreaterThan(0);
      if (bounds.clientWidth > 0) expect(bounds.scrollWidth, `${selector} clipped text at ${width}px`).toBeLessThanOrEqual(bounds.clientWidth + 1);
      for (const rect of bounds.text) {
        expect(rect.left, `${selector} left bound at ${width}px`).toBeGreaterThanOrEqual(Math.max(0, bounds.summary.left) - 1);
        expect(rect.right, `${selector} right bound at ${width}px`).toBeLessThanOrEqual(Math.min(width, bounds.summary.right) + 1);
        expect(rect.top, `${selector} top bound at ${width}px`).toBeGreaterThanOrEqual(bounds.summary.top - 1);
        expect(rect.bottom, `${selector} bottom bound at ${width}px`).toBeLessThanOrEqual(bounds.summary.bottom + 1);
      }
    }
    if (width === 1280) {
      const boxes = await cards.evaluateAll((elements: HTMLElement[]) => elements.map(el => {const r = el.getBoundingClientRect(); return {top: r.top, bottom: r.bottom};}));
      expect(Math.max(...boxes.map((b: any) => b.top)) - Math.min(...boxes.map((b: any) => b.top))).toBeLessThanOrEqual(1);
      expect(Math.max(...boxes.map((b: any) => b.bottom)) - Math.min(...boxes.map((b: any) => b.top))).toBeLessThanOrEqual(160);
    }
    if (width === 375 || width === 1280) {
      const screenshot = testInfo.outputPath(`overview-${width}.png`);
      await page.screenshot({path: screenshot, fullPage: true});
      await testInfo.attach(`overview-${width}`, {path: screenshot, contentType: 'image/png'});
    }
  }
  expect(unexpected).toEqual([]);
});

test('overview plan confirmation keeps its explanation readable and action available', async ({page}) => {
  const unexpected = await overview(page, 'AWAITING_PLAN_CONFIRMATION');
  const explanation = page.locator('.plan-banner p');
  for (const width of [320, 375, 414, 768, 1280]) {
    await page.setViewportSize({width, height: 1000});
    await expect(explanation).toBeVisible();
    await expect(explanation).toHaveText('모듈 목록과 선행 그룹을 확인하면 부트로더 설계부터 진행합니다.');
    expect(await explanation.evaluate((element: HTMLElement) => parseFloat(getComputedStyle(element).fontSize))).toBeGreaterThanOrEqual(12);
    await expect(page.getByRole('button', {name: '계획 검토 · 확인', exact: true})).toBeVisible();
    await expect(page.getByRole('button', {name: '계획 검토 · 확인', exact: true})).toBeEnabled();
  }
  expect(unexpected).toEqual([]);
});
