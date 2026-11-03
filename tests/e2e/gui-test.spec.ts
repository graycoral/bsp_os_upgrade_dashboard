import {test,expect} from '../../apps/web/node_modules/@playwright/test';
import {readFileSync} from 'node:fs';
const standalone=process.env.GUI_TEST_STANDALONE==='1';

test('GUI-UI-16 Windows capabilities require a saved command and send hardware requests',async({page})=>{
 await page.route('**/api/v1/gui-test/capabilities',async route=>{
  const response=await route.fetch();const value=await response.json();
  await route.fulfill({response,json:{...value,mode:'dashboard',simulation:false,hardware:true,job_sync:false}});
 });
 await page.route('**/api/v1/gui-test/boards',async route=>{
  const response=await route.fetch();const value=await response.json();
  await route.fulfill({response,json:{...value,boards:value.boards.map((b:any,i:number)=>({...b,node:i===0?'n295_sadk':'n296_sadk'}))}});
 });
 const preflights:any[]=[],starts:any[]=[];
 await page.route('**/api/v1/gui-test/preflight',async route=>{
  preflights.push(route.request().postDataJSON());
  await route.fulfill({json:{ok:true,simulation:false,checks:['UI fixture only']}});
 });
 await page.route('**/api/v1/gui-test/runs',async route=>{
  if(route.request().method()!=='POST'){await route.continue();return;}
  starts.push(route.request().postDataJSON());
  await route.fulfill({status:409,json:{code:'TEST_ONLY',message:'UI fixture: no TC process was started'}});
 });
 await openTest(page);
 await expect(page.getByText('WINDOWS RUNNER',{exact:true})).toBeVisible();
 await expect(page.getByText('MOCK DEMO',{exact:true})).toHaveCount(0);
 await expect(page.getByRole('button',{name:'Preflight 검사',exact:true})).toBeDisabled();
 await openSettings(page);
 await expect(page.getByLabel('데모 시나리오',{exact:true})).toHaveCount(0);
 await expect(page.getByLabel('GUI Test Job',{exact:true})).toHaveCount(0);
 await page.getByRole('button',{name:'TC 실행 명령 설정',exact:true}).click();
 await page.getByLabel('실행 명령 이름',{exact:true}).fill('Windows fixture command');
 await expect(page.getByLabel('Single 실행 명령',{exact:true})).toHaveValue('python3\n{tc_path}\n-p\n{com_a}');
 await expect(page.getByLabel('Dual 실행 명령',{exact:true})).toHaveValue('python3\n{tc_path}\n-n\n{node_a}\n-n2\n{node_b}');
 await page.getByRole('button',{name:'명령 저장 / 수정',exact:true}).click();
 await expect(page.getByLabel('저장된 실행 명령',{exact:true})).toHaveValue('Windows fixture command');
 const profiles=await (await page.request.get('/api/v1/gui-test/saved/command')).json();
 expect(profiles.find((item:any)=>item.name==='Windows fixture command').single).toEqual(['python3','{tc_path}','-p','{com_a}']);
 expect(profiles.find((item:any)=>item.name==='Windows fixture command').dual).toEqual(['python3','{tc_path}','-n','{node_a}','-n2','{node_b}']);
 await page.getByRole('tab',{name:'실행 및 결과',exact:true}).click();
 await page.getByRole('button',{name:'Preflight 검사',exact:true}).click();
 await expect(page.getByRole('button',{name:'▶ 테스트 시작',exact:true})).toBeEnabled();
 expect(starts).toHaveLength(0);
 await page.getByRole('button',{name:'▶ 테스트 시작',exact:true}).click();
 await expect(page.getByRole('alert').filter({hasText:'UI fixture: no TC process was started'})).toBeVisible();
 expect(preflights).toHaveLength(1);expect(starts).toHaveLength(1);
 expect(starts[0].execution).toBe('hardware');expect(preflights[0].execution).toBe('hardware');
 expect(starts[0].command_profile).toBe('Windows fixture command');
 expect(starts[0].job_id).toBeNull();
 expect(starts[0].connection.a.node).toBe('n295_sadk');expect(starts[0].connection.b.node).toBe('n296_sadk');
});

