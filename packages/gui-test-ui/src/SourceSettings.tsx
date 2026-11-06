import {useEffect, useId, useRef, useState} from 'react';
import './source-settings.css';

type Data=Record<string,any>;
type SourceKind='legacy'|'server-folder'|'git-url';
export type SourceState={
  version:number;
  active:{kind:SourceKind;location:string;ref:string|null;commit:string|null;inspection_id:string|null;snapshot_id:string|null;source_revision:string|null};
  execution:{ready:boolean;reason:string|null;code:string};
};
type Inspection={inspection_id:string;kind:SourceKind;location:string;repository:boolean;refs:{name:string;ref:string;commit:string}[];default_ref:string|null;inspected_at:string};
type Load=(path:string,method?:string,data?:unknown,signal?:AbortSignal)=>Promise<any>;

export default function SourceSettings({load,active,disabled=false,onState,onApplied,onApplying}:{
  load:Load;active:boolean;disabled?:boolean;onState:(state:SourceState)=>void;
  onApplied:(state:SourceState,catalog:Data)=>void;onApplying:(value:boolean)=>void;
}) {
  const [saved,setSaved]=useState<SourceState|null>(null),[kind,setKind]=useState<SourceKind>('server-folder'),[location,setLocation]=useState('');
  const [inspection,setInspection]=useState<Inspection|null>(null),[ref,setRef]=useState('');
  const [loading,setLoading]=useState(false),[inspecting,setInspecting]=useState(false),[applying,setApplying]=useState(false);
  const [error,setError]=useState(''),[notice,setNotice]=useState(''),[reload,setReload]=useState(0);
  const initialized=useRef(false),edited=useRef(false),sequence=useRef(0),inspectionAbort=useRef<AbortController|null>(null);
  const callbacks=useRef({onState,onApplied,onApplying});callbacks.current={onState,onApplied,onApplying};
  const helpId=useId();
  useEffect(()=>{
    if(!active||initialized.current)return;
    let current=true;const controller=new AbortController();setLoading(true);
    load('/source','GET',undefined,controller.signal).then((value:SourceState)=>{
      if(!current)return;
      initialized.current=true;setSaved(value);callbacks.current.onState(value);
      // A slow initial read must not replace text the user has already typed.
      if(!edited.current&&value.active.kind!=='legacy'){setKind(value.active.kind);setLocation(value.active.location);}
    }).catch(e=>{if(current)setError((e as Error).message)}).finally(()=>{if(current)setLoading(false)});
    return()=>{current=false;controller.abort()};
  },[active,load,reload]);
  useEffect(()=>{if(!active){sequence.current++;inspectionAbort.current?.abort();setInspecting(false)}return()=>{inspectionAbort.current?.abort()}},[active]);
  function invalidate(){edited.current=true;sequence.current++;inspectionAbort.current?.abort();setInspection(null);setRef('');setInspecting(false);setError('');setNotice('');}
  async function inspect(){
    const current=++sequence.current;inspectionAbort.current?.abort();const controller=new AbortController();inspectionAbort.current=controller;
    setInspecting(true);setInspection(null);setRef('');setError('');setNotice('');
    try {
      const value:Inspection=await load('/source/inspect','POST',{kind,location:kind==='legacy'?'':location.trim()},controller.signal);
      if(current!==sequence.current)return;
      setInspection(value);setRef(value.default_ref&&value.refs.some(item=>item.ref===value.default_ref)?value.default_ref:value.refs[0]?.ref||'');
      setNotice(value.kind==='legacy'?'기존 기본 소스를 확인했습니다. 적용하면 관리 소스에서 기존 설정으로 돌아갑니다.':value.repository?'소스 확인 완료. 확인된 브랜치를 선택한 뒤 적용하세요.':'폴더 확인 완료. 현재 파일을 적용할 수 있습니다.');
    }catch(e){if(current===sequence.current)setError((e as Error).message)}finally{if(current===sequence.current)setInspecting(false)}
  }
  async function apply(){
    if(!saved||!inspection||(inspection.repository&&!ref))return;
    setApplying(true);callbacks.current.onApplying(true);setError('');setNotice('');
    try {
      const value:SourceState&{catalog:Data}=await load('/source','PUT',{inspection_id:inspection.inspection_id,ref:inspection.repository?ref:null,expected_version:saved.version});
      setSaved(value);callbacks.current.onState(value);callbacks.current.onApplied(value,value.catalog);
      setInspection(null);setRef('');setNotice('TC 소스를 적용했습니다. TC 선택·반복·Suite와 Preflight를 다시 준비하세요. 기존 Run 기록과 실행 명령 입력은 유지됩니다.');
    }catch(e){setError((e as Error).message)}finally{setApplying(false);callbacks.current.onApplying(false)}
  }
  function refresh(){sequence.current++;inspectionAbort.current?.abort();setInspection(null);setRef('');setInspecting(false);setError('');setNotice('');initialized.current=false;setReload(value=>value+1)}
  const locked=disabled||applying;
  return <div className="gt-source-settings">
    <section className="gt-source-applied" aria-label="현재 적용된 TC 소스">
      <div className="gt-source-applied-head"><h4>현재 적용된 TC 소스</h4><button type="button" disabled={locked||loading} onClick={refresh}>적용 상태 다시 확인</button></div>
      {!saved?<p role="status">{loading?'소스 설정을 불러오는 중…':'소스 설정을 확인하지 못했습니다.'}</p>:<>
        <dl><dt>유형</dt><dd>{saved.active.kind==='legacy'?'기존 설정 · Legacy':saved.active.kind==='git-url'?'Git 저장소 URL':'서버 폴더'}</dd>
          <dt>위치</dt><dd>{saved.active.location||'기존 실행기 설정 사용'}</dd>
          <dt>브랜치</dt><dd>{saved.active.kind==='legacy'?'기존 소스 설정에서 확인':saved.active.ref||'Git 브랜치 없음 / 폴더 현재 파일'}</dd>
          {saved.active.commit&&<><dt>커밋</dt><dd>{saved.active.commit}</dd></>}
          {saved.active.source_revision&&<><dt>TC 스냅샷 기준</dt><dd>{saved.active.source_revision}</dd></>}
          <dt>설정 버전</dt><dd>{saved.version}</dd>
        </dl>
        <p role="status" className={saved.execution.ready?'gt-muted':'gt-source-blocked'}>{saved.execution.ready?'소스 전달 가능 · 보드 연결과 Preflight는 별도로 확인합니다.':saved.execution.reason||'실행기를 준비한 뒤 실행할 수 있습니다.'}{saved.execution.code==='SOURCE_SNAPSHOT_UNSUPPORTED'?' · 관리 소스 스냅샷을 지원하는 Windows Runner로 업데이트하세요.':''}</p>
      </>}
    </section>
    <fieldset className="gt-source-editor" disabled={locked}>
      <legend>새 TC 소스 준비</legend>
      <label>TC 소스 유형<select aria-label="TC 소스 유형" value={kind} onChange={e=>{invalidate();setKind(e.target.value as SourceKind)}}><option value="server-folder">서버 폴더</option><option value="git-url">Git 저장소 URL</option><option value="legacy">기존 기본/Runner 공유 소스</option></select></label>
      <label>TC 소스 위치<input aria-label="TC 소스 위치" name="tc-source-location" autoComplete="off" spellCheck={false} aria-describedby={helpId} disabled={kind==='legacy'} value={kind==='legacy'?'':location} placeholder={kind==='legacy'?'기존 설정 사용':kind==='server-folder'?'/srv/test-cases':'https://git.example.com/team/test-cases.git'} onChange={e=>{invalidate();setLocation(e.target.value)}}/></label>
      <p id={helpId} className="gt-muted">{kind==='legacy'?'현재 보기 모드의 기본/Runner 공유 소스로 돌아갑니다. 위치 입력 없이 소스를 확인한 뒤 적용하세요.':kind==='server-folder'?'서버 폴더는 API 서버가 실행되는 호스트의 절대 경로입니다. 브라우저 PC의 폴더 선택이 아닙니다.':'GitHub·Gerrit의 clone URL을 입력하세요. 인증은 서버에 준비된 환경을 사용하며 URL에 암호·토큰을 넣지 마세요.'}</p>
      <button type="button" disabled={(kind!=='legacy'&&!location.trim())||inspecting} onClick={inspect}>{inspecting?'소스 확인 중…':'소스 확인'}</button>
      {inspection&&<div className="gt-source-inspection">
        {inspection.repository?<><label>TC 소스 브랜치<select aria-label="TC 소스 브랜치" value={ref} onChange={e=>{setRef(e.target.value);setNotice('')}}>{!inspection.refs.length&&<option value="">선택할 브랜치 없음</option>}{inspection.refs.map(item=><option key={item.ref} value={item.ref}>{item.name}</option>)}</select></label>
          <p className="gt-muted">선택한 커밋의 파일을 스냅샷으로 고정합니다. Git 폴더의 미커밋 변경은 포함하지 않으며 원본 작업 트리를 checkout하지 않습니다.</p>
          {ref&&<small className="gt-hash">선택 커밋 {inspection.refs.find(item=>item.ref===ref)?.commit}</small>}</>:<p>{inspection.kind==='legacy'?'기존 기본/Runner 공유 소스 사용':'Git 브랜치 없음 / 폴더 현재 파일'}</p>}
        <small className="gt-muted">확인한 위치: {inspection.location} · {inspection.inspected_at}</small>
      </div>}
      <button type="button" className="gt-primary" disabled={!saved||!inspection||(inspection.repository&&!ref)} onClick={apply}>{applying?'소스 적용 중…':'소스 적용'}</button>
      <small className="gt-muted">입력 → 소스 확인 → 브랜치 선택 → 소스 적용 순서입니다. 파일을 갱신하려면 소스를 다시 확인하고 적용하세요.</small>
      <small className="gt-muted">이 보기 모드의 TC 소스만 바뀝니다. 소스 적용으로 Mock/실제 연결 모드나 보드 실행 방식이 바뀌지 않습니다.</small>
    </fieldset>
    {error&&<div className="gt-alert error" role="alert">{error}</div>}
    {notice&&<p role="status" className="gt-source-notice">{notice}</p>}
  </div>;
}
