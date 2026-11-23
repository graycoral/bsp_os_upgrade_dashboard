import { useCallback, useEffect, useRef, useState, type ReactNode } from 'react';
import { api, type Data, labels } from './api';
import './orchestration.css';

const PAGE_SIZE = 10;
const stateLabels: Record<string, string> = {
  DISABLED:'사용 안 함', OK:'정상', DEGRADED:'조정 호출 실패', LIMIT_REACHED:'호출 한도 도달',
  UNKNOWN:'상태 확인 필요', RUNNING:'호출 중', PENDING:'대기', FAILED:'호출 실패', SUCCEEDED:'호출 응답 수신',
  RECORDED:'제안 접수', WAITING_USER:'사람 확인 대기', APPLIED:'명령 적용', BLOCKED:'게이트 대기',
  REJECTED:'제안 거부', STALE:'기준 변경', OPEN:'분류 대기', DECISION:'새 판단',
  ORDINARY_FAILURE:'일반 오류', DISMISSED:'사람이 제외', LINKED:'판단 연결', ACTIVE:'대기 적용 중', RELEASED:'대기 해제',
};
function State({value}:{value:string}) {
  return <span className="badge">{stateLabels[value] || value} · {value}</span>;
}
function Records({title,items,metadata,endpoint,children}:{title:string;items:Data[];metadata?:Data;endpoint:string;children:(item:Data)=>ReactNode}) {
  const [page,setPage]=useState(0),[history,setHistory]=useState<number[]>([]),[remote,setRemote]=useState<Data|null>(null),[loading,setLoading]=useState(false),[error,setError]=useState('');
  const request=useRef<AbortController|null>(null);
  useEffect(()=>()=>{request.current?.abort();request.current=null},[]);
  const rows:Data[]=remote?.items||items, meta=remote||metadata;
  const last=Math.max(0,Math.ceil(rows.length/PAGE_SIZE)-1), current=Math.min(page,last);
  const next=Number.isSafeInteger(meta?.next_cursor)&&meta!.next_cursor>0?meta!.next_cursor:null;
  async function serverPage(cursor:number|null,previous:boolean) {
    if(request.current)return;
    if(cursor===null){setRemote(null);setHistory([]);setPage(0);setError('');return}
    const controller=new AbortController();request.current=controller;
    const timer=setTimeout(()=>controller.abort(),5000);
    setLoading(true);setError('');
    try {
      const value=await api(`${endpoint}?limit=50&before=${cursor}`,{signal:controller.signal});
      if(!Array.isArray(value.items))throw new Error('기록 목록 응답 형식을 확인하세요.');
      if(!controller.signal.aborted&&request.current===controller){setRemote({...value,items:[...value.items].reverse()});setHistory(old=>previous?old.slice(0,-1):[...old,cursor]);setPage(0)}
    }catch(e){if(request.current===controller)setError(controller.signal.aborted?'기록 조회가 취소되었거나 시간이 초과되었습니다.':(e as Error).message)}
    finally{clearTimeout(timer);if(request.current===controller){request.current=null;setLoading(false)}}
  }
  return <details className="orchestration-collection"><summary>{title} ({metadata?.total??items.length})</summary>
    {rows.slice(current*PAGE_SIZE,(current+1)*PAGE_SIZE).map(children)}
    {!rows.length&&<p>저장된 항목이 없습니다.</p>}
    {error&&<p className="error" role="alert">{error}</p>}
    {loading&&<p>서버에서 기록을 조회하고 있습니다…</p>}
    {(last>0||next!==null||history.length>0)&&<nav className="orchestration-actions" aria-label={`${title} 페이지`}>
      <button type="button" disabled={loading||(current===0&&history.length===0)} onClick={()=>current>0?setPage(current-1):void serverPage(history.at(-2)??null,true)}>이전</button>
      <span>{history.length+1}번째 묶음 · {current+1} / {last+1} 페이지 · 전체 {metadata?.total??rows.length}개</span>
      <button type="button" disabled={loading||(current===last&&next===null)} onClick={()=>current<last?setPage(current+1):void serverPage(next,false)}>다음</button>
    </nav>}
  </details>;
}
function StoredDetail({jobId,collection,id,title}:{jobId:string;collection:string;id:string;title:string}) {
  const [open,setOpen]=useState(false),[detail,setDetail]=useState<Data|null>(null),[error,setError]=useState('');
  useEffect(()=>{
    if(!open||detail)return;
    const controller=new AbortController(),timer=setTimeout(()=>controller.abort(),5000);
    let active=true;
    api(`/jobs/${encodeURIComponent(jobId)}/orchestration/${collection}/${encodeURIComponent(id)}`,{signal:controller.signal})
      .then(value=>{if(active)setDetail(value)}).catch(e=>{if(active)setError((e as Error).name==='AbortError'?'상세 조회 시간이 초과되었습니다. 닫았다가 다시 열어 재조회하세요.':(e as Error).message)}).finally(()=>clearTimeout(timer));
    return()=>{active=false;clearTimeout(timer);controller.abort()};
  },[open,detail,jobId,collection,id]);
  return <details onToggle={e=>{setOpen(e.currentTarget.open);if(e.currentTarget.open)setError('')}}><summary>{title}</summary>{error?<p className="error" role="alert">{error}</p>:detail?<pre aria-label={`${title} ${id}`}>{JSON.stringify(detail,null,2)}</pre>:open?<p>상세 기록을 조회하고 있습니다…</p>:null}</details>;
}
function ReportDetail({jobId,report}:{jobId:string;report:Data}) {
  const [open,setOpen]=useState(false),[detail,setDetail]=useState<Data|null>(null),[error,setError]=useState('');
  useEffect(()=>{
    if(!open||detail)return;
    const controller=new AbortController(), timer=setTimeout(()=>controller.abort(),5000);
    let current=true;
    api(`/jobs/${encodeURIComponent(jobId)}/reports/${encodeURIComponent(report.report_id)}`,{signal:controller.signal})
      .then(value=>{if(current)setDetail(value)})
      .catch(e=>{if(current)setError((e as Error).name==='AbortError'?'보고서 조회 시간이 초과되었습니다. 닫았다가 다시 열어 재조회하세요.':(e as Error).message)})
      .finally(()=>clearTimeout(timer));
    return()=>{current=false;clearTimeout(timer);controller.abort()};
  },[open,detail,jobId,report.report_id]);
  return <details className="orchestration-record" onToggle={e=>{setOpen(e.currentTarget.open);if(e.currentTarget.open)setError('')}}>
    <summary>보고서 {report.report_id} · {labels[report.stage]||report.stage} · {report.disposition}</summary>
    <p>SHA-256: {report.sha256}</p>
    {error?<p className="error" role="alert">{error}</p>:detail?<pre aria-label={`보고서 ${report.report_id} 원문과 정규화 사실`}>{JSON.stringify(detail,null,2)}</pre>:open?<p>보고서를 조회하고 있습니다…</p>:null}
  </details>;
}
function Candidate({candidate,job,disabled,submit}:{candidate:Data;job:Data;disabled:boolean;submit:(action:string,data:Data)=>Promise<void>}) {
  const [classification,setClassification]=useState('DECISION'),[reason,setReason]=useState(''),[decisionId,setDecisionId]=useState('');
  const terminal=candidate.status==='DISMISSED';
  return <article className="orchestration-record">
    <div className="orchestration-row"><strong>{candidate.question}</strong><State value={candidate.status}/></div>
    <p>영향 모듈: {(candidate.affected_module_ids||[]).map((id:string)=>job.modules?.find((m:Data)=>m.id===id)?.name||id).join(', ')} · 단계: {(candidate.affected_stages||[]).map((s:string)=>labels[s]||s).join(', ')}</p>
    {candidate.recommendation&&<p>에이전트 권고: {candidate.recommendation}</p>}
    {candidate.options?.length>0&&<p>제시된 선택지: {candidate.options.join(' / ')}</p>}
    <p>근거 보고서: {candidate.report_id}{candidate.decision_id&&` · 연결된 판단: ${candidate.decision_id}`}</p>
    {candidate.classification_reason&&<p>분류 사유: {candidate.classification_reason}</p>}
    <StoredDetail jobId={job.id} collection="candidates" id={candidate.id} title="판단 후보 전체 내용 · 이력"/>
    {!terminal&&<details><summary>후보 분류 · 사유 기록</summary><form onSubmit={e=>{e.preventDefault();void submit('classify-candidate',{candidate_id:candidate.id,classification,reason:reason.trim(),...(decisionId?{decision_id:decisionId}:{})})}}>
      <label>판단 후보 분류<select aria-label="판단 후보 분류" value={classification} onChange={e=>setClassification(e.target.value)}><option value="DECISION">새 판단 필요</option><option value="ORDINARY_FAILURE">일반 오류</option></select></label>
      <label>기존 판단 연결 (선택)<select aria-label="기존 판단 연결 (선택)" value={decisionId} onChange={e=>setDecisionId(e.target.value)}><option value="">연결 안 함</option>{(job.decisions||[]).map((d:Data)=><option key={d.id} value={d.id}>{d.title}</option>)}</select></label>
      <label>분류 · 제외 사유<textarea value={reason} onChange={e=>setReason(e.target.value)} required maxLength={4000}/></label>
      <p>일반 오류 분류만으로 대기가 해제되지는 않습니다. 사람이 제외하면 해당 후보의 대기를 해제합니다. 새 판단 분류만으로 Jira 티켓을 생성하지 않습니다.</p>
      <div className="orchestration-actions"><button type="submit" disabled={disabled||!reason.trim()}>후보 분류 저장</button><button type="button" disabled={disabled||!reason.trim()} onClick={()=>void submit('dismiss-candidate',{candidate_id:candidate.id,reason:reason.trim()})}>사유를 남기고 후보 제외</button></div>
    </form></details>}
  </article>;
}

