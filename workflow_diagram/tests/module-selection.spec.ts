import {jobFixture,moduleFixture,stage,legacySourceFixture} from './fixtures';
const {test,expect}=require('./runtime.cjs');
const {startAppServer}=require('./app-server.cjs');
const path=require('node:path');
let host:any;
test.beforeAll(async()=>{host=await startAppServer()});
test.afterAll(async()=>{await host?.close()});

const sourceRevision='synthetic-module-catalog';
const tests=[
 {id:'ethernet/core.py',name:'Ethernet core',path:'ethernet/core.py',module:'ethernet',kind:'Single',timeout:10,content_hash:'core-fixture',after:[],disabled_reason:''},
 {id:'ethernet/link.py',name:'Ethernet link',path:'ethernet/link.py',module:'ethernet',kind:'Single',timeout:10,content_hash:'link-fixture',after:[],disabled_reason:''},
 {id:'display/panel.py',name:'Display panel',path:'display/panel.py',module:'display',kind:'Single',timeout:10,content_hash:'panel-fixture',after:[],disabled_reason:''},
];
function bspJob(current:'ethernet'|'display'|null,version=1,attempt='attempt-1'){
 const modules=['ethernet','display'].map(id=>{
  const active=id===current;
  const value=moduleFixture(id,'boot',{name:id==='ethernet'?'Ethernet':'Display',current_stage:active?'device_test':'build'});
  value.stages.build=stage('SUCCEEDED');value.stages.verification=stage('SUCCEEDED');
  value.stages.device_test=stage(active?'WAITING_INPUT':'PENDING',{attempts:active?[{id:attempt,status:'WAITING_INPUT',ordinal:1,tool:'manual',started_at:'2026-11-05T00:00:00Z'}]:[]});
  return value;
 });
 return jobFixture(modules,{id:'job-module-fixture',version,fingerprint:'synthetic-plan-fingerprint',plan_version:1,boot_ready:true,state:'TESTING'});
}
async function mount(page:any,options:{deferEthernet?:boolean;selection?:any;failures?:number;catalogEmpty?:boolean}={}){
 const state:any={job:null,selectionRequests:[],preflights:[],starts:[],unexpected:[],held:null,release:null,failures:options.failures||0};
 let release:()=>void=()=>{};
 const deferred=new Promise<void>(resolve=>{release=resolve});state.release=release;
 const historical={id:'historical-run',version:1,state:'COMPLETED',overall_result:'PASS',controller:'module-fixture-session',simulation:true,
  tests:[{...tests[2],name:'Historical TC'}],results:{[tests[2].id]:'PASS'},attempts:[],progress:{done:1,total:1,percent:100,counts:{PASS:1}},
  sync:{status:'NOT_LINKED'},connection_snapshot:{},execution_targets:{labels:['historical-board']},source_revision:'historical-source'};
 await page.addInitScript(()=>{sessionStorage.setItem('gui-session','module-fixture-session');localStorage.setItem('gui-last-run','historical-run')});
 await page.route('**/module-selection-fixture',route=>route.fulfill({contentType:'text/html',body:`<!doctype html><html><head><meta charset="UTF-8"></head><body><div id="root"></div><script type="module">import RefreshRuntime from '/@react-refresh';RefreshRuntime.injectIntoGlobalHook(window);window.$RefreshReg$=()=>{};window.$RefreshSig$=()=>type=>type;window.__vite_plugin_react_preamble_installed__=true;</script><script type="module" src="/@vite/client"></script><script type="module" src="/@fs/${path.resolve(__dirname,'module-selection-host.tsx').replaceAll('\\','/')}"></script></body></html>`}));
 await page.route('**/api/**',async(route:any)=>{
  const request=route.request(),url=new URL(request.url()),p=url.pathname.replace('/api/v1/gui-test','');
  const json=(value:any,status=200)=>route.fulfill({status,contentType:'application/json',body:JSON.stringify(value)});
  if(p==='/source/request-settings')return json({catalog_timeout_seconds:100});
  if(p==='/source')return json(legacySourceFixture());
  if(p==='/capabilities')return json({mode:'dashboard',simulation:true,hardware:false,branches:['demo/main'],features:{}});
  if(p==='/catalog')return json({tests:options.catalogEmpty?[]:tests,branch:'demo/main',revision:options.catalogEmpty?'':sourceRevision});
  if(p==='/boards')return json({boards:[]});
  if(p==='/ports')return json({ports:[],status:'synthetic'});
  if(p==='/module-selection'){
   const moduleId=url.searchParams.get('module_id');state.selectionRequests.push(Object.fromEntries(url.searchParams));
   if(state.failures>0){state.failures--;return json({code:'MODULE_CONTEXT_CHANGED',message:'Synthetic transient module snapshot race'},409)}
   const module=state.job?.modules.find((item:any)=>item.id===moduleId);
   const attempt=module?.stages.device_test.attempts.at(-1);
   const candidates=tests.filter(item=>item.module===moduleId);
   const value={context:{job_id:state.job?.id,module_id:moduleId,attempt_id:attempt?.id,plan_version:state.job?.plan_version,
    fingerprint:state.job?.fingerprint,catalog_revision:sourceRevision},tests:candidates,tc_ids:candidates.map(item=>item.id),mode:'manual',blocked_reason:null,frozen:false,...options.selection};
   if(options.deferEthernet&&moduleId==='ethernet'&&!state.held){state.held=value;await deferred;}
   return json(value);
  }
  if(p==='/preflight'){state.preflights.push(request.postDataJSON());return json({ok:true,simulation:true,checks:['Synthetic only']})}
  if(p==='/runs'&&request.method()==='POST'){state.starts.push(request.postDataJSON());return json({message:'Fixture does not execute TC'},409)}
  if(p==='/runs')return json([historical]);
  if(p==='/runs/historical-run')return json(historical);
  if(p==='/runs/historical-run/events')return json([]);
  if(p==='/runs/historical-run/heartbeat')return json({ok:true});
  if(p.startsWith('/saved/')||p==='/demo/jobs')return json([]);
  state.unexpected.push(p);return json({message:'Unexpected synthetic endpoint'},404);
 });
 await page.goto(host.url+'/module-selection-fixture');
 if(!options.catalogEmpty)await expect(page.getByRole('checkbox',{name:'선택 Ethernet core',exact:true})).toBeChecked();
 await expect(page.getByRole('combobox',{name:'Run 이력',exact:true})).toHaveValue(historical.id);
 const update=async(job:any,active=true)=>{
  state.job=job;
  await page.evaluate(({job,active})=>(window as any).moduleSelectionFixture.update(job,active),{job,active});
  await expect(page.getByTestId('module-fixture-context')).toHaveText(`${job?.id||'none'}:${job?.version||0}:${String(active)}`);
 };
 return {state,update,historical};
}
async function settleResponse(page:any,response:any){
 await response.finished();
 await page.evaluate(()=>new Promise<void>(resolve=>requestAnimationFrame(()=>requestAnimationFrame(()=>resolve()))));
}
async function expectHistoricalRun(page:any){
 await expect(page.getByRole('combobox',{name:'Run 이력',exact:true})).toHaveValue('historical-run');
 await expect(page.locator('.gt-result-details tbody tr')).toHaveCount(1);
 await expect(page.locator('.gt-result-details tbody')).toContainText('Historical TC');
 await expect(page.getByTestId('run-state')).toHaveText('COMPLETED · PASS');
}

