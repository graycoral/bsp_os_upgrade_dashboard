import type { SnapshotObservation } from '../web/types';
export { snapshotHealth } from '../web/presentation';

export const SNAPSHOT_POLL_MS = 1800;
export const SNAPSHOT_TIMEOUT_MS = 5000;
export const SNAPSHOT_STALE_MS = SNAPSHOT_POLL_MS * 3;
export interface SnapshotTicket { generation: number; scope: string; sequence: number }

/** One boundary for polling, post-command reads and conflict recovery. */
export function createSnapshotBoundary(initialScope: string, staleAfterMs = SNAPSHOT_STALE_MS) {
  let scope = initialScope, generation = 0, sequence = 0, settledSequence = 0;
  let version: number | null = null;
  let jobId: string | null = null;
  const initial = (): SnapshotObservation => ({status:'checking', receivedAt:null, receivedMonoMs:null, staleAfterMs, needsConfirmation:true, detail:''});
  let observation = initial();
  const matches = (ticket: SnapshotTicket) => ticket.generation === generation && ticket.scope === scope && ticket.sequence >= settledSequence;
  return {
    selectScope(next: string) {
      if (next === scope) return;
      scope = next; generation++; settledSequence = 0; version = null; jobId = null; observation = initial();
    },
    context: () => ({generation, scope}),
    begin: (): SnapshotTicket => ({generation, scope, sequence:++sequence}),
    accept(ticket: SnapshotTicket, snapshot: {id:string; version:number}, monoMs: number, wallMs: number) {
      if (!matches(ticket)) return false;
      if (!snapshot || typeof snapshot.id !== 'string' || !snapshot.id || !Number.isSafeInteger(snapshot.version) || snapshot.version < 0 || (jobId !== null && snapshot.id !== jobId)) return false;
      settledSequence = ticket.sequence;
      if (version !== null && snapshot.version < version) {
        observation = {...observation, status:'regressed', needsConfirmation:true, detail:'서버 버전이 마지막 확인 기준보다 낮습니다. 서버/DB 기준을 확인한 뒤 조회 기준을 재설정하세요.'};
        return false;
      }
      version = snapshot.version; jobId = snapshot.id;
      observation = {...observation, status:'ready', receivedAt:wallMs, receivedMonoMs:monoMs, needsConfirmation:false, detail:''};
      return true;
    },
    fail(ticket: SnapshotTicket, detail = '상태를 조회하지 못했습니다.') {
      if (!matches(ticket)) return false;
      settledSequence = ticket.sequence;
      observation = {...observation, status:'failed', needsConfirmation:true, detail};
      return true;
    },
    empty(ticket: SnapshotTicket) {
      if (!matches(ticket)) return false;
      settledSequence = ticket.sequence;
      observation = {...initial(), status:'empty', needsConfirmation:false};
      return true;
    },
    requireConfirmation() { observation = {...observation, needsConfirmation:true}; },
    resetBaseline() { generation++; settledSequence = 0; version = null; jobId = null; observation = initial(); },
    observation: (): SnapshotObservation => ({...observation}),
    currentVersion: () => version,
  };
}

/** Abort plus a logical timeout: a provider that ignores AbortSignal still cannot hold the refresh lock. */
export function withRequestTimeout<T>(operation: (signal: AbortSignal) => Promise<T>, timeoutMs = SNAPSHOT_TIMEOUT_MS): Promise<T> {
  const controller = new AbortController();
  let timer: ReturnType<typeof setTimeout>;
  const timeout = new Promise<never>((_, reject) => {
    timer = setTimeout(() => { controller.abort(); reject(new Error(`상태 조회 제한시간 ${timeoutMs}ms 초과`)); }, timeoutMs);
  });
  return Promise.race([Promise.resolve().then(() => operation(controller.signal)), timeout]).finally(() => clearTimeout(timer));
}
