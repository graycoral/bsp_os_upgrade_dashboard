import { memo, useEffect, useId, useRef, useState } from 'react';
import type { AconObservation, DiagramModule, DiagramTabProps } from './types';
import { aconConnection, diagramActivity, snapshotHealth } from './presentation';
import './diagram.css';

function Dot({tone,label}:{tone:string;label:string}) {
  return <span className="wd-status"><i className={`wd-dot wd-${tone}`} aria-hidden="true"/>{label}</span>;
}
function Progress({percent}:{percent:number|null}) {
  return <div className="wd-progress"><span>{percent===null?'미집계':`${percent}%`}</span><div className="wd-progress-track" role="progressbar" aria-label="서버 진행률" aria-valuemin={0} aria-valuemax={100} aria-valuenow={percent??undefined} aria-valuetext={percent===null?'미집계':`${percent}%`}><i style={{width:percent===null?'0':`${percent}%`}}/></div></div>;
}
function Edge({id,flow,connected=false,label,marker}:{id:string;flow:boolean;connected?:boolean;label:string;marker:string}) {
  return <div className={`wd-edge${flow?' wd-flow':''}${connected?' wd-connected':''}`} data-testid={`wd-edge-${id}`} data-flow={flow}>
    <svg viewBox="0 0 100 24" aria-hidden="true"><defs><marker id={marker} viewBox="0 0 10 10" refX="8" refY="5" markerWidth="5" markerHeight="5" orient="auto"><path d="M 0 0 L 10 5 L 0 10 z"/></marker></defs><path className="wd-wire" d="M 0 12 L 96 12" markerEnd={`url(#${marker})`}/>{flow&&<path className="wd-wire-signal" d="M 0 12 L 92 12"/>}</svg><span>{label}</span>
  </div>;
}
const ModuleCard = memo(function ModuleCard({module:m,open,toggle,fresh,acon,now,controlId,jobId}:{module:DiagramModule;open:boolean;toggle:()=>void;fresh:boolean;acon:AconObservation[]|undefined;now:number;controlId:string;jobId:string|null}) {
  const connection = aconConnection(acon,jobId,m.id,now);
  const activity = fresh && m.activity==='running';
  return <article className={`wd-module wd-${m.tone}${activity?' wd-module-active':''}`} data-testid={`wd-module-${m.id}`}>
    <button type="button" className="wd-module-toggle" data-testid={`wd-toggle-${m.id}`} aria-expanded={open} aria-controls={controlId} onClick={toggle}>
      <span className="wd-module-name"><span className="wd-chevron" aria-hidden="true">{open?'⌄':'›'}</span><strong>{m.name}</strong></span>
      <span className="wd-module-summary"><i className={`wd-dot wd-${m.tone}`} aria-hidden="true"/>{m.activity==='complete'?'✓ ':''}{m.summary}{!fresh?' · 마지막 확인 상태':''}</span>
      <Progress percent={m.percent}/>
    </button>
    <div className="wd-module-meta"><Dot tone={connection.tone} label={connection.label}/>{m.detail&&<p>{m.detail}</p>}{m.diagnostics.length>0&&<p className="wd-diagnostic">{m.diagnostics.join(' · ')}</p>}</div>
    {open&&<ol className="wd-stages" id={controlId} data-testid={`wd-stages-${m.id}`}>{m.stages.map((stage,index)=><li className={`wd-stage${fresh&&stage.running&&m.activity==='running'?' wd-flow':''}`} key={stage.id} data-stage={stage.id} data-running={stage.running}>
      <span className="wd-stage-index">{stage.complete?'✓':String(index+1).padStart(2,'0')}</span><div className="wd-stage-body"><strong>{stage.label}</strong>{stage.parts.map(p=><div className="wd-stage-part" key={p.id}><Dot tone={p.tone} label={`${stage.parts.length>1?`${p.label} · `:''}${p.statusLabel}`}/>{p.detail&&<small>{p.detail}</small>}</div>)}</div>
    </li>)}</ol>}
  </article>;
});

