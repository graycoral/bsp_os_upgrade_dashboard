import type { DiagramModel, DiagramModule, DiagramStage, DiagramStagePart, ServerStageName, StageStatus } from '../web/types';

const names: ServerStageName[] = ['analysis','design','code','build','verification','device_test'];
const labels = ['요구사항분석','설계','코드 구현','빌드','검증','Test'];
const statusLabels: Record<StageStatus,string> = {PENDING:'시작 전', RUNNING:'진행 중', DISPATCHING:'배정 중', WAITING_INPUT:'입력 대기', SUCCEEDED:'완료', FAILED:'실패', UNKNOWN:'확인 필요', CANCEL_REQUESTED:'취소 처리 중 · 종료 미확인', CANCELLED:'취소됨', NOT_APPLICABLE:'해당 없음'};
type Value = Record<string, unknown>;
const record = (value: unknown): Value => value !== null && typeof value === 'object' && !Array.isArray(value) ? value as Value : {};
const text = (value: unknown) => typeof value === 'string' ? value : '';
function percent(value: unknown, diagnostics: string[], label: string) {
  const raw = record(value).percent;
  if (raw === null || raw === undefined) return null;
  if (typeof raw === 'number' && Number.isFinite(raw) && raw >= 0 && raw <= 100) return raw;
  diagnostics.push(`${label}: 진행률 범위를 확인하세요.`); return null;
}
function part(name: ServerStageName, value: unknown, current: string, diagnostics: string[]): DiagramStagePart {
  const raw = record(value), label = labels[names.indexOf(name)];
  let status: StageStatus = text(raw.status) as StageStatus;
  if (!Object.hasOwn(statusLabels, status)) { diagnostics.push(`${label}: 필수 단계 누락 또는 미지원 상태`); status = 'UNKNOWN'; }
  const complete = status === 'SUCCEEDED' && raw.validity === 'CURRENT';
  let statusLabel = statusLabels[status];
  let detail = '';
  if (status === 'SUCCEEDED' && !complete) {statusLabel = '재검증 필요'; detail = `이전 성공 · 유효성 ${text(raw.validity) || '미확인'}`;}
  else if (status === 'PENDING') detail = name === current ? text(raw.blocked_reason) : '이전 단계 대기';
  else detail = text(raw.blocked_reason);
  if (status === 'RUNNING' && detail) detail = `실행 중 · 후속 배정 제한: ${detail}`;
  if (status === 'NOT_APPLICABLE') detail = text(raw.exclusion_reason) || '제외 사유 확인 필요';
  if (name === 'device_test') {
    const auto = record(raw.automation), payload = record(auto.payload), baseline = record(payload.baseline), attempts = Array.isArray(raw.attempts) ? raw.attempts : [];
    // Read only the current Attempt identity, never copy its history or logs.
    const attempt = record(attempts.at(-1));
    if (raw.automation && payload.id === attempt.id && baseline.attempt_id && baseline.attempt_id === attempt.id) {
      const phases: Record<string,string> = {DISPATCHING:'Windows 실행 요청',PREPARING:'이미지·TC 준비',ENTERING_LKSHELL:'lkshell 진입',ENTERING_FASTBOOT:'fastboot 진입',FLASHING:'이미지 퓨징',WAITING_BOOT:'부팅 대기',TESTING:'TC 실행',COMPLETED:'자동 실행 종료 · 단계 결과 확인',FAILED:'자동 실행 실패',UNKNOWN:'자동 실행 확인 필요'};
      const phase = phases[text(auto.phase)] || '자동 실행 상태 확인 필요';
      detail = [detail,phase].filter(Boolean).join(' · ');
    } else if (status === 'WAITING_INPUT') detail = text(raw.automation_blocked) ? `자동 준비 대기 · ${text(raw.automation_blocked)}` : [detail,'수동 PASS/FAIL 입력 대기'].filter(Boolean).join(' · ');
  }
  return {id:name,label,status,statusLabel,detail,complete,running:status==='RUNNING',tone:status==='RUNNING'?'blue':status==='FAILED'||status==='CANCELLED'?'red':complete?'green':'gray'};
}
function moduleModel(value: unknown, index: number, duplicates: Set<string>, contextKey: string): DiagramModule {
  const raw = record(value), diagnostics: string[] = [];
  const id = text(raw.id), name = text(raw.name) || '이름 확인 필요';
  if (!id) diagnostics.push('모듈 id 누락');
  if (duplicates.has(id)) diagnostics.push('중복 모듈 id');
  const group = raw.group === 'boot' || raw.group === 'main' ? raw.group : 'unknown';
  if (group === 'unknown') diagnostics.push(`미지원 그룹: ${text(raw.group) || '누락'}`);
  const current = text(raw.current_stage), source = record(raw.stages);
  if (current && !names.includes(current as ServerStageName)) diagnostics.push('미지원 현재 단계');
  const parts = names.map(n => part(n, source[n], current, diagnostics));
  const layout: [DiagramStage['id'],string,ServerStageName[]][] = [['analysis','요구사항분석',['analysis']],['design','설계',['design']],['implementation','구현',['code','build']],['verification','검증',['verification']],['test','Test',['device_test']]];
  const stages = layout.map(([stageId,label,ids]) => {const subset = parts.filter(p=>ids.includes(p.id));return {id:stageId,label,parts:subset,complete:subset.every(p=>p.complete),running:subset.some(p=>p.running)};});
  const running = parts.filter(p=>p.running);
  if (running.length > 1) diagnostics.push('복수 단계 실행 중 · 서버 상태 확인 필요');
  const amount = percent(raw.progress,diagnostics,name);
  const invalidIdentity = !id || duplicates.has(id) || group === 'unknown';
  const actual = running.length ? running : parts.filter(p=>['CANCEL_REQUESTED','DISPATCHING','UNKNOWN'].includes(p.status));
  const focus = actual.length ? actual : parts.filter(p=>p.id===current);
  const complete = parts.every(p=>p.complete);
  const primary = focus.length ? focus : parts.filter(p=>!p.complete).slice(0,1);
  const hasUnknown = parts.some(p=>p.status==='UNKNOWN');
  const activity: DiagramModule['activity'] = invalidIdentity ? 'unknown' : running.length ? 'running' : actual.some(p=>p.status==='CANCEL_REQUESTED'||p.status==='DISPATCHING') ? 'transition' : hasUnknown ? 'unknown' : complete ? 'complete' : primary.some(p=>p.status==='FAILED'||p.status==='CANCELLED') ? 'failed' : 'waiting';
  const summary = invalidIdentity ? '모듈 정보 확인 필요' : complete ? '전체 단계 유효 완료' : primary.map(p=>`${p.id==='build'?'구현 · 빌드':p.id==='code'?'구현 · 코드':p.label} · ${p.statusLabel}`).join(' / ') || '현재 단계 확인 필요';
  return {id:id || `invalid-${index}`,key:`${contextKey}:${id || 'invalid'}${duplicates.has(id)||!id?`:${index}`:''}`,name,group,percent:amount,stages,activity,tone:activity==='running'?'blue':activity==='failed'?'red':activity==='complete'?'green':'gray',summary,detail:primary.map(p=>p.detail).filter(Boolean).join(' / '),runningStages:invalidIdentity?[]:running.map(p=>p.id),diagnostics};
}

