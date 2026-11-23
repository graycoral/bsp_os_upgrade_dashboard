import {test, expect} from '../../apps/web/node_modules/@playwright/test';

test.skip(!process.env.CONNECTOR_FIXTURE_KEY, 'Run with scripts/test_connector_browser.py; never a production service');
test.beforeEach(async ({page, request}) => {
  const response=await request.get('/fixture-ticket',{headers:{'X-Test-Driver':process.env.CONNECTOR_FIXTURE_KEY!,'X-Test-Reset':'true'}});
  expect(response.ok()).toBeTruthy();
  await page.goto((await response.json()).url);
  await expect(page.getByRole('heading',{name:/WINDOWS · BOARD CONNECTOR/})).toBeVisible();
  await expect(page.locator('#connection-power')).toBeEnabled();
});

test('default web view connects, retains board selection and survives reload without disconnect',async ({page})=>{
  expect(new URL(page.url()).hash).toBe('');
  await page.getByRole('button',{name:'연결 시작',exact:true}).click();
  await expect(page.locator('#state')).toHaveAttribute('data-state','CONNECTED');
  await page.locator('#boards button').nth(1).click();
  await expect(page.locator('#board-title')).toHaveText('board-b');
  await page.waitForTimeout(1400);
  await expect(page.locator('#boards button').nth(1)).toHaveAttribute('aria-pressed','true');
  await page.reload();
  await expect(page.locator('#state')).toHaveAttribute('data-state','CONNECTED');
  await expect(page.locator('#connection-power')).toBeEnabled();
  await expect(page.locator('#connection-power')).toHaveAttribute('aria-pressed','true');
  await expect(page.getByRole('button',{name:'연결 종료',exact:true})).toHaveCount(1);
  await page.locator('#connection-power').click();
  await expect(page.locator('#state')).toHaveAttribute('data-state','DISCONNECTED');
  await expect(page.locator('#connection-power')).toHaveAttribute('aria-pressed','false');
  await expect(page.getByRole('button',{name:'연결 시작',exact:true})).toBeEnabled();
});

test('TC script list shows server states without any TC control requests',async ({page})=>{
  await page.locator('#connection-power').click();
  await page.locator('#scenario').selectOption('시험 중');
  const list=page.getByRole('region',{name:'테스트 스크립트 상태'});
  await expect(list.locator('tbody tr')).toHaveCount(5);
  await expect(list).toContainText('/srv/tc');
  await expect(list).toContainText('진행 중');await expect(list).toContainText('대기 중');
  await expect(list).toContainText('PASS');await expect(list).toContainText('FAIL');
  await expect(list).toContainText('미선택');
  await expect(list.locator('button,input[type=checkbox],a')).toHaveCount(0);
  const writes:string[]=[];page.on('request',request=>{if(request.method()!=='GET')writes.push(request.url());});
  await page.locator('#tc-filter').selectOption('FAIL');
  await expect(list.locator('tbody tr')).toHaveCount(1);
  await page.locator('#tc-search').fill('no-such-script');
  await expect(list.locator('tbody tr')).toHaveCount(0);await expect(page.locator('#tc-empty')).toBeVisible();
  await page.locator('#tc-search').clear();await page.locator('#tc-filter').selectOption('all');
  await page.locator('#boards button').nth(1).click();
  await expect(list.locator('td[data-state=NOT_RUN]')).toHaveCount(5);
  await page.locator('#boards button').first().click();
  await expect(list.locator('td[data-state=RUNNING]')).toHaveCount(1);
  await page.waitForTimeout(1500);expect(writes).toEqual([]);
  await page.locator('#scenario').selectOption('확인 필요');
  await expect(page.locator('#tc-status-note')).toContainText('과거 수신 정보');
});

test('TC source replacement clears old results and script paths render as text',async ({page})=>{
  let source='/srv/tc',file='Single/original.py';
  await page.route('**/api/status',async route=>{
    const response=await route.fetch(),value=await response.json();
    value.test_status={source:{location:source},rows:[{id:file,path:file,boards:{}}],message:'',stale:false};
    await route.fulfill({response,json:value});
  });
  await page.locator('#connection-power').click();
  await expect(page.locator('#tc-status-rows')).toContainText('Single/original.py');
  source='/srv/other';file='<img src=x onerror=alert(1)>.py';
  await expect(page.locator('#tc-source')).toHaveText('/srv/other');
  await expect(page.locator('#tc-status-rows')).toContainText(file);
  await expect(page.locator('#tc-status-rows')).not.toContainText('original.py');
  await expect(page.locator('#tc-status-rows img')).toHaveCount(0);
});

