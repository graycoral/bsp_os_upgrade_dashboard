import {selectTestSetting} from '../../tests/e2e/settings-controls';
const {test,expect}=require('./runtime.cjs');
const {startAppServer}=require('./app-server.cjs');
const path=require('node:path');
let server:any;
test.beforeAll(async()=>{server=await startAppServer()});
test.afterAll(async()=>{await server?.close()});
async function mount(page:any,query=''){
 const errors:string[]=[];page.on('pageerror',(e:Error)=>errors.push(e.message));
 await page.route('**/portable-ui-fixture*',route=>route.fulfill({contentType:'text/html',body:`<!doctype html><html><head><meta charset="UTF-8"><style>body{margin:0}</style></head><body><div id="root"></div><script type="module">import RefreshRuntime from '/@react-refresh';RefreshRuntime.injectIntoGlobalHook(window);window.$RefreshReg$=()=>{};window.$RefreshSig$=()=>type=>type;window.__vite_plugin_react_preamble_installed__=true;</script><script type="module" src="/@vite/client"></script><script type="module" src="/@fs/${path.resolve(__dirname,'portable-ui-host.tsx').replaceAll('\\','/')}"></script></body></html>`}));
 await page.route('**/api/**',()=>{throw Error('Custom host must own all requests')});
 await page.goto(server.url+'/portable-ui-fixture'+query);
 await expect(page.getByTestId('run-state')).toContainText(query.includes('terminal')?'COMPLETED':'PAUSED');
 return errors;
}
const hostile=`button{font:32px serif;padding:25px;border:9px dotted red;background:orange;letter-spacing:4px}input,select,textarea{font:29px serif;padding:21px;border:7px solid purple;box-sizing:content-box}label{display:block;font-size:35px;margin:18px}table{border-collapse:separate;border-spacing:25px;font-size:31px}th,td{padding:20px;border:8px solid red}h2,h3,h4,p{margin:29px;font:34px serif}fieldset{padding:29px;border:8px solid blue}`;
async function metrics(page:any){return page.locator('.gt-scope button,.gt-scope input,.gt-scope label,.gt-scope table,.gt-scope select').evaluateAll((nodes:any[])=>nodes.filter(n=>n.getClientRects().length).map(n=>{const c=getComputedStyle(n),r=n.getBoundingClientRect();return {tag:n.tagName,text:n.textContent?.slice(0,35),font:c.font,fontSize:c.fontSize,padding:c.padding,border:c.border,display:c.display,boxSizing:c.boxSizing,color:c.color,background:c.backgroundColor,x:r.x,y:r.y,width:r.width,height:r.height}}))}
for(const width of [375,1024,1440])test(`T-189 portable component survives global host styles at ${width}px`,async({page},testInfo:any)=>{
 await page.setViewportSize({width,height:1000});await page.emulateMedia({reducedMotion:'reduce'});
 const errors=await mount(page);
 const before=await metrics(page);expect(before.length).toBeGreaterThan(5);
 await page.screenshot({path:testInfo.outputPath(`clean-${width}.png`),fullPage:true});
 await page.addStyleTag({content:hostile});
 expect(await metrics(page)).toEqual(before);
 await page.screenshot({path:testInfo.outputPath(`hostile-${width}.png`),fullPage:true});
 const cancel=page.getByRole('button',{name:'테스트 중단',exact:true});await expect(cancel).toBeEnabled();await cancel.click();
 const dialog=page.getByRole('dialog',{name:'테스트 중단 확인'});await expect(dialog).toBeVisible();
 await page.keyboard.press('Shift+Tab');expect(await dialog.evaluate((el:any)=>el.contains(document.activeElement))).toBe(true);
 await page.keyboard.press('Escape');await expect(dialog).toHaveCount(0);await expect(cancel).toBeFocused();
 expect(errors).toEqual([]);
});
test('T-188 custom host owns API download storage controller and shared mode; mount preserves edits',async({page})=>{
 const errors=await mount(page);
 await page.getByRole('tab',{name:'결과 리포트',exact:true}).click();
 await expect(page.getByRole('link',{name:'JSON 다운로드',exact:true})).toHaveAttribute('href','/custom-download/runs/portable-run/report/json');
 await page.getByRole('button',{name:'연결 및 실행 설정',exact:true}).click();
 await selectTestSetting(page,'suite');
 const input=page.getByRole('textbox',{name:'Suite 이름',exact:true});await input.fill('Preserved draft');
 await page.getByTestId('toggle-mount').click();await page.getByTestId('toggle-mount').click();
 await expect(input).toHaveValue('Preserved draft');
 await selectTestSetting(page,'view');
 const mode=page.getByRole('combobox',{name:'Test 현황 보기 모드',exact:true}).first();await mode.selectOption('live');
 await page.getByRole('button',{name:'보기 모드 적용',exact:true}).first().click();
 const state=await page.evaluate(()=>(window as any).portableState);
 expect(state.modes).toEqual(['live']);expect(state.owned).toContain('custom-controller');
 expect(state.storage.some((x:any)=>x[0]==='get'&&x[1]==='gui-last-run')).toBe(true);
 expect(state.calls.some((x:any)=>x.signal)).toBe(true);expect(state.downloads).toContain('/runs/portable-run/report/json');
 expect(errors).toEqual([]);
});
test('T-188 public UI entrypoint imports in Node without browser globals',async()=>{
 const {pathToFileURL}=require('node:url');
 const {realpathSync}=require('node:fs');
 const toolchain=realpathSync(require('./toolchain.cjs'));
 const {createServer}=await import(pathToFileURL(path.join(toolchain,'vite/dist/node/index.js')).href);
 const root=path.resolve(__dirname,'../../apps/web');
 // The browser config aliases React to absolute CJS files. SSR must let Node
 // load those dependencies as packages rather than evaluate CJS as ESM.
 const vite=await createServer({root,configFile:false,
  esbuild:{jsx:'automatic'},resolve:{dedupe:['react','react-dom']},
  ssr:{external:['react','react-dom','react/jsx-runtime','react/jsx-dev-runtime']},
  server:{middlewareMode:true}});
 try{
  expect(typeof window).toBe('undefined');expect(typeof document).toBe('undefined');
  expect(typeof localStorage).toBe('undefined');expect(typeof sessionStorage).toBe('undefined');
  const entry=await vite.ssrLoadModule(path.resolve(__dirname,'../../packages/gui-test-ui/src/index.ts'));
  expect(typeof entry.TestPage).toBe('function');expect(typeof entry.createBrowserGuiTestHost).toBe('function');
 }finally{await vite.close()}
});


