import {jobFixture, moduleFixture} from './fixtures';
const {test,expect}=require('./runtime.cjs');
const {startAppServer}=require('./app-server.cjs');
const path=require('node:path');
let host:any;
test.beforeAll(async()=>{host=await startAppServer()});
test.afterAll(async()=>{await host?.close()});

const profile={execution:'demo',runner:'bridge',host:'synthetic',account:'',workspace:'/synthetic',source_revision:'',old_base:'',vendor_tree:'',new_base:'',
 tool_paths:{},models:{},role_instructions:{},disabled_tools:[],agent_instructions:'',build_env_script:'',build_command:'',artifact_path:'',verification_command:'',integration_command:'',
 build_argv:[],agents:{claude:[],opencode:[],codex:[]},modules:[],max_analysis:3,timeout_seconds:900,jira_mode:'direct',jira_url:'',jira_project:'',jira_auth_env:'BSP_JIRA_TOKEN',mcp_name:'',mcp_argv:[],jira_api_version:'2',jira_issue_type:'Task'};
async function mock(page:any,options:{gui?:boolean;capabilities?:any;catalog?:any}={}){
 const config={version:1,profile:structuredClone(profile)},job=jobFixture([moduleFixture('A')]);
 const state={writes:[] as any[],validations:0,unexpected:[] as string[]};
 const run={id:'synthetic-run',version:3,state:'RUNNING',controller:'synthetic-session',simulation:true,environment_ready:true,overall_result:'PENDING',
  progress:{done:0,total:1,percent:0,counts:{}},tests:[],attempts:[],results:{},connection_snapshot:{a:{},b:null},sync:{status:'PENDING'},execution_targets:[]};
 await page.addInitScript(()=>{sessionStorage.setItem('gui-session','synthetic-session');localStorage.setItem('gui-last-run','synthetic-run')});
 await page.context().route('**/api/**',async(route:any)=>{
  const r=route.request(),p=new URL(r.url()).pathname,method=r.method();
  const json=(data:any,status=200)=>route.fulfill({status,contentType:'application/json',body:JSON.stringify(data)});
  if(p==='/api/v1/config/validate'){state.validations++;return json(r.postDataJSON())}
  if(p==='/api/v1/config'){if(method==='PUT'){state.writes.push({p,body:r.postDataJSON()});Object.assign(config,r.postDataJSON())}return json(config)}
  if(p==='/api/v1/config/probe'||p==='/api/v1/jira/probe'){state.writes.push({p});return json({checks:[],status:'MOCK'})}
  if(p==='/api/v1/jobs')return json([job]);
  if(p===`/api/v1/jobs/${job.id}`)return json(job);
  if(p.endsWith('/events'))return json([]);
  if(p.startsWith('/api/v1/gui-test/')){
   const q=p.replace('/api/v1/gui-test','').replace(/^\/live/,'');
   if(q==='/capabilities')return json(options.capabilities||{simulation:true,hardware:false,mode:'dashboard'});
   if(q==='/catalog')return json(options.catalog||{tests:[],branch:'synthetic',revision:'synthetic'});
   if(q==='/boards')return json({boards:[]});
   if(q==='/ports')return json([]);
   if(q==='/runs')return json(options.gui?[run]:[]);
   if(q==='/runs/synthetic-run')return json(run);
   if(q==='/runs/synthetic-run/actions/cancel'){state.writes.push({p,body:r.postDataJSON()});return json({...run,state:'CANCELLED',version:4})}
   if(q==='/runs/synthetic-run/heartbeat')return json({ok:true});
   if(q.startsWith('/saved/')||q==='/demo/jobs')return json([]);
  }
  state.unexpected.push(p);return json({message:'Unconfigured synthetic endpoint'},404);
 });
 return state;
}
async function fixture(page:any){
 await page.route('**/guidelines-fixture',route=>route.fulfill({contentType:'text/html',body:`<!doctype html><html><head><meta charset="UTF-8"></head><body><div id="root"></div><script type="module">import RefreshRuntime from '/@react-refresh';RefreshRuntime.injectIntoGlobalHook(window);window.$RefreshReg$=()=>{};window.$RefreshSig$=()=>type=>type;window.__vite_plugin_react_preamble_installed__=true;</script><script type="module" src="/@vite/client"></script><script type="module" src="/@fs/${path.resolve(__dirname,'guidelines-host.tsx').replaceAll('\\','/')}"></script></body></html>`}));
 await page.route('**/api/**',route=>route.abort());
 await page.goto(host.url+'/guidelines-fixture');
 await expect(page.getByRole('button',{name:'Open fixture dialog'})).toBeVisible();
}
async function dismissDirtyReload(page:any){
 const pending=page.waitForEvent('dialog');
 // A dismissed reload produces no load event, so page.reload() cannot be awaited.
 await page.evaluate(()=>{setTimeout(()=>location.reload(),0)});
 const dialog=await pending;expect(dialog.type()).toBe('beforeunload');await dialog.dismiss();
}

