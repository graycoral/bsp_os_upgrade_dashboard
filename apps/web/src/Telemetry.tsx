import {useEffect,useRef,useState} from 'react';
import {api,Data,labels} from './api';

export function duration(value:unknown){
  if(typeof value!=='number'||!Number.isFinite(value))return '시간 미집계';
  const seconds=Math.max(0,Math.floor(value));
  return seconds>=3600?`${Math.floor(seconds/3600)}시간 ${Math.floor(seconds%3600/60)}분`:seconds>=60?`${Math.floor(seconds/60)}분 ${seconds%60}초`:`${seconds}초`;
}
function usd(value:unknown){
  if(value==null)return '비용 미집계';
  const n=Number(value);if(!Number.isFinite(n)||n<0)return '비용 미집계';
  return n>0&&n<1e-8?'<$0.00000001':'$'+n.toLocaleString('en-US',{minimumFractionDigits:4,maximumFractionDigits:8});
}
export function cost(value?:Data){
  if(value?.status==='not_applicable')return '모델 호출 없음';
  if(value?.status==='partial')return '집계 '+usd(value.reported_cost_usd)+' · 일부 미집계';
  return usd(value?.cost_usd);
}
const count=(value:unknown)=>typeof value==='number'?value.toLocaleString():'미집계';
const role=(key:string)=>labels[key]||({review:'리뷰',coordinate:'조정',orchestrate:'조정',question:'질의',integration:'전체 통합'} as Data)[key]||key;
export function TelemetryBrief({value={},stage=false}:{value?:Data;stage?:boolean}){
  return <small className="bsp-telemetry-brief" title="경과는 첫 시작부터 마지막 종료까지, 누적은 모든 ROUND의 시간 합계입니다. 병렬 작업은 두 값이 다릅니다. 비용은 CLI 보고 USD이며 미집계를 0으로 추정하지 않습니다.">
    {stage?'누적 ':'경과 '}{duration(stage?value?.total_seconds:value?.elapsed_seconds)}{!stage&&value?.total_seconds!=null&&<> · ROUND 누적 {duration(value.total_seconds)}</>}{value.timing_partial&&value.round_count>0?' · 일부 시간 미집계':''} · {cost(value)}{value?.models?.length>0&&<> · 입력 {value.models.every((r:Data)=>r.input_tokens!=null)?value.models.reduce((n:number,r:Data)=>n+r.input_tokens,0).toLocaleString():'미집계'} / 출력 {value.models.every((r:Data)=>r.output_tokens!=null)?value.models.reduce((n:number,r:Data)=>n+r.output_tokens,0).toLocaleString():'미집계'} tok{value.tokens_partial?' · 일부 토큰 미집계':''}</>}
  </small>;
}
export function Models({rows,status}:{rows:Data[];status?:string}){
  return <div className="bsp-model-usage">{rows?.length?rows.map(row=><small key={row.provider+'/'+row.model}>{row.model==='unreported-model'?'모델 미보고':row.model} · 입력 {count(row.input_tokens)} / 출력 {count(row.output_tokens)} tok{(row.cache_read_tokens!=null||row.cache_write_tokens!=null)&&<> · 캐시 읽기 {count(row.cache_read_tokens)} / 쓰기 {count(row.cache_write_tokens)}</>} · {usd(row.cost_usd)}</small>):<small>{status==='not_applicable'?'모델 호출 없음':'모델별 토큰·비용 미집계'}</small>}</div>;
}
export function TelemetryDetails({value,jobId,moduleId,stage,label='모델별 토큰·비용 / ROUND'}:{value?:Data;jobId:string;moduleId?:string;stage?:string;label?:string}){
  const [open,setOpen]=useState(false),[rows,setRows]=useState<Data[]>([]),[next,setNext]=useState<number|null>(null),[error,setError]=useState(''),[busy,setBusy]=useState(false);
  const sequence=useRef(0);const scope=jobId+':'+(moduleId||'')+':'+(stage||'');
  const metric=JSON.stringify([value?.round_count,value?.call_count,value?.status,value?.cost_usd,value?.total_seconds]);
  async function load(offset:number,signal?:AbortSignal){
    const ticket=++sequence.current;setBusy(true);setError('');
    const query=new URLSearchParams({offset:String(offset),limit:'25'});if(moduleId)query.set('module_id',moduleId);if(stage)query.set('stage',stage);
    try{const result=await api(`/jobs/${jobId}/telemetry?${query}`,{signal});if(ticket!==sequence.current)return;
      setRows(old=>{const values=new Map(old.map(row=>[row.id,row]));for(const row of result.items)values.set(row.id,row);return [...values.values()].sort((a,b)=>String(b.started_at||'').localeCompare(String(a.started_at||'')))});setNext(result.next_offset);
    }catch(e){if(ticket===sequence.current&&(e as Error).name!=='AbortError')setError((e as Error).message)}finally{if(ticket===sequence.current)setBusy(false)}
  }
  useEffect(()=>{setRows([]);setNext(null);sequence.current++;return()=>{sequence.current++}},[scope]);
  useEffect(()=>{if(!open)return;const controller=new AbortController();void load(0,controller.signal);return()=>{sequence.current++;controller.abort()}},[open,scope,metric]);
  return <details className="bsp-telemetry-details" onToggle={e=>setOpen(e.currentTarget.open)}><summary>{label}</summary>
    <Models rows={value?.models||[]} status={value?.status}/>
    {error&&<small role="alert">{error}<button type="button" onClick={()=>void load(0)}>다시 조회</button></small>}
    <div className="bsp-rounds">{rows.map(row=><article key={row.id}><header>{row.module_name} · {role(row.stage)} · ROUND {row.ordinal||1} <span>{duration(row.telemetry?.total_seconds)} · {cost(row.telemetry)}</span></header>
      <Models rows={row.telemetry?.models||[]} status={row.telemetry?.status}/>
      {row.calls?.length>1&&row.calls.map((call:Data)=><small key={call.id}>{role(call.role)} · {call.requested_model} · {duration(call.duration_seconds)} · {usd(call.cost_usd)}</small>)}
    </article>)}</div>
    {busy&&<small role="status">사용량 조회 중…</small>}{!busy&&!rows.length&&<small>기록된 ROUND가 없습니다.</small>}
    {next!=null&&<button type="button" disabled={busy} onClick={()=>void load(next)}>이전 ROUND 더 보기</button>}
    <small className="muted">USD · CLI 보고값 · 실패·재시도·별도 리뷰 포함 · 미수집 값은 추정하지 않음</small>
  </details>;
}
