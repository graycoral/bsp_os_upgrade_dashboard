import {useEffect,useId,useMemo,useState,type KeyboardEvent,type ReactNode} from 'react';
import './connector-mirror.css';

type Data=Record<string,any>;
export interface ConnectorMirrorSnapshot {
  schema:'connector-mirror-v1';
  fresh:boolean;
  inventory:Data;
  console:Data;
  errors:{events:Data[];cursor?:number};
  projection:Data|null;
  settings:Data;
  commands:Data[];
}
export interface ConnectorMirrorCommandRequest {
  runner_id:string;session_id:string;revision:string;
  action:'putty'|'apply-settings';body:Data;
}
interface Props {
  snapshot:ConnectorMirrorSnapshot|null;
  active:boolean;
  loading:boolean;
  error:string;
  busy:boolean;
  onRefresh:()=>void;
  onCommand:(command:ConnectorMirrorCommandRequest)=>Promise<void>;
  onSaveSettings:(body:Data)=>Promise<boolean>;
  onAbandon?:(command:Data)=>Promise<void>;
  controls?:ReactNode;
}
const stateLabels:Record<string,string>={CONNECTED:'연결됨',RUNNING:'실행 중',UNKNOWN:'확인 필요',RESERVED:'예약됨',DISCONNECTED:'미연결',ERROR:'오류',QUEUED:'Windows 전달 대기',APPLIED:'Windows 확인됨',FAILED:'실패',EXPIRED:'만료됨',PENDING:'적용 대기',BLOCKED:'적용 보류',UNCONFIGURED:'미설정',ABANDONED:'결과 불명 확인 완료'};
function when(value:unknown){if(value===undefined||value===null||value==='')return '미수신';const date=new Date(typeof value==='number'?value*1000:String(value));return Number.isNaN(date.getTime())?'미수신':date.toLocaleString('ko-KR')}
function rows(value:unknown):Data[]{return Array.isArray(value)?value:[]}
function text(value:unknown){return typeof value==='string'?value:''}
function tabKeys(event:KeyboardEvent<HTMLButtonElement>){const all=Array.from(event.currentTarget.parentElement?.querySelectorAll<HTMLButtonElement>('[role="tab"]')||[]),index=all.indexOf(event.currentTarget);let next=index;if(['ArrowDown','ArrowRight'].includes(event.key))next=(index+1)%all.length;else if(['ArrowUp','ArrowLeft'].includes(event.key))next=(index+all.length-1)%all.length;else if(event.key==='Home')next=0;else if(event.key==='End')next=all.length-1;else return;event.preventDefault();all[next]?.focus();all[next]?.click()}