test('TC and UNKNOWN block manual ownership; preview control never starts hardware',async ({page})=>{
  await page.locator('#connection-power').click();
  await expect(page.locator('#manual')).toHaveCount(0);
  await expect(page.locator('#putty')).toBeEnabled();
  await page.locator('#putty').click();
  await expect(page.locator('#notice')).toContainText('미리보기에서는 PuTTY를 실행하지 않습니다.');
  await expect(page.locator('#board-server')).toContainText('company.example');
  await page.locator('#scenario').selectOption('시험 중');
  await expect(page.locator('#putty')).toBeDisabled();
  await expect(page.locator('#control-reason')).toContainText('시험·예약');
  await expect(page.locator('#connection-power')).toBeDisabled();
  const running=page.locator('#board-state .signal');
  await expect.poll(()=>running.evaluate(el=>getComputedStyle(el).animationName)).toBe('board-running');
  await expect.poll(()=>page.locator('#boards button').first().locator('.signal').evaluate(el=>getComputedStyle(el).animationName)).toBe('board-running');
  await expect.poll(()=>page.locator('#boards button').nth(1).locator('.signal').evaluate(el=>getComputedStyle(el).animationName)).toBe('none');
  await page.emulateMedia({reducedMotion:'reduce'});
  await expect.poll(()=>running.evaluate(el=>getComputedStyle(el).animationName)).toBe('none');
  await expect.poll(()=>page.locator('#boards button').first().locator('.signal').evaluate(el=>getComputedStyle(el).animationName)).toBe('none');
  await page.emulateMedia({reducedMotion:'no-preference'});
  await page.locator('#scenario').selectOption('확인 필요');
  await expect(page.locator('#putty')).toBeDisabled();
  await expect(page.locator('#freshness')).toContainText('과거 기록');
  await expect.poll(()=>running.evaluate(el=>getComputedStyle(el).animationName)).toBe('none');
  await expect(page.locator('#board-server')).toBeHidden();
});

