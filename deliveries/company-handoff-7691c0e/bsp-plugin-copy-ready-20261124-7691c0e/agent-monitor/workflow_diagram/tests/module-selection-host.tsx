import React, {useEffect, useState} from 'react';
import {createRoot} from 'react-dom/client';
import {TestPage} from '../../packages/gui-test-ui/src';
import {guiTestHost, toGuiTestModuleContext} from '../../apps/web/src/guiTestHost';
import '../../apps/web/src/style.css';

function ModuleSelectionHost(){
 const [job,setJob]=useState<any>(null),[active,setActive]=useState(true);
 useEffect(()=>{
  (window as any).moduleSelectionFixture={update(next:any,visible=true){setJob(next);setActive(visible)}};
  return()=>{delete (window as any).moduleSelectionFixture};
 },[]);
 return <>
  <output data-testid="module-fixture-context">{job?.id||'none'}:{job?.version||0}:{String(active)}</output>
  <div hidden={!active}><TestPage host={guiTestHost} moduleContext={toGuiTestModuleContext(job)} active={active}/></div>
 </>;
}
createRoot(document.getElementById('root')!).render(<ModuleSelectionHost/>);