/** Pure view: the embedding host owns APIs, live/demo scope and polling. */
export default function ConnectorMirror({snapshot,active,loading,error,busy,onRefresh,onCommand,onSaveSettings,onAbandon,controls}:Props) {
  const [selected,setSelected]=useState(''),[source,setSource]=useState('console'),[draft,setDraft]=useState<Data|null>(null),[dirty,setDirty]=useState(false),[draftScope,setDraftScope]=useState(''),[draftRevision,setDraftRevision]=useState(''),[draftProfileRevision,setDraftProfileRevision]=useState(''),[draftDesired,setDraftDesired]=useState<Data>({});
  const id=useId(),inventory=snapshot?.inventory||{},projection=snapshot?.projection;
  const boards=rows(inventory.boards),application=snapshot?.settings?.connector_application||{};
  const profile=useMemo(()=>projection?.profile?{...projection.profile,...(application.state!=='APPLIED'&&application.runner_id===inventory.runner_id?application.settings:{})}:null,[projection?.profile,application.settings,application.state,application.runner_id,inventory.runner_id]);
  const scope=`${inventory.runner_id||''}:${projection?.session_id||''}`;
  const fresh=active&&snapshot?.fresh===true&&inventory.fresh===true&&snapshot.console?.fresh===true&&!!projection?.session_id;
  useEffect(()=>{if(!boards.some(board=>board.board_id===selected))setSelected(boards[0]?.board_id||'')},[boards,selected]);
  useEffect(()=>{if(profile&&(!dirty||draftScope!==scope)){setDraft(structuredClone(profile));setDirty(false);setDraftScope(scope);setDraftRevision(application.revision||'');setDraftProfileRevision(projection?.revision||'');setDraftDesired(structuredClone(application.settings||{}))}},[profile,scope,dirty,draftScope,application.revision,application.settings,projection?.revision]);
  const board=boards.find(item=>item.board_id===selected),consoleBoard=rows(snapshot?.console?.boards).find(item=>item.board_id===selected);
  const events=rows(snapshot?.errors?.events).filter(item=>!item.board_id||item.board_id===selected);
  const executions=rows(projection?.executions).filter(item=>item.board_id===selected||item.board_ids?.includes(selected)||rows(item.connection?.a?[item.connection.a,item.connection.b]:item.boards).some(b=>b?.board_id===selected));
  const logs=source==='console'?(consoleBoard?.text||'보드 콘솔 수신 기록이 없습니다.'):
    source==='executions'?(executions.map(item=>`[${item.id} · ${item.state||''}]\n${text(item.stdout)}${text(item.stderr)?'\n'+item.stderr:''}`).join('\n\n')||'선택한 보드에 연결된 TC 로그가 없습니다.'):
    (events.map(item=>`[${when(item.time)} · ${item.code||'ERROR'} · ${item.board_id||'공통'}]\n${item.message||item.reason||item.text||''}`).join('\n\n')||'선택한 보드의 공통 오류 기록이 없습니다.');
  const commandPending=snapshot?.commands?.some(item=>['QUEUED','RUNNING','UNKNOWN'].includes(item.state));
  const canPutty=fresh&&!busy&&!commandPending&&!!board&&board.state==='CONNECTED'&&board.serial_proxy?.state==='READY'&&!inventory.host_busy&&!inventory.reserved&&!board.serial_proxy?.owner;
  function command(action:ConnectorMirrorCommandRequest['action'],body:Data){if(!fresh||!projection||!inventory.runner_id)return Promise.resolve();return onCommand({runner_id:inventory.runner_id,session_id:projection.session_id,revision:projection.revision,action,body})}
  function field(key:string,value:unknown){setDraft(current=>({...current,[key]:value}));setDirty(true)}
  function boardField(index:number,key:string,value:unknown){field('boards',rows(draft?.boards).map((item,i)=>i===index?{...item,[key]:value}:item))}
  function boardCount(count:number){if(!Number.isInteger(count)||count<1||count>32)return;setDraft(current=>{if(!current)return current;const next=structuredClone(current),activeBoards=rows(next.boards),inactive=rows(next.connector_inactive_boards);while(activeBoards.length>count){const removed=activeBoards.pop()!;inactive.unshift({board:removed,name:next.board_names?.[removed.board_id]||removed.board_id,baudrate:next.serial_settings?.[removed.board_id]?.baudrate??115200,observer:next.console_observers?.[removed.board_id]||{}})}while(activeBoards.length<count){const saved=inactive.shift(),board=saved?.board||{board_id:'board-'+crypto.randomUUID().slice(0,12),host:activeBoards[0]?.host||'Windows',com:'',node:null};activeBoards.push(board);if(saved){next.board_names={...next.board_names,[board.board_id]:saved.name};next.serial_settings={...next.serial_settings,[board.board_id]:{...next.serial_settings?.[board.board_id],baudrate:saved.baudrate}};next.console_observers={...next.console_observers,[board.board_id]:saved.observer}}}return {...next,boards:activeBoards,connector_inactive_boards:inactive}});setDirty(true)}
  const draftBoards=rows(draft?.boards),controlsCom=draftBoards.map(item=>text(item.com).trim().toUpperCase());
  const invalidPorts=controlsCom.some(com=>!com)||new Set(controlsCom).size!==controlsCom.length;
  const profileChanged=dirty&&draftProfileRevision!==projection?.revision;
  async function save(){if(!draft||!fresh||!draftRevision||profileChanged)return;const settings:Data=structuredClone(draftDesired);for(const key of ['boards','board_names','serial_settings','serial_transport','connector_inactive_boards'])if(draft[key]!==undefined)settings[key]=draft[key];settings.serial_transport='proxy';if(await onSaveSettings({expected_revision:draftRevision,expected_profile_revision:draftProfileRevision,runner_id:inventory.runner_id,settings}))setDirty(false)}
  return <section className="gt gt-scope gt-connector-mirror" aria-label="보드 커넥터 화면" hidden={!active}>
    <div className="gt-mirror-heading"><div><h1>보드 커넥터</h1><p>Windows에서 실행한 보드 커넥터의 보드·로그·설정을 같은 서버에서 확인합니다.</p></div><button type="button" onClick={onRefresh} disabled={loading}>새로 확인</button></div>
    {error&&<p className="gt-alert" role="alert">{error}</p>}
    <div className="gt-mirror-connection" role="status"><span className={fresh?'gt-mirror-indicator online':'gt-mirror-indicator'}/><strong>{fresh?'보드 커넥터 연결됨':loading&&!snapshot?'연결 상태 확인 중':inventory.runner_id?'Windows 연결 확인 필요 · 오래된 정보':'보드 커넥터 미연결'}</strong><span>등록 {boards.length}대 · 감지 {boards.filter(b=>b.detected).length}대</span></div>
    {!fresh&&<p className="gt-muted">Windows에서 board-connector.cmd를 실행해 연결하세요. 마지막 수신 기록은 보존하며 Windows 명령은 연결 확인 후 사용할 수 있습니다.</p>}
    {projection?.error&&<p role="status" className="gt-alert">{projection.error}</p>}
    <div className="gt-mirror-layout"><section className="gt-panel" aria-label="등록 보드"><h2>보드 리스트</h2>
      {!boards.length&&<p className="gt-muted">아직 등록된 보드가 없습니다.</p>}
      <div role="tablist" aria-label="보드별 로그" aria-orientation="vertical" className="gt-mirror-boards">{boards.map((item,index)=><button role="tab" type="button" key={item.board_id} id={`${id}-board-${index}`} aria-controls={`${id}-logs`} aria-selected={selected===item.board_id} tabIndex={selected===item.board_id?0:-1} onKeyDown={tabKeys} className={selected===item.board_id?'selected':''} onClick={()=>setSelected(item.board_id)}><strong>{item.name||item.board_id}</strong><span>{item.com} · {fresh?(stateLabels[item.state]||'확인 필요'):'오래된 정보'}</span>{item.blocked_reason&&<small>{item.blocked_reason==='HOST_BUSY'?'다른 보드 작업 대기':item.blocked_reason}</small>}</button>)}</div>
      <button type="button" disabled={!canPutty} onClick={()=>void command('putty',{board_id:selected})}>선택 보드 PuTTY 열기</button><p className="gt-muted">Windows에서 입력 제어권을 확인한 후 창을 엽니다.</p>
    </section><section className="gt-panel gt-mirror-log-panel" id={`${id}-logs`} role="tabpanel" aria-labelledby={selected?`${id}-board-${boards.findIndex(b=>b.board_id===selected)}`:undefined} aria-label={selected?undefined:'보드 로그'}>
      <div className="gt-mirror-log-tabs" role="tablist" aria-label="로그 종류">{[['console','보드 콘솔'],['executions','TC 로그'],['errors','공통 오류']].map(([key,label])=><button type="button" role="tab" key={key} id={`${id}-source-${key}`} aria-selected={source===key} tabIndex={source===key?0:-1} onKeyDown={tabKeys} aria-controls={`${id}-log-text`} onClick={()=>setSource(key)}>{label}</button>)}</div>
      <p className="gt-muted">{board?.name||selected||'보드 선택 대기'}{source==='console'&&consoleBoard?.code?` · ${consoleBoard.code}`:''}{!fresh?' · 과거 수신 기록':''}</p>
      {source==='console'&&(snapshot?.console?.delivery_gap||snapshot?.console?.history_truncated||consoleBoard?.gap)&&<p role="status" className="gt-alert">콘솔 기록에 누락 또는 보관 범위 제한이 있습니다.</p>}
      {source==='executions'&&projection?.logs_truncated&&<p role="status" className="gt-alert">TC 로그는 Windows가 보고한 마지막 일부만 표시합니다.</p>}
      <pre id={`${id}-log-text`} role="tabpanel" aria-labelledby={`${id}-source-${source}`} tabIndex={0}>{logs}</pre>
    </section></div>
    <details className="gt-panel"><summary>소스·실행 경로</summary><p className="gt-muted">서버와 Windows가 실제로 보고한 경로입니다.{!fresh?' 현재 연결의 확인 근거가 아닙니다.':''}</p><dl className="gt-mirror-receipt"><dt>현재 서버 TC 소스</dt><dd>{projection?.server_paths?.selected_tc_source||'미수신'}</dd><dt>서버 실행</dt><dd>{projection?.server_paths?.run?`${projection.server_paths.run.id} · ${projection.server_paths.run.state}${projection.server_paths.run.historical?' · 이전 실행':''}`:'미수신'}</dd><dt>실행 이미지 BAT</dt><dd>{projection?.server_paths?.run?.installer||'미수신'}</dd><dt>실행 TC 소스</dt><dd>{projection?.server_paths?.run?.tc_source||'미수신'}</dd>{rows(projection?.execution_paths).filter(item=>item.working_directory).map(item=><div className="gt-mirror-path" key={item.id}><dt>Windows {item.id}</dt><dd>{item.working_directory}</dd></div>)}</dl></details>
    <section className="gt-panel" aria-label="Windows 명령 확인"><h2>Windows 명령 확인</h2><p className="gt-muted">접수와 실제 Windows 처리 결과를 구분합니다.</p>{!snapshot?.commands?.length?<p>보낸 명령이 없습니다.</p>:<ul className="gt-mirror-command-list">{snapshot.commands.slice(0,12).map(item=><li key={item.command_id}><strong>{item.action==='putty'?'PuTTY 열기':item.action==='apply-settings'?'장비 설정 적용':item.action}</strong><span>{stateLabels[item.state]||item.state}</span>{(item.error||item.result?.message||item.result?.code)&&<span role="status">{item.error?(typeof item.error==='string'?item.error:item.error.message||item.error.code||'Windows 처리 오류'):[item.result?.code,item.result?.message].filter(Boolean).join(' · ')}</span>}{item.result?.opened===false&&<span>Windows 창 열림이 확인되지 않았습니다.</span>}{item.state==='UNKNOWN'&&(item.session_id===projection?.session_id?<span>보드 커넥터를 종료 후 다시 실행하고 보드·PuTTY 상태를 확인하세요.</span>:<><span>이전 Windows 요청의 결과는 불명으로 보존됩니다. 실제 보드·PuTTY 상태를 확인하세요.</span>{onAbandon&&<button type="button" disabled={!fresh||busy} onClick={()=>void onAbandon(item)}>이전 요청 결과 불명 확인</button>}</>)}<small>{item.command_id}</small></li>)}</ul>}</section>
    <section className="gt-panel" aria-label="Windows 장비 설정 적용 상태"><h2>Windows 장비 설정</h2><dl className="gt-mirror-receipt"><dt>처리 상태</dt><dd>{stateLabels[application.state]||application.state||'미수신'}{application.reason?` · ${application.reason}`:''}</dd><dt>요청 버전</dt><dd>{application.desired_revision||'없음'}</dd><dt>Windows 적용 근거</dt><dd>{application.applied_revision||'미수신'}</dd><dt>Windows 확인 수신</dt><dd>{when(application.received_at)}</dd></dl>
      {application.state==='APPLIED'&&!fresh&&<p className="gt-muted">위 적용 확인은 마지막 수신 기록입니다. 현재 Windows 연결은 다시 확인해야 합니다.</p>}
      <details><summary>보드·COM 설정 편집</summary>{!draft?<p>Windows 설정을 아직 받지 못했습니다.</p>:<form onSubmit={e=>{e.preventDefault();if(!invalidPorts)void save()}}><fieldset disabled={busy||!fresh} className="gt-mirror-fields">
        <label>연결할 보드 수<input type="number" min={1} max={32} required value={draftBoards.length} onChange={e=>boardCount(Number(e.target.value))}/></label>
        {draftBoards.map((item,index)=><div className="gt-mirror-board-edit" key={item.board_id}><strong>{item.board_id}</strong><label>보드 이름<input value={draft.board_names?.[item.board_id]||''} onChange={e=>field('board_names',{...draft.board_names,[item.board_id]:e.target.value})}/></label><label>Windows 보드 호스트<input required value={item.host||''} onChange={e=>boardField(index,'host',e.target.value)}/></label><label>COM 포트<select aria-label="COM 포트" required value={item.com} onChange={e=>boardField(index,'com',e.target.value)}><option value="">포트 선택</option>{[...new Set([item.com,...rows(projection?.ports).map(p=>p.com)])].filter(Boolean).map(com=><option key={com}>{com}</option>)}</select></label><label>통신 속도<input required type="number" min={1} max={4000000} value={draft.serial_settings?.[item.board_id]?.baudrate??115200} onChange={e=>field('serial_settings',{...draft.serial_settings,[item.board_id]:{...draft.serial_settings?.[item.board_id],baudrate:Number(e.target.value)}})}/></label></div>)}
        <p className="gt-muted">자동 COM 공유 · 실제 보드 COM과 통신 속도를 선택하면 커넥터가 TC·콘솔·PuTTY 연결을 공유합니다.</p>{!(fresh&&boards.length>0&&boards.every(item=>item.serial_proxy&&!item.stale))&&<p role="status" className="gt-muted">다음 연결 시 자동 적용</p>}<label>Windows TC Python<input value={projection?.profile?.python||''} readOnly/></label><label>Windows PuTTY 경로<input value={projection?.profile?.putty_path||''} readOnly/></label>
        {invalidPorts&&<p role="status" className="gt-alert">보드별 COM을 선택하고 중복을 해소하세요.</p>}
        {profileChanged&&<p role="status" className="gt-alert">편집 중 Windows 설정이 변경되었습니다. 현재 초안을 확인한 뒤 편집을 취소해 최신 설정을 불러오세요.</p>}
        <div className="gt-row"><button type="submit" disabled={!dirty||invalidPorts||profileChanged||!draftRevision}>장비 설정 요청 저장</button><button type="button" disabled={!dirty} onClick={()=>{setDraft(structuredClone(profile));setDirty(false)}}>편집 취소</button></div>
      </fieldset></form>}</details>
      <button type="button" disabled={!fresh||busy||dirty||commandPending||!application.desired_revision||application.state==='APPLIED'} onClick={()=>void command('apply-settings',{desired_revision:application.desired_revision})}>Windows에 설정 적용 요청</button>
    </section>
    {controls}
  </section>;
}