type Props={job:Data;refreshToken:number|null;ready:boolean;busy:boolean;onAction:(name:string,data:Data)=>Promise<unknown>;refresh:()=>Promise<void>;candidatesOnly?:boolean};
export default function OrchestrationPanel({job,refreshToken,ready,busy,onAction,refresh,candidatesOnly=false}:Props) {
  const [summary,setSummary]=useState<Data|null>(null),[reports,setReports]=useState<Data[]>([]),[reportPage,setReportPage]=useState<Data|null>(null);
  const [error,setError]=useState(''),[notice,setNotice]=useState(''),[pending,setPending]=useState(false),[request,setRequest]=useState('');
  const [readError,setReadError]=useState(''),[receivedAt,setReceivedAt]=useState(0);
  const mounted=useRef(false), reading=useRef<Promise<void>|null>(null), controller=useRef<AbortController|null>(null), submitting=useRef(false);
  const load=useCallback(()=>{
    if(reading.current)return reading.current;
    const abort=new AbortController();controller.current=abort;
    const timer=setTimeout(()=>abort.abort(),5000);
    const promise=Promise.all([api(`/jobs/${encodeURIComponent(job.id)}/orchestration`,{signal:abort.signal}),api(`/jobs/${encodeURIComponent(job.id)}/reports`,{signal:abort.signal})])
      .then(([value,list])=>{
        if(!Number.isSafeInteger(value.execution_version)||!['runs','proposals','candidates','holds'].every(key=>Array.isArray(value[key]))||!Array.isArray(list.items))throw new Error('조정 상태 응답 형식을 확인하세요.');
        if(mounted.current){setSummary(value);setReports(list.items);setReportPage(list);setReceivedAt(Date.now());setReadError('')}
      }).catch(e=>{if(mounted.current)setReadError((e as Error).name==='AbortError'?'조정 상태 조회 시간이 초과되었습니다.':(e as Error).message)})
      .finally(()=>{clearTimeout(timer);if(reading.current===promise)reading.current=null});
    reading.current=promise;return promise;
  },[job.id]);
  useEffect(()=>{mounted.current=true;return()=>{mounted.current=false;controller.current?.abort()}},[]);
  // Reuse the dashboard's bounded snapshot polling. Reading never invokes a model.
  useEffect(()=>{void load()},[refreshToken,load]);
  const current=ready&&!readError&&!!summary&&summary.execution_version===job.version&&Date.now()-receivedAt<5400;
  const disabled=busy||pending||!current;
  async function submit(name:string,data:Data) {
    if(disabled||submitting.current||Date.now()-receivedAt>=5400)return;
    submitting.current=true;setPending(true);setError('');setNotice('');
    try {
      const response=await onAction(name,data);
      const result=response&&typeof response==='object'?response as Data:{};
      if(mounted.current)setNotice(name==='apply-proposal'?`제안 처리 결과: ${stateLabels[result?.status]||result?.status||'접수'}${result?.reason?` · ${result.reason}`:''}`:name==='reconcile-run'?`서버 확인 결과: ${stateLabels[result?.status]||result?.status||'접수'}`:'요청을 기록했습니다.');
    } catch(e) {
      if(mounted.current)setError((e as Data).status===409?`${(e as Error).message} 최신 상태를 다시 조회했습니다. 내용을 확인한 뒤 다시 요청하세요.`:(e as Error).message);
    } finally {
      await refresh();if(mounted.current)await load();
      if(mounted.current)setPending(false);submitting.current=false;
    }
  }
  const runs:Data[]=summary?.runs||[], proposals:Data[]=summary?.proposals||[], candidates:Data[]=summary?.candidates||[], holds:Data[]=summary?.holds||[];
  return <section className="card orchestration-panel" aria-label={candidatesOnly?'판단 후보와 범위 대기':'작업 오케스트레이션'}>
    <details open={candidatesOnly||undefined}><summary><h2>{candidatesOnly?'판단 후보 · 범위 대기':'작업 오케스트레이션'}</h2>{summary&&<State value={summary.health?.status||'UNKNOWN'}/>}</summary>
      <p>조정 호출 응답, 제안 접수, 명령 적용은 각각 별도 상태입니다. 모듈 완료는 서버의 단계 결과와 필수 시험으로 확인합니다.</p>
      {readError&&<p className="error" role="alert">{readError}</p>}
      {!summary&&!readError&&<p>조정 상태를 조회하고 있습니다…</p>}
      <p className="orchestration-feedback" role="status" aria-live="polite" aria-atomic="true">{pending?'조정 요청을 처리하고 있습니다…':notice}</p>
      {error&&<p className="error" role="alert">{error}</p>}
      {summary&&<>
        {!summary.enabled&&<p>이 작업은 자동 조정을 사용하지 않습니다. 기존 실행 경로를 유지합니다. 환경 설정 변경은 새 작업에만 적용됩니다.</p>}
        {summary.legacy_report&&<p>모듈 보고 v1 작업입니다. 구조화 근거 기반 자동 조정에는 새 작업에서 v2 지원 확인이 필요합니다.</p>}
        {summary.health?.reason&&<p>조정 상태 사유: {summary.health.reason}</p>}
        {!current&&<p>작업과 조정 상태의 최신 기준을 확인하는 동안 조정 명령을 사용할 수 없습니다.</p>}
        {!candidatesOnly&&<>
          <p>조정 호출 {summary.limits?.used_runs} / {summary.limits?.max_runs_per_job} · 기준 변경 재계획 한도 {summary.limits?.max_stale_replans} · 자동 재시도 한도 {summary.limits?.auto_retry_limit}</p>
          {summary.enabled&&<form onSubmit={e=>{e.preventDefault();void submit('replan',{request:request.trim()})}}><label>새 재계획 요청<textarea value={request} onChange={e=>setRequest(e.target.value)} required maxLength={4000}/></label><button type="submit" disabled={disabled||!request.trim()||summary.health?.status==='LIMIT_REACHED'||runs.some(r=>['PENDING','RUNNING','UNKNOWN'].includes(r.status))}>재계획 요청 기록</button></form>}
          <Records title="조정 호출 이력" items={[...runs].reverse()} metadata={summary.pagination?.runs} endpoint={`/jobs/${encodeURIComponent(job.id)}/orchestration/runs`}>{run=><article className="orchestration-record" key={run.id}><div className="orchestration-row"><strong>호출 {run.id}</strong><State value={run.status}/></div><p>실행 기준 v{run.base_state_version} · 계획 v{run.plan_version}</p>{run.response?.summary&&<p>{run.response.summary}</p>}{run.error&&<p>오류: {run.error_class} · {run.error}</p>}{run.status==='UNKNOWN'&&<><p>저장된 실행 영수증을 서버에서 확인합니다. 프로세스 종료를 사람이 선언하는 작업이 아닙니다.</p><button type="button" disabled={disabled} onClick={()=>void submit('reconcile-run',{run_id:run.id})}>서버에서 실행 상태 확인</button></>}</article>}</Records>
          <Records title="저장된 제안" items={[...proposals].reverse()} metadata={summary.pagination?.proposals} endpoint={`/jobs/${encodeURIComponent(job.id)}/orchestration/proposals`}>{proposal=>{
            const run=runs.find(r=>r.id===proposal.run_id), eligible=['RECORDED','WAITING_USER'].includes(proposal.status), fresh=run?.base_state_version===job.version&&run?.plan_version===job.plan_version;
            return <article className="orchestration-record" key={proposal.id}><div className="orchestration-row"><strong>{proposal.kind} · {proposal.id}</strong><State value={proposal.status}/></div><p>{proposal.reason}</p><p>대상: {(proposal.target?.module_ids||[]).join(', ')} · {labels[proposal.target?.stage]||proposal.target?.stage||'작업 전체'}</p>{proposal.result?.reason&&<p>명령 처리 사유: {proposal.result.reason}</p>}<StoredDetail jobId={job.id} collection="proposals" id={proposal.id} title="제안 내용 · 근거 참조"/>{eligible&&<><button type="button" disabled={disabled||!fresh||!summary.enabled} onClick={()=>void submit('apply-proposal',{proposal_id:proposal.id})}>저장된 제안 적용 요청</button>{!fresh&&<p>제안의 실행 기준이 바뀌었습니다. 최신 기준의 새 제안이 필요합니다.</p>}</>}</article>;
          }}</Records>
          <Records title="모듈 보고서" items={[...reports].reverse()} metadata={reportPage??undefined} endpoint={`/jobs/${encodeURIComponent(job.id)}/reports`}>{report=><ReportDetail key={report.report_id} jobId={job.id} report={report}/>}</Records>
        </>}
        <Records title="판단 후보" items={[...candidates].reverse()} metadata={summary.pagination?.candidates} endpoint={`/jobs/${encodeURIComponent(job.id)}/orchestration/candidates`}>{candidate=><Candidate key={candidate.id} candidate={candidate} job={job} disabled={disabled} submit={submit}/>}</Records>
        <Records title="범위 대기" items={[...holds].reverse()} metadata={summary.pagination?.holds} endpoint={`/jobs/${encodeURIComponent(job.id)}/orchestration/holds`}>{hold=><article className="orchestration-record" key={hold.id}><div className="orchestration-row"><strong>{hold.reason}</strong><State value={hold.status}/></div><p>영향 모듈: {(hold.module_ids||[]).join(', ')} · 단계: {(hold.stages||[]).map((s:string)=>labels[s]||s).join(', ')}</p><p>판단 후보: {hold.candidate_id}</p>{hold.release_reason&&<p>해제 사유: {hold.release_reason}</p>}</article>}</Records>
      </>}
    </details>
  </section>;
}