test('GUI-UI-14 select all preserves filtered selections and invalidates Preflight',async({page})=>{
 await openTest(page);
 const all=page.getByRole('checkbox',{name:'표시된 TC 전체 선택',exact:true});
 await expect(page.getByRole('group',{name:'TC 목록 정렬',exact:true}).getByRole('checkbox',{name:'표시된 TC 전체 선택',exact:true})).toBeVisible();
 const nameSort=page.getByRole('button',{name:'이름 정렬',exact:true});
 const resize=page.getByRole('separator',{name:'TC 검색 패널 너비',exact:true});
 await resize.focus();await page.keyboard.press('Home');
 await nameSort.click();
 const nameBounds=await nameSort.boundingBox(),allBounds=await all.boundingBox();
 const typeBounds=await page.getByRole('button',{name:'유형 정렬',exact:true}).boundingBox();
 expect(allBounds!.x+allBounds!.width).toBeLessThanOrEqual(nameBounds!.x);
 expect(Math.abs(allBounds!.y+allBounds!.height/2-nameBounds!.y-nameBounds!.height/2)).toBeLessThanOrEqual(1);
 expect(nameBounds!.width).toBeGreaterThanOrEqual(32);
 expect(nameBounds!.x+nameBounds!.width).toBeLessThanOrEqual(typeBounds!.x);
 expect(await nameSort.evaluate(el=>el.scrollWidth<=el.clientWidth+1)).toBe(true);
 await page.getByRole('button',{name:'실행 순서로 보기',exact:true}).click();
 await resize.focus();for(let i=0;i<3;i++)await page.keyboard.press('ArrowRight');
 const order=page.getByLabel('TC 실행 순서').locator('li');
 const original=await order.allTextContents();
 await expect(all).toBeChecked();
 await page.getByRole('button',{name:'Preflight 검사',exact:true}).click();
 const start=page.getByRole('button',{name:'▶ 테스트 시작',exact:true});
 await expect(start).toBeEnabled();
 await page.getByLabel('선택 04_pair',{exact:true}).uncheck();
 await expect(all).toHaveJSProperty('indeterminate',true);
 await expect(start).toBeDisabled();
 await all.check();
 await expect(all).toBeChecked();
 await expect(all).toHaveJSProperty('indeterminate',false);
 await expect(order).toHaveText(original);
 await page.getByRole('button',{name:'트리 모두 접기',exact:true}).click();
 await all.uncheck();
 await expect(nameSort).toHaveAttribute('aria-pressed','false');
 await expect(order).toHaveCount(0);
 await all.focus();await page.keyboard.press('Space');
 await expect(order).toHaveText(original);
 await page.getByLabel('연결 유형 필터',{exact:true}).selectOption('Dual');
 await expect(all).toBeChecked();
 await all.uncheck();
 await expect(order).toHaveText(original.filter(name=>name!=='04_pair'));
 await page.getByLabel('연결 유형 필터',{exact:true}).selectOption('all');
 await expect(all).toHaveJSProperty('indeterminate',true);
 await page.getByLabel('TC 검색',{exact:true}).fill('pair');
 await expect(all).not.toBeChecked();
 await all.check();
 await expect(order).toHaveText(original);
 await page.getByLabel('TC 검색',{exact:true}).fill('no-such-test-case');
 await expect(all).toBeDisabled();
 await expect(all).not.toBeChecked();
 await expect(all).toHaveJSProperty('indeterminate',false);
 await expect(order).toHaveText(original);
 await page.getByRole('button',{name:'검색·필터 초기화',exact:true}).click();
 await expect(all).toBeChecked();
 await page.setViewportSize({width:375,height:900});
 await expect(all).toBeVisible();
 const mobileName=await nameSort.boundingBox(),mobileAll=await all.boundingBox();
 expect(mobileAll!.x+mobileAll!.width).toBeLessThanOrEqual(mobileName!.x);
 expect(Math.abs(mobileAll!.y+mobileAll!.height/2-mobileName!.y-mobileName!.height/2)).toBeLessThanOrEqual(1);
 expect(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth)).toBe(true);
 await page.screenshot({path:'../../.local-reports/gui-test/'+(standalone?'standalone':'dashboard')+'-select-all.png',fullPage:true});
});

test('GUI-UI-15 select all excludes disabled cases',async({page})=>{
 await page.route('**/api/v1/gui-test/catalog',async route=>{
  const response=await route.fetch();const catalog=await response.json();
  catalog.tests=catalog.tests.map((tc:any)=>tc.name==='01_boot'?{...tc,disabled_reason:'Test fixture: unavailable'}:tc);
  await route.fulfill({response,json:catalog});
 });
 await openTest(page);
 const all=page.getByRole('checkbox',{name:'표시된 TC 전체 선택',exact:true});
 const boot=page.getByLabel('선택 01_boot',{exact:true});
 await expect(boot).toBeDisabled();await expect(boot).not.toBeChecked();
 await expect(all).toBeChecked();
 await all.uncheck();await all.check();
 await expect(boot).not.toBeChecked();
 await page.getByLabel('TC 검색',{exact:true}).fill('01_boot');
 await expect(all).toBeDisabled();await expect(all).not.toBeChecked();
 await expect(all).toHaveJSProperty('indeterminate',false);
 await expect(page.getByLabel('TC 실행 순서').locator('li')).toHaveCount(4);
});
async function openTest(page:any){
 await page.goto('/');
 if(!standalone)await page.getByRole('navigation').getByRole('button',{name:'Test 현황',exact:true}).click();
 await expect(page.getByRole('heading',{name:'Test 현황',exact:true})).toBeVisible();
 await expect(page.getByLabel('선택 04_pair')).toBeChecked();
}
async function openSettings(page:any){
 const settings=page.getByRole('tab',{name:'연결 및 실행 설정',exact:true});
 if(await settings.getAttribute('aria-selected')!=='true')await settings.click();
 for(const name of ['연결 및 실행 준비','실행 설정']){
  const panel=page.getByRole('button',{name,exact:true});if(await panel.getAttribute('aria-expanded')==='false')await panel.click();
 }
}
async function launch(page:any,scenario='pass',speed='5'){
 await openSettings(page);
 await page.getByLabel('데모 시나리오',{exact:true}).selectOption(scenario);
 await page.getByLabel('데모 속도',{exact:true}).selectOption(speed);
 await page.getByRole('tab',{name:'실행 및 결과',exact:true}).click();
 await page.getByRole('button',{name:'Preflight 검사',exact:true}).click();
 await expect(page.getByRole('status').filter({hasText:'Preflight 통과'})).toBeVisible();
 await page.getByRole('button',{name:'▶ 테스트 시작',exact:true}).click();
}
async function control(page:any,name:string,action:string){
 // Worker transitions can invalidate a polled version before a user clicks.
 // Only retry a rejected version, after a fresh snapshot; keep all server gates.
 for(let attempt=0;attempt<3;attempt++){
  const pending=page.waitForResponse((r:any)=>r.request().method()==='POST'&&r.url().endsWith('/actions/'+action));
  await page.getByRole('button',{name,exact:true}).click();
  const response=await pending;
  if(response.status()===200)return;
  expect(response.status()).toBe(409);expect((await response.json()).code).toBe('VERSION_CONFLICT');
  const runUrl=response.url().replace('/actions/'+action,'');
  await page.waitForResponse((r:any)=>r.request().method()==='GET'&&r.url()===runUrl&&r.status()===200);
 }
 throw Error('Control action repeatedly rejected a stale version: '+action);
}

