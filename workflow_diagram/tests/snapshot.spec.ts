import {createSnapshotBoundary, snapshotHealth, withRequestTimeout} from '../host/snapshot';
const {test, expect} = require('./runtime.cjs');

test.describe('T-146 snapshot acceptance across every ingress', () => {
  test('A → B → A generations reject old success and failure, including conflict-recovery GET', () => {
    const b = createSnapshotBoundary('demo:A');
    const oldA = b.begin();
    b.selectScope('demo:B');
    const activeB = b.begin();
    expect(b.accept(oldA, {id: 'A', version: 99}, 10, 1000)).toBe(false);
    expect(b.fail(oldA, 'late VERSION_CONFLICT recovery')).toBe(false);
    expect(b.accept(activeB, {id: 'B', version: 2}, 20, 2000)).toBe(true);
    b.selectScope('demo:A');
    expect(b.accept(oldA, {id: 'A', version: 100}, 30, 3000)).toBe(false);
    const freshA = b.begin();
    expect(b.accept(freshA, {id: 'A', version: 1}, 40, 4000)).toBe(true);
    expect(b.currentVersion()).toBe(1);
  });

  test('same version refresh remains fresh despite old storage time, progress does not fabricate', () => {
    const b = createSnapshotBoundary('demo:A');
    expect(b.accept(b.begin(), {id: 'A', version: 7}, 0, 1000)).toBe(true);
    expect(b.accept(b.begin(), {id: 'A', version: 7}, 5000, 6000)).toBe(true);
    expect(snapshotHealth(b.observation(), 10000).fresh).toBe(true);
    expect(snapshotHealth(b.observation(), 10401).fresh).toBe(false);
    b.requireConfirmation();
    expect(snapshotHealth(b.observation(), 10001).fresh).toBe(false);
    expect(b.accept(b.begin(), {id: 'A', version: 7}, 11000, 12000)).toBe(true);
    expect(snapshotHealth(b.observation(), 11001).fresh).toBe(true);
  });

  test('out-of-order responses and failures cannot replace newer accepted result', () => {
    const b = createSnapshotBoundary('demo:A');
    const early = b.begin(); const late = b.begin();
    expect(b.accept(late, {id: 'A', version: 9}, 30, 3000)).toBe(true);
    expect(b.accept(early, {id: 'A', version: 10}, 40, 4000)).toBe(false);
    expect(b.fail(early, 'late network error')).toBe(false);
    expect(b.currentVersion()).toBe(9);
    expect(snapshotHealth(b.observation(), 41).fresh).toBe(true);
  });

  test('persistent version regression requires explicit baseline reset', () => {
    const b = createSnapshotBoundary('demo:A');
    b.accept(b.begin(), {id: 'A', version: 12}, 10, 1000);
    for (let n = 0; n < 3; n++) expect(b.accept(b.begin(), {id: 'A', version: 2}, 20 + n, 2000 + n)).toBe(false);
    expect(b.currentVersion()).toBe(12);
    expect(snapshotHealth(b.observation(), 25).fresh).toBe(false);
    b.resetBaseline();
    expect(b.accept(b.begin(), {id: 'A', version: 2}, 30, 3000)).toBe(true);
    expect(b.currentVersion()).toBe(2);
  });

  test('timeout releases permanent pending operation; late success cannot settle it', async () => {
    let complete!: (value: string) => void;
    let aborted = false;
    const pending = withRequestTimeout<string>(signal => {
      signal.addEventListener('abort', () => {aborted = true;});
      return new Promise(resolve => {complete = resolve;});
    }, 20);
    await expect(pending).rejects.toThrow();
    expect(aborted).toBe(true);
    complete('late response');
    expect(await withRequestTimeout(async () => 'recovered', 100)).toBe('recovered');
  });
});

