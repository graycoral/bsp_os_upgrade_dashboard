import type { AconObservation, DiagramModel, SnapshotHealth, SnapshotObservation } from './types';

export function snapshotHealth(observation: SnapshotObservation, nowMonoMs: number): SnapshotHealth {
  if (observation.status === 'failed') return {fresh:false, tone:'red', label:'상태 조회 실패 · 마지막 확인 상태'};
  if (observation.status === 'regressed') return {fresh:false, tone:'gray', label:'버전 역행 · 기준 확인 필요'};
  if (observation.status === 'empty') return {fresh:false, tone:'gray', label:'작업 없음'};
  if (observation.status !== 'ready' || observation.receivedMonoMs === null) return {fresh:false, tone:'gray', label:'최초 상태 확인 중'};
  if (observation.needsConfirmation) return {fresh:false, tone:'gray', label:'갱신 확인 중 · 마지막 확인 상태'};
  if (nowMonoMs - observation.receivedMonoMs >= observation.staleAfterMs) return {fresh:false, tone:'gray', label:'갱신 지연 · 마지막 확인 상태'};
  return {fresh:true, tone:'blue', label:'상태 조회됨'};
}
export function aconConnection(observations: AconObservation[] | undefined, jobId: string | null, moduleId: string | undefined, now: number): SnapshotHealth & {activity:boolean} {
  const applicable = (observations || []).filter(o=>o.jobId===jobId && o.provider && Number.isFinite(o.observedAt) && Number.isFinite(o.expiresAt) && o.observedAt<=now && o.expiresAt>o.observedAt && (moduleId ? o.scope==='module'&&o.moduleId===moduleId || o.scope==='job' : o.scope==='job'));
  const explicit = moduleId ? applicable.filter(o=>o.scope==='module') : applicable;
  const chosen = (explicit.length ? explicit : applicable).reduce<AconObservation | undefined>((last,o)=>!last || last.observedAt<o.observedAt ? o : last, undefined);
  if (!chosen) return {fresh:false,tone:'gray',label:'연결 확인 불가',activity:false};
  if (chosen.expiresAt<=now) return {fresh:false,tone:'gray',label:'연결 관찰 만료',activity:false};
  if (chosen.state==='connected') return {fresh:true,tone:'blue',label:moduleId&&chosen.scope==='job'?'공통 연결':'연결됨',activity:chosen.activity===true};
  if (chosen.state==='disconnected') return {fresh:false,tone:'red',label:'연결 끊김',activity:false};
  return {fresh:false,tone:'gray',label:chosen.state==='not_started'?'연결 시작 전':'연결 확인 불가',activity:false};
}
export function diagramActivity(model: DiagramModel, fresh: boolean) {
  return {
    boot:fresh && model.groups.some(g=>g.id==='boot'&&g.modules.some(m=>m.activity==='running')),
    main:fresh && model.bootReady===true && model.groups.some(g=>g.id==='main'&&g.modules.some(m=>m.runningStages.some(n=>n!=='analysis'))),
  };
}