test('split panels keep console height with many TCs and boards, resize and retain the ratio',async ({page},testInfo)=>{
  await page.setViewportSize({width:1360,height:900});
  let rowCount=5;
  await page.route('**/api/status',async route=>{
    const response=await route.fetch(),value=await response.json(),board=value.boards[0];
    value.boards.push(...Array.from({length:30},(_,index)=>({...board,board_id:'extra-'+index,name:'추가 보드 '+index})));
    value.test_status={source:{location:'/srv/tc'},rows:Array.from({length:rowCount},(_,index)=>({path:`Single/script_${index}.py`,boards:{}})),stale:false};
    value.console={boards:[{board_id:board.board_id,text:Array.from({length:500},(_,i)=>'UART boot log line '+i).join('\n')}],errors:[]};
    await route.fulfill({response,json:value});
  });
  await page.locator('#connection-power').click();
  await expect(page.locator('#tc-status-rows tr')).toHaveCount(5);
  const consoleBefore=await page.locator('#log').boundingBox();
  rowCount=240;
  await expect(page.locator('#tc-status-rows tr')).toHaveCount(240);
  const left=await page.locator('#tc-status').boundingBox(),right=await page.locator('#log-window').boundingBox();
  expect(right!.x).toBeGreaterThan(left!.x+left!.width);expect(Math.abs(right!.y-left!.y)).toBeLessThanOrEqual(1);
  expect(Math.abs((await page.locator('#log').boundingBox())!.height-consoleBefore!.height)).toBeLessThanOrEqual(1);
  expect(consoleBefore!.height).toBeGreaterThan(250);
  expect(await page.locator('.tc-table-scroll').evaluate(el=>el.scrollHeight>el.clientHeight)).toBeTruthy();
  expect(await page.locator('#log').evaluate(el=>el.scrollHeight>el.clientHeight)).toBeTruthy();
  await page.locator('.tc-table-scroll').evaluate(el=>{el.scrollTop=300;});
  const tcScroll=await page.locator('.tc-table-scroll').evaluate(el=>el.scrollTop);
  await page.locator('#log').evaluate(el=>{el.scrollTop=150;});
  expect(await page.locator('.tc-table-scroll').evaluate(el=>el.scrollTop)).toBe(tcScroll);
  expect(await page.locator('#boards').evaluate(el=>el.scrollWidth>el.clientWidth)).toBeTruthy();
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth&&document.documentElement.scrollHeight<=innerHeight)).toBeTruthy();
  const divider=page.getByRole('separator',{name:'TC 목록과 로그 너비 조절'}),box=(await divider.boundingBox())!;
  await page.mouse.move(box.x+box.width/2,box.y+box.height/2);await page.mouse.down();
  await page.mouse.move(box.x+130,box.y+box.height/2,{steps:5});await page.mouse.up();
  const resized=Number(await divider.getAttribute('aria-valuenow'));expect(resized).toBeGreaterThan(35);
  await page.reload();await expect(divider).toHaveAttribute('aria-valuenow',String(resized));
  await divider.focus();await divider.press('ArrowLeft');await expect(divider).toHaveAttribute('aria-valuenow',String(resized-2));
  await divider.press('Home');expect(Number(await divider.getAttribute('aria-valuenow'))).toBe(Number(await divider.getAttribute('aria-valuemin')));
  await divider.press('End');expect(Number(await divider.getAttribute('aria-valuenow'))).toBe(Number(await divider.getAttribute('aria-valuemax')));
  await divider.press('Enter');await expect(divider).toHaveAttribute('aria-valuenow','30');
  await page.locator('#boards button').nth(1).click();
  await expect(page.locator('#board-title')).toHaveText('board-b');await expect(page.locator('#log')).not.toHaveValue(/UART boot log/);
  await page.locator('#boards button').first().click();
  await page.screenshot({path:testInfo.outputPath('split-panels-desktop.png')});
  await page.setViewportSize({width:390,height:900});
  await expect(divider).toBeHidden();
  const mobileLog=(await page.locator('#log').boundingBox())!,footer=(await page.locator('.board-detail>details').first().boundingBox())!;
  expect(mobileLog.y+mobileLog.height).toBeLessThanOrEqual(footer.y);
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBeTruthy();
});

test('settings drafts, board shrink and restore, save and cancel preserve mappings',async ({page})=>{
  await page.getByRole('button',{name:'환경설정'}).click();
  await page.locator('#server').fill('edited.example');
  await page.getByRole('button',{name:'보드 현황',exact:true}).click();
  await expect(page.locator('#settings-tab')).toBeFocused();
  await page.getByRole('button',{name:'환경설정'}).click();
  await expect(page.locator('#overview-tab')).toBeFocused();
  await expect(page.locator('#server')).toHaveValue('edited.example');
  await page.locator('#board-count').fill('1');await page.locator('#board-count').blur();
  await expect(page.locator('#board-forms fieldset')).toHaveCount(1);
  await page.locator('#board-count').fill('2');await page.locator('#board-count').blur();
  await expect(page.locator('#board-forms fieldset')).toHaveCount(2);
  await expect(page.locator('#board-forms fieldset:visible')).toHaveCount(1);
  await page.locator('#board-tabs [role=tab]').nth(1).click();
  await expect(page.locator('#board-forms fieldset').nth(1)).toBeVisible();
  const boardTab=page.locator('#board-tabs [role=tab]').nth(1);
  await expect(page.locator('#board-forms fieldset').nth(1)).toHaveAttribute('id',(await boardTab.getAttribute('aria-controls'))!);
  await expect(page.locator('#board-forms fieldset').nth(1)).toHaveAttribute('aria-labelledby',(await boardTab.getAttribute('id'))!);
  await page.locator('#board-tabs [role=tab]').nth(1).press('ArrowLeft');
  await expect(page.locator('#board-forms fieldset').first()).toBeVisible();
  await expect(page.locator('#board-forms input[name=com]').nth(1)).toHaveValue('COM8');
  await page.waitForTimeout(1400);
  await expect(page.locator('#server')).toHaveValue('edited.example');
  await page.locator('#cancel').click();
  await expect(page.locator('#server')).toHaveValue('company.example');
  await page.locator('#server').fill('saved.example');await page.locator('#save').click();
  await expect(page.locator('#notice')).toContainText('Windows 설정을 저장');
  await page.reload();await page.getByRole('button',{name:'환경설정'}).click();
  await expect(page.locator('#server')).toHaveValue('saved.example');
});