test('GUI-UI-01 TC filters, suites, profiles, Single/Dual, report downloads',async({page})=>{
 const errors:string[]=[];page.on('pageerror',e=>errors.push(e.message));
 await openTest(page);
 await page.getByLabel('TC 검색',{exact:true}).fill('pair');
 await expect(page.getByLabel('선택 04_pair')).toBeChecked();
 await page.getByLabel('TC 검색',{exact:true}).fill('');
 await expect(page.getByLabel('선택 01_boot')).toBeChecked();
 await openSettings(page);
 const suitePanel=page.getByRole('button',{name:'Suite 관리',exact:true});if(await suitePanel.getAttribute('aria-expanded')==='false')await suitePanel.click();
 await page.getByLabel('Suite 이름').fill('Browser suite');
 await page.getByRole('button',{name:'Suite 저장 / 수정',exact:true}).click();
 await expect(page.getByRole('status')).toContainText('Suite를 저장');
 await openSettings(page);
 await page.getByRole('button',{name:'프로파일 저장',exact:true}).click();
 await expect(page.getByRole('status')).toContainText('연결 프로파일 저장');
 await launch(page);
 await expect(page.getByTestId('run-state')).toHaveText('COMPLETED · PASS',{timeout:20000});
 await page.getByRole('tab',{name:'결과 리포트',exact:true}).click();
 const waiting=page.waitForEvent('download');await page.getByRole('link',{name:'JSON 다운로드',exact:true}).click();
 const download=await waiting;const report=JSON.parse(readFileSync((await download.path())!,'utf8'));
 expect(report.overall_result).toBe('PASS');expect(report.attempts).toHaveLength(5);
 const pair=report.attempts.find((a:any)=>a.tc_id.includes('dual'));
 expect(pair.resolved_command_argv.slice(-2)).toEqual(['COM3','COM4']);
 await page.screenshot({path:'../../.local-reports/gui-test/'+(standalone?'standalone':'dashboard')+'-desktop.png',fullPage:true});
 await page.setViewportSize({width:680,height:1000});
 await page.screenshot({path:'../../.local-reports/gui-test/'+(standalone?'standalone':'dashboard')+'-narrow.png',fullPage:true});
 expect(errors).toEqual([]);
});

test('GUI-UI-02 disconnect, reload, explicit recovery and new attempt',async({page})=>{
 await openTest(page);await launch(page,'disconnect');
 await expect(page.getByTestId('run-state')).toContainText('PAUSED',{timeout:20000});
 await page.reload();if(!standalone)await page.getByRole('navigation').getByRole('button',{name:'Test 현황',exact:true}).click();
 await expect(page.getByTestId('run-state')).toContainText('PAUSED');
 await expect(page.getByRole('button',{name:'▶ 재개',exact:true})).toBeDisabled();
 await page.getByRole('button',{name:'데모 연결 / 종료 확인',exact:true}).click();
 await page.getByRole('button',{name:'▶ 재개',exact:true}).click();
 await expect(page.getByTestId('run-state')).toHaveText('COMPLETED · PASS',{timeout:20000});
 await expect(page.locator('.gt-logs')).toContainText('Attempt 2');
});

