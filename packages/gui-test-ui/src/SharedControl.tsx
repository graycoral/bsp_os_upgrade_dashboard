import StorageControl from './StorageControl';
import {useEffect,useRef,useState} from 'react';
type Data=Record<string,any>;
type Request=(path:string,method?:string,data?:unknown,signal?:AbortSignal)=>Promise<any>;

export default function SharedControl({request,active,onStarted}:{request:Request;active:boolean;onStarted:(run:Data)=>void}) {
  const [value,setValue]=useState<Data|null>(null),[draft,setDraft]=useState<Data|null>(null),[error,setError]=useState(''),[busy,setBusy]=useState(false),[notice,setNotice]=useState('');
  const [browser,setBrowser]=useState<{kind:string;path:string;entries:Data[];roots:string[]}|null>(null);
  const [dirty,setDirtyState]=useState(false);
  const dirtyRef=useRef(false),busyRef=useRef(false);
  function setDirty(next:boolean){dirtyRef.current=next;setDirtyState(next)}
  async function load(){const v=await request('/integration/settings');setValue(v);setDraft(structuredClone(v));setDirty(false)}
  useEffect(()=>{if(!active)return;const abort=new AbortController();
    async function refresh(){if(busyRef.current)return;try{const v=await request('/integration/settings','GET',undefined,abort.signal);if(!abort.signal.aborted&&!dirtyRef.current&&!busyRef.current){setValue(v);setDraft(structuredClone(v))}}catch(e){if(!abort.signal.aborted)setError((e as Error).message)}}
    void refresh();const timer=setInterval(()=>void refresh(),3000);return()=>{abort.abort();clearInterval(timer)}},[active]);
  async function action(fn:()=>Promise<void>){busyRef.current=true;setBusy(true);setError('');setNotice('');try{await fn()}catch(e){setError((e as Error).message)}finally{busyRef.current=false;setBusy(false)}}
  function field(key:string,next:any){setDraft(d=>d?{...d,integration:{...d.integration,[key]:next}}:d);setDirty(true)}
  async function save(){if(!draft||!value)return;const {default_seconds,source_revision,overrides}=draft.timeouts;const v=await request('/integration/settings','PUT',{expected_revision:value.revision,integration:draft.integration,timeouts:{default_seconds,source_revision,overrides}});setValue(v);setDraft(structuredClone(v));setDirty(false);setNotice('공통 설정을 저장했습니다. 새 실행부터 적용됩니다.')}
  async function browse(kind:string,path=''){const result=await request('/integration/paths?'+new URLSearchParams({kind,path}));setBrowser({kind,...result})}
  async function exportFile(){const file=await request('/integration/settings/file');const url=URL.createObjectURL(new Blob([JSON.stringify(file,null,2)+'\n'],{type:'application/json'}));const a=document.createElement('a');a.href=url;a.download='agent-monitor-settings.json';a.click();URL.revokeObjectURL(url)}
  async function importFile(file:File){if(file.size>65536)throw new Error('설정 파일은 64 KiB 이하만 지원합니다.');const result=await request('/integration/settings/file','POST',JSON.parse(await file.text()));setValue(result);setDraft(structuredClone(result));setDirty(false);setNotice('파일 설정을 반영했습니다.')}
  return <details className="gt-panel gt-shared-control"><summary>플러그인 공통 설정 · 이미지 설치와 TC 실행</summary>
    {error&&<p role="alert" className="gt-alert">{error}</p>}{notice&&<p role="status">{notice}</p>}
    {!draft?<button onClick={()=>void action(load)} disabled={busy}>불러오기</button>:<>
      <fieldset className="gt-settings-grid" disabled={busy} style={{border:0,padding:0}}>
        <label>Linux 설치 BAT<div className="gt-row"><input value={draft.integration.installer_path||''} onChange={e=>field('installer_path',e.target.value)}/><button disabled={busy} onClick={()=>void action(()=>browse('installer'))}>서버에서 선택</button></div></label>
        <label>Linux TC 폴더<div className="gt-row"><input value={draft.integration.tc_root||''} onChange={e=>field('tc_root',e.target.value)}/><button disabled={busy} onClick={()=>void action(()=>browse('source'))}>서버에서 선택</button></div></label>
        <label>TC 패턴 (쉼표 구분)<input value={(draft.integration.global_defaults||[]).join(', ')} onChange={e=>field('global_defaults',e.target.value.split(',').map(v=>v.trim()).filter(Boolean))}/></label>
        <label>플래싱 프로파일<input value={draft.integration.flash_profile||''} onChange={e=>field('flash_profile',e.target.value)}/></label>
        <label>공통 TC 제한시간 (초)<input type="number" min={1} max={86400} placeholder="기본 600 · TC 지정값 우선" value={draft.timeouts.default_seconds??''} onChange={e=>{setDirty(true);setDraft({...draft,timeouts:{...draft.timeouts,default_seconds:e.target.value===''?null:Number(e.target.value)}})}}/></label>
      </fieldset>
      <details><summary>서버 접근 범위</summary><fieldset className="gt-settings-grid" disabled={busy} style={{border:0,padding:0}}>
        <label>이미지 허용 폴더 (한 줄에 하나)<textarea value={(draft.integration.installer_roots||[]).join('\n')} onChange={e=>field('installer_roots',e.target.value.split('\n').filter(Boolean))}/></label>
        <label>TC 허용 폴더 (한 줄에 하나)<textarea value={(draft.integration.source_roots||[]).join('\n')} onChange={e=>field('source_roots',e.target.value.split('\n').filter(Boolean))}/></label>
      </fieldset></details>
      <p className="gt-muted">플러그인·Agent Monitor·ACON·보드 커넥터가 같은 설정을 사용합니다. 장비 설정: {draft.connector_application?.state||'변경 없음'}</p>
      <div className="gt-row"><button disabled={busy} onClick={()=>void action(load)}>다시 불러오기</button><button disabled={busy||!dirty} onClick={()=>void action(save)}>공통 설정 저장</button><button disabled={busy} onClick={()=>void action(exportFile)}>설정 파일 저장</button><label>설정 파일 적용<input type="file" accept=".json,application/json" disabled={busy} onChange={e=>{const file=e.target.files?.[0];if(file)void action(()=>importFile(file));e.target.value=''}}/></label>
      <button className="gt-primary" disabled={busy||dirty||!draft.integration.installer_path||!draft.integration.global_defaults?.length} onClick={()=>void action(async()=>{const r=await request('/integration/runs','POST',{installer_path:draft.integration.installer_path,tc_patterns:draft.integration.global_defaults});onStarted(r);setNotice('이미지 설치·부팅 확인 후 TC를 실행합니다.')})}>이미지 설치 후 TC 실행</button></div>
    </>}
    <StorageControl request={request}/>
    {browser&&<div className="gt-dialog-backdrop"><section role="dialog" aria-modal="true" aria-label="Linux 서버 경로 선택" className="gt-panel"><h3>Linux 서버 경로 선택</h3><p>{browser.path||'허용 폴더'}</p><button disabled={busy} onClick={()=>void action(()=>browse(browser.kind))}>허용 폴더로</button><ul>{(browser.path?browser.entries:browser.roots.map(path=>({name:path,path,directory:true}))).map(entry=><li key={entry.path}><button disabled={busy||(!entry.directory&&browser.kind!=='installer')} onClick={()=>entry.directory?void action(()=>browse(browser.kind,entry.path)):(field('installer_path',entry.path),setBrowser(null))}>{entry.directory?'▸ ':''}{entry.name}</button></li>)}</ul>{browser.kind==='source'&&browser.path&&<button onClick={()=>{field('tc_root',browser.path);setBrowser(null)}}>이 폴더 선택</button>}<button onClick={()=>setBrowser(null)}>닫기</button></section></div>}
  </details>
}