test('native modal confines Tab to visible enabled controls, blocks background focus and restores Escape focus',async({page})=>{
 await fixture(page);const opener=page.getByRole('button',{name:'Open fixture dialog'});await opener.click();
 const dialog=page.getByRole('dialog',{name:'Fixture dialog'});await expect(dialog).toBeVisible();
 expect(await dialog.evaluate(el=>el instanceof HTMLDialogElement&&el.matches(':modal'))).toBe(true);
 for(let i=0;i<9;i++){
  expect(await dialog.evaluate(el=>el.contains(document.activeElement))).toBe(true);
  expect(await page.evaluate(()=>['Hidden action','CSS hidden action','Disabled action'].includes(document.activeElement?.textContent||''))).toBe(false);
  await page.keyboard.press(i%2?'Tab':'Shift+Tab');
 }
 await page.getByRole('button',{name:'Background action'}).evaluate(el=>(el as HTMLElement).focus());
 expect(await dialog.evaluate(el=>el.contains(document.activeElement))).toBe(true);
 await page.keyboard.press('Escape');await expect(dialog).toHaveCount(0);await expect(opener).toBeFocused();
});

test('contextual progress preserves zero and gives unavailable data separate semantics',async({page})=>{
 await fixture(page);
 await expect(page.getByRole('progressbar',{name:'Zero progress'})).toHaveAttribute('aria-valuenow','0');
 await expect(page.getByRole('status',{name:/Unavailable progress/})).toBeVisible();
 await expect(page.getByRole('progressbar')).toHaveCount(1);
});

test('sidebar links support new tabs, history and reload while preserving execution query',async({page,context})=>{
 const state=await mock(page);await page.goto(host.url+'/?tab=overview&guiExecution=live&keep=synthetic');
 const nav=page.getByRole('navigation'),settings=nav.getByRole('link',{name:'환경 설정',exact:true});
 expect(new URL(await settings.getAttribute('href'),host.url).searchParams.get('guiExecution')).toBe('live');
 const [popup]=await Promise.all([context.waitForEvent('page'),settings.click({modifiers:['Control']})]);
 await popup.waitForURL(/tab=settings/);expect(new URL(popup.url()).searchParams.get('guiExecution')).toBe('live');await popup.close();
 await settings.click();await expect(settings).toHaveAttribute('aria-current','page');await expect(page).toHaveURL(/tab=settings/);
 await nav.getByRole('link',{name:'실행 기록',exact:true}).click();await page.goBack();await expect(settings).toHaveAttribute('aria-current','page');
 await page.reload();await expect(settings).toHaveAttribute('aria-current','page');expect(new URL(page.url()).searchParams.get('keep')).toBe('synthetic');
 expect(state.unexpected).toEqual([]);
});