test('GUI-UI-03 pause/cancel and observer control transfer',async({page,context})=>{
 await openTest(page);await launch(page,'pass','0.2');
 await expect(page.getByTestId('run-state')).toContainText('RUNNING');
 const observer=await context.newPage();await openTest(observer);
 await expect(observer.getByText('관찰 모드',{exact:false})).toBeVisible();
 await control(observer,'제어권 요청','request-control');
 await expect(page.getByRole('button',{name:'제어권 이전 승인',exact:true})).toBeVisible();
 await control(page,'제어권 이전 승인','grant-control');
 await expect(observer.getByRole('button',{name:'Ⅱ 일시 정지',exact:true})).toBeEnabled();
 await control(observer,'Ⅱ 일시 정지','pause');
 await expect(observer.getByTestId('run-state')).toContainText('PAUSED',{timeout:20000});
 await control(observer,'■ 테스트 중단','cancel');
 await expect(observer.getByTestId('run-state')).toHaveText('CANCELLED · INCOMPLETE');
 await observer.close();
});

test('GUI-UI-04 FAIL continues and isolated Dashboard synchronization',async({page})=>{
 await openTest(page);
 if(!standalone){await openSettings(page);await page.getByRole('button',{name:'격리 데모 Job 준비',exact:true}).click();await expect(page.getByLabel('GUI Test Job')).not.toHaveValue('');}
 await launch(page,'fail');
 await expect(page.getByTestId('run-state')).toHaveText('COMPLETED · FAIL',{timeout:20000});
 await expect(page.getByLabel('TC 판정 진행률')).toHaveAttribute('value','5');
 if(!standalone){await page.getByRole('tab',{name:'결과 리포트',exact:true}).click();await expect(page.getByRole('heading',{name:'판정 FAIL · 동기화 SUCCEEDED'})).toBeVisible();
  const jobId=await page.getByLabel('GUI Test Job').inputValue();const j=await (await page.request.get('/api/v1/gui-test/demo/jobs/'+jobId)).json();
  expect(j.modules.map((m:any)=>m.stages.device_test.status)).toEqual(['FAILED','SUCCEEDED']);}
});

test('GUI-UI-05 catalog drag invalidates Preflight and preserves completed Run',async({page})=>{
 await openTest(page);
 await expect(page.getByRole('button',{name:/(위로|아래로) 이동$/})).toHaveCount(0);
 const names=page.getByLabel('TC 실행 순서').locator('li');
 const original=await names.allTextContents();
 await page.getByRole('button',{name:'Preflight 검사',exact:true}).click();
 const start=page.getByRole('button',{name:'▶ 테스트 시작',exact:true});await expect(start).toBeEnabled();
 const last=page.locator('.gt-tree-case').filter({hasText:'04_pair'}),first=page.locator('.gt-tree-case').filter({hasText:'01_boot'});
 await last.locator('.gt-drag-handle').dragTo(first,{targetPosition:{x:40,y:6}});
 await expect(names).toHaveText(['04_pair',...original.slice(0,-1)]);await expect(start).toBeDisabled();
 const bottom=page.locator('.gt-tree-case').filter({hasText:'03_link'});
 await bottom.scrollIntoViewIfNeeded();const bounds=await bottom.boundingBox();
 expect(bounds!.y+bounds!.height).toBeLessThanOrEqual(page.viewportSize()!.height);
 // Move through the native drag threshold and across the target before releasing.
 // Scroll the full target into view before measuring; a lower-half drop can otherwise be outside the viewport.
 const handleBounds=await last.locator('.gt-drag-handle').boundingBox();
 await page.mouse.move(handleBounds!.x+handleBounds!.width/2,handleBounds!.y+handleBounds!.height/2);
 await page.mouse.down();
 await page.mouse.move(handleBounds!.x+handleBounds!.width/2+12,handleBounds!.y+handleBounds!.height/2,{steps:4});
 await page.mouse.move(bounds!.x+40,bounds!.y+bounds!.height*0.6,{steps:8});
 await page.mouse.move(bounds!.x+40,bounds!.y+bounds!.height*0.75,{steps:2});
 await page.mouse.up();
 await expect(names).toHaveText(original);
 await expect(page.getByLabel(/실행 위치/)).toHaveCount(0);
 await launch(page);await expect(page.getByTestId('run-state')).toHaveText('COMPLETED · PASS',{timeout:20000});
 const id=await page.getByLabel('Run 이력').inputValue();
 const snapshot=await (await page.request.get('/api/v1/gui-test/runs/'+id)).json();expect(snapshot.tests.map((t:any)=>t.name)).toEqual(original);
 await last.locator('.gt-drag-handle').dragTo(first,{targetPosition:{x:40,y:6}});
 const after=await (await page.request.get('/api/v1/gui-test/runs/'+id)).json();expect(after.tests).toEqual(snapshot.tests);
});

