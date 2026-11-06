import React,{useState} from 'react';
import {createRoot} from 'react-dom/client';
import {TestPage,ExecutionViewSettings,type GuiTestHost} from '../../packages/gui-test-ui/src';
const flags=new URLSearchParams(location.search);
const tc={id:'portable/case.py',name:'Portable case',path:'portable/case.py',module:'portable',kind:'Single',timeout:10,content_hash:'fixture',after:[],disabled_reason:''};
const run={id:'portable-run',version:1,state:'PAUSED',overall_result:'INCOMPLETE',controller:'custom-controller',simulation:true,
 tests:[tc],results:{},attempts:[],progress:{done:0,total:1,percent:0,counts:{PENDING:1}},sync:{status:'NOT_LINKED'},
 connection_snapshot:{},execution_targets:{labels:['fixture-board']},source_revision:'portable-source',environment_ready:true};
if(flags.has('foreign'))run.controller='another-controller';
if(flags.has('terminal'))run.state='COMPLETED';
const memory=new Map([['gui-last-run','portable-run']]);
const state={calls:[] as any[],storage:[] as any[],modes:[] as string[],downloads:[] as string[],owned:[] as string[]};
(window as any).portableState=state;
const host:GuiTestHost={mode:'default',
 storage:{getItem(key){state.storage.push(['get',key]);return memory.get(key)??null},setItem(key,value){state.storage.push(['set',key,value]);memory.set(key,value)},removeItem(key){state.storage.push(['remove',key]);memory.delete(key)}},
 ownsSession(controller){state.owned.push(controller);return controller==='custom-controller'},
 applyMode(mode){state.modes.push(mode)},download(path){state.downloads.push(path);return '/custom-download'+path},
 async request(path,method='GET',data,signal){state.calls.push({path,method,data,signal:signal instanceof AbortSignal});
  if(path==='/capabilities')return {mode:'standalone',simulation:true,hardware:false,job_sync:false,branches:['demo/main']};
  if(path==='/source')return {version:0,active:{kind:'legacy',location:'',ref:null,commit:null,inspection_id:null,snapshot_id:null,source_revision:null},execution:{ready:true,reason:null,code:'READY'}};
  if(path.startsWith('/catalog'))return {tests:[tc],branch:'demo/main',revision:'portable-source',metadata_revision:''};
  if(path==='/boards')return {boards:[{host:'demo-windows',board_id:'demo-board-a',com:'COM3'}]};
  if(path==='/ports')return {ports:[]};
  if(path==='/runs')return [run];
  if(path==='/runs/portable-run')return run;
  if(path.startsWith('/saved/')||path.endsWith('/events'))return [];
  if(path.endsWith('/heartbeat'))return {ok:true};
  throw new Error('Unexpected custom host request '+path);
 }};
if(flags.has('observer'))delete host.ownsSession;
function Fixture(){const [active,setActive]=useState(true);return <>
 <button style={{position:"fixed",right:0,bottom:0,zIndex:99}} data-testid="toggle-mount" onClick={()=>setActive(!active)}>Toggle visibility</button>
 <ExecutionViewSettings host={host}/>
 <div data-testid="portable-mount" hidden={!active}><TestPage host={host} active={active}/></div>
 </>}
createRoot(document.getElementById('root')!).render(<Fixture/>);