test('logs support selection, search and distinct evidence; stale errors are visible',async ({page})=>{
  await page.locator('#connection-power').click();
  await expect(page.locator('#log')).toHaveValue(/Starting kernel/);
  await page.locator('#search').fill('login');
  await expect(page.locator('#log')).toHaveValue('board login :');
  await page.locator('#search').fill('');
  await page.getByRole('tab',{name:'TC 로그',exact:true}).click();
  await expect(page.getByRole('tab',{name:'TC 로그',exact:true})).toBeFocused();
  await expect(page.getByRole('tab',{name:'TC 로그',exact:true})).toHaveAttribute('aria-controls','log-panel');
  await expect(page.locator('#log-panel')).toHaveAttribute('aria-labelledby','log-tabs-tab-execution');
  await expect(page.locator('#log')).toHaveValue(/TC process stdout/);
  await page.locator('#scenario').selectOption('오류');
  await expect(page.locator('#error')).toContainText('모의 콘솔 오류');
  await page.getByRole('tab',{name:'공통 오류',exact:true}).click();
  await expect(page.locator('#log')).toHaveValue(/CONSOLE_PANIC/);
});

test('multiple invalid COM fields keep the first hidden board visible and focused',async ({page})=>{
  await page.getByRole('button',{name:'환경설정'}).click();
  await page.locator('#board-count').fill('4');await page.locator('#board-count').blur();
  await page.locator('#board-tabs [role=tab]').first().click();
  await page.locator('#save').click();
  await expect(page.locator('#board-tabs [role=tab]').nth(2)).toHaveAttribute('aria-selected','true');
  await expect(page.locator('#board-forms input[name=com]').nth(2)).toBeFocused();
  await expect(page.locator('#notice')).toContainText('보드 3');
  await page.locator('#board-forms input[name=com]').nth(2).fill('COM9');
  await page.locator('#save').click();
  await expect(page.locator('#board-tabs [role=tab]').nth(3)).toHaveAttribute('aria-selected','true');
  await expect(page.locator('#board-forms input[name=com]').nth(3)).toBeFocused();
  await page.locator('#board-forms input[name=com]').nth(3).fill('COM10');
  await page.locator('#save').click();await expect(page.locator('#notice')).toContainText('Windows 설정을 저장');
});

test('server settings retain overrides and use Linux path browsing',async ({page})=>{
  let release!:()=>void;const gate=new Promise<void>(resolve=>{release=resolve;});
  const shared={revision:'a'.repeat(64),integration:{installer_path:'/srv/images/install.bat',tc_root:'/srv/tc',metadata:{keep:true}},
    timeouts:{revision:'b'.repeat(64),default_seconds:600,source_revision:'source-r',overrides:{'tc.py':120}},connector_application:{state:'PENDING'}};
  await page.route('**/api/shared',async route=>{
    if(route.request().method()==='POST'){
      const body=route.request().postDataJSON();expect(body.expected_revision).toBe(shared.revision);
      expect(body.integration.metadata).toEqual({keep:true});expect(body.timeouts.overrides).toEqual({'tc.py':120});
      expect(body.timeouts.default_seconds).toBe(900);expect(body.integration.tc_root).toBe('/srv/new-tc');
      await gate;
      await route.fulfill({json:{...shared,integration:body.integration,timeouts:body.timeouts}});return;
    }
    await route.fulfill({json:shared});
  });
  await page.route('**/api/server-paths',async route=>{const body=route.request().postDataJSON();
    await route.fulfill({json:body.path?{kind:body.kind,path:body.path,roots:['/srv'],entries:[]}:{kind:body.kind,path:null,roots:['/srv/new-tc'],entries:[]}});});
  await page.getByRole('button',{name:'환경설정'}).click();await page.locator('#load-shared').click();
  await expect(page.locator('#shared-state')).toContainText('적용 대기');
  await page.locator('#timeout').fill('900');await page.locator('#browse-source').click();
  await page.getByRole('button',{name:'폴더 · /srv/new-tc',exact:true}).click();await page.locator('#use-folder').click();
  await expect(page.locator('#tc-root')).toHaveValue('/srv/new-tc');await page.locator('#save-shared').click();
  await expect(page.locator('#timeout')).toBeDisabled();await expect(page.locator('#use-folder')).toBeDisabled();release();
  await expect(page.locator('#notice')).toContainText('서버 공통 설정을 저장');
  await expect(page.locator('#timeout')).toBeEnabled();await expect(page.locator('#timeout')).toHaveValue('900');
});