test('GUI-UI-06 nested search sort and settings persistence',async({page})=>{
 await openTest(page);
 const network=page.locator('.gt-case-group').filter({has:page.getByRole('button',{name:'network 폴더 목록',exact:true})}).first();
 await expect(network.getByRole('button',{name:'network/dual 폴더 목록',exact:true})).toBeVisible();
 const order=await page.getByLabel('TC 실행 순서').locator('li').allTextContents();
 await page.getByRole('button',{name:'이름 정렬',exact:true}).click();
 await page.getByRole('button',{name:'이름 정렬',exact:true}).click();
 const boot=page.locator('.gt-case-group').filter({has:page.getByRole('button',{name:'boot 폴더 목록',exact:true})});
 await expect(boot.locator('.gt-tc-name')).toHaveText(['02_smoke','01_boot']);
 await page.getByRole('button',{name:'트리 모두 접기',exact:true}).click();
 await page.getByLabel('TC 검색',{exact:true}).fill('network/dual');await expect(page.getByLabel('선택 04_pair')).toBeVisible();
 await page.getByLabel('폴더 network', {exact:true}).uncheck();
 await page.getByLabel('TC 검색',{exact:true}).fill('');await expect(page.getByLabel('선택 03_link')).toBeChecked();
 await page.getByLabel('선택 04_pair').check();
 await expect(page.getByLabel('TC 실행 순서').locator('li')).toHaveText(order);
 await openSettings(page);
 const suitePanel=page.getByRole('button',{name:'Suite 관리',exact:true});if(await suitePanel.getAttribute('aria-expanded')==='false')await suitePanel.click();
 await page.getByLabel('Suite 이름').fill('Preserved input');
 await page.getByRole('button',{name:'설정 모두 접기',exact:true}).click();
 await expect(page.getByLabel('Suite 이름')).toBeHidden();await expect(page.getByLabel('선택 01_boot')).toBeVisible();
 await page.getByRole('button',{name:'설정 모두 펼치기',exact:true}).click();await expect(page.getByLabel('Suite 이름')).toHaveValue('Preserved input');
 await page.getByRole('button',{name:'설정 모두 접기',exact:true}).click();await page.reload();
 if(!standalone)await page.getByRole('navigation').getByRole('button',{name:'Test 현황',exact:true}).click();
 await page.getByRole('tab',{name:'연결 및 실행 설정',exact:true}).click();
 await expect(page.getByRole('button',{name:'연결 및 실행 준비',exact:true})).toHaveAttribute('aria-expanded','false');
 await page.setViewportSize({width:375,height:900});
 await expect(page.getByLabel('TC 검색',{exact:true})).toBeVisible();
 expect(await page.evaluate(()=>document.documentElement.scrollWidth)).toBeLessThanOrEqual(375);
});

test('GUI-UI-07 failed TC only rerun retains original and displays usage',async({page})=>{
 await openTest(page);await launch(page,'fail');await expect(page.getByTestId('run-state')).toHaveText('COMPLETED · FAIL',{timeout:20000});
 const id=await page.getByLabel('Run 이력').inputValue();
 const original=await (await page.request.get('/api/v1/gui-test/runs/'+id)).json();
 const failed=original.tests.find((t:any)=>original.results[t.id]==='FAIL');
 const retry=page.getByRole('button',{name:failed.name+' 재실행',exact:true});
 await expect(retry).toHaveText('Retry');await expect(retry.locator('..')).toContainText('FAIL');
 await expect(page.getByRole('columnheader',{name:'재실행',exact:true})).toHaveCount(0);
 await retry.click();
 await expect(page.getByLabel('Run 이력')).not.toHaveValue(id);await expect(page.getByTestId('run-state')).toHaveText('COMPLETED · PASS',{timeout:20000});
 const childId=await page.getByLabel('Run 이력').inputValue();
 const child=await (await page.request.get('/api/v1/gui-test/runs/'+childId)).json();
 expect(child.parent_run_id).toBe(id);expect(child.tests.map((t:any)=>t.id)).toEqual([failed.id]);expect(child.link).toBeNull();
 const after=await (await page.request.get('/api/v1/gui-test/runs/'+id)).json();expect(after.results).toEqual(original.results);expect(after.attempts).toEqual(original.attempts);
 await expect(page.getByLabel('진행 요약',{exact:true})).toContainText('모델 호출 없음');
 const usage=page.locator('.gt-usage').first();await expect(usage).not.toHaveAttribute('open','');
 await usage.locator('summary').click();await expect(usage).toContainText('모델 호출 없음');
});

test('GUI-UI-08 catalog hide and resize persist without clearing selections',async({page})=>{
 await openTest(page);
 const handle=page.getByRole('separator',{name:'TC 검색 패널 너비'});
 const before=Number(await handle.getAttribute('aria-valuenow'));
 await handle.focus();await page.keyboard.press('ArrowRight');await expect(handle).toHaveAttribute('aria-valuenow',String(before+20));
 const bounds=await handle.boundingBox();await page.mouse.move(bounds!.x+4,bounds!.y+50);await page.mouse.down();await page.mouse.move(bounds!.x+64,bounds!.y+50);await page.mouse.up();
 expect(Number(await handle.getAttribute('aria-valuenow'))).toBeGreaterThan(before+20);
 await page.getByRole('button',{name:'TC 검색 패널 숨기기',exact:true}).click();await expect(page.getByLabel('TC 검색',{exact:true})).toBeHidden();
 await page.reload();if(!standalone)await page.getByRole('navigation').getByRole('button',{name:'Test 현황',exact:true}).click();
 await expect(page.getByLabel('TC 검색',{exact:true})).toBeHidden();await page.getByRole('button',{name:'TC 검색 패널 보이기',exact:true}).click();await expect(page.getByLabel('선택 04_pair')).toBeChecked();
 expect(Number(await handle.getAttribute('aria-valuenow'))).toBeGreaterThan(before+20);
});


