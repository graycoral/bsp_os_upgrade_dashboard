import {useEffect, useId, useRef, useState, type ReactNode} from 'react';

import {useGuiTestHost} from './HostContext';
import {type GuiTestHost} from './host';

export type SettingsFold = {open:boolean};

// One mounted editor per section. Folding changes visibility, never its draft.
export default function SettingsSection({name, number, title, summary='', children, compact=false, defaultOpen=true, fold, hidden=false, className='',host:providedHost}: {
  name:string; number?:string; title:string; summary?:string; children:ReactNode; compact?:boolean;
  defaultOpen?:boolean; fold?:SettingsFold; hidden?:boolean; className?:string;host?:GuiTestHost;
}) {
  const host=useGuiTestHost(providedHost);
  const contentId=useId(), section=useRef<HTMLElement>(null);
  const storageKey='gui-settings-panel:'+name;
  const [open,setOpen]=useState(()=>{try {const saved=host.storage.getItem(storageKey);return saved===null?defaultOpen:saved!=='collapsed';} catch {return defaultOpen;}});
  function remember(next:boolean) {setOpen(next);try {host.storage.setItem(storageKey,next?'expanded':'collapsed');}catch{/* Optional browser preference. */}}
  useEffect(()=>{if(fold)remember(fold.open)},[fold,storageKey]);
  useEffect(()=>{const node=section.current;const reveal=()=>remember(true);node?.addEventListener('settings-reveal',reveal);return()=>node?.removeEventListener('settings-reveal',reveal)},[storageKey]);
  return <section ref={section} hidden={hidden} data-settings-section={name} className={'gt-panel gt-settings-panel'+(compact?' gt-settings-compact':'')+' '+className}>
    <h3><button className="gt-settings-toggle" type="button" aria-label={title} aria-expanded={open} aria-controls={contentId} onClick={()=>remember(!open)}>
      {number&&<span className="gt-settings-number" aria-hidden="true">{number}</span>}
      <span className="gt-settings-label"><span className="gt-settings-title">{title}</span>{summary&&<span className="gt-settings-summary">{summary}</span>}</span>
      <span className="gt-settings-action" aria-hidden="true">{open?'접기':'펼치기'}<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d={open?'m6 15 6-6 6 6':'m6 9 6 6 6-6'}/></svg></span>
    </button></h3>
    <div id={contentId} className="gt-settings-content" hidden={!open}>{children}</div>
  </section>;
}
