import {useEffect,useState,type ReactNode} from 'react';
import {api,type Data} from './api';

type Props={active:boolean;modules:Data[];onChange:(modules:Data[])=>void;onRemove:(index:number)=>void;targets?:(module:Data,index:number)=>ReactNode};

export default function PluginModules({active,modules,onChange,onRemove,targets}:Props){
  const [catalog,setCatalog]=useState<Data|null>(null),[error,setError]=useState('');
  const [manualName,setManualName]=useState(''),[manualGroup,setManualGroup]=useState<'boot'|'main'>('main');
  useEffect(()=>{
    if(!active)return;
    const controller=new AbortController();let pending=false;
    async function refresh(){
      if(pending||document.visibilityState==='hidden')return;pending=true;
      try{
        const value=await api('/config/modules',{signal:controller.signal});
        if(!Number.isSafeInteger(value.version)||value.version<0||!Array.isArray(value.modules)||value.modules.some((m:Data)=>typeof m.stable_key!=='string'||typeof m.name!=='string'||!['boot','main'].includes(m.group)||!Array.isArray(m.target_paths)))throw Error('플러그인 모듈 목록 형식을 확인하세요.');
        if(!controller.signal.aborted){setCatalog(value);setError('')}
      }catch(e){if(!controller.signal.aborted)setError((e as Error).message)}finally{pending=false}
    }
    void refresh();const timer=setInterval(()=>void refresh(),3000);
    const visible=()=>{if(document.visibilityState!=='hidden')void refresh()};document.addEventListener('visibilitychange',visible);
    return()=>{controller.abort();clearInterval(timer);document.removeEventListener('visibilitychange',visible)};
  },[active]);
  const choices:Data[]=catalog?.modules||[];
  const used=(choice:Data,index=-1)=>modules.some((module,i)=>i!==index&&(module.stable_key===choice.stable_key||module.name===choice.name));
  function choose(key:string,index?:number){
    const item=choices.find(choice=>choice.stable_key===key);if(!item||error||used(item,index))return;
    const value=structuredClone(item);
    onChange(index===undefined?[...modules,value]:modules.map((module,i)=>i===index?value:module));
  }
  function addManual(){
    const name=manualName.trim();
    if(!name||modules.some(m=>m.name===name||m.stable_key===name))return;
    onChange([...modules,{name,group:manualGroup,stable_key:name,target_paths:[]}]);
    setManualName('');
  }
  return <>
    {error&&<p role="status" className="error">모듈 목록 조회 실패 · {error}</p>}
    {!catalog&&!error&&<p role="status">플러그인 모듈 목록 확인 중</p>}
    {catalog&&!choices.length&&<p role="status">플러그인 모듈 정보 미수신 (플러그인에서 bsp list --available 결과를 /api/v1/config/modules로 게시하면 표시됩니다) · 아래에서 직접 추가하거나 기존 선택을 유지할 수 있습니다.</p>}
    <div className="module-config">{modules.map((module,index)=>{
      const current=choices.find(choice=>choice.stable_key===module.stable_key&&choice.name===module.name);
      const value=current?'plugin:'+current.stable_key:'saved';
      return <div key={index}>
        <select name={`module-${index+1}-name`} aria-label={`모듈 ${index+1} 이름`} value={value} disabled={!choices.length||!!error} onChange={e=>choose(e.target.value.slice(7),index)}>
          {!current&&<option value="saved">{module.name} · 기존 선택</option>}
          {choices.map(choice=><option key={choice.stable_key} value={'plugin:'+choice.stable_key} disabled={used(choice,index)}>{choice.name}</option>)}
        </select>
        <select name={`module-${index+1}-group`} aria-label={`모듈 ${index+1} 그룹`} value={module.group} onChange={e=>onChange(modules.map((item,i)=>i===index?{...item,group:e.target.value}:item))}><option value="boot">부트로더 선행 그룹</option><option value="main">나머지 그룹</option></select>
        <select name={`module-${index+1}-prereq`} aria-label={`모듈 ${index+1} 선행 모듈`} value={module.group} onChange={e=>onChange(modules.map((item,i)=>i===index?{...item,group:e.target.value}:item))}><option value="boot">선행 모듈</option><option value="main">일반 모듈</option></select>
        <button type="button" className="icon-btn" aria-label={`모듈 ${index+1} 삭제`} onClick={()=>onRemove(index)}>×</button>
        {targets?.(module,index)}
      </div>;
    })}</div>
    <label>모듈 추가<select aria-label="추가할 플러그인 모듈" value="" disabled={!!error||!choices.some(choice=>!used(choice))} onChange={e=>choose(e.target.value)}><option value="">플러그인 모듈 선택</option>{choices.map(choice=><option key={choice.stable_key} value={choice.stable_key} disabled={used(choice)}>{choice.name}</option>)}</select></label>
    <div className="module-manual-add"><input aria-label="직접 추가할 모듈 이름" placeholder="직접 추가 (예: kernel)" value={manualName} onChange={e=>setManualName(e.target.value)} onKeyDown={e=>{if(e.key==='Enter'){e.preventDefault();addManual()}}}/><select aria-label="직접 추가할 모듈 선행 여부" value={manualGroup} onChange={e=>setManualGroup(e.target.value==='boot'?'boot':'main')}><option value="boot">부트로더 선행 그룹 · 선행 모듈</option><option value="main">나머지 그룹 · 일반 모듈</option></select><button type="button" disabled={!manualName.trim()||modules.some(m=>m.name===manualName.trim()||m.stable_key===manualName.trim())} onClick={addManual}>직접 추가</button></div>
  </>;
}
