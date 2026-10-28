import {useEffect, useId, useRef, useState, type ReactNode} from 'react';
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

function SettingsPanel({name, number, title, summary, children, compact=false, defaultOpen=true}: {
  name:string; number?:string; title:string; summary:string; children:ReactNode; compact?:boolean; defaultOpen?:boolean;
}) {
  const contentId=useId();
  const storageKey='gui-settings-panel:'+name;
  const [open,setOpen]=useState(()=>{
    try {const saved=localStorage.getItem(storageKey);return saved===null?defaultOpen:saved!=='collapsed';} catch {return defaultOpen;}
  });
  function toggle() {
    const next=!open;
    setOpen(next);
    try {localStorage.setItem(storageKey,next?'expanded':'collapsed');} catch { /* Folding still works without storage. */ }
  }
  return <section className={'gt-panel gt-settings-panel'+(compact?' gt-settings-compact':'')}>
    <h3><button className="gt-settings-toggle" type="button" aria-label={title} aria-expanded={open} aria-controls={contentId} onClick={toggle}>
      {number&&<span className="gt-settings-number" aria-hidden="true">{number}</span>}
      <span className="gt-settings-label"><span className="gt-settings-title">{title}</span><span className="gt-settings-summary">{summary}</span></span>
      <span className="gt-settings-action" aria-hidden="true">{open?'접기':'펼치기'}<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d={open?'m6 15 6-6 6 6':'m6 9 6 6 6-6'}/></svg></span>
    </button></h3>
    <div id={contentId} className="gt-settings-content" hidden={!open}>{children}</div>
  </section>;
}

function CaseGroup({folder, items, selected, onSelect}: {
  folder:string; items:Data[]; selected:string[]; onSelect:(ids:string[],on:boolean)=>void;
}) {
  const [open,setOpen]=useState(true);
  const listId=useId();
  const checkbox=useRef<HTMLInputElement>(null);
  const available=items.filter(t=>!t.disabled_reason);
  const count=available.filter(t=>selected.includes(t.id)).length;
  useEffect(()=>{if(checkbox.current)checkbox.current.indeterminate=count>0&&count<available.length;},[count,available.length]);
  return <div className="gt-case-group">
    <div className="gt-folder-head">
      <label className="gt-folder-select"><input ref={checkbox} type="checkbox" aria-label={'폴더 '+folder} checked={available.length>0&&count===available.length} disabled={!available.length} onChange={e=>onSelect(available.map(t=>t.id),e.target.checked)}/></label>
      <button type="button" aria-label={folder+' 폴더 목록'} aria-expanded={open} aria-controls={listId} onClick={()=>setOpen(!open)}>
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true"><path d={open?'m6 9 6 6 6-6':'m9 6 6 6-6 6'}/></svg>
        <span className="gt-folder-name">{folder}</span><span className="gt-folder-count">{count}/{available.length}</span>
      </button>
    </div>
    <ul id={listId} className="gt-case-list" hidden={!open}>{items.map(t=><li key={t.id}>
      <label className={'gt-tc'+(selected.includes(t.id)?' is-selected':'')+(t.disabled_reason?' is-disabled':'')} title={t.path}>
        <input type="checkbox" aria-label={'선택 '+t.name} disabled={!!t.disabled_reason} checked={selected.includes(t.id)} onChange={e=>onSelect([t.id],e.target.checked)}/>
        <span className="gt-tc-copy"><span className="gt-tc-name">{t.name}</span><small>{t.disabled_reason||`${t.timeout}s 제한`}</small></span>
        <span className={'gt-kind '+(t.kind==='Dual'?'dual':'single')}>{t.kind}</span>
      </label>
    </li>)}</ul>
  </div>;
}

