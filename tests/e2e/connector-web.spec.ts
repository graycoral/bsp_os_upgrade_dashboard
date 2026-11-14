import {test, expect} from '../../apps/web/node_modules/@playwright/test';

test.skip(!process.env.CONNECTOR_FIXTURE_KEY, 'Run with scripts/test_connector_browser.py; never a production service');
test.beforeEach(async ({page, request}) => {
  const response=await request.get('/fixture-ticket',{headers:{'X-Test-Driver':process.env.CONNECTOR_FIXTURE_KEY!,'X-Test-Reset':'true'}});
  expect(response.ok()).toBeTruthy();
  await page.goto((await response.json()).url);
  await expect(page.getByRole('heading',{name:'보드 커넥터'})).toBeVisible();
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

test('TC and UNKNOWN block manual ownership; preview control never starts hardware',async ({page})=>{
  await page.locator('#connection-power').click();
  await expect(page.locator('#manual')).toBeEnabled();
  await page.locator('#manual').click();
  await expect(page.locator('#manual')).toHaveText('수동 제어 종료');
  await page.locator('#manual').click();
  await page.locator('#scenario').selectOption('시험 중');
  await expect(page.locator('#manual')).toBeDisabled();
  await expect(page.locator('#control-reason')).toContainText('시험·예약');
  await expect(page.locator('#connection-power')).toBeDisabled();
  await page.locator('#scenario').selectOption('확인 필요');
  await expect(page.locator('#manual')).toBeDisabled();
  await expect(page.locator('#freshness')).toContainText('과거 기록');
});

test('settings drafts, board shrink and restore, save and cancel preserve mappings',async ({page})=>{
  await page.getByRole('button',{name:'환경설정'}).click();
  await page.locator('#server').fill('edited.example');
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
  await expect(page.locator('#manual')).toBeDisabled();
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


test('compact board list uses traffic lights, tooltips, power control and always visible logs',async ({page})=>{
  await expect(page.getByRole('heading',{name:'보드 리스트',exact:true})).toBeVisible();
  await expect(page.getByRole('heading',{name:'내 보드',exact:true})).toHaveCount(0);
  await expect(page.locator('#connection-details')).not.toHaveAttribute('open','');
  await expect(page.locator('#connection-details .callout')).toBeHidden();
  const row=await page.locator('#boards button').first().boundingBox();
  expect(row!.height).toBeLessThanOrEqual(46);expect(row!.width).toBeLessThan(230);
  const left=await page.locator('.board-sidebar').boundingBox(),right=await page.locator('.board-detail').boundingBox();
  expect(Math.abs(left!.y-right!.y)).toBeLessThanOrEqual(1);expect(Math.abs(left!.height-right!.height)).toBeLessThanOrEqual(1);
  await expect(page.locator('#boards .board-port').first()).toHaveText('COM7');
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
  const log=await page.locator('#log').boundingBox();expect(log!.height).toBeLessThanOrEqual(190);
  await page.getByRole('tab',{name:'TC 로그',exact:true}).click();
  await expect(page.locator('#log-hint')).toContainText('TC 프로그램 출력');
  await expect(page.locator('#log-window > summary')).toHaveCount(0);
  await page.locator('#connection-details > summary').click();
  await page.waitForTimeout(1400);await expect(page.locator('#log')).toBeVisible();
  await expect(page.locator('#log')).toHaveValue(/TC process stdout/);
  await page.locator('#scenario').selectOption('오류');
  await expect(page.locator('#board-state')).toHaveAttribute('data-tone','red');
  await page.locator('#scenario').selectOption('확인 필요');
  await expect(page.locator('#state')).toHaveAttribute('data-tone','amber');await expect(page.locator('#manual')).toBeDisabled();
  await page.locator('[data-stage=ssh]').hover();await expect(tip).toContainText('확인 필요');
});