test('a new tab preserves the first tabs unsaved form and write session',async ({page,context,request})=>{
  await page.getByRole('button',{name:'환경설정'}).click();await page.locator('#server').fill('first-tab.example');
  const response=await request.get('/fixture-ticket',{headers:{'X-Test-Driver':process.env.CONNECTOR_FIXTURE_KEY!}});
  const second=await context.newPage();await second.goto((await response.json()).url);
  await expect(second.locator('#connection-power')).toBeEnabled();
  await expect(page.locator('#server')).toHaveValue('first-tab.example');
  await page.locator('#save').click();await expect(page.locator('#notice')).toContainText('Windows 설정을 저장');
  await expect(page.locator('#server')).toHaveValue('first-tab.example');await second.close();
});

test('local save locks only the submitted form during a delayed response',async ({page})=>{
  let release!:()=>void;const gate=new Promise<void>(resolve=>{release=resolve;});
  await page.route('**/api/settings',async route=>{
    if(route.request().method()==='POST')await gate;
    const response=await route.fetch();await route.fulfill({response});
  });
  await page.getByRole('button',{name:'환경설정'}).click();await page.locator('#server').fill('delayed.example');
  await page.locator('#save').click();await expect(page.locator('#server')).toBeDisabled();
  await expect(page.locator('#board-count')).toBeDisabled();release();
  await expect(page.locator('#notice')).toContainText('Windows 설정을 저장');
  await expect(page.locator('#server')).toBeEnabled();await expect(page.locator('#server')).toHaveValue('delayed.example');
});

test('a pending status request expires the displayed connection and recovers',async ({page})=>{
  await page.locator('#connection-power').click();await expect(page.locator('#state')).toHaveAttribute('data-state','CONNECTED');
  const held:any[]=[];
  await page.route('**/api/status',route=>{held.push(route);});
  await expect(page.locator('#state')).toHaveAttribute('data-state','UNKNOWN',{timeout:10000});
  await expect(page.locator('#putty')).toBeDisabled();
  await expect(page.locator('#notice')).toContainText('응답 시간이 초과');
  await page.unroute('**/api/status');for(const route of held)await route.abort().catch(()=>{});
  await expect(page.locator('#state')).toHaveAttribute('data-state','CONNECTED',{timeout:10000});
});

test('board names are text and cancelling a picker preserves the typed path',async ({page})=>{
  await page.getByRole('button',{name:'환경설정'}).click();
  await page.locator('#python').fill('C:/한글 폴더/python.exe');await page.locator('[data-pick=python]').click();
  await expect(page.locator('#python')).toHaveValue('C:/한글 폴더/python.exe');
  await page.locator('#board-forms input[name=name]').first().fill('<img src=x onerror=alert(1)>');
  await page.locator('#save').click();await expect(page.locator('#notice')).toContainText('Windows 설정을 저장');
  await page.getByRole('button',{name:'보드 현황'}).click();await page.locator('#connection-power').click();
  await expect(page.locator('#board-title')).toHaveText('<img src=x onerror=alert(1)>');await expect(page.locator('img')).toHaveCount(0);
});

test('narrow and desktop layouts fit the viewport and use keyboard-focusable controls',async ({page},testInfo)=>{
  for(const width of [1360,390]){
    await page.setViewportSize({width,height:900});
    expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBeTruthy();
    await page.getByRole('button',{name:'환경설정'}).click();
    expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBeTruthy();
    await page.locator('#server').focus();await expect(page.locator('#server')).toBeFocused();
    await page.getByRole('button',{name:'보드 현황'}).click();
    const log=(await page.locator('#log').boundingBox())!,footer=(await page.locator('.board-detail>details').first().boundingBox())!;
    expect(log.y+log.height).toBeLessThanOrEqual(footer.y);
    await page.screenshot({path:testInfo.outputPath(`connector-${width}.png`),fullPage:true});
  }
});