function ExecutionOrder({selected, tests, onReorder}: {
  selected:string[]; tests:Data[]; onReorder:(ids:string[])=>void;
}) {
  const dragged=useRef('');
  const [dragging,setDragging]=useState('');
  const [target,setTarget]=useState<{id:string;after:boolean}|null>(null);
  const [announcement,setAnnouncement]=useState('');
  function clearDrag(){dragged.current='';setDragging('');setTarget(null);}
  function reorder(next:string[],id:string){
    if(next.every((value,index)=>value===selected[index]))return;
    onReorder(next);
    setAnnouncement(`${tests.find(t=>t.id===id)?.name||id} · ${next.indexOf(id)+1}번째로 이동했습니다.`);
  }
  return <>
    <p className="gt-order-hint">행을 끌어서 순서를 바꾸세요. 순서 번호를 선택해도 이동할 수 있습니다.</p>
    <ol className="gt-order" aria-label="TC 실행 순서">{selected.map((id,i)=>{
      const name=tests.find(t=>t.id===id)?.name||'누락: '+id;
      return <li key={id} draggable className={(dragging===id?'is-dragging ':'')+(target?.id===id?(target.after?'drop-after':'drop-before'):'')}
        onDragStart={e=>{if((e.target as HTMLElement).closest('select')){e.preventDefault();return;}dragged.current=id;setDragging(id);e.dataTransfer.effectAllowed='move';e.dataTransfer.setData('text/plain',id);}}
        onDragEnd={clearDrag}
        onDragOver={e=>{if(!dragged.current)return;e.preventDefault();e.dataTransfer.dropEffect='move';if(dragged.current===id){setTarget(null);return;}const bounds=e.currentTarget.getBoundingClientRect();setTarget({id,after:e.clientY>bounds.top+bounds.height/2});}}
        onDragLeave={e=>{if(!e.currentTarget.contains(e.relatedTarget as Node|null))setTarget(old=>old?.id===id?null:old);}}
        onDrop={e=>{e.preventDefault();const from=dragged.current;if(from&&from!==id&&selected.includes(from)&&e.dataTransfer.getData('text/plain')===from){const bounds=e.currentTarget.getBoundingClientRect();const after=e.clientY>bounds.top+bounds.height/2;const next=selected.filter(value=>value!==from);next.splice(next.indexOf(id)+(after?1:0),0,from);reorder(next,from);}clearDrag();}}>
        <svg className="gt-drag-handle" width="18" height="20" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><circle cx="9" cy="5" r="1.5"/><circle cx="15" cy="5" r="1.5"/><circle cx="9" cy="12" r="1.5"/><circle cx="15" cy="12" r="1.5"/><circle cx="9" cy="19" r="1.5"/><circle cx="15" cy="19" r="1.5"/></svg>
        <span className="gt-order-name">{name}</span>
        <select aria-label={name+' 실행 위치'} value={i} onChange={e=>{const next=selected.filter(value=>value!==id);next.splice(Number(e.target.value),0,id);reorder(next,id);}}>
          {selected.map((_,index)=><option key={index} value={index}>{index+1}번째</option>)}
        </select>
      </li>;
    })}</ol>
    {!selected.length&&<p className="gt-muted">왼쪽 목록에서 실행할 TC를 선택하세요.</p>}
    <span className="gt-sr-only" aria-live="polite" aria-atomic="true">{announcement}</span>
  </>;
}

type CommandChoice = {name:string; revision:string; dirty:boolean};
const defaultSingleCommand = ['mock-tc','{tc_path}','{com_a}'];
const defaultDualCommand = ['mock-tc','{tc_path}','{com_a}','{com_b}'];