test('module entry selects only matching TC once, preserves manual edits on polling and invalidates Preflight for a new attempt',async({page})=>{
 const {state,update}=await mount(page);
 expect(state.selectionRequests).toEqual([]);
 await update(bspJob('ethernet'));
 const scope=page.getByRole('region',{name:'모듈 TC 대상',exact:true});await expect(scope).toContainText('2개 자동 검색');
 await expect(page.getByRole('checkbox',{name:'선택 Ethernet core',exact:true})).toBeChecked();
 const link=page.getByRole('checkbox',{name:'선택 Ethernet link',exact:true});await expect(link).toBeChecked();
 await expect(page.getByRole('checkbox',{name:'선택 Display panel',exact:true})).toHaveCount(0);
 const preflight=page.getByRole('button',{name:'Preflight 검사',exact:true}),start=page.getByRole('button',{name:'테스트 시작',exact:true});
 await preflight.click();await expect(start).toBeEnabled();
 expect(state.preflights[0].module_context).toEqual({job_id:'job-module-fixture',module_id:'ethernet',attempt_id:'attempt-1',plan_version:1,fingerprint:'synthetic-plan-fingerprint',catalog_revision:sourceRevision});
 expect(state.preflights[0].tc_ids).toEqual(['ethernet/core.py','ethernet/link.py']);
 await link.uncheck();await expect(start).toBeDisabled();
 const requestsBeforePoll=state.selectionRequests.length;
 await update(bspJob('ethernet',2));
 await page.evaluate(()=>new Promise<void>(resolve=>requestAnimationFrame(()=>requestAnimationFrame(()=>resolve()))));
 expect(state.selectionRequests).toHaveLength(requestsBeforePoll);await expect(link).not.toBeChecked();
 await update(bspJob('ethernet',2),false);
 const polling=page.waitForResponse((response:any)=>new URL(response.url()).pathname.endsWith('/module-selection'));
 await update(bspJob('ethernet',2),true);await settleResponse(page,await polling);
 await expect(link).not.toBeChecked();await expect(page.getByRole('checkbox',{name:'선택 Ethernet core',exact:true})).toBeChecked();
 await preflight.click();await expect(start).toBeEnabled();
 await update(bspJob('ethernet',3,'attempt-2'));await expect(link).toBeChecked();await expect(start).toBeDisabled();
 await expectHistoricalRun(page);expect(state.starts).toEqual([]);expect(state.unexpected).toEqual([]);
});