test('all six workspace tabs omit heading introductions and preserve navigation',async({page})=>{
 const state=await mock(page,{gui:true});await page.goto(host.url+'/?tab=overview');
 const nav=page.getByRole('navigation');
 for(const name of ['대시보드','다이어그램','사람 검토 · Jira','Test 현황','실행 기록','환경 설정']){
  const link=nav.getByRole('link',{name,exact:true});await link.click();await expect(link).toHaveAttribute('aria-current','page');
  if(name==='Test 현황'){
   await expect(page.getByRole('heading',{name:'Test 현황',exact:true})).toBeVisible();
   await expect(page.locator('.gt-intro>div>p')).toHaveCount(0);
  }else{
   await expect(page.locator('.heading h1')).toBeVisible();
   await expect(page.locator('.heading>div>p')).toHaveCount(0);
  }
 }
 expect(state.writes).toEqual([]);expect(state.unexpected).toEqual([]);
});

test('view mode applies explicitly from environment settings and preserves URL context without config writes',async({page})=>{
 const state=await mock(page);await page.goto(host.url+'/?tab=settings&guiExecution=default&keep=fixture#mode');
 const setting=page.getByRole('region',{name:'Test 현황 보기 모드',exact:true});
 const select=setting.getByRole('combobox',{name:'Test 현황 보기 모드',exact:true});
 const apply=setting.getByRole('button',{name:'보기 모드 적용',exact:true});
 await expect(select).toHaveValue('default');await expect(apply).toBeDisabled();
 const initialUrl=page.url();await select.selectOption('live');await expect(apply).toBeEnabled();
 expect(page.url()).toBe(initialUrl);expect(await page.evaluate(()=>localStorage.getItem('gui-execution-view'))).toBe('default');
 await apply.click();await expect(page).toHaveURL(/guiExecution=live/);await expect(select).toHaveValue('live');await expect(apply).toBeDisabled();
 const next=new URL(page.url());expect(next.searchParams.get('tab')).toBe('settings');expect(next.searchParams.get('keep')).toBe('fixture');expect(next.hash).toBe('#mode');
 expect(await page.evaluate(()=>localStorage.getItem('gui-execution-view'))).toBe('live');
 await page.getByRole('navigation').getByRole('link',{name:'Test 현황',exact:true}).click();
 await expect(page.getByRole('button',{name:'실제 연결 모드로 전환'})).toHaveCount(0);
 await expect(page.getByRole('button',{name:'기존 모드 보기'})).toHaveCount(0);
 await page.getByRole('button',{name:'연결 및 실행 설정',exact:true}).click();
 await expect(page.getByRole('combobox',{name:'Test 현황 보기 모드',exact:true})).toHaveCount(0);
 expect(state.writes).toEqual([]);expect(state.unexpected).toEqual([]);
});

test('cancelled view mode navigation preserves unsaved environment edits and the saved mode',async({page})=>{
 const state=await mock(page);await page.goto(host.url+'/?tab=settings&guiExecution=default&keep=fixture#dirty');
 const workspace=page.getByLabel('프로젝트 작업 폴더',{exact:true});await workspace.fill('/synthetic/unsaved-mode-edit');
 const select=page.getByRole('combobox',{name:'Test 현황 보기 모드',exact:true});await select.selectOption('live');
 const initialUrl=page.url(),pending=page.waitForEvent('dialog');
 const clicking=page.getByRole('button',{name:'보기 모드 적용',exact:true}).click();
 const dialog=await pending;expect(dialog.type()).toBe('beforeunload');await dialog.dismiss();await clicking;
 expect(page.url()).toBe(initialUrl);await expect(workspace).toHaveValue('/synthetic/unsaved-mode-edit');await expect(select).toHaveValue('live');
 expect(await page.evaluate(()=>localStorage.getItem('gui-execution-view'))).toBe('default');
 expect(state.writes).toEqual([]);expect(state.unexpected).toEqual([]);
});

