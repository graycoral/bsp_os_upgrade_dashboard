const {test, expect} = require('./runtime.cjs');
const {startIsolatedServer} = require('./isolated-server.cjs');
const fs = require('node:fs');
const path = require('node:path');
let host: any;
const screenshots = path.resolve(__dirname, '../../.local-reports/workflow-diagram');
test.beforeAll(async () => {host = await startIsolatedServer();});
test.afterAll(async () => {await host?.close();});
test.beforeEach(async ({page}) => {
  await page.goto(host.url);
  await expect(page.getByTestId('workflow-diagram')).toBeVisible();
});

test('T-144 T-148 isolated copy uses four horizontal nodes, keyboard independent expansion and scope reset', async ({page}) => {
  expect(fs.existsSync(path.join(host.isolated, 'apps/web'))).toBe(false);
  expect(fs.existsSync(path.join(host.isolated, 'gui_test'))).toBe(false);
  const topology = page.getByTestId('wd-topology');
  const rects = [];
  const headings = topology.locator('.wd-node h3');
  await expect(headings).toHaveCount(4);
  await expect(headings.nth(0)).toContainText('FrontEnd'); await expect(headings.nth(1)).toContainText('BackEnd');
  await expect(headings.nth(2)).toContainText('선행 IP 모듈 그룹'); await expect(headings.nth(3)).toContainText('일반 IP 모듈 그룹');
  for (let i = 0; i < 4; i++) {const box = await headings.nth(i).boundingBox(); expect(box).not.toBeNull(); rects.push(box);}
  for (let i = 1; i < rects.length; i++) {expect(rects[i].x).toBeGreaterThan(rects[i - 1].x); expect(Math.abs(rects[i].y - rects[0].y)).toBeLessThan(40);}
  await expect(page.locator('[data-testid^="wd-stages-"]')).toHaveCount(0);
  const a = page.getByTestId('wd-toggle-A'), b = page.getByTestId('wd-toggle-B');
  await a.focus(); await a.press('Enter'); await expect(a).toHaveAttribute('aria-expanded', 'true');
  await expect(page.getByTestId('wd-stages-A')).toBeVisible();
  await expect(page.getByTestId('wd-stages-B')).toHaveCount(0);
  await b.focus(); await b.press('Space'); await expect(b).toHaveAttribute('aria-expanded', 'true');
  fs.mkdirSync(screenshots, {recursive: true});
  await page.screenshot({path: path.join(screenshots, 'desktop.png'), fullPage: true});
  await a.press('Enter'); await expect(page.getByTestId('wd-stages-A')).toHaveCount(0);
  await expect(page.getByTestId('wd-stages-B')).toBeVisible();
  await page.evaluate(() => (window as any).wdTest.setActive(false));
  await page.evaluate(() => (window as any).wdTest.setActive(true));
  await expect(b).toHaveAttribute('aria-expanded', 'true');
  await page.evaluate(() => (window as any).wdTest.setContext('linux:another-job'));
  await expect(page.locator('[data-testid^="wd-stages-"]')).toHaveCount(0);
});

test('T-147 connection evidence remains independent of execution and only active paths flow', async ({page}) => {
  await page.evaluate(() => {
    const api = (window as any).wdTest, {jobFixture, moduleFixture, stage} = api.fixtures;
    const boot = moduleFixture('A'), main = moduleFixture('B', 'main');
    main.stages.analysis = stage('RUNNING'); api.setSnapshot(jobFixture([boot, main])); api.refresh();
    api.setAcon([{provider: 'synthetic', jobId: 'job-A', scope: 'job', state: 'disconnected', observedAt: Date.now(), expiresAt: Date.now() + 60000}]);
  });
  await expect(page.getByTestId('wd-module-B')).toContainText('진행 중');
  await expect(page.getByTestId('wd-module-B')).toContainText('연결 끊김');
  await expect(page.getByTestId('wd-edge-boot')).toHaveAttribute('data-flow', 'false');
  await expect(page.getByTestId('wd-edge-main')).toHaveAttribute('data-flow', 'false');
  await page.evaluate(() => {
    const api = (window as any).wdTest; api.setAcon([{provider: 'synthetic', jobId: 'job-A', scope: 'job', state: 'connected', observedAt: Date.now(), expiresAt: Date.now() + 60000}]);
  });
  await expect(page.getByTestId('wd-module-A')).toContainText('시작 전');
  await expect(page.getByTestId('wd-module-A')).toContainText('공통 연결');
  await expect(page.getByTestId('wd-edge-acon')).toHaveAttribute('data-flow', 'false');
  await page.evaluate(() => {const api = (window as any).wdTest; api.setObservation({status: 'failed', receivedAt: Date.now(), receivedMonoMs: performance.now(), staleAfterMs: 5400, needsConfirmation: false, detail: 'synthetic failure'});});
  await expect(page.getByTestId('wd-module-B')).toContainText('진행 중');
  await expect.poll(() => page.locator('.wd-flow').count()).toBe(0);
});

