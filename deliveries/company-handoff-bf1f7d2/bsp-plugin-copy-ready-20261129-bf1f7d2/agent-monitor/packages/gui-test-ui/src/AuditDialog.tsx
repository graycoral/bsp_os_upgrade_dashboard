import {useEffect, useRef, type KeyboardEvent, type ReactNode} from 'react';
import './tokens.css';
import './baseline.css';
import './audit-dialog.css';

function tabbableControls(dialog:HTMLDialogElement){
 return Array.from(dialog.querySelectorAll<HTMLElement>('button,input,select,textarea,a[href],area[href],summary,[contenteditable="true"],[tabindex]'))
  .filter(el=>el.tabIndex>=0&&!el.matches(':disabled,input[type="hidden"]')&&!el.closest('[hidden],[inert]')&&el.getClientRects().length>0&&getComputedStyle(el).visibility==='visible')
  .sort((a,b)=>(a.tabIndex||Infinity)-(b.tabIndex||Infinity));
}

export function AuditDialog({title,onClose,children,error='',busy=false,guiTest=false}:{title:string;onClose:()=>void;children:ReactNode;error?:string;busy?:boolean;guiTest?:boolean}){
 const dialog=useRef<HTMLDialogElement>(null), previous=useRef<HTMLElement|null>(null), alert=useRef<HTMLDivElement>(null);
 useEffect(()=>{const el=dialog.current!;previous.current=document.activeElement as HTMLElement;el.showModal();const overflow=document.body.style.overflow;document.body.style.overflow='hidden';return()=>{el.close();document.body.style.overflow=overflow;if(previous.current?.isConnected)previous.current.focus()}},[]);
 useEffect(()=>{if(error)alert.current?.focus()},[error]);
 function containTab(e:KeyboardEvent<HTMLDialogElement>){
  if(e.key!=='Tab')return;
  const controls=tabbableControls(e.currentTarget), first=controls[0],last=controls.at(-1),active=document.activeElement;
  // Native modal focus isolation does not prevent Tab moving into browser chrome.
  if(!first){e.preventDefault();e.currentTarget.focus()}
  else if(!controls.includes(active as HTMLElement)||e.shiftKey&&active===first||!e.shiftKey&&active===last){e.preventDefault();(e.shiftKey?last:first)?.focus()}
 }
 return <dialog ref={dialog} tabIndex={-1} className={guiTest?'gt-scope gt-audit-dialog':'veil audit-dialog'} aria-label={title} onKeyDown={containTab} onCancel={e=>{e.preventDefault();onClose()}} onClick={e=>{if(e.target===e.currentTarget)onClose()}}><section className={guiTest?'gt-dialog-panel':'modal'} aria-busy={busy}><div className={guiTest?'gt-dialog-head':'modal-head'}><h2>{title}</h2><button type="button" className={guiTest?'gt-dialog-close':'icon-btn'} aria-label="닫기" onClick={onClose}>×</button></div>{error&&<div ref={alert} tabIndex={-1} className={guiTest?'gt-dialog-error':'alert error'} role="alert">{error}</div>}{busy&&<p role="status">처리 중…</p>}{children}</section></dialog>;
}