test('a delayed response for the previous module cannot replace the current module list or selection',async({page})=>{
 const {state,update}=await mount(page,{deferEthernet:true});
 try{
  await update(bspJob('ethernet'));await expect.poll(()=>Boolean(state.held)).toBe(true);
  const next=bspJob('display',2,'display-attempt');next.modules[0]=bspJob('ethernet').modules[0];
  await update(next);await page.getByRole('combobox',{name:'TC 대상 모듈',exact:true}).selectOption('display');
  await expect(page.getByRole('checkbox',{name:'선택 Display panel',exact:true})).toBeChecked();
  const oldResponse=page.waitForResponse((response:any)=>new URL(response.url()).pathname.endsWith('/module-selection')&&new URL(response.url()).searchParams.get('module_id')==='ethernet');
  state.release();await settleResponse(page,await oldResponse);
  await expect(page.getByRole('checkbox',{name:'선택 Display panel',exact:true})).toBeChecked();
  await expect(page.getByRole('checkbox',{name:'선택 Ethernet core',exact:true})).toHaveCount(0);
  await expect(page.getByRole('combobox',{name:'TC 대상 모듈',exact:true})).toHaveValue('display');
  await expectHistoricalRun(page);expect(state.starts).toEqual([]);expect(state.unexpected).toEqual([]);
 }finally{state.release()}
});

for(const frozen of [false,true])test(`automatic ownership displays ${frozen?'frozen':'configured waiting'} candidates but cannot create a duplicate GUI run`,async({page})=>{
 const {state,update}=await mount(page,{selection:{mode:'automatic',frozen,blocked_reason:'Synthetic automatic pipeline already owns this attempt'}});
 await update(bspJob('ethernet'));
 const scope=page.getByRole('region',{name:'모듈 TC 대상',exact:true});await expect(scope).toContainText('자동 장비 시험 · 읽기 전용');
 await expect(scope).toContainText('Synthetic automatic pipeline already owns this attempt');
 await expect(page.getByRole('checkbox',{name:'선택 Ethernet core',exact:true})).toBeChecked();
 for(const name of ['선택 Ethernet core','선택 Ethernet link','표시된 TC 전체 선택'])await expect(page.getByRole('checkbox',{name,exact:true})).toBeDisabled();
 await expect(page.getByRole('button',{name:'Preflight 검사',exact:true})).toBeDisabled();
 await expect(page.getByRole('button',{name:'테스트 시작',exact:true})).toBeDisabled();
 await page.getByRole('button',{name:'트리 모두 접기',exact:true}).click();
 await page.getByRole('button',{name:'트리 모두 펼치기',exact:true}).click();
 await expect(page.getByRole('checkbox',{name:'선택 Ethernet core',exact:true})).toBeChecked();
 await expectHistoricalRun(page);expect(state.preflights).toEqual([]);expect(state.starts).toEqual([]);expect(state.unexpected).toEqual([]);
});

test('an empty or blocked module selection shows its reason and never falls back to all TC',async({page})=>{
 const {state,update}=await mount(page,{selection:{tests:[],tc_ids:[],blocked_reason:'Synthetic module mapping has no matching TC'}});
 await update(bspJob('ethernet'));
 await expect(page.getByRole('region',{name:'모듈 TC 대상',exact:true})).toContainText('Synthetic module mapping has no matching TC');
 await expect(page.locator('.gt-tree-case')).toHaveCount(0);
 await expect(page.getByRole('button',{name:'Preflight 검사',exact:true})).toBeDisabled();
 await expect(page.getByRole('button',{name:'테스트 시작',exact:true})).toBeDisabled();
 await expectHistoricalRun(page);expect(state.preflights).toEqual([]);expect(state.starts).toEqual([]);expect(state.unexpected).toEqual([]);
});