test('runner connection help is absent when ready and folded with keyboard access when unavailable',async({page})=>{
 const capabilities={simulation:false,hardware:true,mode:'dashboard',connection:{state:'connected',ready:true,message:'Synthetic ready'}};
 const state=await mock(page,{capabilities});await page.goto(host.url+'/?tab=gui-test&guiExecution=live');
 const connection=page.getByLabel('실행기 연결 상태',{exact:true});await expect(connection).toHaveCount(0);
 for(const [status,summary] of [['unconfigured','미설정'],['disconnected','미연결']]){
  capabilities.connection={state:status,ready:false,message:'Synthetic unavailable '+status};await page.reload();
  await expect(connection).toBeVisible();await expect(connection).not.toHaveAttribute('open','');
  await expect(connection.locator(':scope>summary')).toHaveText(summary);
  await expect(connection.getByText('Synthetic unavailable '+status,{exact:true})).toBeHidden();
  const reload=connection.getByRole('button',{name:'연결 다시 확인',exact:true});await expect(reload).toBeHidden();
  await connection.locator(':scope>summary').press('Enter');await expect(reload).toBeVisible();
  await expect(connection.getByText('Synthetic unavailable '+status,{exact:true})).toBeVisible();
  await expect(connection.getByRole('heading',{name:'연결 준비 안내',exact:true})).toBeVisible();
  await connection.locator(':scope>summary').press('Space');await expect(reload).toBeHidden();
  await expect(page.getByRole('button',{name:'Preflight 검사',exact:true})).toBeDisabled();
  await expect(page.getByRole('button',{name:'테스트 시작',exact:true})).toBeDisabled();
 }
 capabilities.connection={state:'connected',ready:true,message:'Synthetic ready'};await page.reload();await expect(connection).toHaveCount(0);
 expect(state.writes).toEqual([]);expect(state.unexpected).toEqual([]);
});

async function openSourceSettings(page:any){
 const settings=page.getByRole('button',{name:'연결 및 실행 설정',exact:true});if(await settings.getAttribute('aria-expanded')!=='true')await settings.click();
 const source=page.getByRole('button',{name:'소스 설정',exact:true});if(await source.getAttribute('aria-expanded')!=='true')await source.click();
 return page.getByRole('region',{name:'TC 소스 Git',exact:true});
}

test('source settings distinguish Git commit metadata from the TC snapshot and show detached or missing remote values',async({page})=>{
 const commit='0123456789abcdef0123456789abcdef01234567';
 const git={status:'available',source_path:'/synthetic/tc/cases',repository_path:'/synthetic/tc',remote:'https://example.invalid/fixtures/tc.git',branch:'release/fixture',commit,detached:false,checked_at:'2026-11-05T01:02:03Z'};
 const catalog={tests:[],branch:'release/fixture',revision:'sha256:tc-snapshot-fixture',git};
 const capabilities={simulation:false,hardware:true,mode:'dashboard',connection:{state:'connected',ready:true}};
 const state=await mock(page,{capabilities,catalog});await page.goto(host.url+'/?tab=gui-test');
 const section=await openSourceSettings(page);await expect(section).toContainText('Git 정보 확인됨');
 await expect(section.locator('dd')).toHaveText([git.source_path,git.repository_path,git.remote,git.branch,commit,git.checked_at]);
 await expect(page.locator('.gt-source-snapshot')).toHaveText('TC 스냅샷 기준 '+catalog.revision);
 await expect(page.locator('.gt-source-snapshot')).not.toContainText(commit);
 git.remote='';git.branch='';git.detached=true;await page.reload();await openSourceSettings(page);
 await expect(section.locator('dd')).toHaveText([git.source_path,git.repository_path,'미등록','detached HEAD',commit,git.checked_at]);
 expect(state.writes).toEqual([]);expect(state.unexpected).toEqual([]);
});