test('T-147 T-148 100 long names at 375px, no hidden stages, scoped CSS and bounded rendering', async ({page}) => {
  await page.setViewportSize({width: 375, height: 900});
  const network: string[] = []; page.on('request', request => {if (!request.url().includes('/@vite') && !request.url().includes('host.tsx')) network.push(request.url());});
  const measurement = await page.evaluate(async () => {
    const api = (window as any).wdTest;
    const raw = api.fixtures.scaleFixture(true); const encoded = JSON.stringify(raw);
    const parseStart = performance.now(); JSON.parse(encoded); const parseMs = performance.now() - parseStart;
    const start = performance.now(); api.setSnapshot(raw); api.refresh();
    await new Promise(requestAnimationFrame); await new Promise(requestAnimationFrame);
    return {bytes: new TextEncoder().encode(encoded).length, parseMs, displayMs: performance.now() - start};
  });
  await expect(page.locator('[data-testid^="wd-module-"]')).toHaveCount(100);
  await expect(page.locator('[data-testid^="wd-stages-"]')).toHaveCount(0);
  expect(measurement.displayMs).toBeLessThanOrEqual(1500);
  const expandMs = await page.evaluate(async () => {
    const start = performance.now();
    document.querySelectorAll<HTMLButtonElement>('[data-testid^="wd-toggle-"]').forEach(el => el.click());
    await new Promise(requestAnimationFrame); await new Promise(requestAnimationFrame);
    return performance.now() - start;
  });
  await expect(page.locator('[data-testid^="wd-stages-"]')).toHaveCount(100);
  expect(expandMs).toBeLessThanOrEqual(1500);
  const namesFit = await page.locator('[data-testid^="wd-toggle-"]').evaluateAll(nodes => nodes.every(node => {
    const button = node as HTMLElement;
    return button.clientWidth > 0 && button.scrollWidth <= button.clientWidth;
  }));
  expect(namesFit).toBe(true);
  const cardsOverlap = await page.locator('[data-testid^="wd-module-"]').evaluateAll(nodes => {
    const rects = nodes.map(node => node.getBoundingClientRect());
    return rects.some((a, i) => rects.slice(i + 1).some(b => a.left < b.right - 1 && a.right > b.left + 1 && a.top < b.bottom - 1 && a.bottom > b.top + 1));
  });
  expect(cardsOverlap).toBe(false);
  fs.mkdirSync(screenshots, {recursive: true});
  await page.screenshot({path: path.join(screenshots, 'narrow.png'), fullPage: true});
  await page.evaluate(() => (window as any).wdTest.setHostile(true));
  const buttonFont = await page.getByTestId('wd-toggle-ip-0').evaluate(el => getComputedStyle(el).fontSize);
  expect(parseFloat(buttonFont)).toBeLessThan(30);
  const cssIds = await page.locator('[data-testid="workflow-diagram"] [id]').evaluateAll(nodes => nodes.map(n => n.id));
  expect(new Set(cssIds).size).toBe(cssIds.length);
  await page.evaluate(() => (window as any).wdTest.setActive(false));
  expect(await page.getByTestId('workflow-diagram').evaluate(el => el.getAnimations({subtree: true}).filter(a => a.playState === 'running').length)).toBe(0);
  console.log('T-148 browser_metrics', JSON.stringify({...measurement, expandMs, networkRequests: network, metrics: await page.evaluate(() => (window as any).wdMetrics)}));
  expect(network.filter(url => /\/api\//.test(url))).toEqual([]);
});

test('T-147 reduced motion and explicit motion pause stop animation without commands', async ({page}) => {
  await page.evaluate(() => {const api = (window as any).wdTest, m = api.fixtures.moduleFixture('A'); m.stages.analysis = api.fixtures.stage('RUNNING'); api.setSnapshot(api.fixtures.jobFixture([m])); api.refresh();});
  await page.emulateMedia({reducedMotion: 'reduce'});
  await expect.poll(() => page.getByTestId('workflow-diagram').evaluate(el => el.getAnimations({subtree: true}).filter(a => a.playState === 'running').length)).toBe(0);
  await page.emulateMedia({reducedMotion: 'no-preference'});
  await page.getByRole('button', {name: '흐름 효과 일시정지'}).click();
  await expect.poll(() => page.getByTestId('workflow-diagram').evaluate(el => el.getAnimations({subtree: true}).filter(a => a.playState === 'running').length)).toBe(0);
  await expect(page.getByTestId('wd-module-A')).toContainText('진행 중');
});

test('T-148 REG-0034 inactive repeated observations perform zero diagram renders after transition settles', async ({page}) => {
  await page.evaluate(() => (window as any).wdTest.setActive(false));
  await expect(page.getByTestId('workflow-diagram')).toBeHidden();
  // Exclude the active→inactive commit, and let cleanup/effects finish before measurement.
  await page.evaluate(async () => {await new Promise(requestAnimationFrame); await new Promise(requestAnimationFrame);});
  const counts = await page.evaluate(async () => {
    const before = (window as any).__wdViewEntries;
    const profilerBefore = (window as any).wdMetrics.renders;
    for (let i = 0; i < 10; i++) {
      (window as any).wdTest.refresh();
      await new Promise(requestAnimationFrame);
    }
    await new Promise(requestAnimationFrame);
    return {before, after: (window as any).__wdViewEntries, profilerBefore, profilerAfter: (window as any).wdMetrics.renders, observations: 10};
  });
  console.log('T-148 inactive_profiler_counts', JSON.stringify(counts));
  expect(counts.after - counts.before).toBe(0);
});