test('a transient module snapshot conflict retries the same context and does not make ordinary version polls overwrite manual selection',async({page})=>{
 const {state,update}=await mount(page,{failures:1});
 await update(bspJob('ethernet'));
 await expect(page.getByRole('button',{name:'테스트 시작',exact:true})).toBeDisabled();
 const link=page.getByRole('checkbox',{name:'선택 Ethernet link',exact:true});await expect(link).toBeChecked();
 expect(state.selectionRequests).toHaveLength(2);expect(state.selectionRequests[0]).toEqual(state.selectionRequests[1]);
 await link.uncheck();await update(bspJob('ethernet',2));
 await page.evaluate(()=>new Promise<void>(resolve=>requestAnimationFrame(()=>requestAnimationFrame(()=>resolve()))));
 await expect(link).not.toBeChecked();expect(state.selectionRequests).toHaveLength(2);
 await expect(page.getByRole('button',{name:'모듈 TC 다시 확인',exact:true})).toHaveCount(0);
 await expectHistoricalRun(page);expect(state.starts).toEqual([]);expect(state.unexpected).toEqual([]);
});

test('exhausted module retries remain blocked until explicit recheck succeeds in the same context',async({page})=>{
 const {state,update}=await mount(page,{failures:3});await update(bspJob('ethernet'));
 const retry=page.getByRole('button',{name:'모듈 TC 다시 확인',exact:true});await expect(retry).toBeVisible();
 expect(state.selectionRequests).toHaveLength(3);
 await expect(page.getByRole('region',{name:'모듈 TC 대상',exact:true})).toContainText('모듈 TC 확인 실패');
 await expect(page.getByRole('button',{name:'Preflight 검사',exact:true})).toBeDisabled();
 await expect(page.getByRole('button',{name:'테스트 시작',exact:true})).toBeDisabled();
 await retry.press('Enter');await expect(page.getByRole('checkbox',{name:'선택 Ethernet core',exact:true})).toBeChecked();
 expect(state.selectionRequests).toHaveLength(4);
 await expect(retry).toHaveCount(0);await expectHistoricalRun(page);
 expect(state.preflights).toEqual([]);expect(state.starts).toEqual([]);expect(state.unexpected).toEqual([]);
});

test('offline live catalog does not hide the automatic pipeline frozen TC snapshot',async({page})=>{
 const {state,update}=await mount(page,{catalogEmpty:true,selection:{mode:'automatic',frozen:true,blocked_reason:'Synthetic automatic pipeline owns this frozen snapshot'}});
 const job=bspJob('ethernet');
 job.modules[0].stages.device_test={...job.modules[0].stages.device_test,status:'RUNNING',automation:{payload:{
  id:'frozen-automatic-payload',source_revision:sourceRevision,tests:tests.slice(0,2),
  cases:{boot:['ethernet/core.py'],functional:['ethernet/link.py']}}}};
 await update(job);
 await expect(page.getByRole('checkbox',{name:'선택 Ethernet core',exact:true})).toBeChecked();
 await expect(page.getByRole('checkbox',{name:'선택 Ethernet core',exact:true})).toBeDisabled();
 await expect(page.getByRole('checkbox',{name:'선택 Ethernet link',exact:true})).toBeChecked();
 await expect(page.getByRole('region',{name:'모듈 TC 대상',exact:true})).toContainText('자동 장비 시험 · 읽기 전용');
 expect(state.selectionRequests).toHaveLength(1);expect(state.selectionRequests[0].catalog_revision).toBe('');
 await expect(page.getByRole('button',{name:'Preflight 검사',exact:true})).toBeDisabled();
 await expect(page.getByRole('button',{name:'테스트 시작',exact:true})).toBeDisabled();
 await expectHistoricalRun(page);expect(state.preflights).toEqual([]);expect(state.starts).toEqual([]);expect(state.unexpected).toEqual([]);
});

test('manual module with no live catalog remains blocked without making an unbound selection request',async({page})=>{
 const {state,update}=await mount(page,{catalogEmpty:true});await update(bspJob('ethernet'));
 await expect(page.getByRole('region',{name:'모듈 TC 대상',exact:true})).toBeVisible();
 await page.evaluate(()=>new Promise<void>(resolve=>requestAnimationFrame(()=>requestAnimationFrame(()=>resolve()))));
 expect(state.selectionRequests).toEqual([]);await expect(page.locator('.gt-tree-case')).toHaveCount(0);
 await expect(page.getByRole('button',{name:'Preflight 검사',exact:true})).toBeDisabled();
 await expect(page.getByRole('button',{name:'테스트 시작',exact:true})).toBeDisabled();
 expect(state.starts).toEqual([]);expect(state.unexpected).toEqual([]);
});
