import {useEffect, useMemo, useRef, useState, type CSSProperties} from 'react';
import './test.css';
import './motion.css';
import CaseTree from './CaseTree';
import { AuditDialog } from './AuditDialog';
import ExecutionViewSettings from './ExecutionViewSettings';
import SettingsPanel, {type SettingsFold} from './SettingsSection';
import SourceSettings, {type SourceState} from './SourceSettings';
import {executionView} from './executionView';
import useModuleSelection, {sameModuleContext} from './useModuleSelection';

type Data = Record<string, any>;
const liveView=executionView==='live';
const BASE = '/api/v1/gui-test'+(liveView?'/live':'');
const lastRunKey=liveView?'gui-last-run:live':'gui-last-run';
const session = (()=>{try {const value=sessionStorage.getItem('gui-session')||crypto.randomUUID();sessionStorage.setItem('gui-session',value);return value;}catch{return crypto.randomUUID();}})();
async function api(path: string, method = 'GET', data?: unknown, signal?:AbortSignal) {
  const response = await fetch(BASE + path, {method, signal, headers: {'Content-Type':'application/json', 'X-BSP-Client':'dashboard',
    'X-GUI-Session':session, 'Idempotency-Key':crypto.randomUUID()}, ...(data === undefined ? {} : {body:JSON.stringify(data)})});
  if (!response.ok) {const e = await response.json(); throw new Error(e.message || JSON.stringify(e.detail));}
  return response.json();
}
const emptyConnection = {a:{host:'demo-windows',board_id:'demo-board-a',com:'COM3'},b:{host:'demo-windows',board_id:'demo-board-b',com:'COM4'}};
const terminal = (run:Data|null) => !run || ['COMPLETED','CANCELLED'].includes(run.state);

function ActionIcon({name}:{name:'play'|'pause'|'stop'|'check'}) {
  return <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    {name==='play'?<path d="m8 5 11 7-11 7Z"/>:name==='pause'?<path d="M8 5v14M16 5v14"/>:name==='stop'?<rect x="6" y="6" width="12" height="12" rx="2"/>:<><path d="m9 12 2 2 4-4"/><path d="M12 3 4 6v6c0 4 8 9 8 9s8-5 8-9V6Z"/></>}
  </svg>;
}

function TargetLabel({target}:{target?:Data}) {
  return <span className="gt-target-label">{target?.labels?.length?target.labels.join(' · '):'기록 없음'}{target?.incomplete&&target?.labels?.length?' · 일부 기록 없음':''}</span>;
}

function SourceGitInfo({catalog,cap,managed=false}:{catalog:Data|null;cap:Data|null;managed?:boolean}) {
  const git=catalog?.git;
  const disconnected=!managed&&cap?.connection?.ready===false;
  const status=disconnected?'실행기 미연결 · 미확인':(cap?.simulation&&!managed)?'모의 소스':!git?'Git 정보 미제공':({
    available:'Git 정보 확인됨',not_repository:'Git 저장소 아님',git_unavailable:'Git 실행 파일 미확인',
    timeout:'Git 조회 시간 초과',error:'Git 정보 미확인',unborn:'첫 커밋 없음',
  } as Record<string,string>)[git.status]||'Git 정보 미확인';
  const showDetails=git&&!disconnected&&(!cap?.simulation||managed);
  const remoteMissing=git&&['available','unborn'].includes(git.status)?'미등록':'미확인';
  return <section className="gt-source-git" aria-label="TC 소스 Git">
    <div className="gt-source-git-head"><h4>TC 소스 Git</h4><span>{status}</span></div>
    {showDetails&&<><dl className="gt-source-git-fields">
      <dt>소스 경로</dt><dd>{git.source_path||'미제공'}</dd>
      <dt>저장소 경로</dt><dd>{git.repository_path||'미확인'}</dd>
      <dt>Remote</dt><dd>{git.remote||remoteMissing}</dd>
      <dt>브랜치</dt><dd>{git.detached?'detached HEAD':git.branch||'미확인'}</dd>
      <dt>커밋</dt><dd>{git.commit||'미확인'}</dd>
      <dt>조회 시각</dt><dd>{git.checked_at||'미확인'}</dd>
    </dl><small>조회 시점 Git 정보 · 실행 파일 동일성은 별도 확인</small></>}
  </section>;
}

function UsageLines({usage}:{usage?:Data}) {
  const count=(n:number|null)=>n==null?'미집계':n.toLocaleString();
  return <span className="gt-usage-lines">{usage?.models?.map((m:Data)=><span key={m.provider+'/'+m.model} title={m.provider+' · USD · 어댑터 보고값'}>{m.model} · 입력 {count(m.input_tokens)} / 출력 {count(m.output_tokens)} tok · {m.cost_usd==null?'비용 미집계':'$'+Number(m.cost_usd).toLocaleString('en-US',{minimumFractionDigits:4,maximumFractionDigits:8})}</span>)}
    {usage?.status==='partial'&&<span>일부 Attempt 집계 없음</span>}
    {(!usage?.models?.length)&&<span>{usage?.status==='not_applicable'?'모델 호출 없음':'토큰·비용 집계 없음'}</span>}
  </span>;
}

function usageCost(usage?:Data) {
  const models=usage?.models||[];
  if(!models.length)return usage?.status==='not_applicable'?'비용 — · 모델 호출 없음':'비용 미집계';
  const costs=models.filter((m:Data)=>m.cost_usd!=null);
  if(!costs.length)return '비용 미집계';
  const total=costs.reduce((n:number,m:Data)=>n+Number(m.cost_usd),0);
  const partial=usage?.status==='partial'||costs.length!==models.length;
  return (partial?'집계 비용 $':'비용 $')+total.toLocaleString('en-US',{minimumFractionDigits:4,maximumFractionDigits:8})+(partial?' · 일부 미집계':'');
}

function UsageDetails({usage,label='토큰·비용 상세',runTotal=false}:{usage?:Data;label?:string;runTotal?:boolean}) {
  return <details className="gt-usage"><summary aria-label={label}>토큰·비용 상세</summary><UsageLines usage={usage}/>{runTotal&&<small>USD · 현재 Run의 재시도 포함 누적 · 원본 Run 비용은 원본 이력에 보존</small>}</details>;
}

type CommandChoice = {name:string; revision:string; dirty:boolean};
const defaultSingleCommand = ['mock-tc','{tc_path}','{com_a}'];
const defaultDualCommand = ['mock-tc','{tc_path}','{com_a}','{com_b}'];