test('Git fallbacks identify missing, unavailable and simulated data without inventing commit metadata',async({page})=>{
 const catalog:any={tests:[],branch:'synthetic',revision:'snapshot-only'};
 const capabilities:any={simulation:false,hardware:true,mode:'dashboard',connection:{state:'connected',ready:true}};
 const state=await mock(page,{capabilities,catalog});await page.goto(host.url+'/?tab=gui-test');
 const section=await openSourceSettings(page);await expect(section).toContainText('Git 정보 미제공');await expect(section.locator('dd')).toHaveCount(0);
 for(const [status,label] of [['not_repository','Git 저장소 아님'],['git_unavailable','Git 실행 파일 미확인'],['timeout','Git 조회 시간 초과'],['error','Git 정보 미확인'],['unborn','첫 커밋 없음']]){
  catalog.git={status,source_path:'/synthetic/tc',checked_at:'2026-11-05T01:02:03Z'};await page.reload();await openSourceSettings(page);
  await expect(section).toContainText(label);await expect(section.locator('dd').nth(4)).toHaveText('미확인');
  await expect(section.locator('dd').nth(2)).toHaveText(status==='unborn'?'미등록':'미확인');
 }
 catalog.git={status:'available',commit:'must-not-present-as-real',source_path:'/synthetic/tc'};capabilities.simulation=true;
 await page.reload();await openSourceSettings(page);await expect(section).toContainText('모의 소스');await expect(section.locator('dd')).toHaveCount(0);
 await expect(page.locator('.gt-source-snapshot')).toHaveText('TC 스냅샷 기준 snapshot-only');
 capabilities.simulation=false;capabilities.connection={state:'disconnected',ready:false};await page.reload();await openSourceSettings(page);
 await expect(section).toContainText('실행기 미연결 · 미확인');await expect(section.locator('dd')).toHaveCount(0);
 expect(state.writes).toEqual([]);expect(state.unexpected).toEqual([]);
});

test('keyboard import can select the identical file twice and invalid JSON cannot save or probe',async({page})=>{
 const state=await mock(page);await page.goto(host.url+'/?tab=settings');
 const importer=page.getByRole('button',{name:'파일 가져오기',exact:true});
 for(let i=0;i<2;i++){
  await importer.focus();const [chooser]=await Promise.all([page.waitForEvent('filechooser'),importer.press('Enter')]);
  await chooser.setFiles({name:'synthetic.json',mimeType:'application/json',buffer:Buffer.from(JSON.stringify(profile))});
  await expect.poll(()=>state.validations).toBe(i+1);
 }
 const input=page.getByLabel('Claude MCP 조회/연결 브리지 실행 배열');await input.fill('[invalid');await expect(input).toHaveAttribute('aria-invalid','true');
 for(const name of ['설정 저장','저장 후 환경 점검','읽기 연결 확인'])await page.getByRole('button',{name,exact:true}).click();
 expect(state.writes).toEqual([]);
 await page.getByRole('navigation').getByRole('link',{name:'실행 기록',exact:true}).click();
 await page.getByRole('navigation').getByRole('link',{name:'환경 설정',exact:true}).click();
 await expect(input).toHaveValue('[invalid');await expect(input).toHaveAttribute('aria-invalid','true');
 await dismissDirtyReload(page);
 await expect(input).toHaveValue('[invalid');
 await input.fill('["synthetic-command"]');await page.getByRole('button',{name:'설정 저장',exact:true}).click();
 await expect.poll(()=>state.writes.length).toBe(1);expect(state.writes[0].body.profile.mcp_argv).toEqual(['synthetic-command']);
 expect(state.unexpected).toEqual([]);
});