test('storage policy is shared and cleanup distinguishes Linux from unavailable Windows',async({page})=>{
 const policy={revision:'a'.repeat(64),enabled:true,max_age_seconds:604800,max_bytes:20*1024**3,connector_sync:{state:'APPLIED'}};
 const writes:any[]=[];
 await page.route('**/api/storage',async route=>{if(route.request().method()==='POST'){writes.push(route.request().postDataJSON());}await route.fulfill({json:policy});});
 await page.route('**/api/storage-cleanup',async route=>{expect(route.request().postDataJSON()).toEqual({dry_run:true});await route.fulfill({json:{dry_run:true,planned_bytes:1048576,over_budget:true,connector_cleanup:{state:'CHECKED',report:{dry_run:true,planned_bytes:2097152,over_budget:true}}}});});
 await page.getByRole('button',{name:'환경설정'}).click();await page.getByText('저장 공간 자동 정리',{exact:true}).click();
 await page.locator('#load-storage').click();await page.locator('#storage-days').fill('14');await page.locator('#save-storage').click();
 await expect.poll(()=>writes[0]).toMatchObject({expected_revision:policy.revision,max_age_seconds:1209600});
 await page.locator('#preview-cleanup').click();await expect(page.locator('#cleanup-report')).toContainText('Linux · 정리 예정 1 MiB');
 await expect(page.locator('#cleanup-report')).toContainText('Windows · 정리 예정 2 MiB · 용량 한도 초과');
});

test('missing required COM selects the first invalid board settings tab',async({page})=>{
 await page.getByRole('button',{name:'환경설정'}).click();
 await page.locator('#board-count').fill('3');await page.locator('#board-count').blur();
 await page.locator('#board-tabs [role=tab]').nth(1).click();
 await page.locator('#board-forms input[name=com]').nth(1).fill('');
 await page.locator('#board-tabs [role=tab]').first().click();
 await page.locator('#save').click();
 await expect(page.locator('#board-forms fieldset').nth(1)).toBeVisible();
 await expect(page.locator('#board-forms input[name=com]').nth(1)).toBeFocused();
 await expect(page.locator('#notice')).toContainText('보드 2의 필수 COM');
 await expect(page.locator('#board-forms fieldset').nth(2)).toBeHidden();
});