export function AnalysisStatus({run,request,onChanged}:{run:Data;request:Request;onChanged:()=>void}) {
  const [error,setError]=useState('');const a=run.failure_analysis;
  if(!a&&!run.integration)return null;
  const labels:Data={PENDING:'분석 대기',LEASED:'분석 중',HOLD:'조치 확인 대기',RETRY_READY:'자동 재실행 준비',STOPPED:'자동 재실행 중단',STALE:'현재 상태 재확인',CHILD_PENDING:'새 입력 준비 중'};
  async function control(action:string){try{setError('');await request(`/integration/runs/${run.id}/actions/${action}`,'POST',{expected_version:run.version,data:{}});onChanged()}catch(e){setError((e as Error).message)}}
  return <section className="gt-panel" aria-label="플러그인 분석 상태"><strong>{a?(labels[a.status]||a.status):'플러그인 실행'}</strong>{a&&<><p>{a.reason||'후속 TC를 멈추고 플러그인 분석을 기다립니다.'}</p>{a.cause_key&&<p>원인: {a.cause_key}</p>}<small>자동 재실행 {run.retry_chain?.automatic_retries||0}/3 · 같은 원인 재발 시 중단</small></>}{run.integration&&!['COMPLETED','CANCELLED'].includes(run.state)&&<div className="gt-row"><button disabled={!['QUEUED','RUNNING'].includes(run.state)} onClick={()=>void control('pause')}>일시중지</button><button disabled={!!a?.latched||run.state!=='PAUSED'||!run.environment_ready} onClick={()=>void control('resume')}>재개</button><button onClick={()=>void control('cancel')}>테스트 중단</button></div>}{error&&<p role="alert">{error}</p>}</section>
}