function CommandSettings({mode, tests, connection, sourceRevision, onChange, fold, simulation=true, active=true}: {
  simulation?:boolean; active?:boolean; fold?:SettingsFold; mode:string; tests:Data[]; connection:Data; sourceRevision:string; onChange:(choice:CommandChoice)=>void;
}) {
  const defaultSingle=simulation?defaultSingleCommand:['python3','{tc_path}','-p','{com_a}'];
  const defaultDual=simulation?defaultDualCommand:['python3','{tc_path}','-n','{node_a}','-n2','{node_b}'];
  const [saved,setSaved]=useState<Data[]>([]), [profile,setProfile]=useState('');
  const [name,setName]=useState('My command'), [single,setSingle]=useState(defaultSingle.join('\n')), [dual,setDual]=useState(defaultDual.join('\n'));
  const [revision,setRevision]=useState(''), [dirty,setDirty]=useState(false), [loading,setLoading]=useState(true), [working,setWorking]=useState(false);
  const [error,setError]=useState(''), [message,setMessage]=useState(''), [preview,setPreview]=useState<Data|null>(null), [previewTc,setPreviewTc]=useState('');
  const selection=tests.some(t=>t.id===previewTc)?previewTc:tests[0]?.id||'';
  const tc=tests.find(t=>t.id===selection);
  const template={single:single.split('\n'),dual:dual.split('\n')};
  const previewRequest={tc_id:selection,source_revision:sourceRevision,connection:{a:connection.a,b:tc?.kind==='Dual'?connection.b:null},template};
  const previewSignature=JSON.stringify(previewRequest);
  const latestPreview=useRef(previewSignature);latestPreview.current=previewSignature;
  const previewSequence=useRef(0);
  const initialized=useRef(false);
  const storageKey='gui-command-profile:'+mode+(liveView?':live':'');
  function remember(value:string){try{localStorage.setItem(storageKey,value);}catch{/* Saving the profile itself is server-side. */}}
  function choose(item:Data|undefined) {
    const value=item?.name||'';
    setProfile(value);setName(value||'My command');setSingle((item?.single||defaultSingle).join('\n'));setDual((item?.dual||defaultDual).join('\n'));
    setRevision(item?.revision||'');setDirty(!simulation&&!item);setPreview(null);setError('');setMessage('');remember(value);
    onChange({name:value,revision:item?.revision||'',dirty:!simulation&&!item});
  }
  async function reload() {
    setWorking(true);setError('');setDirty(true);onChange({name:profile,revision,dirty:true});
    try {const items=await api('/saved/command');setSaved(items);const item=items.find((x:Data)=>x.name===profile);if(profile&&!item)throw Error('저장된 명령이 없습니다. 저장된 다른 명령을 선택하세요.');choose(item);setMessage('최신 저장 내용을 불러왔습니다. Preflight를 다시 검사하세요.');}
    catch(e){setError((e as Error).message);}finally{setWorking(false);}
  }
  useEffect(()=>{if(!active||initialized.current)return;let live=true;const controller=new AbortController();setLoading(true);(async()=>{
    try {const items=await api('/saved/command','GET',undefined,controller.signal);if(!live)return;initialized.current=true;setSaved(items);let previous='';try{previous=localStorage.getItem(storageKey)||'';}catch{}
      const item=items.find((x:Data)=>x.name===previous);
      if(previous&&!item){setProfile(previous);setName(previous);setDirty(true);setError('이전에 선택한 명령이 없습니다. 저장된 다른 명령을 직접 선택하세요.');onChange({name:previous,revision:'',dirty:true});}
      else choose(item);
    }catch(e){if(live){setError((e as Error).message);onChange({name:'',revision:'',dirty:true});}}
    finally{if(live)setLoading(false);}
  })();return()=>{live=false;controller.abort();};},[storageKey,active]);
  useEffect(()=>{setPreview(null);previewSequence.current+=1;},[previewSignature]);
  function edit(field:'name'|'single'|'dual',value:string) {
    if(field==='name')setName(value);else if(field==='single')setSingle(value);else setDual(value);
    setDirty(true);setPreview(null);setError('');setMessage('');onChange({name:profile,revision,dirty:true});
  }
  async function save() {
    setWorking(true);setError('');setMessage('');
    try {const result=await api('/saved/command','PUT',{name,data:template});const item={...result,name};setSaved(old=>[...old.filter(x=>x.name!==name),item].sort((a,b)=>a.name.localeCompare(b.name)));choose(item);setMessage('공통 명령을 저장했습니다. 각 TC의 이름과 COM 값은 실행 시 자동 치환됩니다.');}
    catch(e){setError((e as Error).message);}finally{setWorking(false);}
  }
  async function showPreview() {
    const signature=previewSignature, sequence=++previewSequence.current;
    setWorking(true);setError('');setPreview(null);
    try {const value=await api('/commands/preview','POST',previewRequest);if(latestPreview.current===signature&&previewSequence.current===sequence)setPreview(value);}
    catch(e){if(latestPreview.current===signature&&previewSequence.current===sequence)setError((e as Error).message);}finally{setWorking(false);}
  }
  return <SettingsPanel fold={fold} name="command" number="02" title="TC 실행 명령 설정" summary={loading?'설정 불러오는 중':`${profile||(simulation?'기본 Mock 명령':'명령 저장 필요')}${dirty?' · 저장 필요':''}`} defaultOpen={false}>
    <p className="gt-command-help">{simulation?'현재는 치환 결과를 Mock에서 확인하며 실제 명령은 실행하지 않습니다.':'Windows에 설정된 Python으로 TC를 실행합니다. Single 기본 명령은 python3 {tc_path} -p {com_a}입니다. python/python3는 Windows에 설정된 실행 파일을 사용합니다. 미리보기는 실행하지 않습니다.'}</p>
    <div className="gt-row"><label>저장된 명령<select aria-label="저장된 실행 명령" value={profile} disabled={loading||working} onChange={e=>choose(saved.find(x=>x.name===e.target.value))}><option value="">{simulation?'기본 Mock 명령':'실행 명령을 저장·선택하세요'}</option>{profile&&!saved.some(item=>item.name===profile)&&<option value={profile}>찾을 수 없음 · {profile}</option>}{saved.map(item=><option key={item.name} value={item.name}>{item.name}</option>)}</select></label><button disabled={loading||working} onClick={reload}>명령 다시 불러오기</button></div>
    <fieldset className="gt-command-editor" disabled={loading||working}>
      <label>명령 프로파일 이름<input name="command-profile" autoComplete="off" spellCheck={false} aria-label="실행 명령 이름" maxLength={80} value={name} onChange={e=>edit('name',e.target.value)}/></label>
      <p className="gt-command-help">첫 줄은 실행 파일, 다음 줄부터는 인자를 하나씩 입력하세요. 공백이 있는 경로도 한 줄에 입력하며 따옴표로 감싸지 않습니다.</p>
      {!simulation&&<p className="gt-command-help">Dual은 -n에 Board A 노드명, -n2에 Board B 노드명을 전달합니다. 연결 설정에서 두 노드명을 확인하세요.</p>}
      <div className="gt-command-columns"><label>Single 명령<textarea name="single-command" autoComplete="off" aria-label="Single 실행 명령" spellCheck={false} rows={6} value={single} onChange={e=>edit('single',e.target.value)}/></label><label>Dual 명령<textarea name="dual-command" autoComplete="off" aria-label="Dual 실행 명령" spellCheck={false} rows={6} value={dual} onChange={e=>edit('dual',e.target.value)}/></label></div>
      <dl className="gt-command-tokens"><dt>{'{tc_name}'}</dt><dd>TC 파일명, 확장자 제외 · 예: 01_boot</dd><dt>{'{tc_file}'}</dt><dd>TC 파일명, 확장자 포함 · 예: 01_boot.py</dd><dt>{'{tc_path}'}</dt><dd>TC 상대 경로 · 예: boot/01_boot.py</dd><dt>{'{com_a}'} / {'{com_b}'}</dt><dd>선택한 Board A / B의 COM 포트</dd><dt>{'{node_a}'} / {'{node_b}'}</dt><dd>선택한 Board A / B의 노드명 · Dual용</dd></dl>
      <p className="gt-command-help">TC 자리표시자는 위 3개 중 하나를 한 번 사용합니다. Single은 COM A, Dual은 노드명 A/B 쌍 또는 기존 COM A/B 쌍을 사용합니다. 자리표시자는 각각 별도 줄에 넣으세요. 암호·토큰은 입력하지 마세요.</p>
      <div className="gt-row"><button onClick={save} disabled={!name.trim()}>명령 저장 / 수정</button><span className="gt-muted">{dirty?'저장 후 Preflight를 다시 검사하세요.':revision?'저장 버전 '+revision.slice(0,12):simulation?'기본 Mock 명령 사용 중':'명령 저장 필요'}</span></div>
    </fieldset>
    <div className="gt-row gt-command-preview-controls"><label>미리 볼 TC<select aria-label="명령 미리보기 TC" value={selection} disabled={!tests.length||working} onChange={e=>setPreviewTc(e.target.value)}>{tests.map(item=><option key={item.id} value={item.id}>{item.name} · {item.kind}</option>)}</select></label><button disabled={loading||working||!selection} onClick={showPreview}>치환 명령 미리보기</button></div>
    {error&&<div role="alert" className="gt-alert error">{error}</div>}
    {message&&<p className="gt-command-message" role="status">{message}</p>}
    {preview&&<div className="gt-command-preview" data-testid="command-preview"><strong>{simulation?'Mock 치환 미리보기':'명령 치환 미리보기'} · 실행하지 않음</strong><p>{preview.kind} · {tc?.name}</p><pre>{JSON.stringify(preview.argv,null,2)}</pre><small>각 배열 항목을 하나의 인자로 전달합니다. 실제 실행 연결은 Adapter 검증 후 가능합니다.</small></div>}
  </SettingsPanel>;
}