test('horizontal board strip uses traffic lights, tooltips, power control and always visible logs',async ({page})=>{
  await expect(page.locator('.board-sidebar')).toHaveCount(0);
  await expect(page.getByRole('navigation',{name:'화면 선택'})).toHaveCount(0);
  await expect(page.locator('#settings')).toBeHidden();
  const settingsButton=await page.locator('#settings-tab').boundingBox(),powerButton=await page.locator('#connection-power').boundingBox();
  expect(settingsButton!.x+settingsButton!.width).toBeLessThanOrEqual(powerButton!.x);
  expect(Math.abs(settingsButton!.y-powerButton!.y)).toBeLessThanOrEqual(1);
  const stagesLine=await page.locator('#stages').boundingBox();expect(Math.abs((stagesLine!.y+stagesLine!.height/2)-(powerButton!.y+powerButton!.height/2))).toBeLessThanOrEqual(1);
  await expect(page.locator('#freshness')).toBeHidden();
  await expect(page.getByText('화면을 닫아도 연결과 시험은 계속됩니다.',{exact:true})).toHaveCount(0);
  await expect(page.locator('.page-footer')).toHaveCount(0);
  await expect(page.locator('#settings-tab')).toHaveAccessibleName('환경설정');
  await expect(page.locator('#settings-tab')).toHaveAttribute('title','환경설정');
  expect(settingsButton!.width).toBeLessThanOrEqual(40);
  await expect(page.getByRole('heading',{name:'내 보드',exact:true})).toHaveCount(0);
  await expect(page.locator('.board-title-row #putty')).toHaveAccessibleName('PuTTY 열기');
  const title=await page.locator('#board-title').boundingBox(),icon=await page.locator('#putty').boundingBox();
  expect(icon!.width).toBeLessThanOrEqual(32);expect(icon!.height).toBeLessThanOrEqual(32);expect(icon!.x).toBeGreaterThan(title!.x+title!.width);expect(Math.abs((icon!.y+icon!.height/2)-(title!.y+title!.height/2))).toBeLessThanOrEqual(1);
  await expect(page.locator('.board-toolbar #summary')).toHaveAccessibleName('등록 2대 · 감지 2대 · 시험 중 0대');
  const strip=await page.locator('.board-toolbar').boundingBox(),detail=await page.locator('.board-detail').boundingBox();
  expect(strip!.y).toBeGreaterThanOrEqual(stagesLine!.y+stagesLine!.height);expect(strip!.y+strip!.height).toBeLessThanOrEqual(detail!.y);
  await expect(page.locator('.toolbar #summary')).toHaveCount(0);
  await expect(page.locator('#connection-details')).not.toHaveAttribute('open','');
  await expect(page.locator('#connection-details .callout')).toBeHidden();
  const row=await page.locator('#boards button').first().boundingBox();
  expect(row!.height).toBeLessThanOrEqual(46);expect(row!.width).toBeLessThan(230);
  const first=await page.locator('#boards button').first().boundingBox(),second=await page.locator('#boards button').nth(1).boundingBox();
  expect(Math.abs(first!.y-second!.y)).toBeLessThanOrEqual(1);expect(second!.x).toBeGreaterThan(first!.x);
  await expect(page.locator('#boards button').first()).toHaveAttribute('title',/COM7/);
  await expect(page.locator('#boards .board-status').first()).toHaveAttribute('data-tone','gray');
  await page.locator('#connection-power').click();
  await expect(page.locator('#state')).toHaveAttribute('data-tone','green');
  await expect(page.locator('#boards .board-status').first()).toHaveAttribute('aria-label','연결됨');
  await expect(page.locator('#stages .signal.green')).toHaveCount(4);
  const stageLight=await page.locator('#stages .signal').first().boundingBox();expect(stageLight!.width).toBeLessThanOrEqual(12);
  const ssh=page.locator('[data-stage=ssh]'),tip=ssh.getByRole('tooltip');
  await expect(tip).toBeHidden();await ssh.hover();
  await expect(tip).toBeVisible();await expect(tip).toContainText('SSH 연결 · 정상');await expect(tip).toContainText('Windows에서 Linux 서버');
  await page.waitForTimeout(1400);await expect(tip).toBeVisible();
  await page.mouse.move(0,0);await expect(tip).toBeHidden();
  await ssh.focus();await expect(tip).toBeVisible();await page.waitForTimeout(1400);await expect(ssh).toBeFocused();
  await ssh.press('Escape');await expect(tip).toBeHidden();
  await page.locator('#connection-details > summary').click();
  await expect(page.locator('#connection-details')).toContainText('PuTTY는 같은 보드의 별도 터미널');
  await expect(page.locator('#connection-details .callout')).toBeVisible();
  const log=await page.locator('#log').boundingBox();expect(log!.height).toBeGreaterThanOrEqual(200);
  await page.getByRole('tab',{name:'TC 로그',exact:true}).click();
  await expect(page.locator('#log-hint')).toContainText('TC 프로그램 출력');
  await expect(page.locator('#log-window > summary')).toHaveCount(0);
  await expect(page.locator('#log-window h3')).toHaveCount(0);
  await expect(page.locator('#log-tabs')).toHaveClass('tabs');
  await expect(page.locator('.log-tab-bar #open-logs')).toBeVisible();
  await page.locator('#connection-details > summary').click();
  await page.waitForTimeout(1400);await expect(page.locator('#log')).toBeVisible();
  await expect(page.locator('#log')).toHaveValue(/TC process stdout/);
  await page.locator('#scenario').selectOption('오류');
  await expect(page.locator('#board-state')).toHaveAttribute('data-tone','red');
  await page.locator('#scenario').selectOption('확인 필요');
  await expect(page.locator('#state')).toHaveAttribute('data-tone','amber');await expect(page.locator('#putty')).toBeDisabled();
  await page.locator('[data-stage=ssh]').hover();await expect(tip).toContainText('확인 필요');
});


