import React, {useState} from 'react';
import {createRoot} from 'react-dom/client';
import {AuditDialog} from '../../gui_test/web/AuditDialog';
import {Bar} from '../../apps/web/src/ProgressBar';
import CaseTree from '../../gui_test/web/CaseTree';
import '../../apps/web/src/style.css';
import '../../gui_test/web/test.css';

const tests=[
  {id:'a',name:'Alpha',path:'first/alpha.py',kind:'Single',timeout:10},
  {id:'b',name:'Beta',path:'second/beta.py',kind:'Dual',timeout:10},
  {id:'c',name:'Gamma',path:'second/gamma.py',kind:'Single',timeout:10},
  {id:'d',name:'Disabled',path:'first/disabled.py',kind:'Single',timeout:10,disabled_reason:'Synthetic unavailable'},
];
function Host(){
 const [open,setOpen]=useState(false),[selected,setSelected]=useState(['a','b','c']);
 return <div className="gt">
  <button onClick={()=>setOpen(true)}>Open fixture dialog</button><button>Background action</button>
  {open&&<AuditDialog title="Fixture dialog" onClose={()=>setOpen(false)}>
    <button hidden>Hidden action</button><button style={{display:'none'}}>CSS hidden action</button><button disabled>Disabled action</button>
    <label>Visible field<input/></label><button>Last action</button>
  </AuditDialog>}
  <Bar value={{percent:0}} label="Zero progress"/><Bar value={{percent:null}} label="Unavailable progress"/>
  <output data-testid="selected-order">{selected.join(',')}</output>
  <CaseTree tests={tests} selected={selected} onSelect={(ids,on)=>setSelected(old=>on?[...old,...ids.filter(id=>!old.includes(id))]:old.filter(id=>!ids.includes(id)))} onReorder={setSelected} repeats={{}} onRepeat={()=>{}}/>
 </div>;
}
createRoot(document.getElementById('root')!).render(<Host/>);
