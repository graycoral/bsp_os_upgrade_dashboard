import {useEffect,useId,useRef,useState} from 'react';

type Load=(path:string,method?:string,data?:unknown,signal?:AbortSignal)=>Promise<any>;

export default function SourceRequestSettings({load,active,onReveal}:{load:Load;active:boolean;onReveal?:()=>void}) {
  const [draft,setDraft]=useState('100'),[loading,setLoading]=useState(false),[saving,setSaving]=useState(false);
  const [error,setError]=useState(''),[notice,setNotice]=useState(''),[reload,setReload]=useState(0);
  const initialized=useRef(false),edited=useRef(false),epoch=useRef(0),pending=useRef<AbortController|null>(null),savePending=useRef(false);
  const [custom,setCustom]=useState(false),details=useRef<HTMLDetailsElement>(null);
  const presets=['30','60','100','180','300','600'];
  const helpId=useId();
  useEffect(()=>{if(error&&active){if(details.current)details.current.open=true;onReveal?.()}},[error,active]);
  useEffect(()=>{
    if(!active||initialized.current)return;
    const ticket=++epoch.current,controller=new AbortController();pending.current=controller;setLoading(true);
    load('/source/request-settings','GET',undefined,controller.signal).then(value=>{
      if(ticket!==epoch.current||controller.signal.aborted)return;
      initialized.current=true;
      if(!edited.current)setDraft(String(value.catalog_timeout_seconds));
      setError('');
    }).catch(e=>{if(ticket===epoch.current&&!controller.signal.aborted)setError((e as Error).message)}).finally(()=>{
      if(ticket===epoch.current){pending.current=null;setLoading(false)}
    });
    return()=>{controller.abort();if(ticket===epoch.current){epoch.current++;pending.current=null;setLoading(false)}};
  },[active,load,reload]);
  useEffect(()=>()=>{epoch.current++;pending.current?.abort();pending.current=null;savePending.current=false;setSaving(false);setLoading(false)},[active]);
  async function save(){
    if(savePending.current||!active)return;
    const seconds=Number(draft);
    setError('');setNotice('');
    if(!draft.trim()||!Number.isInteger(seconds)||seconds<1||seconds>600){setError('조회 제한 시간은 1~600초의 정수로 입력하세요.');return}
    savePending.current=true;
    const ticket=++epoch.current;pending.current?.abort();const controller=new AbortController();pending.current=controller;
    setLoading(false);setSaving(true);
    try {
      const value=await load('/source/request-settings','PUT',{catalog_timeout_seconds:seconds},controller.signal);
      if(ticket!==epoch.current||controller.signal.aborted)return;
      initialized.current=true;setDraft(String(value.catalog_timeout_seconds));
      setNotice('조회 제한 시간을 저장했습니다. 다음 TC 목록 조회부터 적용됩니다.');
    }catch(e){if(ticket===epoch.current&&!controller.signal.aborted)setError((e as Error).message)}finally{
      if(ticket===epoch.current){pending.current=null;savePending.current=false;setSaving(false)}
    }
  }
  return <section className="gt-source-request-settings" aria-label="TC 목록 조회 설정">
    <details ref={details} className="gt-settings-detail"><summary>조회 고급 설정</summary>
    <div className="gt-source-timeout-row"><label>목록 조회 제한 시간<select aria-label="TC 목록 조회 제한 시간 선택" value={custom||!presets.includes(draft)?'custom':draft} disabled={saving} onChange={e=>{setCustom(e.target.value==='custom');if(e.target.value!=='custom'){edited.current=true;setDraft(e.target.value);setNotice('');setError('')}}}>{presets.map(value=><option key={value} value={value}>{value}초{value==='100'?' · 기본':''}</option>)}<option value="custom">직접 입력</option></select></label>
    <label hidden={!custom&&presets.includes(draft)}>TC 목록 조회 제한 시간(초)<input name="catalog-timeout-seconds" aria-label="TC 목록 조회 제한 시간(초)" type="number" min="1" max="600" step="1" value={draft} disabled={saving} aria-describedby={helpId} onChange={e=>{edited.current=true;setDraft(e.target.value);setNotice('');setError('')}}/></label></div>
    <small id={helpId} className="gt-muted">1~600초 · 저장 후 다음 조회부터 적용됩니다. 진행 중인 조회의 제한 시간은 유지됩니다.</small>
    <div className="gt-row"><button type="button" disabled={saving||!active} onClick={save}>{saving?'조회 제한 시간 저장 중…':'조회 제한 시간 저장'}</button>{loading&&<small role="status" className="gt-muted">조회 설정을 불러오는 중…</small>}</div>
    </details>
    {error&&<div className="gt-alert error" role="alert">{error}<button type="button" disabled={saving||loading} onClick={()=>{initialized.current=false;setReload(value=>value+1)}}>조회 설정 다시 확인</button></div>}
    {notice&&<p role="status" className="gt-source-notice">{notice}</p>}
  </section>;
}