test('connection notices share the stage line, wrap long messages and stay visible in settings',async ({page})=>{
  await expect(page.locator('.header #notice')).toHaveCount(0);
  await page.locator('#connection-power').click();
  await expect(page.locator('#state')).toHaveAttribute('data-state','CONNECTED');
  await expect(page.locator('#notice')).toBeHidden();
  await expect(page.locator('#board-server')).toHaveText('서버 · company.example');
  let returning=false;
  await page.route('**/api/status',async route=>{const response=await route.fetch();const status=await response.json();status.connection_server={server:'updated.example',account:'tester',ssh_port:22};status.putty_cleanup=returning?[{board_id:'board-a',state:'RETRYING',attempts:1}]:[];await route.fulfill({response,json:status});});
  await expect(page.locator('#board-server')).toHaveText('서버 · updated.example');
  await page.locator('#putty').click();await expect(page.locator('.connection-line #notice')).toBeVisible();
  returning=true;await expect(page.locator('#cleanup-state')).toContainText('반환 재시도');await expect(page.locator('#putty')).toBeDisabled();
  returning=false;await expect(page.locator('#cleanup-state')).toBeHidden();await expect(page.locator('#putty')).toBeEnabled();
  await page.getByRole('button',{name:'환경설정',exact:true}).click();
  await page.locator('#load-shared').click();await expect(page.locator('#notice')).toContainText('미리보기');
  await page.setViewportSize({width:390,height:844});
  const stages=await page.locator('#stages').boundingBox(),notice=await page.locator('#notice').boundingBox();
  expect(notice!.y).toBeGreaterThanOrEqual(stages!.y+stages!.height);
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBeTruthy();
});

test('legacy native settings use automatic COM sharing and preserve hidden observer and inactive data',async({page})=>{
  const observer={port:'COM7',rx_only_confirmed:false,control_lines_isolated:true,company:{keep:'observer'}};
  const inactive={board:{board_id:'saved-board',host:'WIN',com:'COM29',extra:'keep'},name:'Saved board',baudrate:9600,observer:{port:'COM29',rx_only_confirmed:true,control_lines_isolated:false},company:{keep:'inactive'}};
  let posted:any;
  await page.route('**/api/settings',async route=>{
    if(route.request().method()==='POST'){
      posted=route.request().postDataJSON();await route.fulfill({json:{profile:posted.profile,revision:'saved-auto'}});return;
    }
    const response=await route.fetch(),value=await response.json();value.profile.serial_transport='native';value.profile.console_observers={'board-a':observer};value.profile.connector_inactive_boards=[inactive];
    await route.fulfill({json:value});
  });
  await page.route('**/api/status',async route=>{const response=await route.fetch(),value=await response.json();for(const board of value.boards||[])delete board.serial_proxy;await route.fulfill({json:value});});
  await page.getByRole('button',{name:'환경설정'}).click();await page.locator('#reload').click();
  await expect(page.locator('#transport')).toHaveCount(0);await expect(page.locator('[name=rx],[name=confirmed]')).toHaveCount(0);
  await expect(page.locator('#serial-status')).toHaveText('다음 연결 시 자동 적용');
  await page.locator('#board-forms input[name=com]').first().fill('COM9');await page.locator('#save').click();
  await expect.poll(()=>posted?.profile.serial_transport).toBe('proxy');
  expect(posted.profile.console_observers).toEqual({'board-a':observer});expect(posted.profile.connector_inactive_boards).toEqual([inactive]);
  await expect(page.locator('#serial-status')).toHaveText('다음 연결 시 자동 적용');
});

test('flash settings are visible before loading and save the Linux BAT and profile together',async({page})=>{
  const shared={revision:'fixture',integration:{installer_roots:['/images'],flash_profile_revision:'old',metadata:{keep:true}},
    timeouts:{default_seconds:120,overrides:{},source_revision:''}};
  await page.route('**/api/shared',async route=>{
    if(route.request().method()==='POST'){
      const body=route.request().postDataJSON();
      expect(body.expected_revision).toBe('fixture');
      expect(body.integration).toMatchObject({installer_path:'/images/new/flash.bat',installer_roots:['/images'],flash_profile:'board-a',flash_profile_revision:null,metadata:{keep:true}});
      await route.fulfill({json:{...shared,integration:body.integration}});return;
    }
    await route.fulfill({json:shared});
  });
  await page.getByRole('button',{name:'환경설정'}).click();
  await expect(page.getByLabel('Linux 설치 BAT 경로')).toBeVisible();
  await page.locator('#load-shared').click();
  await page.getByLabel('Linux 설치 BAT 경로').fill('/images/new/flash.bat');
  await page.getByLabel('플래싱 프로파일').fill('board-a');
  await page.locator('#save-shared').click();
  await expect(page.locator('#notice')).toContainText('서버 공통 설정을 저장');
});
