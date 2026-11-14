import {useState} from 'react';
type Data=Record<string,any>;
type Request=(path:string,method?:string,data?:unknown)=>Promise<any>;
export default function StorageControl({request}:{request:Request}){
 const [value,setValue]=useState<Data|null>(null),[draft,setDraft]=useState<Data|null>(null),[report,setReport]=useState<Data|null>(null),[busy,setBusy]=useState(false),[error,setError]=useState('');
 async function action(fn:()=>Promise<void>){setBusy(true);setError('');try{await fn()}catch(e){setError((e as Error).message)}finally{setBusy(false)}}
 function received(v:Data){setValue(v);setDraft({...v})}
 function result(label:string,r:Data){return <p key={label}>{label}: {r.skipped_reason||r.reason||r.state||((r.dry_run?'정리 예정 ':'정리됨 ')+(((r.dry_run?r.planned_bytes:r.deleted_bytes)||0)/1024**2).toFixed(1)+' MiB')}{r.over_budget?' · 용량 한도 초과':''}{r.batch_limited?' · 다음 주기에 계속 정리':''}{r.measurement_complete===false?' · 일부 집계':''}</p>}
 return <details className="gt-storage-control"><summary>저장 공간 자동 정리</summary><p className="gt-muted">기본 7일 · 20 GiB. 진행 중 작업과 실패 근거는 보존합니다. 보호 파일이 많으면 한도를 넘을 수 있습니다.</p>
 {error&&<p role="alert">{error}</p>}
 <button disabled={busy} onClick={()=>void action(async()=>received(await request('/integration/storage-policy')))}>정리 기준 불러오기</button>
 {draft&&<fieldset disabled={busy} style={{border:0,padding:0}}>
 <label><input type="checkbox" checked={draft.enabled} onChange={e=>setDraft({...draft,enabled:e.target.checked})}/>자동 정리</label>
 <label>보관 기간 (일)<input type="number" min={1/24} max={3650} step="any" value={draft.max_age_seconds/86400} onChange={e=>setDraft({...draft,max_age_seconds:Math.round(Number(e.target.value)*86400)})}/></label>
 <label>캐시 한도 (GiB)<input type="number" min={1/1024**3} step="any" value={draft.max_bytes/1024**3} onChange={e=>setDraft({...draft,max_bytes:Math.round(Number(e.target.value)*1024**3)})}/></label>
 <button onClick={()=>void action(async()=>received(await request('/integration/storage-policy','PUT',{expected_revision:value?.revision,enabled:draft.enabled,max_age_seconds:draft.max_age_seconds,max_bytes:draft.max_bytes})))}>정리 기준 저장</button>
 <p>Windows 적용: {value?.connector_sync?.state||'확인 전'}</p>
 </fieldset>}
 <div className="gt-row">{[[true,'정리 대상 확인'],[false,'지금 정리']].map(([dry_run,label])=><button key={String(label)} disabled={busy} onClick={()=>void action(async()=>setReport(await request('/integration/storage-cleanup','POST',{dry_run})))}>{label}</button>)}</div>
 {report&&<div role="status">{result('Linux',report)}{report.connector_cleanup&&result('Windows',report.connector_cleanup.report||report.connector_cleanup)}</div>}
 </details>
}