export default function TestPage({standalone=false,bspJob=null,active=true,presentation='workspace',settingsFold}:{standalone?:boolean;bspJob?:Data|null;active?:boolean;presentation?:'workspace'|'settings'|'hidden';settingsFold?:SettingsFold}) {
  const globalSettings=presentation==='settings';
  const [catalog,setCatalog]=useState<Data|null>(null), [branch,setBranch]=useState(liveView?'shared':'demo/main');
  const [source,setSource]=useState<SourceState|null>(null),[sourceApplying,setSourceApplying]=useState(false);
  const catalogEpoch=useRef(0);
  const [cap,setCap]=useState<Data|null>(null), [boards,setBoards]=useState<Data[]>([]), [ports,setPorts]=useState<Data|null>(null);
  const [selected,setSelected]=useState<string[]>([]);
  const [connection,setConnection]=useState<Data>(liveView?{a:{host:'',board_id:'',com:''},b:{host:'',board_id:'',com:''}}:emptyConnection), [manual,setManual]=useState(false);
  const [scenario,setScenario]=useState('pass'), [speed,setSpeed]=useState(1), [jobId,setJobId]=useState('');
  const [jobs,setJobs]=useState<Data[]>([]), [job,setJob]=useState<Data|null>(null);
  const [cancelRun,setCancelRun]=useState<{id:string;version:number}|null>(null);
  const [run,setRun]=useState<Data|null>(null), [history,setHistory]=useState<Data[]>([]), [tab,setTab]=useState('execution');
  const [suites,setSuites]=useState<Data[]>([]), [profiles,setProfiles]=useState<Data[]>([]), [suiteRevision,setSuiteRevision]=useState('');
  const [suiteName,setSuiteName]=useState('My suite'), [profileName,setProfileName]=useState('My connection');
  const [checked,setChecked]=useState(''), [error,setError]=useState(''), [notice,setNotice]=useState(''), [busy,setBusy]=useState(false), [online,setOnline]=useState(true);
  const [focusTc,setFocusTc]=useState(''), [events,setEvents]=useState<Data[]>([]);
  const [command,setCommand]=useState<CommandChoice>({name:'',revision:'',dirty:true});
  const [tcRepeats,setTcRepeats]=useState<Record<string,number>>({}),[cycles,setCycles]=useState(1);
  const [workspaceView,setWorkspaceView]=useState('results');
  const [fold,setFold]=useState<SettingsFold>();
  useEffect(()=>{if(settingsFold)setFold(settingsFold)},[settingsFold]);
  const initialized=useRef(false);
  const [catalogHidden,setCatalogHidden]=useState(()=>{try{return localStorage.getItem('gui-catalog-hidden')==='true';}catch{return false;}});
  const [catalogWidth,setCatalogWidth]=useState(()=>{try{const n=Number(localStorage.getItem('gui-catalog-width'));return Number.isFinite(n)&&n>=240?Math.min(600,n):300;}catch{return 300;}});
  const resize=useRef<{x:number;width:number}|null>(null);
  useEffect(()=>{try{localStorage.setItem('gui-catalog-hidden',String(catalogHidden));localStorage.setItem('gui-catalog-width',String(catalogWidth));}catch{}},[catalogHidden,catalogWidth]);
  function changeWidth(value:number){setCatalogWidth(Math.max(240,Math.min(600,Math.round(value))));}

  const current=useRef('');
  const moduleScope=useModuleSelection({job:bspJob,catalog,branch,active,load:api});
  const scopeRef=useRef(moduleScope.active);scopeRef.current=moduleScope.active;
  const scopeKey=useRef(''),appliedScope=useRef('');
  useEffect(()=>{
    if(scopeKey.current===moduleScope.contextKey)return;
    const wasScoped=!!scopeKey.current;scopeKey.current=moduleScope.contextKey;appliedScope.current='';
    setChecked('');setSuiteRevision('');setTcRepeats({});setCycles(1);
    if(moduleScope.active){setSelected([]);setJobId('');}
    else if(wasScoped)setSelected((catalog?.tests||[]).filter((test:Data)=>!test.disabled_reason).map((test:Data)=>test.id));
  },[moduleScope.contextKey,moduleScope.active]);
  useEffect(()=>{
    const selection=moduleScope.selection;
    if(!moduleScope.active||!selection||!moduleScope.applicationKey||appliedScope.current===moduleScope.applicationKey)return;
    const automaticSelection=moduleScope.readOnly&&selection.tc_ids.length>0&&selection.tests.length===selection.tc_ids.length&&selection.tests.every(test=>selection.tc_ids.includes(test.id)&&!test.disabled_reason);
    if(moduleScope.blockedReason&&!automaticSelection)return;
    appliedScope.current=moduleScope.applicationKey;
    setSelected([...selection.tc_ids]);setTcRepeats({});if(moduleScope.readOnly)setCycles(1);setChecked('');setSuiteRevision('');
  },[moduleScope.active,moduleScope.applicationKey,moduleScope.selection,moduleScope.blockedReason,moduleScope.readOnly]);
  const moduleDraftReady=!moduleScope.active||(!!moduleScope.applicationKey&&appliedScope.current===moduleScope.applicationKey);
  const moduleBlocked=moduleScope.active?moduleScope.blockedReason||(!moduleDraftReady?'모듈 TC 확인 중':''):'';
  const tests:Data[]=moduleScope.active?moduleScope.tests:catalog?.tests||[];
  const testsById=useMemo(()=>new Map(tests.map(t=>[t.id,t])),[tests]);
  const selectedSet=useMemo(()=>new Set(selected),[selected]);
  const needsDual=selected.some(id=>testsById.get(id)?.kind==='Dual');
  const selectedRepeats=Object.fromEntries(selected.map(id=>[id,tcRepeats[id]||1]));
  const plannedCount=selected.reduce((n,id)=>n+(tcRepeats[id]||1),0)*cycles;
  const request={tc_ids:selected,tc_repeats:selectedRepeats,cycles, connection:{a:connection.a,b:needsDual?connection.b:null}, source_revision:catalog?.revision||'', suite_revision:suiteRevision, job_id:moduleScope.active?null:jobId||null, scenario,speed, execution:cap?.hardware?'hardware':'mock', command_profile:command.name||null, command_revision:command.revision,...(moduleScope.active&&typeof moduleScope.context?.attempt_id==='string'?{module_context:moduleScope.context}:{})};
  const signature=JSON.stringify(request);
  const sourceBlocked=!source?'TC 소스 설정을 확인하고 있습니다.':!source.execution.ready?source.execution.reason||'TC 소스 실행 준비가 필요합니다.':'';
  const historyScopeReason=run&&(moduleScope.active||run.module_context)?!sameModuleContext(run.module_context,moduleScope.context)?'현재 모듈과 다른 실행 기록입니다.':moduleBlocked:'';
  async function perform(fn:()=>Promise<void>) {setBusy(true);setError('');setNotice('');try{await fn();}catch(e){setError((e as Error).message);}finally{setBusy(false);}}
  async function refreshLists(){const [h,s,p,j]=await Promise.all([api('/runs'),api('/saved/suite'),api('/saved/profile'),api('/demo/jobs')]);setHistory(h);setSuites(s);setProfiles(p);setJobs(j);}
  async function chooseRun(id:string){current.current=id; const r=await api('/runs/'+id);if(current.current===id){setRun(r);localStorage.setItem(lastRunKey,id);}}
  useEffect(()=>{if(!active||initialized.current)return;let live=true;const controller=new AbortController();
    const load=(path:string)=>api(path,'GET',undefined,controller.signal),catalogTicket=catalogEpoch.current;
    (async()=>{
      try {const ca=await load('/capabilities');if(!live)return;
        const [c,b,po,h,s,p,j]=await Promise.all(['/catalog','/boards','/ports','/runs','/saved/suite','/saved/profile','/demo/jobs'].map(load));
        if(!live)return;
        let previous:Data|null=null;let id='';try{id=localStorage.getItem(lastRunKey)||'';}catch{}
        if(id){try{previous=await load('/runs/'+id);}catch{if(!live)return;try{localStorage.removeItem(lastRunKey);}catch{}}}
        if(!live)return;
        initialized.current=true;setCap(ca);
        if(!ca.simulation)setConnection({a:b.boards[0]||{host:'',board_id:'',com:''},b:b.boards[1]||b.boards[0]||{host:'',board_id:'',com:''}});
        if(catalogEpoch.current===catalogTicket){setBranch(c.branch);setCatalog(c);if(!scopeRef.current)setSelected(c.tests.filter((t:Data)=>!t.disabled_reason).map((t:Data)=>t.id));}
        setBoards(b.boards);setPorts(po);setHistory(h);setSuites(s);setProfiles(p);setJobs(j);
        if(previous){current.current=previous.id;setRun(previous);}
      }catch(e){if(live)setError((e as Error).message);}
    })();return()=>{live=false;controller.abort();};},[active]);
  useEffect(()=>{if(!active)return;let pending=false,live=true;const controller=new AbortController();
    const load=(path:string,method='GET')=>api(path,method,undefined,controller.signal);
    const timer=setInterval(async()=>{if(pending||!initialized.current)return;pending=true;try{
      const id=current.current;
      if(id){const r=await load('/runs/'+id);if(!live)return;
        if(current.current===id){setRun(old=>old&&old.id===id&&old.version>r.version?old:r);const events=await load('/runs/'+id+'/events');if(!live)return;if(current.current===id)setEvents(events);}
        if(!live)return;await load('/runs/'+id+'/heartbeat','POST');if(!live)return;}
      if(jobId){const job=await load('/demo/jobs/'+jobId);if(!live)return;setJob(job);}
      const history=await load('/runs');if(!live)return;setHistory(history);setOnline(true);
    }catch{if(live)setOnline(false);}finally{pending=false;}},700);
    return()=>{live=false;controller.abort();clearInterval(timer);};},[jobId,active]);
  async function act(action:string,data:Data={}) {if(!run)return;const r=await api(`/runs/${run.id}/actions/${action}`,'POST',{expected_version:run.version,data});setRun(r);}
  async function retryCase(id:string) {
    if(!run)return;
    if(historyScopeReason)throw new Error(historyScopeReason);
    const payload={tc_ids:[id],source_revision:run.source_revision,suite_revision:'',connection:run.connection_snapshot,
      parent_run_id:run.id,job_id:null,scenario:run.scenario,speed:run.speed,execution:run.simulation?'mock':'hardware',
      command_profile:command.name||null,command_revision:command.revision,...(run.module_context?{module_context:run.module_context}:{})};
    await api('/preflight','POST',payload);
    const r=await api('/runs','POST',payload);
    current.current=r.id;setRun(r);setFocusTc('');setTab('execution');localStorage.setItem(lastRunKey,r.id);
    await refreshLists();setNotice('실패 TC 하나를 새 Run으로 재실행합니다. 원본 결과는 Run 이력에 유지됩니다. 개별 재실행은 Dashboard 전체 판정을 갱신하지 않습니다.');
  }
  async function reverifyRun(){
    if(!run)return;if(historyScopeReason)throw new Error(historyScopeReason);
    const r=await api('/runs','POST',{...request,tc_ids:run.tests.map((test:Data)=>test.id),source_revision:run.source_revision,suite_revision:'',tc_repeats:run.tc_repeats||{},cycles:run.cycles||1,connection:run.connection_snapshot,parent_run_id:run.id,module_context:run.module_context});current.current=r.id;setRun(r);
  }
  function toggle(ids:string[],on:boolean){if(moduleScope.readOnly||!moduleDraftReady)return;setSelected(old=>{const previous=new Set(old),changed=new Set(ids);return on?[...old,...ids.filter(id=>!previous.has(id))]:old.filter(id=>!changed.has(id))});setSuiteRevision('');}
  function reorder(ids:string[]){if(moduleScope.readOnly||!moduleDraftReady)return;setSelected(ids);setSuiteRevision('');setChecked('');}
  function closeSettings(){setWorkspaceView('results');document.getElementById('gt-tab-settings')?.focus();}
  const controlling=run?.controller===session;
  const attempts:Data[]=run?.attempts.filter((a:Data)=>!focusTc||a.tc_id===focusTc)||[];
  return <div id="gui-test-settings" hidden={presentation==='hidden'} data-standalone={standalone||undefined} className={'gt'+(globalSettings?' gt-global-settings':'')} onPointerDownCapture={e=>{e.currentTarget.dataset.input="pointer"}} onKeyDownCapture={e=>{e.currentTarget.dataset.input="keyboard"}}>
    {cancelRun&&<AuditDialog title="테스트 중단 확인" onClose={()=>setCancelRun(null)} error={error} busy={busy}><p>Run {cancelRun.id}의 테스트를 중단할까요? 실행 결과와 로그는 보존됩니다.</p><div className="gt-dialog-actions"><button type="button" autoFocus onClick={()=>setCancelRun(null)}>계속 실행</button><button type="button" className="gt-danger" disabled={busy} onClick={()=>perform(async()=>{const confirmed=cancelRun;const result=await api(`/runs/${confirmed.id}/actions/cancel`,'POST',{expected_version:confirmed.version,data:{}});if(current.current===confirmed.id)setRun(result);setCancelRun(null)})}>테스트 중단</button></div></AuditDialog>}
    {busy&&!cancelRun&&<p role="status" className="gt-busy">처리 중…</p>}
    <div className="gt-intro" hidden={globalSettings}><div><span className="gt-eyebrow">GUI TEST WORKSPACE</span><h2>Test 현황</h2></div><span className={'gt-status '+(online?'pass':'error')}>{online?'● 실행 관리자 연결됨':'● 연결 끊김 · 마지막 상태'}</span></div>
    <p hidden={!globalSettings} role="status" className="gt-muted">GUI Test · {online?'실행 관리자 조회 중':'연결 끊김 · 마지막 확인 상태'}</p>
    <div className="gt-demo" hidden={globalSettings}><strong>{!cap?'연결 확인 중':cap.simulation?'MOCK DEMO':liveView?'실제 연결 모드':'WINDOWS RUNNER'}</strong><span>{cap?.hardware?'Linux Dashboard에서 관리 · Windows Python과 공유 폴더 TC로 실행':cap?.mode==='standalone'?'Windows 단독 모드 · 로컬 Run 저장':'Dashboard 통합 모드 · 별도 데모 Job 사용'}<br/>{cap?.hardware?'선택한 Windows COM을 TC에 전달합니다. 보드 이미지 검증·운영 Job 자동 반영은 아직 연결되지 않았습니다.':'실제 TC·RBM은 미연동입니다. 장비와 운영 Dashboard 결과를 변경하지 않습니다.'}</span></div>
    {error&&!cancelRun&&<div role="alert" className="gt-alert error">{error}<button onClick={()=>setError('')}>닫기</button></div>}
    {cap?.connection&&!cap.connection.ready&&<details className="gt-panel gt-connection-details" aria-label="실행기 연결 상태">
      <summary>{cap.connection.state==='unconfigured'?'미설정':'미연결'}</summary>
      <div className="gt-connection-content"><p>{cap.connection.message}</p>
      <p>실제 TC와 등록 보드가 연결되면 여기에 표시됩니다. 현재 테스트 실행은 사용할 수 없습니다.</p>
      <button type="button" onClick={()=>location.reload()}>연결 다시 확인</button>
      <h4>연결 준비 안내</h4><p>Linux와 Windows에서 설정 마법사의 연결 설정을 저장하고 실행기를 시작하세요. Linux API와 worker에는 같은 실행기 토큰이 필요합니다. 설정 변경 후 두 프로세스를 다시 시작하세요.</p>{cap.mode==='standalone'&&<p>이 단독 화면에서는 연결 준비 상태를 확인합니다. 실제 TC 실행은 Linux 통합 대시보드를 사용하세요.</p>}</div>
    </details>}
    {notice&&<div role="status" className="gt-alert pass">{notice}</div>}
    <div className="gt-workspace-tabs gt-workspace-toolbar" hidden={globalSettings}><button className="gt-icon-toggle" aria-label={catalogHidden?'TC 검색 패널 보이기':'TC 검색 패널 숨기기'} title={catalogHidden?'TC 검색 패널 보이기':'TC 검색 패널 숨기기'} aria-expanded={!catalogHidden} aria-controls="gt-catalog-panel" onClick={()=>setCatalogHidden(!catalogHidden)}><svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" aria-hidden="true"><rect x="3" y="4" width="18" height="16" rx="2"/><path d="M9 4v16"/><path d={catalogHidden?'m13 9 3 3-3 3':'m16 9-3 3 3 3'}/></svg></button>
        <label className="gt-run-picker"><span>세션</span><select aria-label="Run 이력" title={run?.id||'실행 세션 선택'} value={run?.id||''} onChange={e=>perform(()=>chooseRun(e.target.value))}><option value="">Run 선택</option>{history.map(h=><option key={h.id} value={h.id}>{h.id.slice(0,8)} · {h.state} · {h.overall_result}</option>)}</select></label>
        <button id="gt-tab-settings" className="gt-icon-toggle" aria-label="연결 및 실행 설정" title={workspaceView==='settings'?'설정 닫기 · 결과로 돌아가기':'연결 및 실행 설정'} aria-expanded={workspaceView==='settings'} aria-controls="gt-settings-view" onClick={()=>workspaceView==='settings'?closeSettings():setWorkspaceView('settings')}><svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" aria-hidden="true"><path d="m9 3-.6 2.2-2 .9-2.1-.6-2 3.5 1.6 1.6v2.8L2.3 15l2 3.5 2.1-.6 2 .9L9 21h4l.6-2.2 2-.9 2.1.6 2-3.5-1.6-1.6v-2.8L19.7 9l-2-3.5-2.1.6-2-.9L13 3Z"/><circle cx="11" cy="12" r="3"/></svg></button>
    </div>
    <div className={'gt-layout'+(catalogHidden&&!globalSettings?' gt-catalog-hidden':'')} style={{'--gt-catalog-width':catalogWidth+'px'} as CSSProperties}><aside id="gt-catalog-panel" hidden={catalogHidden&&!globalSettings} className="gt-panel gt-catalog">
      <div className="gt-resize" role="separator" aria-label="TC 검색 패널 너비" aria-orientation="vertical" aria-valuemin={240} aria-valuemax={600} aria-valuenow={catalogWidth} tabIndex={0}
        onPointerDown={e=>{e.preventDefault();resize.current={x:e.clientX,width:e.currentTarget.parentElement!.getBoundingClientRect().width};e.currentTarget.setPointerCapture(e.pointerId);}}
        onPointerMove={e=>{if(resize.current)changeWidth(resize.current.width+e.clientX-resize.current.x);}}
        onPointerUp={e=>{resize.current=null;e.currentTarget.releasePointerCapture(e.pointerId);}} onPointerCancel={()=>{resize.current=null;}} onLostPointerCapture={()=>{resize.current=null;}}
        onKeyDown={e=>{if(['ArrowLeft','ArrowRight','Home','End'].includes(e.key)){e.preventDefault();changeWidth(e.key==='Home'?240:e.key==='End'?600:catalogWidth+(e.key==='ArrowRight'?20:-20));}}} title="드래그 또는 좌우 방향키로 너비 조절"/>

      <div className="gt-section-head"><h3>Test cases</h3><span>{selected.length}개 선택</span></div>
      {moduleScope.active&&<section className="gt-module-scope" aria-label="모듈 TC 대상"><label>대상 모듈<select aria-label="TC 대상 모듈" value={moduleScope.moduleId} disabled={busy} onChange={e=>moduleScope.selectModule(e.target.value)}>{moduleScope.modules.map(module=><option key={module.id} value={module.id}>{module.name}</option>)}</select></label><span>{moduleScope.readOnly?'자동 장비 시험 · 읽기 전용':`${tests.length}개 자동 검색`}</span>{moduleBlocked&&<span className="gt-module-reason" role="status">{moduleBlocked}</span>}{moduleScope.retryAvailable&&<button type="button" className="gt-module-retry" disabled={busy} onClick={moduleScope.retry}>모듈 TC 다시 확인</button>}</section>}
      <CaseTree tests={tests} selected={selected} selectionLocked={moduleScope.readOnly||!moduleDraftReady} onSelect={toggle} onReorder={reorder} repeats={tcRepeats} onRepeat={(id,count)=>{if(moduleScope.readOnly||!moduleDraftReady)return;setTcRepeats(old=>({...old,[id]:count}));setSuiteRevision('');setChecked('');}}/>

    </aside><div className="gt-main">
      <div id="gt-settings-view" className="gt-settings-view" role="region" aria-label="연결 및 실행 설정" onKeyDown={e=>{if(e.key==='Escape'&&!globalSettings){e.stopPropagation();closeSettings();}}} hidden={!globalSettings&&workspaceView!=='settings'}>
        <div className="gt-section-head"><button hidden={globalSettings} className="gt-settings-back" onClick={closeSettings}>← 결과로 돌아가기</button><h3>{globalSettings?'GUI Test 설정':'연결 및 실행 설정'}</h3><div className="gt-tree-actions"><button onClick={()=>setFold({open:false})}>설정 모두 접기</button><button onClick={()=>setFold({open:true})}>설정 모두 펼치기</button></div></div>
      <p className="gt-muted">GUI Test 설정은 소스 적용·연결 프로파일·명령·Suite의 버튼으로 각각 저장합니다. 보기 모드 적용은 이 브라우저를 새로 불러옵니다. BSP 설정 저장에는 포함되지 않습니다.</p>
      <SettingsPanel fold={fold} name="view-mode" title="Test 현황 보기 모드" summary="이 브라우저에 적용"><ExecutionViewSettings disabled={busy}/></SettingsPanel>

      <SettingsPanel fold={fold} name="source" title="소스 설정" summary={catalog?.branch||branch} defaultOpen={false}>
      <SourceSettings load={api} active={active} disabled={busy} onState={setSource} onApplying={setSourceApplying} onApplied={(state,nextCatalog)=>{
        catalogEpoch.current++;setSource(state);setCatalog(nextCatalog);setBranch(nextCatalog.branch);setSelected([]);setTcRepeats({});setCycles(1);setSuiteRevision('');setChecked('');
        setNotice('TC 소스를 적용했습니다. 새 TC 목록을 선택하고 Preflight를 다시 검사하세요. 기존 Run 기록은 유지됩니다.');
      }}/>
      {source?.active.kind==='legacy'&&<div className="gt-source-legacy"><p className="gt-muted">기존 소스 모드 · 아래 목록 이름은 기존 실행기/데모 설정입니다. 새 소스의 Git 브랜치는 소스 확인 후 선택합니다.</p>
      <label>기존 TC 목록<select aria-label="TC 브랜치" value={branch} disabled={busy||sourceApplying} onChange={e=>setBranch(e.target.value)}>{(cap?.branches||[branch]).map((b:string)=><option key={b}>{b}</option>)}</select></label>
      <button className="gt-wide" disabled={busy||sourceApplying} onClick={()=>perform(async()=>{const c=await api('/catalog?branch='+encodeURIComponent(branch));setCatalog(c);setChecked('');setNotice('TC 갱신 완료. 기존 Run 소스는 유지됩니다. 저장된 Suite의 버전을 다시 확인하세요.');})}>↻ TC 갱신</button></div>}
      <SourceGitInfo catalog={catalog} cap={cap} managed={!!source&&source.active.kind!=='legacy'}/>
      <small className="gt-hash gt-source-snapshot">TC 스냅샷 기준 {catalog?.revision||'미확인'}</small>
      </SettingsPanel>
      <SettingsPanel fold={fold} name="connection" number="01" title="연결 및 실행 준비" summary={`Board A · ${connection.a.board_id} / ${connection.a.com}${needsDual?` · Board B · ${connection.b.board_id} / ${connection.b.com}`:''}`}>
        <div className="gt-section-head"><label className="gt-inline"><input type="checkbox" checked={manual} onChange={e=>setManual(e.target.checked)}/>수동 보드 / COM 입력</label></div>
        <datalist id="gt-com-ports">{[...new Set([...boards.map(b=>b.com),...(ports?.ports||[]).map((p:Data)=>p.com)])].map(com=><option key={String(com)} value={String(com)}/>)}</datalist><div className="gt-boards">{(['a','b'] as const).map((role)=><fieldset key={role} disabled={role==='b'&&!needsDual}><legend>Board {role.toUpperCase()} <small>{role==='b'?'Dual TC 선택 시 사용':'Single / Dual'}</small></legend>{manual?<div className="gt-fields">{['host','board_id','com',...(cap?.hardware?['node']:[])].map(field=><label key={field}>{field}<input name={`board-${role}-${field}`} autoComplete="off" spellCheck={false} aria-label={`Board ${role.toUpperCase()} ${field}`} list={field==='com'?'gt-com-ports':undefined} value={connection[role][field]??''} onChange={e=>setConnection({...connection,[role]:{...connection[role],[field]:field==='node'?(e.target.value||null):e.target.value}})}/></label>)}</div>:<label>보드 · COM<select aria-label={`Board ${role.toUpperCase()}`} value={connection[role].board_id} onChange={e=>setConnection({...connection,[role]:boards.find(b=>b.board_id===e.target.value)})}>{boards.map(b=><option key={b.board_id} value={b.board_id}>{b.board_id} · {b.com}</option>)}</select><small>{connection[role].host}{connection[role].node?' · 노드 '+connection[role].node:''} · {cap?.hardware?'Windows COM 조회':'Mock 확인'}</small></label>}</fieldset>)}</div>
        {cap?.mode==='standalone'&&<p className="gt-muted">Windows 실제 COM 조회: {ports?.status} {ports?.ports.map((p:Data)=>p.com).join(', ')} · 실제 TC 실행은 Adapter 연결 후 가능</p>}
        <div className="gt-row"><select aria-label="연결 프로파일 불러오기" value="" onChange={e=>{const p=profiles.find(x=>x.name===e.target.value);if(p)setConnection({...emptyConnection,...p.connection,b:p.connection.b||emptyConnection.b});}}><option value="">연결 프로파일 선택</option>{profiles.map(p=><option key={p.name}>{p.name}</option>)}</select><input name="connection-profile" autoComplete="off" spellCheck={false} aria-label="프로파일 이름" value={profileName} onChange={e=>setProfileName(e.target.value)}/><button disabled={busy} onClick={()=>perform(async()=>{await api('/saved/profile','PUT',{name:profileName,data:{connection}});await refreshLists();setNotice('연결 프로파일 저장 완료. 실행 직전 다시 검증합니다.');})}>프로파일 저장</button></div>
        {!moduleScope.active&&cap?.mode==='dashboard'&&cap.simulation&&<div className="gt-row"><label>Dashboard Job (선택)<select aria-label="GUI Test Job" value={jobId} onChange={e=>setJobId(e.target.value)}><option value="">미연동 · 일반 TC 실행</option>{jobs.map(j=><option key={j.id} value={j.id}>{j.title}</option>)}</select></label><button disabled={busy} onClick={()=>perform(async()=>{const j=await api('/demo/jobs','POST');await refreshLists();setJobId(j.id);setJob(j);})}>격리 데모 Job 준비</button></div>}
      </SettingsPanel>
      {cap&&<CommandSettings active={active} fold={fold} mode={cap.mode+(cap.hardware?'-windows':'')} simulation={cap.simulation} tests={tests.filter(t=>selectedSet.has(t.id))} connection={connection} sourceRevision={catalog?.revision||''} onChange={value=>{setCommand(value);setChecked('');}}/>}
      <SettingsPanel fold={fold} name="execution" number="03" title="실행 설정" summary={`TC ${selected.length}개 · 전체 ${cycles}회 · 총 ${plannedCount}회 실행`}>
        <p className="gt-muted">실행 순서와 TC별 횟수는 왼쪽 목록에서 변경하세요.</p>
        <label>전체 목록 반복<input name="cycles" disabled={moduleScope.readOnly||!moduleDraftReady} autoComplete="off" spellCheck={false} aria-label="전체 목록 반복 횟수" type="number" min="1" max="100" step="1" value={cycles} onChange={e=>{const n=Number(e.target.value);if(Number.isInteger(n)&&n>=1&&n<=100){setCycles(n);setSuiteRevision('');setChecked('');}}}/><small>TC별 횟수대로 선택 목록을 실행한 뒤, 목록 전체를 {cycles}회 반복합니다. 총 {plannedCount}회 실행.</small></label>
        {cap?.simulation&&<div className="gt-row"><label>데모 시나리오<select aria-label="데모 시나리오" value={scenario} onChange={e=>setScenario(e.target.value)}><option value="pass">전체 PASS</option><option value="fail">2번째 FAIL 후 계속</option><option value="disconnect">COM 끊김 → 복구 → 재개</option><option value="timeout">Timeout → 재개</option><option value="unknown">종료 불명 UNKNOWN</option><option value="sync-failure">동기화 실패 → 자동 재시도</option><option value="sync-lost-response">동기화 응답 유실 → 멱등 재전송</option></select></label><label>데모 속도<select aria-label="데모 속도" value={speed} onChange={e=>setSpeed(Number(e.target.value))}><option value={.2}>0.2×</option><option value={1}>1×</option><option value={5}>5×</option></select></label></div>}
      </SettingsPanel>
      <SettingsPanel fold={fold} name="suite" title="Suite 관리" summary={`${suites.length}개 저장됨`}>
      <label>Suite 불러오기<select aria-label="Suite 불러오기" disabled={moduleScope.readOnly||!moduleDraftReady} value="" onChange={e=>perform(async()=>{const s=suites.find(x=>x.name===e.target.value);if(!s)return;if(s.source_revision!==catalog?.revision||s.tc_ids.some((id:string)=>testsById.get(id)?.content_hash!==s.tc_hashes[id]))throw Error('Suite 소스 또는 TC가 변경됐습니다. 목록을 검토하고 새 Suite로 저장하세요.');setSelected(s.tc_ids);setTcRepeats(s.tc_repeats||{});setCycles(s.cycles||1);setChecked('');setSuiteRevision(s.revision);})}><option value="">저장된 Suite 선택</option>{suites.map(s=><option key={s.name}>{s.name}</option>)}</select></label>
      <label>Suite 이름<input name="suite-name" autoComplete="off" spellCheck={false} aria-label="Suite 이름" value={suiteName} onChange={e=>setSuiteName(e.target.value)}/></label><button className="gt-wide" disabled={busy||sourceApplying||moduleScope.readOnly||!moduleDraftReady||!selected.length} onClick={()=>perform(async()=>{const s=await api('/saved/suite','PUT',{name:suiteName,data:{tc_ids:selected,branch:catalog?.branch,source_revision:catalog?.revision,tc_repeats:selectedRepeats,cycles}});setSuiteRevision(s.revision);await refreshLists();setNotice('Suite를 저장했습니다.');})}>Suite 저장 / 수정</button>
      </SettingsPanel>
      </div>
      <div id="gt-results-view" className="gt-results-view" role="region" aria-label="테스트 작업 영역" hidden={globalSettings||workspaceView!=='results'}>
      <section className="gt-panel gt-result-panel" aria-label="실행 결과">
        {run&&<>
          <div className="gt-run-head"><div><span className={'gt-status '+run.overall_result.toLowerCase()} data-testid="run-state">{run.state} · {run.overall_result}</span><small>{controlling?'이 브라우저가 제어 중':'관찰 모드'}</small></div></div>
          <div className="gt-run-progress gt-counts" aria-label="진행률 및 상태별 집계"><span>진행 <b>{run.progress.percent}%</b></span>{Object.entries(run.progress.counts).map(([k,v])=><span key={k}>{k} <b>{String(v)}</b></span>)}</div>
          <progress aria-label="TC 판정 진행률" value={run.progress.done} max={run.progress.total}/>
          <div className="gt-progress-summary" aria-label="진행 요약"><span title="PASS/FAIL 판정 완료 · 반복 실행 포함">완료 {run.progress.done}/{run.progress.total}회</span><span>{usageCost(run.progress.usage)}</span></div>
        </>}
        <section className="gt-execution-bar" aria-label="실행 조작">
          {sourceBlocked&&<p role="status" className="gt-source-blocked">{sourceBlocked}</p>}
          <div className="gt-row gt-launch">{plannedCount>10000&&<span role="alert">전체 실행은 최대 10,000회입니다. 반복 횟수를 줄이세요.</span>}<small>TC {selected.length}개 · 전체 {cycles}회 · 총 {plannedCount}회 실행 · {cap?.hardware?'Windows 실행':`${speed}× · ${scenario}`} · {connection.a.board_id}</small><button disabled={busy||sourceApplying||!!sourceBlocked||!!moduleBlocked||cap?.connection?.ready===false||command.dirty||!selected.length||plannedCount>10000} onClick={()=>perform(async()=>{await api('/preflight','POST',request);setChecked(signature);setNotice('Preflight 통과 · 시작 시 예약을 원자적으로 확보합니다.');})}><ActionIcon name="check"/>Preflight 검사</button><button className="gt-primary" disabled={busy||sourceApplying||!!sourceBlocked||!!moduleBlocked||cap?.connection?.ready===false||command.dirty||!online||checked!==signature} onClick={()=>perform(async()=>{const r=await api('/runs','POST',request);current.current=r.id;setRun(r);setFocusTc('');setTab('execution');localStorage.setItem(lastRunKey,r.id);await refreshLists();})}><ActionIcon name="play"/>테스트 시작</button></div>
          {run&&<>
            <div className="gt-row gt-controls"><button disabled={busy||!controlling||!['RUNNING','QUEUED'].includes(run.state)} onClick={()=>perform(()=>act('pause'))}><ActionIcon name="pause"/>일시 정지</button><button className="gt-primary" disabled={busy||cap?.connection?.ready===false||!controlling||run.state!=='PAUSED'||!run.environment_ready} onClick={()=>perform(()=>act('resume'))}><ActionIcon name="play"/>재개</button><button className="gt-danger" disabled={busy||!controlling||terminal(run)||run.state==='UNKNOWN'} onClick={()=>{setError('');setCancelRun({id:run.id,version:run.version})}}><ActionIcon name="stop"/>테스트 중단</button><button disabled={busy||!controlling||!['PAUSED','UNKNOWN'].includes(run.state)} onClick={()=>perform(()=>act(run.simulation?'demo-recover':'recover'))}>{run.simulation?'데모 연결 / 종료 확인':'Windows 종료 / 연결 재확인'}</button>{run.simulation&&<button disabled={busy||!controlling||terminal(run)} onClick={()=>perform(()=>act('demo-inject',{fault:'disconnect'}))}>다음 TC 오류 주입</button>}</div>
            <div className="gt-row gt-secondary-controls">{!controlling&&<><button disabled={busy} onClick={()=>perform(()=>act('request-control'))}>제어권 요청</button><button disabled={busy} onClick={()=>perform(()=>act('take-control'))}>만료된 제어권 인수</button></>}{controlling&&run.control_request&&<button disabled={busy} onClick={()=>perform(()=>act('grant-control'))}>제어권 이전 승인</button>}{terminal(run)&&<button disabled={busy||sourceApplying||!!sourceBlocked||!!historyScopeReason||cap?.connection?.ready===false||command.dirty} title={historyScopeReason||undefined} onClick={()=>perform(reverifyRun)}>새 Run으로 재검증</button>}</div>
            {historyScopeReason&&<small className="gt-history-scope-reason">재실행: {historyScopeReason}</small>}
          </>}
        </section>
        {!run?<div className="gt-empty">아직 선택한 실행 결과가 없습니다.<small>테스트를 시작하거나 위에서 세션을 선택하세요.</small></div>:<>
          <section className="gt-session-info" aria-label="세션 정보"><span className="gt-session-id">Run {run.id}</span>
          <div className="gt-target-summary"><small>실제 실행 대상</small><TargetLabel target={run.execution_targets}/>{run.simulation&&<small>Mock · 실보드 미연결</small>}</div>
          <UsageDetails key={run.id} usage={run.progress.usage} runTotal/>
          </section>
          {run.reason&&<div className="gt-alert">{run.reason}</div>}
          <div className="gt-result-details" aria-label="결과 상세">
          <div className="gt-tabs" role="tablist"><button role="tab" aria-selected={tab==='execution'} onClick={()=>setTab('execution')}>TC 결과 · 로그</button><button role="tab" aria-selected={tab==='report'} onClick={()=>setTab('report')}>결과 리포트</button><button role="tab" aria-selected={tab==='audit'} onClick={()=>setTab('audit')}>감사 이력</button></div>
          {tab==='execution'&&<><div className="gt-table-scroll"><table className="gt-table"><thead><tr><th>TC</th><th>유형</th><th>현재 결과</th><th>실행 대상</th><th>Attempts</th><th>토큰 · 비용</th></tr></thead><tbody>{run.tests.map((t:Data)=><tr key={t.id}><td><button onClick={()=>setFocusTc(t.id)}>{t.name}</button></td><td>{t.kind}</td><td><span className={'gt-status '+(run.results[t.id]||'pending').toLowerCase()}>{run.results[t.id]||'PENDING'}</span>{run.results[t.id]==='FAIL'&&<button className="gt-retry" aria-label={t.name+' 재실행'} disabled={busy||sourceApplying||!!sourceBlocked||!!historyScopeReason||cap?.connection?.ready===false||command.dirty||!online||!terminal(run)||!controlling} title={historyScopeReason||(terminal(run)?'원본 기록을 유지하고 이 TC만 새 Run으로 실행':'현재 Run 종료 후 재실행 가능')} onClick={()=>perform(()=>retryCase(t.id))}>Retry</button>}</td><td><TargetLabel target={run.targets_by_tc?.[t.id]}/></td><td>{run.attempts.filter((a:Data)=>a.tc_id===t.id).length}</td><td><UsageDetails key={run.id+':'+t.id} label={t.name+' 토큰·비용 상세'} usage={run.progress.usage?.cases?.find((c:Data)=>c.tc_id===t.id)}/></td></tr>)}</tbody></table></div><section className="gt-log-section" aria-label="실시간 로그"><div className="gt-section-head"><h4>로그</h4><button onClick={()=>setFocusTc('')}>전체 로그</button></div><div className="gt-logs">{attempts.map(a=><article key={a.id}><header>{a.tc_id} · 전체 {a.cycle||1}회차 / TC {a.iteration||1}회 · Attempt {a.ordinal} · {a.state} · {a.ended_at?((Date.parse(a.ended_at)-Date.parse(a.started_at))/1000).toFixed(2)+'s':'실행 중'}</header><pre>{a.stdout}{a.stderr}{a.reason?'\n'+a.reason:''}</pre><small>명령 argv: {JSON.stringify(a.executed_command_argv||a.resolved_command_argv)} · exit {String(a.exit_code)}</small><a href={`${BASE}/runs/${run.id}/logs/${a.id}/stdout`}>stdout 다운로드</a><a href={`${BASE}/runs/${run.id}/logs/${a.id}/stderr`}>stderr 다운로드</a></article>)}</div></section></>}
          {tab==='report'&&<div><h4>판정 {run.overall_result} · 동기화 {run.sync.status}</h4><p>{run.sync.reason}</p><p className="gt-hash">소스 {run.source_revision}<br/>Suite {run.suite_revision||'직접 선택'}<br/>명령 {run.command_snapshot?.name||'기본 Mock'} · {run.command_snapshot?.revision?.slice(0,12)||'이전 Run'}<br/>매핑 {run.link?.mapping_hash||'미연동'}<br/>시작 {run.started_at} / 종료 {run.ended_at||'진행 중'}</p><pre className="gt-json">{JSON.stringify(run.connection_snapshot,null,2)}</pre><div className="gt-row">{['pdf','html','csv','json','logs'].map(f=><a className="gt-download" key={f} href={`${BASE}/runs/${run.id}/report/${f}`}>{f==='logs'?'전체 로그 ZIP':f.toUpperCase()+' 다운로드'}</a>)}<button disabled={busy||!controlling||!['FAILED','BLOCKED'].includes(run.sync.status)} onClick={()=>perform(()=>act('retry-sync'))}>동기화 재시도</button></div></div>}
          {tab==='audit'&&<div className="gt-audit">{events.slice().reverse().map(e=><p key={e.seq}><time>{e.at}</time> {e.type} <small>{JSON.stringify(e.data)}</small></p>)}</div>}
          </div>
        </>}
      </section>
      {jobId&&job&&<section className="gt-panel"><div className="gt-section-head"><h3>격리 Dashboard 결과</h3><button disabled={busy} onClick={()=>perform(async()=>{await api(`/demo/jobs/${jobId}/change-baseline`,'POST');setNotice('데모 Job 기준을 변경했습니다. 진행 중 Run은 다음 TC 전에 정지합니다.');})}>데모 Job 기준 변경</button></div>{job.gui_revalidation?.status==='AWAITING_APPROVAL'&&<div className="gt-alert"><div><strong>재검증 승인 대기</strong><p>대상: {job.gui_revalidation.modules.join(', ')||'통합 검증'}</p><p>순서: {job.gui_revalidation.steps.join(' → ')}</p><button disabled={busy} onClick={()=>perform(async()=>{await api(`/demo/jobs/${jobId}/approve-revalidation`,'POST',{expected_version:job.version,data:{run_id:job.gui_revalidation.run_id}});setJob(await api(`/demo/jobs/${jobId}`));})}>재검증 계획 승인</button></div></div>}<p>운영 Job과 분리된 모의 상태입니다. 전체 Run 종료 후 모듈별 결과를 반영합니다.</p><table className="gt-table"><tbody>{job.modules.map((m:Data)=><tr key={m.id}><td>{m.name}</td><td>{m.stages.device_test.status}</td><td>{JSON.stringify(m.stages.device_test.result?.cases||{})}</td></tr>)}</tbody></table></section>}
    </div></div></div>
  </div>;
}