function CommandSettings({mode, tests, connection, sourceRevision, onChange}: {
  mode:string; tests:Data[]; connection:Data; sourceRevision:string; onChange:(choice:CommandChoice)=>void;
}) {
  const [saved,setSaved]=useState<Data[]>([]), [profile,setProfile]=useState('');
  const [name,setName]=useState('My command'), [single,setSingle]=useState(defaultSingleCommand.join('\n')), [dual,setDual]=useState(defaultDualCommand.join('\n'));
  const [revision,setRevision]=useState(''), [dirty,setDirty]=useState(false), [loading,setLoading]=useState(true), [working,setWorking]=useState(false);
  const [error,setError]=useState(''), [message,setMessage]=useState(''), [preview,setPreview]=useState<Data|null>(null), [previewTc,setPreviewTc]=useState('');
  const selection=tests.some(t=>t.id===previewTc)?previewTc:tests[0]?.id||'';
  const tc=tests.find(t=>t.id===selection);
  const template={single:single.split('\n'),dual:dual.split('\n')};
  const previewRequest={tc_id:selection,source_revision:sourceRevision,connection:{a:connection.a,b:tc?.kind==='Dual'?connection.b:null},template};
  const previewSignature=JSON.stringify(previewRequest);
  const latestPreview=useRef(previewSignature);latestPreview.current=previewSignature;
  const previewSequence=useRef(0);
  const storageKey='gui-command-profile:'+mode;
  function remember(value:string){try{localStorage.setItem(storageKey,value);}catch{/* Saving the profile itself is server-side. */}}
  function choose(item:Data|undefined) {
    const value=item?.name||'';
    setProfile(value);setName(value||'My command');setSingle((item?.single||defaultSingleCommand).join('\n'));setDual((item?.dual||defaultDualCommand).join('\n'));
    setRevision(item?.revision||'');setDirty(false);setPreview(null);setError('');setMessage('');remember(value);
    onChange({name:value,revision:item?.revision||'',dirty:false});
  }
  async function reload() {
    setWorking(true);setError('');setDirty(true);onChange({name:profile,revision,dirty:true});
    try {const items=await api('/saved/command');setSaved(items);const item=items.find((x:Data)=>x.name===profile);if(profile&&!item)throw Error('저장된 명령이 없습니다. 기본 Mock 또는 다른 명령을 선택하세요.');choose(item);setMessage('최신 저장 내용을 불러왔습니다. Preflight를 다시 검사하세요.');}
    catch(e){setError((e as Error).message);}finally{setWorking(false);}
  }
  useEffect(()=>{let active=true;setLoading(true);(async()=>{
    try {const items=await api('/saved/command');if(!active)return;setSaved(items);let previous='';try{previous=localStorage.getItem(storageKey)||'';}catch{}
      const item=items.find((x:Data)=>x.name===previous);
      if(previous&&!item){setProfile(previous);setName(previous);setDirty(true);setError('이전에 선택한 명령이 없습니다. 기본 Mock 또는 다른 명령을 직접 선택하세요.');onChange({name:previous,revision:'',dirty:true});}
      else choose(item);
    }catch(e){if(active){setError((e as Error).message);onChange({name:'',revision:'',dirty:true});}}
    finally{if(active)setLoading(false);}
  })();return()=>{active=false;};},[storageKey]);
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
  return <SettingsPanel name="command" number="02" title="TC 실행 명령 설정" summary={loading?'설정 불러오는 중':`${profile||'기본 Mock 명령'}${dirty?' · 저장 필요':''}`} defaultOpen={false}>
    <p className="gt-command-help">공통 실행 명령을 한 번 저장하면 TC마다 이름과 COM 포트만 바뀝니다. 현재는 치환 결과를 Mock에서 확인하며 실제 Python·셸 명령은 실행하지 않습니다.</p>
    <div className="gt-row"><label>저장된 명령<select aria-label="저장된 실행 명령" value={profile} disabled={loading||working} onChange={e=>choose(saved.find(x=>x.name===e.target.value))}><option value="">기본 Mock 명령</option>{profile&&!saved.some(item=>item.name===profile)&&<option value={profile}>찾을 수 없음 · {profile}</option>}{saved.map(item=><option key={item.name} value={item.name}>{item.name}</option>)}</select></label><button disabled={loading||working} onClick={reload}>명령 다시 불러오기</button></div>
    <fieldset className="gt-command-editor" disabled={loading||working}>
      <label>명령 프로파일 이름<input aria-label="실행 명령 이름" maxLength={80} value={name} onChange={e=>edit('name',e.target.value)}/></label>
      <p className="gt-command-help">첫 줄은 실행 파일, 다음 줄부터는 인자를 하나씩 입력하세요. 공백이 있는 경로도 한 줄에 입력하며 따옴표로 감싸지 않습니다.</p>
      <div className="gt-command-columns"><label>Single 명령<textarea aria-label="Single 실행 명령" spellCheck={false} rows={6} value={single} onChange={e=>edit('single',e.target.value)}/></label><label>Dual 명령<textarea aria-label="Dual 실행 명령" spellCheck={false} rows={6} value={dual} onChange={e=>edit('dual',e.target.value)}/></label></div>
      <dl className="gt-command-tokens"><dt>{'{tc_name}'}</dt><dd>TC 파일명, 확장자 제외 · 예: 01_boot</dd><dt>{'{tc_file}'}</dt><dd>TC 파일명, 확장자 포함 · 예: 01_boot.py</dd><dt>{'{tc_path}'}</dt><dd>TC 상대 경로 · 예: boot/01_boot.py</dd><dt>{'{com_a}'} / {'{com_b}'}</dt><dd>선택한 Board A / B의 COM 포트</dd></dl>
      <p className="gt-command-help">TC 자리표시자는 위 3개 중 하나를 한 번 사용합니다. COM A는 필수이며 Dual에는 COM B도 필요합니다. 자리표시자는 각각 별도 줄에 넣으세요. 암호·토큰은 입력하지 마세요.</p>
      <div className="gt-row"><button onClick={save} disabled={!name.trim()}>명령 저장 / 수정</button><span className="gt-muted">{dirty?'저장 후 Preflight를 다시 검사하세요.':revision?'저장 버전 '+revision.slice(0,12):'기본 Mock 명령 사용 중'}</span></div>
    </fieldset>
    <div className="gt-row gt-command-preview-controls"><label>미리 볼 TC<select aria-label="명령 미리보기 TC" value={selection} disabled={!tests.length||working} onChange={e=>setPreviewTc(e.target.value)}>{tests.map(item=><option key={item.id} value={item.id}>{item.name} · {item.kind}</option>)}</select></label><button disabled={loading||working||!selection} onClick={showPreview}>치환 명령 미리보기</button></div>
    {error&&<div role="alert" className="gt-alert error">{error}</div>}
    {message&&<p className="gt-command-message" role="status">{message}</p>}
    {preview&&<div className="gt-command-preview" data-testid="command-preview"><strong>Mock 치환 미리보기 · 실행하지 않음</strong><p>{preview.kind} · {tc?.name}</p><pre>{JSON.stringify(preview.argv,null,2)}</pre><small>각 배열 항목을 하나의 인자로 전달합니다. 실제 실행 연결은 Adapter 검증 후 가능합니다.</small></div>}
  </SettingsPanel>;
}

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
  const [command,setCommand]=useState<CommandChoice>({name:'',revision:'',dirty:true});
  const current=useRef('');
  const tests:Data[]=catalog?.tests||[];
  const needsDual=selected.some(id=>tests.find(t=>t.id===id)?.kind==='Dual');
  const request={tc_ids:selected, connection:{a:connection.a,b:needsDual?connection.b:null}, source_revision:catalog?.revision||'', suite_revision:suiteRevision, job_id:jobId||null, scenario,speed, command_profile:command.name||null, command_revision:command.revision};
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
  function reorder(ids:string[]){setSelected(ids);setSuiteRevision('');setChecked('');}
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
      <SettingsPanel name="source" title="소스 설정" summary={catalog?.branch||branch} compact defaultOpen={false}>
      <label>Git 브랜치<select aria-label="TC 브랜치" value={branch} onChange={e=>setBranch(e.target.value)}>{(cap?.branches||['demo/main']).map((b:string)=><option key={b}>{b}</option>)}</select></label>
      <button className="gt-wide" disabled={busy} onClick={()=>perform(async()=>{const c=await api('/catalog?branch='+encodeURIComponent(branch));setCatalog(c);setChecked('');setNotice('TC 갱신 완료. 기존 Run 소스는 유지됩니다. 저장된 Suite의 버전을 다시 확인하세요.');})}>↻ TC 갱신</button>
      <small className="gt-hash" title={catalog?.revision}>현재 소스 {catalog?.revision?.slice(0,19)}… / {catalog?.branch}</small>
      </SettingsPanel>
      <div className="gt-catalog-tools"><label>TC 검색<input aria-label="TC 검색" placeholder="이름 · 경로 검색" value={search} onChange={e=>setSearch(e.target.value)}/></label>
      <label>연결 유형<select aria-label="연결 유형 필터" value={kind} onChange={e=>setKind(e.target.value)}><option value="all">전체 · Single + Dual</option><option>Single</option><option>Dual</option></select></label></div>
      <div className="gt-list-meta"><span>TC 목록</span><span>{shown.length} / {tests.length}개 표시</span></div>
      <div className="gt-tree" role="group" aria-label="테스트 케이스 목록">{folders.map(folder=><CaseGroup key={folder} folder={folder} items={shown.filter(t=>t.module===folder)} selected={selected} onSelect={toggle}/>)}
        {!shown.length&&<div className="gt-catalog-empty">{catalog?'검색 결과가 없습니다.':'TC 목록을 불러오는 중입니다.'}{catalog&&<button onClick={()=>{setSearch('');setKind('all');}}>검색·필터 초기화</button>}</div>}
      </div>
      <p className="gt-selection-note">필터 밖의 선택도 유지됩니다.</p>
      <SettingsPanel name="suite" title="Suite 관리" summary={`${suites.length}개 저장됨`} compact>
      <label>Suite 불러오기<select aria-label="Suite 불러오기" value="" onChange={e=>perform(async()=>{const s=suites.find(x=>x.name===e.target.value);if(!s)return;if(s.source_revision!==catalog?.revision||s.tc_ids.some((id:string)=>!tests.some(t=>t.id===id&&t.content_hash===s.tc_hashes[id])))throw Error('Suite 소스 또는 TC가 변경됐습니다. 목록을 검토하고 새 Suite로 저장하세요.');setSelected(s.tc_ids);setSuiteRevision(s.revision);})}><option value="">저장된 Suite 선택</option>{suites.map(s=><option key={s.name}>{s.name}</option>)}</select></label>
      <label>Suite 이름<input aria-label="Suite 이름" value={suiteName} onChange={e=>setSuiteName(e.target.value)}/></label><button className="gt-wide" disabled={busy||!selected.length} onClick={()=>perform(async()=>{const s=await api('/saved/suite','PUT',{name:suiteName,data:{tc_ids:selected,branch:catalog?.branch}});setSuiteRevision(s.revision);await refreshLists();setNotice('Suite를 저장했습니다.');})}>Suite 저장 / 수정</button>
      </SettingsPanel>
    </aside><div className="gt-main">
      <SettingsPanel name="connection" number="01" title="연결 및 실행 준비" summary={`Board A · ${connection.a.board_id} / ${connection.a.com}${needsDual?` · Board B · ${connection.b.board_id} / ${connection.b.com}`:''}`}>
        <div className="gt-section-head"><label className="gt-inline"><input type="checkbox" checked={manual} onChange={e=>setManual(e.target.checked)}/>수동 보드 / COM 입력</label></div>
        <datalist id="gt-com-ports">{[...new Set([...boards.map(b=>b.com),...(ports?.ports||[]).map((p:Data)=>p.com)])].map(com=><option key={String(com)} value={String(com)}/>)}</datalist><div className="gt-boards">{(['a','b'] as const).map((role)=><fieldset key={role} disabled={role==='b'&&!needsDual}><legend>Board {role.toUpperCase()} <small>{role==='b'?'Dual TC 선택 시 사용':'Single / Dual'}</small></legend>{manual?<div className="gt-fields">{['host','board_id','com'].map(field=><label key={field}>{field}<input aria-label={`Board ${role.toUpperCase()} ${field}`} list={field==='com'?'gt-com-ports':undefined} value={connection[role][field]} onChange={e=>setConnection({...connection,[role]:{...connection[role],[field]:e.target.value}})}/></label>)}</div>:<label>보드 · COM<select aria-label={`Board ${role.toUpperCase()}`} value={connection[role].board_id} onChange={e=>setConnection({...connection,[role]:boards.find(b=>b.board_id===e.target.value)})}>{boards.map(b=><option key={b.board_id} value={b.board_id}>{b.board_id} · {b.com}</option>)}</select><small>{connection[role].host} · Mock 확인</small></label>}</fieldset>)}</div>
        {cap?.mode==='standalone'&&<p className="gt-muted">Windows 실제 COM 조회: {ports?.status} {ports?.ports.map((p:Data)=>p.com).join(', ')} · 실제 TC 실행은 Adapter 연결 후 가능</p>}
        <div className="gt-row"><select aria-label="연결 프로파일 불러오기" value="" onChange={e=>{const p=profiles.find(x=>x.name===e.target.value);if(p)setConnection({...emptyConnection,...p.connection,b:p.connection.b||emptyConnection.b});}}><option value="">연결 프로파일 선택</option>{profiles.map(p=><option key={p.name}>{p.name}</option>)}</select><input aria-label="프로파일 이름" value={profileName} onChange={e=>setProfileName(e.target.value)}/><button disabled={busy} onClick={()=>perform(async()=>{await api('/saved/profile','PUT',{name:profileName,data:{connection}});await refreshLists();setNotice('연결 프로파일 저장 완료. 실행 직전 다시 검증합니다.');})}>프로파일 저장</button></div>
        {cap?.mode==='dashboard'&&<div className="gt-row"><label>Dashboard Job (선택)<select aria-label="GUI Test Job" value={jobId} onChange={e=>setJobId(e.target.value)}><option value="">미연동 · 일반 TC 실행</option>{jobs.map(j=><option key={j.id} value={j.id}>{j.title}</option>)}</select></label><button disabled={busy} onClick={()=>perform(async()=>{const j=await api('/demo/jobs','POST');await refreshLists();setJobId(j.id);setJob(j);})}>격리 데모 Job 준비</button></div>}
      </SettingsPanel>
      {cap&&<CommandSettings mode={cap.mode} tests={tests.filter(t=>selected.includes(t.id))} connection={connection} sourceRevision={catalog?.revision||''} onChange={value=>{setCommand(value);setChecked('');}}/>}
      <SettingsPanel name="execution" number="03" title="실행 순서와 데모 시나리오" summary={`TC ${selected.length}개 선택 · 순차 실행 · ${speed}×`}>
        <ExecutionOrder selected={selected} tests={tests} onReorder={reorder}/>
        <div className="gt-row"><label>데모 시나리오<select aria-label="데모 시나리오" value={scenario} onChange={e=>setScenario(e.target.value)}><option value="pass">전체 PASS</option><option value="fail">2번째 FAIL 후 계속</option><option value="disconnect">COM 끊김 → 복구 → 재개</option><option value="timeout">Timeout → 재개</option><option value="unknown">종료 불명 UNKNOWN</option><option value="sync-failure">동기화 실패 → 자동 재시도</option><option value="sync-lost-response">동기화 응답 유실 → 멱등 재전송</option></select></label><label>데모 속도<select aria-label="데모 속도" value={speed} onChange={e=>setSpeed(Number(e.target.value))}><option value={.2}>0.2×</option><option value={1}>1×</option><option value={5}>5×</option></select></label><button disabled={busy||command.dirty||!selected.length} onClick={()=>perform(async()=>{await api('/preflight','POST',request);setChecked(signature);setNotice('Preflight 통과 · 시작 시 예약을 원자적으로 확보합니다.');})}>Preflight 검사</button><button className="gt-primary" disabled={busy||command.dirty||!online||checked!==signature} onClick={()=>perform(async()=>{const r=await api('/runs','POST',request);current.current=r.id;setRun(r);setFocusTc('');setTab('execution');localStorage.setItem('gui-last-run',r.id);await refreshLists();})}>▶ 테스트 시작</button></div>
      </SettingsPanel>
      <section className="gt-panel"><div className="gt-section-head"><h3>04 <span>실행 및 결과</span></h3><select aria-label="Run 이력" value={run?.id||''} onChange={e=>perform(()=>chooseRun(e.target.value))}><option value="">Run 선택</option>{history.map(h=><option key={h.id} value={h.id}>{h.id.slice(0,8)} · {h.state} · {h.overall_result}</option>)}</select></div>
        {!run?<div className="gt-empty">Preflight 검사 후 테스트를 시작하세요.<small>브라우저를 닫아도 서버의 Run은 유지됩니다.</small></div>:<>
          <div className="gt-run-head"><div><span className={'gt-status '+run.overall_result.toLowerCase()} data-testid="run-state">{run.state} · {run.overall_result}</span><small>Run {run.id.slice(0,12)} · {controlling?'이 브라우저가 제어 중':'관찰 모드'}</small></div><strong>{run.progress.percent}%<small>{run.progress.done} / {run.progress.total} 판정 완료</small></strong></div>
          <progress aria-label="TC 판정 진행률" value={run.progress.done} max={run.progress.total}/>
          <div className="gt-counts">{Object.entries(run.progress.counts).map(([k,v])=><span key={k}>{k} <b>{String(v)}</b></span>)}</div>
          {run.reason&&<div className="gt-alert">{run.reason}</div>}
          <div className="gt-row gt-controls"><button disabled={busy||!controlling||!['RUNNING','QUEUED'].includes(run.state)} onClick={()=>perform(()=>act('pause'))}>Ⅱ 일시 정지</button><button disabled={busy||!controlling||run.state!=='PAUSED'||!run.environment_ready} onClick={()=>perform(()=>act('resume'))}>▶ 재개</button><button className="gt-danger" disabled={busy||!controlling||terminal(run)||run.state==='UNKNOWN'} onClick={()=>perform(()=>act('cancel'))}>■ 테스트 중단</button><button disabled={busy||!controlling||!['PAUSED','UNKNOWN'].includes(run.state)} onClick={()=>perform(()=>act('demo-recover'))}>데모 연결 / 종료 확인</button><button disabled={busy||!controlling||terminal(run)} onClick={()=>perform(()=>act('demo-inject',{fault:'disconnect'}))}>다음 TC 오류 주입</button></div>
          <div className="gt-row">{!controlling&&<><button disabled={busy} onClick={()=>perform(()=>act('request-control'))}>제어권 요청</button><button disabled={busy} onClick={()=>perform(()=>act('take-control'))}>만료된 제어권 인수</button></>}{controlling&&run.control_request&&<button disabled={busy} onClick={()=>perform(()=>act('grant-control'))}>제어권 이전 승인</button>}{terminal(run)&&<button disabled={busy||command.dirty} onClick={()=>perform(async()=>{const r=await api('/runs','POST',{...request,tc_ids:run.tests.map((t:Data)=>t.id),source_revision:run.source_revision,connection:run.connection_snapshot,parent_run_id:run.id});current.current=r.id;setRun(r);})}>새 Run으로 재검증</button>}</div>
          <div className="gt-tabs" role="tablist"><button role="tab" aria-selected={tab==='execution'} onClick={()=>setTab('execution')}>TC 결과 · 로그</button><button role="tab" aria-selected={tab==='report'} onClick={()=>setTab('report')}>결과 리포트</button><button role="tab" aria-selected={tab==='audit'} onClick={()=>setTab('audit')}>감사 이력</button></div>
          {tab==='execution'&&<><table className="gt-table"><thead><tr><th>TC</th><th>유형</th><th>현재 결과</th><th>Attempts</th></tr></thead><tbody>{run.tests.map((t:Data)=><tr key={t.id}><td><button onClick={()=>setFocusTc(t.id)}>{t.name}</button></td><td>{t.kind}</td><td><span className={'gt-status '+(run.results[t.id]||'pending').toLowerCase()}>{run.results[t.id]||'PENDING'}</span></td><td>{run.attempts.filter((a:Data)=>a.tc_id===t.id).length}</td></tr>)}</tbody></table><div className="gt-section-head"><h4>실시간 로그 · 과거 Attempt 포함</h4><button onClick={()=>setFocusTc('')}>전체 로그</button></div><div className="gt-logs">{attempts.map(a=><article key={a.id}><header>{a.tc_id} · Attempt {a.ordinal} · {a.state} · {a.ended_at?((Date.parse(a.ended_at)-Date.parse(a.started_at))/1000).toFixed(2)+'s':'실행 중'}</header><pre>{a.stdout}{a.stderr}{a.reason?'\n'+a.reason:''}</pre><small>명령 argv: {JSON.stringify(a.resolved_command_argv)} · exit {String(a.exit_code)}</small><a href={`${BASE}/runs/${run.id}/logs/${a.id}/stdout`}>stdout 다운로드</a><a href={`${BASE}/runs/${run.id}/logs/${a.id}/stderr`}>stderr 다운로드</a></article>)}</div></>}
          {tab==='report'&&<div><h4>판정 {run.overall_result} · 동기화 {run.sync.status}</h4><p>{run.sync.reason}</p><p className="gt-hash">소스 {run.source_revision}<br/>Suite {run.suite_revision||'직접 선택'}<br/>명령 {run.command_snapshot?.name||'기본 Mock'} · {run.command_snapshot?.revision?.slice(0,12)||'이전 Run'}<br/>매핑 {run.link?.mapping_hash||'미연동'}<br/>시작 {run.started_at} / 종료 {run.ended_at||'진행 중'}</p><pre className="gt-json">{JSON.stringify(run.connection_snapshot,null,2)}</pre><div className="gt-row">{['pdf','html','csv','json','logs'].map(f=><a className="gt-download" key={f} href={`${BASE}/runs/${run.id}/report/${f}`}>{f==='logs'?'전체 로그 ZIP':f.toUpperCase()+' 다운로드'}</a>)}<button disabled={busy||!controlling||!['FAILED','BLOCKED'].includes(run.sync.status)} onClick={()=>perform(()=>act('retry-sync'))}>동기화 재시도</button></div></div>}
          {tab==='audit'&&<div className="gt-audit">{events.slice().reverse().map(e=><p key={e.seq}><time>{e.at}</time> {e.type} <small>{JSON.stringify(e.data)}</small></p>)}</div>}
        </>}
      </section>
      {jobId&&job&&<section className="gt-panel"><div className="gt-section-head"><h3>격리 Dashboard 결과</h3><button disabled={busy} onClick={()=>perform(async()=>{await api(`/demo/jobs/${jobId}/change-baseline`,'POST');setNotice('데모 Job 기준을 변경했습니다. 진행 중 Run은 다음 TC 전에 정지합니다.');})}>데모 Job 기준 변경</button></div>{job.gui_revalidation?.status==='AWAITING_APPROVAL'&&<div className="gt-alert"><div><strong>재검증 승인 대기</strong><p>대상: {job.gui_revalidation.modules.join(', ')||'통합 검증'}</p><p>순서: {job.gui_revalidation.steps.join(' → ')}</p><button disabled={busy} onClick={()=>perform(async()=>{await api(`/demo/jobs/${jobId}/approve-revalidation`,'POST',{expected_version:job.version,data:{run_id:job.gui_revalidation.run_id}});setJob(await api(`/demo/jobs/${jobId}`));})}>재검증 계획 승인</button></div></div>}<p>운영 Job과 분리된 모의 상태입니다. 전체 Run 종료 후 모듈별 결과를 반영합니다.</p><table className="gt-table"><tbody>{job.modules.map((m:Data)=><tr key={m.id}><td>{m.name}</td><td>{m.stages.device_test.status}</td><td>{JSON.stringify(m.stages.device_test.result?.cases||{})}</td></tr>)}</tbody></table></section>}
    </div></div>
  </div>;
}