test('GUI-UI-09 settings icon tab preserves inputs and keeps launch in results',async({page})=>{
 await openTest(page);
 await expect(page.getByRole('tab',{name:'실행 및 결과',exact:true})).toHaveAttribute('aria-selected','true');
 await expect(page.getByRole('button',{name:'연결 및 실행 준비',exact:true})).toBeHidden();
 await expect(page.getByRole('button',{name:'Preflight 검사',exact:true})).toBeVisible();
 await openSettings(page);
 await page.getByLabel('프로파일 이름').fill('Tab input preserved');
 await page.getByLabel('데모 속도',{exact:true}).selectOption('5');
 await page.getByRole('tab',{name:'실행 및 결과',exact:true}).click();
 await expect(page.getByLabel('선택 04_pair')).toBeChecked();
 await page.getByRole('button',{name:'Preflight 검사',exact:true}).click();
 await expect(page.getByRole('button',{name:'▶ 테스트 시작',exact:true})).toBeEnabled();
 await openSettings(page);
 await expect(page.getByLabel('프로파일 이름')).toHaveValue('Tab input preserved');
 await expect(page.getByLabel('데모 속도',{exact:true})).toHaveValue('5');
 await page.getByLabel('데모 속도',{exact:true}).selectOption('1');
 await page.getByRole('tab',{name:'연결 및 실행 설정',exact:true}).press('ArrowLeft');
 await expect(page.getByRole('tab',{name:'실행 및 결과',exact:true})).toBeFocused();
 await expect(page.getByRole('button',{name:'▶ 테스트 시작',exact:true})).toBeDisabled();
});

test('GUI-UI-10 per-TC and whole-list repetitions preserve verdicts in compact rows',async({page})=>{
 await openTest(page);
 const rows=page.locator('.gt-tree-case');
 for(const row of await rows.all())expect((await row.boundingBox())!.height).toBeLessThanOrEqual(36);
 await expect(page.getByLabel('01_boot 실행 횟수',{exact:true})).toHaveCount(0);
 await page.getByRole('button',{name:'01_boot 실행 횟수 설정',exact:true}).click();
 await expect(page.getByLabel('01_boot 실행 횟수',{exact:true})).toHaveValue('1');
 await page.getByLabel('01_boot 실행 횟수',{exact:true}).fill('2');
 await page.getByRole('button',{name:'01_boot 실행 횟수 설정',exact:true}).click();
 await page.getByLabel('폴더 extra',{exact:true}).uncheck();await page.getByLabel('폴더 network',{exact:true}).uncheck();
 await openSettings(page);
 await expect(page.getByLabel('전체 목록 반복 횟수',{exact:true})).toHaveValue('1');
 await page.getByLabel('전체 목록 반복 횟수',{exact:true}).fill('2');
 await launch(page,'fail');
 await expect(page.getByTestId('run-state')).toHaveText('COMPLETED · FAIL',{timeout:20000});
 await expect(page.getByLabel('TC 판정 진행률')).toHaveAttribute('value','6');
 await expect(page.getByLabel('진행 요약',{exact:true})).toContainText('완료 6/6회');
 await expect(page.getByLabel('TC 판정 진행률')).toHaveAttribute('max','6');
 const id=await page.getByLabel('Run 이력').inputValue();const run=await(await page.request.get('/api/v1/gui-test/runs/'+id)).json();
 expect(run.plan.map((s:any)=>s.tc_id)).toEqual(['boot/01_boot.py','boot/01_boot.py','boot/02_smoke.py','boot/01_boot.py','boot/01_boot.py','boot/02_smoke.py']);
 expect(run.results['boot/01_boot.py']).toBe('FAIL');expect(run.attempts).toHaveLength(6);
});


test('GUI-UI-11 settings return button gear toggle and Escape',async({page})=>{
 await openTest(page);await openSettings(page);
 await page.getByLabel('전체 목록 반복 횟수',{exact:true}).fill('3');
 await page.getByRole('button',{name:'← 실행 및 결과로 돌아가기',exact:true}).click();
 await expect(page.getByRole('tabpanel',{name:'실행 및 결과',exact:true})).toBeVisible();
 await expect(page.getByRole('tab',{name:'실행 및 결과',exact:true})).toBeFocused();
 await openSettings(page);await expect(page.getByLabel('전체 목록 반복 횟수',{exact:true})).toHaveValue('3');
 await page.getByRole('tab',{name:'연결 및 실행 설정',exact:true}).click();
 await expect(page.getByRole('tabpanel',{name:'실행 및 결과',exact:true})).toBeVisible();
 await openSettings(page);await page.getByLabel('전체 목록 반복 횟수',{exact:true}).press('Escape');
 await expect(page.getByRole('tabpanel',{name:'실행 및 결과',exact:true})).toBeVisible();
});


