import {useEffect, useRef, useState} from 'react';
import './test.css';

type Data = Record<string, any>;
const BASE = '/api/v1/gui-test';
const session = sessionStorage.getItem('gui-session') || crypto.randomUUID();
sessionStorage.setItem('gui-session', session);
async function api(path: string, method = 'GET', data?: unknown) {
  const response = await fetch(BASE + path, {method, headers: {'Content-Type':'application/json', 'X-BSP-Client':'dashboard',
    'X-GUI-Session':session, 'Idempotency-Key':crypto.randomUUID()}, ...(data === undefined ? {} : {body:JSON.stringify(data)})});
  if (!response.ok) {const e = await response.json(); throw new Error(e.message || JSON.stringify(e.detail));}
  return response.json();
}
const emptyConnection = {a:{host:'demo-windows',board_id:'demo-board-a',com:'COM3'},b:{host:'demo-windows',board_id:'demo-board-b',com:'COM4'}};
const terminal = (run:Data|null) => !run || ['COMPLETED','CANCELLED'].includes(run.state);

export default function TestPage() {
  const [catalog,setCatalog]=useState<Data|null>(null), [branch,setBranch]=useState('demo/main');
  const [cap,setCap]=useState<Data|null>(null), [boards,setBoards]=useState<Data[]>([]), [ports,setPorts]=useState<Data|null>(null);
  const [selected,setSelected]=useState<string[]>([]), [search,setSearch]=useState(''), [kind,setKind]=useState('all');
  const [connection,setConnection]=useState<Data>(emptyConnection), [manual,setManual]=useState(false);
  const [scenario,setScenario]=useState('pass'), [speed,setSpeed]=useState(1), [jobId,setJobId]=useState('');
  const [jobs,setJobs]=useState<Data[]>([]), [job,setJob]=useState<Data|null>(null);
  const [run,setRun]=useState<Data|null>(null), [history,setHistory]=useState<Data[]>([]), [tab,setTab]=useState('execution');
  const [suites,setSuites]=useState<Data[]>([]), [profiles,setProfiles]=useState<Data[]>([]), [suiteRevision,setSuiteRevision]=useState('');
  const [suiteName,setSuiteName]=useState('My suite'), [profileName,setProfileName]=useState('My connection');
  const [checked,setChecked]=useState(''), [error,setError]=useState(''), [notice,setNotice]=useState(''), [busy,setBusy]=useState(false), [online,setOnline]=useState(true);
  const [focusTc,setFocusTc]=useState(''), [events,setEvents]=useState<Data[]>([]);
  const current=useRef('');
  const tests:Data[]=catalog?.tests||[];
  const needsDual=selected.some(id=>tests.find(t=>t.id===id)?.kind==='Dual');
  const request={tc_ids:selected, connection:{a:connection.a,b:needsDual?connection.b:null}, source_revision:catalog?.revision||'', suite_revision:suiteRevision, job_id:jobId||null, scenario,speed};
  const signature=JSON.stringify(request);
  async function perform(fn:()=>Promise<void>) {setBusy(true);setError('');setNotice('');try{await fn();}catch(e){setError((e as Error).message);}finally{setBusy(false);}}
  async function refreshLists(){const [h,s,p,j]=await Promise.all([api('/runs'),api('/saved/suite'),api('/saved/profile'),api('/demo/jobs')]);setHistory(h);setSuites(s);setProfiles(p);setJobs(j);}
  async function chooseRun(id:string){current.current=id; const r=await api('/runs/'+id);if(current.current===id){setRun(r);localStorage.setItem('gui-last-run',id);}}
  useEffect(()=>{let live=true; (async()=>{
    try {const [c,b,ca,po]=await Promise.all([api('/catalog'),api('/boards'),api('/capabilities'),api('/ports')]);if(!live)return;
      setCatalog(c);setSelected(c.tests.filter((t:Data)=>!t.disabled_reason).map((t:Data)=>t.id));setBoards(b.boards);setCap(ca);setPorts(po);await refreshLists();
      const id=localStorage.getItem('gui-last-run');if(id){try{await chooseRun(id);}catch{localStorage.removeItem('gui-last-run');}}
    } catch(e){if(live)setError((e as Error).message);}
  })();return()=>{live=false;};},[]);
  useEffect(()=>{let pending=false;const timer=setInterval(async()=>{if(pending)return;pending=true;try{
    const id=current.current;
    if(id){const r=await api('/runs/'+id);if(current.current===id){setRun(old=>old&&old.id===id&&old.version>r.version?old:r);setEvents(await api('/runs/'+id+'/events'));}
      await api('/runs/'+id+'/heartbeat','POST');}
    if(jobId)setJob(await api('/demo/jobs/'+jobId));
    setHistory(await api('/runs'));setOnline(true);
  }catch{setOnline(false);}finally{pending=false;}},700);return()=>clearInterval(timer);},[jobId]);
  async function act(action:string,data:Data={}) {if(!run)return;const r=await api(`/runs/${run.id}/actions/${action}`,'POST',{expected_version:run.version,data});setRun(r);}
  function toggle(ids:string[],on:boolean){setSelected(old=>on?[...old,...ids.filter(id=>!old.includes(id))]:old.filter(id=>!ids.includes(id)));setSuiteRevision('');}
  function move(index:number,delta:number){const next=[...selected];[next[index],next[index+delta]]=[next[index+delta],next[index]];setSelected(next);setSuiteRevision('');}
  const shown=tests.filter(t=>(kind==='all'||t.kind===kind)&&(t.name+' '+t.path).toLowerCase().includes(search.toLowerCase()));
  const folders=[...new Set(shown.map(t=>t.module))];
  const controlling=run?.controller===session;
  const attempts:Data[]=run?.attempts.filter((a:Data)=>!focusTc||a.tc_id===focusTc)||[];
  return <div className="gt">
    <div className="gt-intro"><div><span className="gt-eyebrow">GUI TEST WORKSPACE</span><h2>Test 현황</h2><p>테스트 선택부터 실행, 근거와 결과 확인까지</p></div><span className={'gt-status '+(online?'pass':'error')}>{online?'● 실행 관리자 연결됨':'● 연결 끊김 · 마지막 상태'}</span></div>
    <div className="gt-demo"><strong>MOCK DEMO</strong><span>{cap?.mode==='standalone'?'Windows 단독 모드 · 로컬 Run 저장':'Dashboard 통합 모드 · 별도 데모 Job 사용'}<br/>실제 TC·RBM은 미연동입니다. 장비와 운영 Dashboard 결과를 변경하지 않습니다.</span></div>
    {error&&<div role="alert" className="gt-alert error">{error}<button onClick={()=>setError('')}>닫기</button></div>}
    {notice&&<div role="status" className="gt-alert pass">{notice}</div>}
    <div className="gt-layout"><aside className="gt-panel gt-catalog">
      <div className="gt-section-head"><h3>Test cases</h3><span>{selected.length}개 선택</span></div>
      <label>Git 브랜치<select aria-label="TC 브랜치" value={branch} onChange={e=>setBranch(e.target.value)}>{(cap?.branches||['demo/main']).map((b:string)=><option key={b}>{b}</option>)}</select></label>
      <button className="gt-wide" disabled={busy} onClick={()=>perform(async()=>{const c=await api('/catalog?branch='+encodeURIComponent(branch));setCatalog(c);setChecked('');setNotice('TC 갱신 완료. 기존 Run 소스는 유지됩니다. 저장된 Suite의 버전을 다시 확인하세요.');})}>↻ TC 갱신</button>
      <small className="gt-hash" title={catalog?.revision}>현재 소스 {catalog?.revision?.slice(0,19)}… / {catalog?.branch}</small>
      <input aria-label="TC 검색" placeholder="이름 또는 경로 검색" value={search} onChange={e=>setSearch(e.target.value)}/>
      <select aria-label="연결 유형 필터" value={kind} onChange={e=>setKind(e.target.value)}><option value="all">Single + Dual</option><option>Single</option><option>Dual</option></select>
      <div className="gt-tree">{folders.map(folder=>{const items=shown.filter(t=>t.module===folder);return <div key={folder}><label className="gt-folder"><input type="checkbox" aria-label={'폴더 '+folder} checked={items.every(t=>selected.includes(t.id))} onChange={e=>toggle(items.filter(t=>!t.disabled_reason).map(t=>t.id),e.target.checked)}/>▾ {folder}</label>{items.map(t=><label key={t.id} className="gt-tc" title={t.disabled_reason||t.path}><input type="checkbox" aria-label={'선택 '+t.name} disabled={!!t.disabled_reason} checked={selected.includes(t.id)} onChange={e=>toggle([t.id],e.target.checked)}/><span>{t.name}<small>{t.disabled_reason||t.kind+' · '+t.timeout+'s'}</small></span></label>)}</div>})}</div>
      <p className="gt-muted">검색·필터를 바꿔도 숨겨진 TC의 선택은 유지됩니다.</p>
      <label>Suite 불러오기<select aria-label="Suite 불러오기" value="" onChange={e=>perform(async()=>{const s=suites.find(x=>x.name===e.target.value);if(!s)return;if(s.source_revision!==catalog?.revision||s.tc_ids.some((id:string)=>!tests.some(t=>t.id===id&&t.content_hash===s.tc_hashes[id])))throw Error('Suite 소스 또는 TC가 변경됐습니다. 목록을 검토하고 새 Suite로 저장하세요.');setSelected(s.tc_ids);setSuiteRevision(s.revision);})}><option value="">저장된 Suite 선택</option>{suites.map(s=><option key={s.name}>{s.name}</option>)}</select></label>
      <input aria-label="Suite 이름" value={suiteName} onChange={e=>setSuiteName(e.target.value)}/><button disabled={busy||!selected.length} onClick={()=>perform(async()=>{const s=await api('/saved/suite','PUT',{name:suiteName,data:{tc_ids:selected,branch:catalog?.branch}});setSuiteRevision(s.revision);await refreshLists();setNotice('Suite를 저장했습니다.');})}>Suite 저장 / 수정</button>
    </aside><div className="gt-main">
      <section className="gt-panel"><div className="gt-section-head"><h3>01 <span>연결 및 실행 준비</span></h3><label className="gt-inline"><input type="checkbox" checked={manual} onChange={e=>setManual(e.target.checked)}/>수동 보드 / COM 입력</label></div>
        <datalist id="gt-com-ports">{[...new Set([...boards.map(b=>b.com),...(ports?.ports||[]).map((p:Data)=>p.com)])].map(com=><option key={String(com)} value={String(com)}/>)}</datalist><div className="gt-boards">{(['a','b'] as const).map((role)=><fieldset key={role} disabled={role==='b'&&!needsDual}><legend>Board {role.toUpperCase()} <small>{role==='b'?'Dual TC 선택 시 사용':'Single / Dual'}</small></legend>{manual?<div className="gt-fields">{['host','board_id','com'].map(field=><label key={field}>{field}<input aria-label={`Board ${role.toUpperCase()} ${field}`} list={field==='com'?'gt-com-ports':undefined} value={connection[role][field]} onChange={e=>setConnection({...connection,[role]:{...connection[role],[field]:e.target.value}})}/></label>)}</div>:<label>보드 · COM<select aria-label={`Board ${role.toUpperCase()}`} value={connection[role].board_id} onChange={e=>setConnection({...connection,[role]:boards.find(b=>b.board_id===e.target.value)})}>{boards.map(b=><option key={b.board_id} value={b.board_id}>{b.board_id} · {b.com}</option>)}</select><small>{connection[role].host} · Mock 확인</small></label>}</fieldset>)}</div>
        {cap?.mode==='standalone'&&<p className="gt-muted">Windows 실제 COM 조회: {ports?.status} {ports?.ports.map((p:Data)=>p.com).join(', ')} · 실제 TC 실행은 Adapter 연결 후 가능</p>}
        <div className="gt-row"><select aria-label="연결 프로파일 불러오기" value="" onChange={e=>{const p=profiles.find(x=>x.name===e.target.value);if(p)setConnection({...emptyConnection,...p.connection,b:p.connection.b||emptyConnection.b});}}><option value="">연결 프로파일 선택</option>{profiles.map(p=><option key={p.name}>{p.name}</option>)}</select><input aria-label="프로파일 이름" value={profileName} onChange={e=>setProfileName(e.target.value)}/><button disabled={busy} onClick={()=>perform(async()=>{await api('/saved/profile','PUT',{name:profileName,data:{connection}});await refreshLists();setNotice('연결 프로파일 저장 완료. 실행 직전 다시 검증합니다.');})}>프로파일 저장</button></div>
        {cap?.mode==='dashboard'&&<div className="gt-row"><label>Dashboard Job (선택)<select aria-label="GUI Test Job" value={jobId} onChange={e=>setJobId(e.target.value)}><option value="">미연동 · 일반 TC 실행</option>{jobs.map(j=><option key={j.id} value={j.id}>{j.title}</option>)}</select></label><button disabled={busy} onClick={()=>perform(async()=>{const j=await api('/demo/jobs','POST');await refreshLists();setJobId(j.id);setJob(j);})}>격리 데모 Job 준비</button></div>}
      </section>
      <section className="gt-panel"><div className="gt-section-head"><h3>02 <span>실행 순서와 데모 시나리오</span></h3><span>순차 실행</span></div>
        <ol className="gt-order">{selected.map((id,i)=><li key={id}><span>{tests.find(t=>t.id===id)?.name||'누락: '+id}</span><button aria-label={id+' 위로'} disabled={i===0} onClick={()=>move(i,-1)}>↑</button><button aria-label={id+' 아래로'} disabled={i===selected.length-1} onClick={()=>move(i,1)}>↓</button></li>)}</ol>
        <div className="gt-row"><label>데모 시나리오<select aria-label="데모 시나리오" value={scenario} onChange={e=>setScenario(e.target.value)}><option value="pass">전체 PASS</option><option value="fail">2번째 FAIL 후 계속</option><option value="disconnect">COM 끊김 → 복구 → 재개</option><option value="timeout">Timeout → 재개</option><option value="unknown">종료 불명 UNKNOWN</option><option value="sync-failure">동기화 실패 → 자동 재시도</option><option value="sync-lost-response">동기화 응답 유실 → 멱등 재전송</option></select></label><label>데모 속도<select aria-label="데모 속도" value={speed} onChange={e=>setSpeed(Number(e.target.value))}><option value={.2}>0.2×</option><option value={1}>1×</option><option value={5}>5×</option></select></label><button disabled={busy||!selected.length} onClick={()=>perform(async()=>{await api('/preflight','POST',request);setChecked(signature);setNotice('Preflight 통과 · 시작 시 예약을 원자적으로 확보합니다.');})}>Preflight 검사</button><button className="gt-primary" disabled={busy||!online||checked!==signature} onClick={()=>perform(async()=>{const r=await api('/runs','POST',request);current.current=r.id;setRun(r);setFocusTc('');setTab('execution');localStorage.setItem('gui-last-run',r.id);await refreshLists();})}>▶ 테스트 시작</button></div>
      </section>
      <section className="gt-panel"><div className="gt-section-head"><h3>03 <span>실행 및 결과</span></h3><select aria-label="Run 이력" value={run?.id||''} onChange={e=>perform(()=>chooseRun(e.target.value))}><option value="">Run 선택</option>{history.map(h=><option key={h.id} value={h.id}>{h.id.slice(0,8)} · {h.state} · {h.overall_result}</option>)}</select></div>
        {!run?<div className="gt-empty">Preflight 검사 후 테스트를 시작하세요.<small>브라우저를 닫아도 서버의 Run은 유지됩니다.</small></div>:<>
          <div className="gt-run-head"><div><span className={'gt-status '+run.overall_result.toLowerCase()} data-testid="run-state">{run.state} · {run.overall_result}</span><small>Run {run.id.slice(0,12)} · {controlling?'이 브라우저가 제어 중':'관찰 모드'}</small></div><strong>{run.progress.percent}%<small>{run.progress.done} / {run.progress.total} 판정 완료</small></strong></div>
          <progress aria-label="TC 판정 진행률" value={run.progress.done} max={run.progress.total}/>
          <div className="gt-counts">{Object.entries(run.progress.counts).map(([k,v])=><span key={k}>{k} <b>{String(v)}</b></span>)}</div>
          {run.reason&&<div className="gt-alert">{run.reason}</div>}
          <div className="gt-row gt-controls"><button disabled={busy||!controlling||!['RUNNING','QUEUED'].includes(run.state)} onClick={()=>perform(()=>act('pause'))}>Ⅱ 일시 정지</button><button disabled={busy||!controlling||run.state!=='PAUSED'||!run.environment_ready} onClick={()=>perform(()=>act('resume'))}>▶ 재개</button><button className="gt-danger" disabled={busy||!controlling||terminal(run)||run.state==='UNKNOWN'} onClick={()=>perform(()=>act('cancel'))}>■ 테스트 중단</button><button disabled={busy||!controlling||!['PAUSED','UNKNOWN'].includes(run.state)} onClick={()=>perform(()=>act('demo-recover'))}>데모 연결 / 종료 확인</button><button disabled={busy||!controlling||terminal(run)} onClick={()=>perform(()=>act('demo-inject',{fault:'disconnect'}))}>다음 TC 오류 주입</button></div>
          <div className="gt-row">{!controlling&&<><button disabled={busy} onClick={()=>perform(()=>act('request-control'))}>제어권 요청</button><button disabled={busy} onClick={()=>perform(()=>act('take-control'))}>만료된 제어권 인수</button></>}{controlling&&run.control_request&&<button disabled={busy} onClick={()=>perform(()=>act('grant-control'))}>제어권 이전 승인</button>}{terminal(run)&&<button disabled={busy} onClick={()=>perform(async()=>{const r=await api('/runs','POST',{...request,tc_ids:run.tests.map((t:Data)=>t.id),source_revision:run.source_revision,connection:run.connection_snapshot,parent_run_id:run.id});current.current=r.id;setRun(r);})}>새 Run으로 재검증</button>}</div>
          <div className="gt-tabs" role="tablist"><button role="tab" aria-selected={tab==='execution'} onClick={()=>setTab('execution')}>TC 결과 · 로그</button><button role="tab" aria-selected={tab==='report'} onClick={()=>setTab('report')}>결과 리포트</button><button role="tab" aria-selected={tab==='audit'} onClick={()=>setTab('audit')}>감사 이력</button></div>
          {tab==='execution'&&<><table className="gt-table"><thead><tr><th>TC</th><th>유형</th><th>현재 결과</th><th>Attempts</th></tr></thead><tbody>{run.tests.map((t:Data)=><tr key={t.id}><td><button onClick={()=>setFocusTc(t.id)}>{t.name}</button></td><td>{t.kind}</td><td><span className={'gt-status '+(run.results[t.id]||'pending').toLowerCase()}>{run.results[t.id]||'PENDING'}</span></td><td>{run.attempts.filter((a:Data)=>a.tc_id===t.id).length}</td></tr>)}</tbody></table><div className="gt-section-head"><h4>실시간 로그 · 과거 Attempt 포함</h4><button onClick={()=>setFocusTc('')}>전체 로그</button></div><div className="gt-logs">{attempts.map(a=><article key={a.id}><header>{a.tc_id} · Attempt {a.ordinal} · {a.state} · {a.ended_at?((Date.parse(a.ended_at)-Date.parse(a.started_at))/1000).toFixed(2)+'s':'실행 중'}</header><pre>{a.stdout}{a.stderr}{a.reason?'\n'+a.reason:''}</pre><small>COM argv: {JSON.stringify(a.resolved_command_argv)} · exit {String(a.exit_code)}</small><a href={`${BASE}/runs/${run.id}/logs/${a.id}/stdout`}>stdout 다운로드</a><a href={`${BASE}/runs/${run.id}/logs/${a.id}/stderr`}>stderr 다운로드</a></article>)}</div></>}
          {tab==='report'&&<div><h4>판정 {run.overall_result} · 동기화 {run.sync.status}</h4><p>{run.sync.reason}</p><p className="gt-hash">소스 {run.source_revision}<br/>Suite {run.suite_revision||'직접 선택'}<br/>매핑 {run.link?.mapping_hash||'미연동'}<br/>시작 {run.started_at} / 종료 {run.ended_at||'진행 중'}</p><pre className="gt-json">{JSON.stringify(run.connection_snapshot,null,2)}</pre><div className="gt-row">{['pdf','html','csv','json','logs'].map(f=><a className="gt-download" key={f} href={`${BASE}/runs/${run.id}/report/${f}`}>{f==='logs'?'전체 로그 ZIP':f.toUpperCase()+' 다운로드'}</a>)}<button disabled={busy||!controlling||!['FAILED','BLOCKED'].includes(run.sync.status)} onClick={()=>perform(()=>act('retry-sync'))}>동기화 재시도</button></div></div>}
          {tab==='audit'&&<div className="gt-audit">{events.slice().reverse().map(e=><p key={e.seq}><time>{e.at}</time> {e.type} <small>{JSON.stringify(e.data)}</small></p>)}</div>}
        </>}
      </section>
      {jobId&&job&&<section className="gt-panel"><div className="gt-section-head"><h3>격리 Dashboard 결과</h3><button disabled={busy} onClick={()=>perform(async()=>{await api(`/demo/jobs/${jobId}/change-baseline`,'POST');setNotice('데모 Job 기준을 변경했습니다. 진행 중 Run은 다음 TC 전에 정지합니다.');})}>데모 Job 기준 변경</button></div>{job.gui_revalidation?.status==='AWAITING_APPROVAL'&&<div className="gt-alert"><div><strong>재검증 승인 대기</strong><p>대상: {job.gui_revalidation.modules.join(', ')||'통합 검증'}</p><p>순서: {job.gui_revalidation.steps.join(' → ')}</p><button disabled={busy} onClick={()=>perform(async()=>{await api(`/demo/jobs/${jobId}/approve-revalidation`,'POST',{expected_version:job.version,data:{run_id:job.gui_revalidation.run_id}});setJob(await api(`/demo/jobs/${jobId}`));})}>재검증 계획 승인</button></div></div>}<p>운영 Job과 분리된 모의 상태입니다. 전체 Run 종료 후 모듈별 결과를 반영합니다.</p><table className="gt-table"><tbody>{job.modules.map((m:Data)=><tr key={m.id}><td>{m.name}</td><td>{m.stages.device_test.status}</td><td>{JSON.stringify(m.stages.device_test.result?.cases||{})}</td></tr>)}</tbody></table></section>}
    </div></div>
  </div>;
}