test('a delayed settings save preserves newer edits and warns until those edits are saved',async({page})=>{
 const state=await mock(page);
 let saved={version:1,profile:structuredClone(profile)},held:any;
 const submissions:any[]=[];
 await page.route('**/api/v1/config',async route=>{
  if(route.request().method()==='PUT'){
   const body=route.request().postDataJSON();submissions.push(body);
   if(submissions.length===1){held=route;return}
   saved={...body,version:saved.version+1};
  }
  await route.fulfill({contentType:'application/json',body:JSON.stringify(saved)});
 });
 await page.goto(host.url+'/?tab=settings');
 const workspace=page.getByLabel('프로젝트 작업 폴더',{exact:true}),save=page.getByRole('button',{name:'설정 저장',exact:true});
 await workspace.fill('/synthetic/first-edit');await save.click();await expect.poll(()=>submissions.length).toBe(1);
 await workspace.fill('/synthetic/newer-edit');
 saved={...submissions[0],version:2};await held.fulfill({contentType:'application/json',body:JSON.stringify(saved)});
 await expect(save).toBeEnabled();await expect(workspace).toHaveValue('/synthetic/newer-edit');
 await dismissDirtyReload(page);await expect(workspace).toHaveValue('/synthetic/newer-edit');
 await save.click();await expect.poll(()=>submissions.length).toBe(2);await expect(save).toBeEnabled();
 expect(submissions.map(value=>value.profile.workspace)).toEqual(['/synthetic/first-edit','/synthetic/newer-edit']);
 const dialogs:string[]=[];page.on('dialog',async dialog=>{dialogs.push(dialog.type());await dialog.dismiss()});
 await page.reload({timeout:5000});expect(dialogs).toEqual([]);await expect(workspace).toHaveValue('/synthetic/newer-edit');
 expect(state.unexpected).toEqual([]);
});

test('keyboard and touch ordering use complete selection across filtered folders and collapsed rows unmount',async({page,browser})=>{
 await fixture(page);await page.getByText('현재 실행 순서 확인',{exact:true}).click();
 await page.getByRole('button',{name:'Beta 위로 이동'}).focus();await page.keyboard.press('Enter');await expect(page.getByTestId('selected-order')).toHaveText('b,a,c');
 await expect(page.getByRole('button',{name:'Beta 위로 이동'})).toBeDisabled();
 await expect(page.getByRole('button',{name:'Beta 아래로 이동'})).toBeEnabled();
 await expect(page.getByRole('button',{name:'Beta 아래로 이동'})).toBeFocused();
 await page.getByLabel('TC 검색',{exact:true}).fill('Gamma');await page.getByRole('button',{name:'Gamma 위로 이동'}).focus();await page.keyboard.press('Space');
 await expect(page.getByTestId('selected-order')).toHaveText('b,c,a');await expect(page.getByRole('checkbox',{name:'선택 Gamma'})).toBeChecked();
 await page.getByLabel('TC 검색',{exact:true}).fill('');await page.getByRole('button',{name:'second 폴더 목록',exact:true}).click();
 await expect(page.locator('[data-tc-id="b"],[data-tc-id="c"]')).toHaveCount(0);await expect(page.getByTestId('selected-order')).toHaveText('b,c,a');
 await expect(page.getByRole('checkbox',{name:'선택 Disabled'})).toBeDisabled();
 const touch=await browser.newContext({hasTouch:true,viewport:{width:800,height:1000}});const mobile=await touch.newPage();
 try{await fixture(mobile);await mobile.getByText('현재 실행 순서 확인',{exact:true}).tap();await mobile.getByRole('button',{name:'Beta 위로 이동'}).tap();await expect(mobile.getByTestId('selected-order')).toHaveText('b,a,c')}finally{await touch.close()}
});

test('stop confirmation dismisses without a request and acceptance targets the displayed run',async({page})=>{
 const state=await mock(page,{gui:true});await page.goto(host.url+'/?tab=gui-test');
 const stop=page.getByRole('button',{name:'테스트 중단',exact:true});await expect(stop).toBeEnabled();await stop.click();
 const dialog=page.getByRole('dialog');await expect(dialog).toBeVisible();await page.keyboard.press('Escape');await expect(dialog).toHaveCount(0);expect(state.writes).toEqual([]);await expect(stop).toBeFocused();
 await stop.click();await dialog.getByRole('button',{name:'테스트 중단',exact:true}).click();
 await expect.poll(()=>state.writes.length).toBe(1);expect(state.writes[0].p).toBe('/api/v1/gui-test/runs/synthetic-run/actions/cancel');expect(state.writes[0].body.expected_version).toBe(3);
 expect(state.unexpected).toEqual([]);
});