/** Pure O(modules × 6) projection. Attempts/logs/auth/config never enter the view model. */
export function toDiagramModel(snapshot: unknown, options: {contextKey: string}): DiagramModel {
  const job = record(snapshot), diagnostics: string[] = [];
  const rawModules = Array.isArray(job.modules) ? job.modules : [];
  if (snapshot && !Array.isArray(job.modules)) diagnostics.push('모듈 목록이 없거나 올바르지 않습니다.');
  const seen = new Set<string>(), duplicates = new Set<string>();
  rawModules.forEach(value=>{const id=text(record(value).id);if(seen.has(id))duplicates.add(id);seen.add(id)});
  const modules = rawModules.map((value,index)=>moduleModel(value,index,duplicates,options.contextKey));
  const groups = record(job.groups);
  const result: DiagramModel = {contractVersion:1,contextKey:options.contextKey,jobId:text(job.id)||null,title:text(job.title)||'업그레이드 작업',storedAt:text(job.updated_at)||null,paused:job.paused===true,bootReady:typeof job.boot_ready==='boolean'?job.boot_ready:null,overallPercent:percent(job.overall,diagnostics,'전체'),groups:([{id:'boot',label:'선행 IP 모듈 그룹'},{id:'main',label:'일반 IP 모듈 그룹'}] as const).map(g=>({...g,modules:modules.filter(m=>m.group===g.id),percent:percent(groups[g.id],diagnostics,g.label)})),unassigned:modules.filter(m=>m.group==='unknown'),diagnostics};
  if (job.boot_ready !== undefined && typeof job.boot_ready !== 'boolean') diagnostics.push('선행 게이트 확인 불가');
  if (job.boot_ready === false && modules.some(m=>m.group==='main'&&m.runningStages.some(n=>n!=='analysis'))) diagnostics.push('서버 상태 불일치: 선행 게이트 대기 중 일반 IP의 설계 이후 실행이 보고됐습니다.');
  return result;
}