test('GUI-UI-12 explorer column sorting leaves execution order unchanged',async({page})=>{
 await openTest(page);
 const order=await page.getByLabel('TC 실행 순서').locator('li').allTextContents();
 const name=page.getByRole('button',{name:'이름 정렬',exact:true});
 await name.click();await expect(name).toHaveText('이름↑');
 await name.click();await expect(name).toHaveText('이름↓');
 await expect(page.getByRole('combobox',{name:'TC 목록 정렬',exact:true})).toHaveCount(0);
 await page.getByRole('button',{name:'유형 정렬',exact:true}).click();
 await expect(page.getByRole('button',{name:'유형 정렬',exact:true})).toHaveAttribute('aria-pressed','true');
 await page.getByRole('button',{name:'시간 정렬',exact:true}).click();
 await expect(page.getByLabel('TC 실행 순서').locator('li')).toHaveText(order);
 await page.getByRole('button',{name:'실행 순서로 보기',exact:true}).click();
 await expect(name).toHaveText('이름');
});

test('GUI-UI-13 saved command substitutes TC/COM and freezes repeated Run',async({page})=>{
 await openTest(page);
 await openSettings(page);
 await page.getByRole('button',{name:'TC 실행 명령 설정',exact:true}).click();
 const profile='Browser command '+Date.now();
 await page.getByLabel('실행 명령 이름',{exact:true}).fill(profile);
 await page.getByLabel('Single 실행 명령',{exact:true}).fill('python\nrun_suite.py\n--case\n{tc_name}\n--port\n{com_a}');
 await page.getByLabel('Dual 실행 명령',{exact:true}).fill('python\nrun_suite.py\n--case\n{tc_file}\n--port-a\n{com_a}\n--port-b\n{com_b}');
 await page.getByRole('tab',{name:'실행 및 결과',exact:true}).click();
 await expect(page.getByRole('button',{name:'Preflight 검사',exact:true})).toBeDisabled();
 await openSettings(page);
 await page.getByRole('button',{name:'명령 저장 / 수정',exact:true}).click();
 await expect(page.getByLabel('저장된 실행 명령',{exact:true})).toHaveValue(profile);
 const options=await page.getByLabel('명령 미리보기 TC',{exact:true}).locator('option').evaluateAll(items=>items.map(o=>({value:(o as HTMLOptionElement).value,text:o.textContent||''})));
 await page.getByLabel('명령 미리보기 TC',{exact:true}).selectOption(options.find(o=>o.text.includes('01_boot'))!.value);
 const runsBefore=await (await page.request.get('/api/v1/gui-test/runs')).json();
 await page.getByRole('button',{name:'치환 명령 미리보기',exact:true}).click();
 const preview=page.getByTestId('command-preview');
 await expect(preview).toContainText('실행하지 않음');
 expect(JSON.parse(await preview.locator('pre').innerText())).toEqual(['python','run_suite.py','--case','01_boot','--port','COM3']);
 await page.getByLabel('명령 미리보기 TC',{exact:true}).selectOption(options.find(o=>o.text.includes('04_pair'))!.value);
 await expect(preview).toHaveCount(0);
 await page.getByRole('button',{name:'치환 명령 미리보기',exact:true}).click();
 expect(JSON.parse(await preview.locator('pre').innerText())).toEqual(['python','run_suite.py','--case','04_pair.py','--port-a','COM3','--port-b','COM4']);
 const runsAfter=await (await page.request.get('/api/v1/gui-test/runs')).json();
 expect(runsAfter.map((r:any)=>r.id)).toEqual(runsBefore.map((r:any)=>r.id));
 await page.reload();
 if(!standalone)await page.getByRole('navigation').getByRole('button',{name:'Test 현황',exact:true}).click();
 await openSettings(page);
 await expect(page.getByLabel('저장된 실행 명령',{exact:true})).toHaveValue(profile);
 await expect(page.getByLabel('Single 실행 명령',{exact:true})).toHaveValue('python\nrun_suite.py\n--case\n{tc_name}\n--port\n{com_a}');
 await page.getByLabel('전체 목록 반복 횟수',{exact:true}).fill('2');
 await launch(page);
 await expect(page.getByTestId('run-state')).toHaveText('COMPLETED · PASS',{timeout:20000});
 const id=await page.getByLabel('Run 이력').inputValue();
 const snapshot=await (await page.request.get('/api/v1/gui-test/runs/'+id)).json();
 expect(snapshot.command_snapshot.name).toBe(profile);
 expect(snapshot.cycles).toBe(2);expect(snapshot.attempts).toHaveLength(10);
 expect(snapshot.execution_targets.labels).toEqual(['local']);
 expect(snapshot.progress.usage.status).toBe('not_applicable');
 expect(snapshot.attempts[0].resolved_command_argv).toEqual(['python','run_suite.py','--case','01_boot','--port','COM3']);
 const pair=snapshot.attempts.find((a:any)=>a.tc_id.includes('dual'));
 expect(pair.resolved_command_argv).toEqual(['python','run_suite.py','--case','04_pair.py','--port-a','COM3','--port-b','COM4']);
 await page.getByRole('button',{name:'Preflight 검사',exact:true}).click();
 await expect(page.getByRole('button',{name:'▶ 테스트 시작',exact:true})).toBeEnabled();
 await openSettings(page);
 await page.getByLabel('Single 실행 명령',{exact:true}).fill('python\nnew_runner.py\n{tc_path}\n{com_a}');
 await page.getByRole('tab',{name:'실행 및 결과',exact:true}).click();
 await expect(page.getByRole('button',{name:'▶ 테스트 시작',exact:true})).toBeDisabled();
 await expect(preview).toHaveCount(0);
 await openSettings(page);
 await page.getByRole('button',{name:'명령 저장 / 수정',exact:true}).click();
 const after=await (await page.request.get('/api/v1/gui-test/runs/'+id)).json();
 expect(after.attempts.map((a:any)=>a.resolved_command_argv)).toEqual(snapshot.attempts.map((a:any)=>a.resolved_command_argv));
 await page.setViewportSize({width:680,height:1000});
 await page.screenshot({path:'../../.local-reports/gui-test/'+(standalone?'standalone':'dashboard')+'-commands.png',fullPage:true});
 await page.evaluate(key=>localStorage.setItem(key,'deleted-command'), 'gui-command-profile:'+(standalone?'standalone':'dashboard'));
 await page.reload();
 if(!standalone)await page.getByRole('navigation').getByRole('button',{name:'Test 현황',exact:true}).click();
 await openSettings(page);
 await expect(page.getByRole('alert').filter({hasText:'이전에 선택한 명령이 없습니다'})).toBeVisible();
 await page.getByRole('tab',{name:'실행 및 결과',exact:true}).click();
 await expect(page.getByRole('button',{name:'Preflight 검사',exact:true})).toBeDisabled();
 await openSettings(page);
 await page.getByLabel('저장된 실행 명령',{exact:true}).selectOption('');
 await page.getByRole('tab',{name:'실행 및 결과',exact:true}).click();
 await expect(page.getByRole('button',{name:'Preflight 검사',exact:true})).toBeEnabled();
});