test('T-188 omitted session capability displays Runs without mutation or heartbeat',async({page})=>{
 const errors=await mount(page,'?observer&terminal');
 await expect(page.getByRole('checkbox',{name:'선택 Portable case',exact:true})).toBeChecked();
 await expect(page.getByRole('button',{name:'테스트 시작',exact:true})).toBeDisabled();
 await expect(page.getByRole('button',{name:'새 Run으로 재검증',exact:true})).toBeDisabled();
 await expect(page.getByRole('button',{name:'테스트 중단',exact:true})).toBeDisabled();
 await expect(page.getByRole('button',{name:'제어권 요청',exact:true})).toHaveCount(0);
 await expect(page.getByRole('button',{name:'만료된 제어권 인수',exact:true})).toHaveCount(0);
 await expect.poll(()=>page.evaluate(()=>(window as any).portableState.calls.filter((c:any)=>c.path==='/runs/portable-run/events').length)).toBeGreaterThanOrEqual(2);
 const calls=await page.evaluate(()=>(window as any).portableState.calls);
 expect(calls.every((c:any)=>c.method==='GET')).toBe(true);
 expect(calls.some((c:any)=>c.path.endsWith('/heartbeat')||c.path.includes('/actions/'))).toBe(false);
 expect(errors).toEqual([]);
});
for(const foreign of [false,true])test(`T-188 custom host heartbeat requires fetched Run ownership (${foreign?'foreign':'owned'})`,async({page})=>{
 const errors=await mount(page,foreign?'?foreign':'');
 await expect.poll(()=>page.evaluate(()=>(window as any).portableState.calls.filter((c:any)=>c.path==='/runs/portable-run/events').length)).toBeGreaterThanOrEqual(2);
 const calls=await page.evaluate(()=>(window as any).portableState.calls);
 const heartbeats=calls.filter((c:any)=>c.path==='/runs/portable-run/heartbeat');
 if(foreign){expect(heartbeats).toEqual([]);expect(calls.every((c:any)=>c.method==='GET')).toBe(true)}
 else {expect(heartbeats.length).toBeGreaterThan(0);expect(heartbeats.every((c:any)=>c.method==='POST')).toBe(true)}
 expect(errors).toEqual([]);
});
