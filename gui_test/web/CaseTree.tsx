import {useEffect, useId, useLayoutEffect, useMemo, useRef, useState} from 'react';
type Case = Record<string, any>;
type TreeNode = {path:string; name:string; folders:Map<string,TreeNode>; cases:Case[]; descendants:Case[]};
const collator=new Intl.Collator('ko',{numeric:true,sensitivity:'base'});
export default function CaseTree({tests,selected,onSelect,onReorder,repeats,onRepeat}: {
  repeats:Record<string,number>;onRepeat:(id:string,count:number)=>void;tests:Case[];selected:string[];onSelect:(ids:string[],on:boolean)=>void;onReorder:(ids:string[])=>void;
}) {
  const [repeatEditor,setRepeatEditor]=useState('');
  const [search,setSearch]=useState(''),[kind,setKind]=useState('all'),[sort,setSort]=useState('execution');
  const [closed,setClosed]=useState<Set<string>>(new Set());
  const [dragging,setDragging]=useState(''),[target,setTarget]=useState<{id:string;after:boolean}|null>(null);
  const [announcement,setAnnouncement]=useState('');
  const dragged=useRef('');
  const orderPreview=useRef<HTMLUListElement>(null), movedFocus=useRef<{id:string;direction:number}|null>(null);
  useLayoutEffect(()=>{const moved=movedFocus.current;if(!moved)return;movedFocus.current=null;const row=orderPreview.current?.querySelector<HTMLElement>(`[data-order-id="${CSS.escape(moved.id)}"]`);const sameDirection=row?.querySelector<HTMLButtonElement>(`button[data-order-direction="${moved.direction}"]:not(:disabled)`);(sameDirection||row?.querySelector<HTMLButtonElement>('button:not(:disabled)'))?.focus()},[selected]);
  const shown=useMemo(()=>tests.filter(t=>(kind==='all'||t.kind===kind)&&(t.name+' '+t.path).toLowerCase().includes(search.trim().toLowerCase())),[tests,kind,search]);
  const testsById=useMemo(()=>new Map(tests.map(t=>[t.id,t])),[tests]);
  const selectedOrder=useMemo(()=>new Map(selected.map((id,index)=>[id,index])),[selected]);
  const allCheckbox=useRef<HTMLInputElement>(null);
  const available=useMemo(()=>shown.filter(t=>!t.disabled_reason),[shown]);
  const selectedSet=useMemo(()=>new Set(selected),[selected]);
  const selectedCount=available.filter(t=>selectedSet.has(t.id)).length;
  useEffect(()=>{if(allCheckbox.current)allCheckbox.current.indeterminate=selectedCount>0&&selectedCount<available.length;},[selectedCount,available.length]);
  const root=useMemo(()=>{const root:TreeNode={path:'',name:'',folders:new Map(),cases:[],descendants:[]};
  for(const tc of shown){
    let node=root;node.descendants.push(tc);
    for(const name of String(tc.path).replaceAll('\\','/').split('/').slice(0,-1).filter(Boolean)){
      const path=node.path?node.path+'/'+name:name;
      if(!node.folders.has(name))node.folders.set(name,{path,name,folders:new Map(),cases:[],descendants:[]});
      node=node.folders.get(name)!;node.descendants.push(tc);
    }
    node.cases.push(tc);
  }
  return root;},[shown]);
  function compare(a:Case,b:Case){
    if(sort==='execution')return (selectedOrder.get(a.id)??Infinity)-(selectedOrder.get(b.id)??Infinity)||collator.compare(a.name,b.name);
    if(sort.startsWith('kind'))return (sort==='kind-desc'?-1:1)*collator.compare(a.kind,b.kind)||collator.compare(a.name,b.name);
    if(sort.startsWith('timeout'))return (sort==='timeout-desc'?-1:1)*(a.timeout-b.timeout)||collator.compare(a.name,b.name);
    return (sort==='name-desc'?-1:1)*collator.compare(a.name,b.name);
  }
  function clearDrag(){dragged.current='';setDragging('');setTarget(null);}
  function drop(e:React.DragEvent,id:string){
    e.preventDefault();const from=dragged.current;
    if(from&&from!==id&&selectedSet.has(from)&&selectedSet.has(id)&&e.dataTransfer.getData('text/plain')===from){
      const bounds=e.currentTarget.getBoundingClientRect(),after=e.clientY>bounds.top+bounds.height/2;
      const next=selected.filter(value=>value!==from);next.splice(next.indexOf(id)+(after?1:0),0,from);
      if(next.some((value,i)=>value!==selected[i])){onReorder(next);setSort('execution');setAnnouncement('실행 순서를 변경했습니다. Preflight를 다시 검사하세요.');}
    }
    clearDrag();
  }
  function row(t:Case){return <li key={t.id} data-tc-id={t.id} draggable={selectedSet.has(t.id)&&!t.disabled_reason}
    className={'gt-tree-case '+(dragging===t.id?'is-dragging ':'')+(target?.id===t.id?(target?.after?'drop-after':'drop-before'):'')}
    onDragStart={e=>{if((e.target as HTMLElement).closest('button,input')){e.preventDefault();return;}dragged.current=t.id;setDragging(t.id);e.dataTransfer.effectAllowed='move';e.dataTransfer.setData('text/plain',t.id);}}
    onDragEnd={clearDrag} onDragOver={e=>{if(!dragged.current||!selectedSet.has(t.id)||dragged.current===t.id)return;e.preventDefault();e.dataTransfer.dropEffect='move';const b=e.currentTarget.getBoundingClientRect();setTarget({id:t.id,after:e.clientY>b.top+b.height/2});}}
    onDragLeave={e=>{if(!e.currentTarget.contains(e.relatedTarget as Node|null))setTarget(old=>old?.id===t.id?null:old);}} onDrop={e=>drop(e,t.id)}>
    <label className={'gt-tc'+(selectedSet.has(t.id)?' is-selected':'')+(t.disabled_reason?' is-disabled':'')} title={t.path+' · '+(t.disabled_reason||t.timeout+'s 제한')}>
      <span aria-hidden="true" className="gt-drag-handle" draggable={selectedSet.has(t.id)&&!t.disabled_reason}>⠿</span><input type="checkbox" aria-label={'선택 '+t.name} disabled={!!t.disabled_reason} checked={selectedSet.has(t.id)} onChange={e=>onSelect([t.id],e.target.checked)}/>
      <span className="gt-tc-copy"><span className="gt-tc-name">{t.name}</span><small>{t.disabled_reason||`${t.timeout}s 제한`}</small></span><span className={'gt-kind '+(t.kind==='Dual'?'dual':'single')}>{t.kind}</span><span className="gt-tc-time">{t.timeout}s</span>
    </label>
    <div className="gt-tc-actions"><button className="gt-repeat-toggle" aria-label={t.name+' 실행 횟수 설정'} title={'실행 횟수: '+(repeats[t.id]||1)+'회'} aria-expanded={repeatEditor===t.id} onClick={()=>setRepeatEditor(repeatEditor===t.id?'':t.id)}><svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" aria-hidden="true"><path d="m17 2 4 4-4 4M3 11V8a2 2 0 0 1 2-2h16M7 22l-4-4 4-4m14-1v3a2 2 0 0 1-2 2H3"/></svg>{(repeats[t.id]||1)>1&&<span>×{repeats[t.id]}</span>}</button>
</div>
    {repeatEditor===t.id&&<label className="gt-repeat-editor">실행 횟수<input type="number" min="1" max="100" step="1" aria-label={t.name+' 실행 횟수'} value={repeats[t.id]||1} onChange={e=>{const n=Number(e.target.value);if(Number.isInteger(n)&&n>=1&&n<=100)onRepeat(t.id,n);}}/><small>각 전체 회차에서 반복 · 1~100회</small></label>}
  </li>;}
  function children(node:TreeNode):React.ReactNode{return <>
    {[...node.folders.values()].sort((a,b)=>(sort==='name-desc'?-1:1)*collator.compare(a.name,b.name)).map(folder=><Folder key={folder.path} node={folder} selected={selectedSet} onSelect={onSelect} open={!closed.has(folder.path)} toggle={()=>setClosed(old=>{const next=new Set(old);next.has(folder.path)?next.delete(folder.path):next.add(folder.path);return next;})}>{!closed.has(folder.path)&&children(folder)}</Folder>)}
    {[...node.cases].sort(compare).map(row)}
  </>;}
  function paths(node:TreeNode):string[]{return [...node.folders.values()].flatMap(n=>[n.path,...paths(n)]);}
  function move(id:string,direction:number){const index=selectedOrder.get(id);if(index==null||index+direction<0||index+direction>=selected.length)return;const next=[...selected];[next[index],next[index+direction]]=[next[index+direction],next[index]];movedFocus.current={id,direction};onReorder(next);setSort('execution');setAnnouncement(`${testsById.get(id)?.name||id}: ${index+direction+1}/${next.length}번째로 이동했습니다. Preflight를 다시 검사하세요.`)}
  const folderPaths=paths(root),allExpanded=folderPaths.length>0&&folderPaths.every(path=>!closed.has(path));
  function sortHeader(key:string,label:string){return <button key={key} aria-label={label+' 정렬'} aria-pressed={sort.startsWith(key)} title={(key==='timeout'?'제한 시간':label)+' 정렬 · 클릭하면 '+(sort===key+'-asc'?'내림차순':'오름차순')} onClick={()=>setSort(sort===key+'-asc'?key+'-desc':key+'-asc')}>{label}<span aria-hidden="true">{sort===key+'-asc'?'↑':sort===key+'-desc'?'↓':''}</span></button>;}
  return <>
    <div className="gt-catalog-tools"><label>TC 검색<input name="tc-search" autoComplete="off" spellCheck={false} aria-label="TC 검색" placeholder="이름 · 경로 검색…" value={search} onChange={e=>{setSearch(e.target.value);setClosed(new Set());}}/></label>
      <label>유형<select aria-label="연결 유형 필터" value={kind} onChange={e=>{setKind(e.target.value);setClosed(new Set());}}><option value="all">전체</option><option>Single</option><option>Dual</option></select></label>

    </div>
    <div className="gt-tree-actions gt-tree-icon-actions"><button type="button" aria-label={allExpanded?'트리 모두 접기':'트리 모두 펼치기'} title={allExpanded?'트리 모두 접기':'트리 모두 펼치기'} aria-expanded={allExpanded} disabled={!folderPaths.length} onClick={()=>setClosed(allExpanded?new Set(folderPaths):new Set())}><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true"><path d={allExpanded?'M5 12h14':'M12 5v14M5 12h14'}/></svg></button></div>
    <div className="gt-list-meta"><span>{selectedCount}/{available.length}개 선택 · {shown.length}/{tests.length}개 표시</span></div>
    <div className="gt-column-head" role="group" aria-label="TC 목록 정렬">
      <div className="gt-name-head"><label className="gt-select-all" title="표시된 TC 전체 선택 / 해제"><input ref={allCheckbox} type="checkbox" aria-label="표시된 TC 전체 선택" disabled={!available.length} checked={available.length>0&&selectedCount===available.length} onChange={e=>onSelect(available.map(t=>t.id),e.target.checked)}/></label>{sortHeader('name','이름')}</div>
      {sortHeader('kind','유형')}{sortHeader('timeout','시간')}
      <button className="gt-order-reset" aria-label="실행 순서로 보기" title="실행 순서로 보기 · 표시 정렬만 초기화" aria-pressed={sort==='execution'} onClick={()=>setSort('execution')}>↶</button>
    </div>
    <div className="gt-tree" role="group" aria-label="테스트 케이스 목록"><ul className="gt-tree-root">{children(root)}</ul>{!shown.length&&<div className="gt-catalog-empty">검색 결과가 없습니다.<button onClick={()=>{setSearch('');setKind('all');setClosed(new Set());}}>검색·필터 초기화</button></div>}</div>
    <p className="gt-selection-note">전체·폴더 선택은 검색·필터에 표시된 실행 가능한 TC에만 적용됩니다. 필터 밖 선택은 유지됩니다. 선택한 TC를 끌거나 아래 실행 순서의 위·아래 이동 버튼으로 순서를 바꿀 수 있으며 검색·정렬은 실행 순서를 유지합니다.</p>
    <details className="gt-order-preview"><summary>현재 실행 순서 확인</summary><ul ref={orderPreview} aria-label="TC 실행 순서">{selected.map(id=><li key={id} data-order-id={id}><span>{testsById.get(id)?.name||id}</span><div><button type="button" data-order-direction="-1" aria-label={(testsById.get(id)?.name||id)+' 위로 이동'} disabled={selectedOrder.get(id)===0} onClick={()=>move(id,-1)}>↑</button><button type="button" data-order-direction="1" aria-label={(testsById.get(id)?.name||id)+' 아래로 이동'} disabled={selectedOrder.get(id)===selected.length-1} onClick={()=>move(id,1)}>↓</button></div></li>)}</ul></details>
    <span className="gt-sr-only" aria-live="polite">{announcement}</span>
  </>;
}
function Folder({node,selected,onSelect,open,toggle,children}:{node:TreeNode;selected:ReadonlySet<string>;onSelect:(ids:string[],on:boolean)=>void;open:boolean;toggle:()=>void;children:React.ReactNode}){
  const id=useId(),checkbox=useRef<HTMLInputElement>(null);
  const available=node.descendants.filter(t=>!t.disabled_reason),count=available.filter(t=>selected.has(t.id)).length;
  useEffect(()=>{if(checkbox.current)checkbox.current.indeterminate=count>0&&count<available.length;},[count,available.length]);
  return <li className="gt-case-group"><div className="gt-folder-head"><label className="gt-folder-select"><input ref={checkbox} type="checkbox" aria-label={'폴더 '+node.path} checked={available.length>0&&count===available.length} disabled={!available.length} onChange={e=>onSelect(available.map(t=>t.id),e.target.checked)}/></label><button type="button" aria-label={node.path+' 폴더 목록'} aria-expanded={open} aria-controls={id} onClick={toggle}><span aria-hidden="true">{open?'▾':'▸'}</span><span className="gt-folder-name">{node.name}</span><span className="gt-folder-count">{count}/{available.length}</span></button></div><ul id={id} className="gt-case-list" hidden={!open}>{children}</ul></li>;
}