test('GUI-UI-17 usage details collapse while progress shows complete and partial costs',async({page})=>{
 await openTest(page);await launch(page);await expect(page.getByTestId('run-state')).toHaveText('COMPLETED · PASS',{timeout:20000});
 const id=await page.getByLabel('Run 이력').inputValue();
 let status='reported',costs:(string|null)[]=['0.1','0.2'];
 await page.route('**/api/v1/gui-test/runs/'+id,async route=>{
  const response=await route.fetch();const value=await response.json();
  const usage={status,models:costs.map((cost,i)=>({provider:'fixture',model:'model-'+i,input_tokens:10,output_tokens:5,cost_usd:cost}))};
  value.progress.usage={...usage,cases:value.tests.map((tc:any)=>({...usage,tc_id:tc.id}))};
  await route.fulfill({response,json:value});
 });
 await page.getByLabel('Run 이력').selectOption('');await page.getByLabel('Run 이력').selectOption(id);
 const summary=page.getByLabel('진행 요약',{exact:true}),details=page.locator('.gt-usage').first();
 await expect(summary).toContainText('완료 5/5회');await expect(summary).toContainText('비용 $0.3000');
 await expect(details).not.toHaveAttribute('open','');await expect(details.locator('.gt-usage-lines')).toBeHidden();
 await details.locator('summary').focus();await page.keyboard.press('Enter');
 await expect(details.locator('.gt-usage-lines')).toBeVisible();await expect(details).toContainText('model-0');
 await page.keyboard.press('Enter');await expect(details.locator('.gt-usage-lines')).toBeHidden();
 const rowDetails=page.locator('.gt-table .gt-usage').first();await rowDetails.locator('summary').click();await expect(rowDetails.locator('.gt-usage-lines')).toBeVisible();
 status='partial';costs=['0.1',null];
 await page.getByLabel('Run 이력').selectOption('');await page.getByLabel('Run 이력').selectOption(id);
 await expect(summary).toContainText('집계 비용 $0.1000 · 일부 미집계');
 status='reported';costs=['0'];
 await page.getByLabel('Run 이력').selectOption('');await page.getByLabel('Run 이력').selectOption(id);
 await expect(summary).toContainText('비용 $0.0000');
 costs=[null];
 await page.getByLabel('Run 이력').selectOption('');await page.getByLabel('Run 이력').selectOption(id);
 await expect(summary).toContainText('비용 미집계');await expect(summary).not.toContainText('$0');
 await page.setViewportSize({width:375,height:900});expect(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth)).toBe(true);
 await page.screenshot({path:'../../.local-reports/gui-test/'+(standalone?'standalone':'dashboard')+'-usage-summary.png',fullPage:true});
});
