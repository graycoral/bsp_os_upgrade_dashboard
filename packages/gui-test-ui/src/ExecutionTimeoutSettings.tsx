import {useEffect,useRef,useState} from 'react';

type Load=(path:string,method?:string,data?:unknown,signal?:AbortSignal)=>Promise<any>;
export type TimeoutProfile={revision:string;default_seconds:number|null;source_revision:string;overrides:Record<string,number>};
type Case=Record<string,any>;

export function useExecutionTimeouts(load:Load,active:boolean,catalogRevision:string,onSaved:(value:TimeoutProfile)=>void){
  const [value,setValue]=useState<TimeoutProfile|null>(null),[loading,setLoading]=useState(false),[saving,setSaving]=useState(false),[error,setError]=useState('');
  const epoch=useRef(0),pending=useRef<AbortController|null>(null),savingRef=useRef(false),saved=useRef(onSaved);saved.current=onSaved;
  useEffect(()=>{
    if(!active)return;
    const ticket=++epoch.current,controller=new AbortController();pending.current=controller;setLoading(true);
    load('/execution-timeouts','GET',undefined,controller.signal).then(result=>{
      if(ticket===epoch.current&&!controller.signal.aborted){setValue(result);setError('')}
    }).catch(e=>{if(ticket===epoch.current&&!controller.signal.aborted)setError((e as Error).message)}).finally(()=>{if(ticket===epoch.current)setLoading(false)});
    return()=>{epoch.current++;controller.abort();pending.current?.abort();pending.current=null;savingRef.current=false;setSaving(false);setLoading(false)};
  },[active,load,catalogRevision]);
  async function save(next:Omit<TimeoutProfile,'revision'>,expected=value?.revision){
    if(!active||savingRef.current||!expected)return false;
    const ticket=++epoch.current;pending.current?.abort();const controller=new AbortController();pending.current=controller;
    savingRef.current=true;setSaving(true);setLoading(false);setError('');
    try{
      const result=await load('/execution-timeouts','PUT',{...next,expected_revision:expected},controller.signal);
      if(ticket!==epoch.current||controller.signal.aborted)return false;
      setValue(result);saved.current(result);return true;
    }catch(e){if(ticket===epoch.current&&!controller.signal.aborted)setError((e as Error).message);return false}
    finally{if(ticket===epoch.current){savingRef.current=false;setSaving(false);pending.current=null}}
  }
  return {value,loading,saving,error,save};
}

export default function ExecutionTimeoutSettings({open,target,tests,sourceRevision,profile,saving,error,onSave,onClose}: {
  open:boolean;target:string;tests:Case[];sourceRevision:string;profile:TimeoutProfile|null;saving:boolean;error:string;
  onSave:(value:Omit<TimeoutProfile,'revision'>,expected:string)=>Promise<boolean>;onClose:()=>void;
}){
  const dialog=useRef<HTMLDialogElement>(null),previousFocus=useRef<HTMLElement|null>(null);
  const [bulk,setBulk]=useState('10'),[selection,setSelection]=useState(''),[individual,setIndividual]=useState('10'),[validation,setValidation]=useState('');
  const frozen=useRef<TimeoutProfile|null>(null);
  useEffect(()=>{
    const node=dialog.current;if(!node)return;
    if(open&&profile){
      previousFocus.current=document.activeElement as HTMLElement;frozen.current=profile;
      setBulk(String(profile.default_seconds??10));const test=tests.find(t=>t.id===target)||tests[0];
      setSelection(test?.id||'');setIndividual(String(test?.timeout??10));setValidation('');
      if(!node.open)node.showModal();
    }else if(node.open){node.close();previousFocus.current?.focus()}
  },[open,target,!!profile]);
  function seconds(value:string){const n=Number(value);if(!value.trim()||!Number.isInteger(n)||n<1||n>86400){setValidation('실행 제한시간은 1~86,400초의 정수로 입력하세요.');return null}setValidation('');return n}
  async function apply(all:boolean){
    const base=frozen.current;if(!base)return;const n=seconds(all?bulk:individual);if(n===null)return;
    if(!all&&!tests.some(t=>t.id===selection)){setValidation('목록에서 TC를 선택하세요.');return}
    const overrides=all?{}:{...(base.source_revision===sourceRevision?base.overrides:{}),[selection]:n};
    if(await onSave({default_seconds:all?n:base.default_seconds,source_revision:sourceRevision,overrides},base.revision))onClose();
  }
  async function reset(){const base=frozen.current;if(base&&await onSave({default_seconds:null,source_revision:'',overrides:{}},base.revision))onClose()}
  return <dialog ref={dialog} className="gt-timeout-dialog" aria-labelledby="gt-timeout-title" onCancel={e=>{e.preventDefault();if(!saving)onClose()}}>
    <div className="gt-section-head"><h3 id="gt-timeout-title">TC 실행 제한시간 전체·개별 설정</h3><button type="button" aria-label="시간 설정 닫기" disabled={saving} onClick={onClose}>×</button></div>
    <p>저장 후 새 테스트부터 적용합니다. 실행 중인 세션의 제한시간은 유지됩니다.</p>
    <fieldset disabled={saving}><legend>전체 TC에 일괄 적용</legend><label>공통 실행 제한시간(초)<input type="number" min="1" max="86400" step="1" value={bulk} onChange={e=>setBulk(e.target.value)}/></label><small>현재 개별 예외를 모두 지우고 모든 TC에 같은 시간을 적용합니다. 새로 추가되는 TC에도 적용합니다.</small><button type="button" onClick={()=>void apply(true)}>전체 TC에 시간 적용</button></fieldset>
    <fieldset disabled={saving||!tests.length}><legend>개별 TC 예외</legend><label>시간을 변경할 TC<select value={selection} onChange={e=>{setSelection(e.target.value);setIndividual(String(tests.find(t=>t.id===e.target.value)?.timeout??10))}}>{tests.map(t=><option key={t.id} value={t.id}>{t.name} · {t.path}</option>)}</select></label><label>선택 TC 실행 제한시간(초)<input type="number" min="1" max="86400" step="1" value={individual} onChange={e=>setIndividual(e.target.value)}/></label><button type="button" onClick={()=>void apply(false)}>선택 TC에 시간 적용</button><small>개별 예외는 현재 소스 스냅샷에 적용합니다. 소스가 바뀌면 TC 목록을 다시 확인하세요.</small></fieldset>
    {(validation||error)&&<p role="alert" className="gt-alert error">{validation||error}</p>}
    <div className="gt-row"><button type="button" disabled={saving} onClick={()=>void reset()}>원본 TC 시간으로 복원</button><button type="button" disabled={saving} onClick={onClose}>닫기</button>{saving&&<span role="status">제한시간 저장 중…</span>}</div>
    <small>대시보드 서버의 설정 DB에 저장합니다. 브라우저를 닫거나 서버를 다시 시작해도 유지됩니다.</small>
  </dialog>;
}