function DiagramView({model,observation,active,acon}:DiagramTabProps) {
  const [expanded,setExpanded] = useState<Set<string>>(()=>new Set());
  const [motionPaused,setMotionPaused] = useState(false);
  const [visible,setVisible] = useState(()=>typeof document==='undefined'||document.visibilityState!=='hidden');
  const [now,setNow] = useState(()=>({mono:performance.now(),wall:Date.now()}));
  const canvas = useRef<HTMLDivElement>(null);
  const context = useRef(model.contextKey);
  const instance = useId().replace(/[^a-zA-Z0-9_-]/g,'');
  useEffect(()=>{
    if (context.current !== model.contextKey) {context.current=model.contextKey;setExpanded(new Set());if(canvas.current){canvas.current.scrollLeft=0;canvas.current.scrollTop=0}}
    else {const keys = new Set([...model.groups.flatMap(g=>g.modules),...model.unassigned].map(m=>m.key));setExpanded(old=>{const next=new Set([...old].filter(k=>keys.has(k)));return next.size===old.size?old:next})}
  },[model.contextKey,model.groups,model.unassigned]);
  useEffect(()=>{if(!active)return;const update=()=>setVisible(document.visibilityState!=='hidden');update();document.addEventListener('visibilitychange',update);return()=>document.removeEventListener('visibilitychange',update)},[active]);
  useEffect(()=>{if(active&&visible)setNow({mono:performance.now(),wall:Date.now()})},[active,visible,observation,acon]);
  useEffect(()=>{
    if(!active||!visible)return;
    const deadlines:number[]=[];
    if(observation.status==='ready'&&!observation.needsConfirmation&&observation.receivedMonoMs!==null){const remaining=observation.receivedMonoMs+observation.staleAfterMs-performance.now();if(remaining>0)deadlines.push(remaining)}
    acon?.forEach(o=>{const remaining=o.expiresAt-Date.now();if(remaining>0)deadlines.push(remaining)});
    if(!deadlines.length)return;
    const timer=setTimeout(()=>setNow({mono:performance.now(),wall:Date.now()}),Math.min(...deadlines)+5);
    return()=>clearTimeout(timer);
  },[active,visible,observation,acon,now]);
  const health = snapshotHealth(observation,now.mono);
  const edges = diagramActivity(model,health.fresh);
  const aconJob = aconConnection(acon,model.jobId,undefined,now.wall);
  const scopedAcon = acon?.filter(o=>o.jobId===model.jobId);
  const toggle=(key:string)=>setExpanded(old=>{const next=new Set(old);next.has(key)?next.delete(key):next.add(key);return next});
  const motion = active&&visible&&!motionPaused;
  return <section className="wd-root" hidden={!active} data-testid="workflow-diagram" data-motion={motion?'running':'paused'} aria-label="BSP 업그레이드 다이어그램">
    <div className="wd-toolbar"><div><p className="wd-eyebrow">WORKFLOW / LIVE STATE</p><h2>모듈 흐름도</h2><p>모든 IP의 분석은 병렬로 진행합니다. 화살표는 구성 관계와 설계 이후 선행 조건을 나타냅니다.</p></div><button type="button" className="wd-motion-button" aria-pressed={motionPaused} onClick={()=>setMotionPaused(v=>!v)}>{motionPaused?'흐름 효과 재개':'흐름 효과 일시정지'}</button></div>
    <div className="wd-observation" aria-live="polite"><Dot tone={health.tone} label={health.label}/><span>{observation.receivedAt!==null?`마지막 조회 확인 ${new Date(observation.receivedAt).toLocaleTimeString('ko-KR')}`:'아직 수용한 상태가 없습니다'}</span>{model.storedAt&&<span>상태 저장 {new Date(model.storedAt).toLocaleString('ko-KR')}</span>}{model.paused&&<strong>신규 배정 일시 중지 · 실행 중 프로세스는 별도 표시</strong>}</div>
    {observation.detail&&<p className="wd-notice">{observation.detail}</p>}
    {!model.jobId&&<div className="wd-empty">{observation.status==='empty'?'아직 실행한 작업이 없습니다.':observation.status==='failed'?'작업을 조회하지 못했습니다. 다음 조회를 기다립니다.':'선택 작업의 상태를 확인하고 있습니다.'}</div>}
    <div className="wd-canvas" ref={canvas} tabIndex={0} role="region" aria-label="가로 모듈 흐름도 · 좌우로 스크롤" data-testid="wd-canvas"><div className="wd-topology" data-testid="wd-topology">
      <div className="wd-column"><div className="wd-node wd-service"><span className="wd-node-index">01 / INTERFACE</span><h3>FrontEnd <small>(ACON)</small></h3><Dot tone={aconJob.tone} label={aconJob.label}/><p>ACON 제공 근거 기준</p><Edge id="acon" flow={aconJob.fresh&&aconJob.activity} connected={aconJob.fresh} label="연결 관계" marker={`${instance}-acon`}/></div></div>
      <div className="wd-column"><div className="wd-node wd-service"><span className="wd-node-index">02 / EXECUTION</span><h3>BackEnd <small>(bsp-os-upgrade)</small></h3><Dot tone={health.tone} label={health.label}/><p>전체 진행률 {model.overallPercent===null?'미집계':`${model.overallPercent}%`}</p><Edge id="boot" flow={edges.boot} label="선행 IP 실행 활동" marker={`${instance}-boot`}/></div></div>
      {model.groups.map((g,groupIndex)=>{const counts={running:0,waiting:0,failed:0,unknown:0};g.modules.forEach(m=>{if(m.activity==='running')counts.running++;else if(m.activity==='failed')counts.failed++;else if(m.activity==='unknown'||m.activity==='transition')counts.unknown++;else if(m.activity==='waiting')counts.waiting++});return <div className="wd-column wd-group" key={g.id} data-group={g.id}><div className="wd-node wd-group-heading"><span className="wd-node-index">0{groupIndex+3} / {g.id==='boot'?'PREREQUISITE':'MODULES'}</span><h3>{g.label}<span className="wd-count">{g.modules.length}</span></h3><p>실행 {counts.running} · 대기 {counts.waiting} · 실패 {counts.failed} · 불명 {counts.unknown}</p><Progress percent={g.percent}/>{g.id==='boot'&&<Edge id="main" flow={edges.main} label={model.bootReady===true?'설계 이후 선행 조건 충족':model.bootReady===false?'설계 이후 대기 · 분석 가능':'설계 이후 선행 조건 미확인'} marker={`${instance}-main`}/>}</div><div className="wd-module-list">{g.modules.length?g.modules.map((m,i)=><ModuleCard key={m.key} module={m} open={expanded.has(m.key)} toggle={()=>toggle(m.key)} fresh={health.fresh} acon={scopedAcon} now={now.wall} jobId={model.jobId} controlId={`${instance}-${g.id}-${i}`}/>):<p className="wd-empty-group">저장된 소속 IP가 없습니다.</p>}</div></div>})}
    </div></div>
    {model.unassigned.length>0&&<div className="wd-unassigned"><h3>소속 확인 필요</h3>{model.unassigned.map((m,i)=><ModuleCard key={m.key} module={m} open={expanded.has(m.key)} toggle={()=>toggle(m.key)} fresh={false} acon={undefined} now={now.wall} jobId={model.jobId} controlId={`${instance}-unknown-${i}`}/>)}</div>}
    {model.diagnostics.length>0&&<div className="wd-notice" role="status">{model.diagnostics.map((d,i)=><p key={i}>{d}</p>)}</div>}
    <div className="wd-legend"><span><i className="wd-dot wd-blue"/>연결됨 / 실행 중</span><span><i className="wd-dot wd-red"/>연결 끊김 / 실패·취소</span><span><i className="wd-dot wd-gray"/>시작 전 / 확인 필요</span><span>✓ 현재 기준 유효 완료</span></div>
    <p className="wd-footnote">연결과 실행 상태는 별도로 표시합니다. 진행률은 서버의 유효 완료 단위 기준입니다. 구현은 코드·빌드를 포함하며 Test는 해당 IP의 장비 시험입니다.</p>
  </section>;
}
export const DiagramTab = memo(DiagramView,(previous,next)=>
  !previous.active&&!next.active || previous.model===next.model&&previous.observation===next.observation&&previous.active===next.active&&previous.acon===next.acon);
