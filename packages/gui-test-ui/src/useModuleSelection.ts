import {useEffect, useRef, useState} from 'react';

import {type GuiTestModuleContext} from './host';

type Data = Record<string, any>;
type Selection = {context:Data|null;module_name:string;mode:'manual'|'automatic';blocked_reason:string|null;tests:Data[];tc_ids:string[];frozen:boolean};
const deviceStates=new Set(['WAITING_INPUT','RUNNING','UNKNOWN','CANCEL_REQUESTED']);

export function sameModuleContext(left?:Data|null,right?:Data|null) {
  return !!left&&!!right&&['job_id','module_id','attempt_id','plan_version','fingerprint','catalog_revision'].every(key=>left[key]===right[key]);
}

export default function useModuleSelection({job,catalog,branch,active,load}:{job?:GuiTestModuleContext|null;catalog:Data|null;branch:string;active:boolean;load:(path:string)=>Promise<any>}) {
  const [choice,setChoice]=useState({jobId:'',moduleId:''});
  const [retryRevision,setRetryRevision]=useState(0);
  const allModules=Array.isArray(job?.modules)?job.modules:[];
  const eligible=allModules.filter(module=>deviceStates.has(module.status||'')&&module.attempt_id);
  const chosen=choice.jobId===job?.job_id?allModules.find(module=>module.id===choice.moduleId):undefined;
  // Keep a selected persistent attempt scoped when its state changes. Falling
  // back to the full catalog here could prepare unrelated tests after completion.
  const module=chosen||eligible[0];
  const stage=module;
  const scoped=!!job?.job_id&&!!module;
  const canLookup=!!catalog?.revision||!!stage?.automatic;
  const modules=chosen&&!eligible.some(item=>item.id===chosen.id)?[...eligible,chosen]:eligible;
  const contextKey=scoped?JSON.stringify([job!.job_id,module.id,module.attempt_id||null,job!.plan_version,job!.fingerprint,catalog?.revision||'',branch]):'';
  const queryKey=contextKey+'|'+JSON.stringify([stage?.status,!!stage?.automatic,stage?.request_hash,stage?.frozen_run_id,stage?.source_revision,stage?.automation_blocked,stage?.blocked_reason,job?.paused,job?.session_status]);
  const requestKey=queryKey+'|'+retryRevision;
  const latest=useRef('');latest.current=active?requestKey:'';
  const sequence=useRef(0);
  const [result,setResult]=useState<{key:string;query:string;pending:boolean;value:Selection|null;error:string}>({key:'',query:'',pending:false,value:null,error:''});

  useEffect(()=>{if(scoped)setChoice(current=>current.jobId===job!.job_id&&current.moduleId===module.id?current:{jobId:job!.job_id,moduleId:module.id})},[scoped,job?.job_id,module?.id]);
  useEffect(()=>{
    if(!active||!scoped||!canLookup)return;
    const current=++sequence.current;
    let cancelled=false;
    let retryTimer:ReturnType<typeof setTimeout>|undefined;
    const isCurrent=()=>!cancelled&&sequence.current===current&&latest.current===requestKey;
    setResult(previous=>({key:contextKey,query:requestKey,pending:true,value:previous.key===contextKey?previous.value:null,error:''}));
    const params=new URLSearchParams({job_id:job!.job_id,module_id:module.id,branch,catalog_revision:catalog?.revision||''});
    async function request(retries=0) {
      try {
        const value=await load('/module-selection?'+params);
        if(!isCurrent())return;
        const context=value?.context;
        const frozen=value?.mode==='automatic'&&value?.frozen===true;
        const validContext=context&&context.job_id===job!.job_id&&context.module_id===module.id&&context.attempt_id===(module.attempt_id||null)&&context.plan_version===job!.plan_version&&context.fingerprint===job!.fingerprint&&(frozen||context.catalog_revision===(catalog?.revision||''));
        const tests:Data[]=Array.isArray(value?.tests)?value.tests:[];
        const ids=Array.isArray(value?.tc_ids)?value.tc_ids:[];
        const available=new Set(tests.map(test=>test.id));
        if(!validContext||!['manual','automatic'].includes(value?.mode)||!Array.isArray(value?.tests)||!Array.isArray(value?.tc_ids)||ids.some((id:unknown)=>typeof id!=='string'||!available.has(id))||new Set(ids).size!==ids.length||(!value.blocked_reason&&!frozen&&!context.attempt_id))throw new Error('모듈 TC 응답 기준을 확인하세요.');
        setResult({key:contextKey,query:requestKey,pending:false,value,error:''});
      } catch(error) {
        if(!isCurrent())return;
        if(retries<2) {
          retryTimer=setTimeout(()=>{if(isCurrent())void request(retries+1)},[250,750][retries]);
          return;
        }
        setResult(previous=>({key:contextKey,query:requestKey,pending:false,value:previous.key===contextKey?previous.value:null,error:(error as Error).message}));
      }
    }
    void request();
    return()=>{cancelled=true;if(retryTimer!==undefined)clearTimeout(retryTimer)};
  },[active,scoped,canLookup,contextKey,requestKey,catalog?.revision,load]);

  const value=result.key===contextKey?result.value:null;
  const pending=scoped&&(!active||!canLookup||result.query!==requestKey||result.pending);
  const readOnly=value?.mode==='automatic';
  // Automatic device-test ownership always blocks generic Run creation, even
  // when its frozen list is valid and the server supplies no additional reason.
  const reason=!scoped?'':pending?'모듈 TC 확인 중':result.error?'모듈 TC 확인 실패 · '+result.error:!value?'모듈 TC를 확인하세요.':value.blocked_reason||(readOnly?'자동 장비 시험에서 실행 중입니다.':'');
  return {active:scoped,contextKey,applicationKey:value?contextKey+'|'+value.mode+'|'+value.context?.catalog_revision:'',context:value?.context||null,selection:value,
    tests:scoped?(value?.tests||[]):[],modules,moduleId:module?.id||'',moduleName:value?.module_name||module?.name||'',readOnly:!!readOnly,blockedReason:reason,
    retryAvailable:scoped&&!pending&&result.key===contextKey&&!!result.error,retry:()=>{if(scoped&&!pending&&result.key===contextKey&&result.error)setRetryRevision(revision=>revision+1)},
    selectModule:(id:string)=>{if(modules.some(item=>item.id===id))setChoice({jobId:job!.job_id,moduleId:id})}};
}
