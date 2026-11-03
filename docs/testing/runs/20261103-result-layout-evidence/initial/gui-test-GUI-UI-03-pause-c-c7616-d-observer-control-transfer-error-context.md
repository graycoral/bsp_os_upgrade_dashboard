# Instructions

- Following Playwright test failed.
- Explain why, be concise, respect Playwright best practices.
- Provide a snippet of code with the fix, if possible.

# Test info

- Name: gui-test.spec.ts >> GUI-UI-03 pause/cancel and observer control transfer
- Location: ..\..\tests\e2e\gui-test.spec.ts:213:5

# Error details

```
Error: expect(locator).toBeVisible() failed

Locator:  getByText('관찰 모드')
Expected: visible
Received: hidden
Timeout:  5000ms

Call log:
  - Expect "toBeVisible" getByText('관찰 모드') with timeout 5000ms
  - waiting for getByText('관찰 모드')
    13 × locator resolved to <p class="gt-hash">Run b6f6196c0f344eb894b49492fc1ffe94 · 관찰 모드</p>
       - unexpected value "hidden"

```

```yaml
- text: GUI TEST WORKSPACE
- heading "Test 현황" [level=2]
- paragraph: 테스트 선택부터 실행, 근거와 결과 확인까지
- text: ● 실행 관리자 연결됨
- strong: MOCK DEMO
- text: Windows 단독 모드 · 로컬 Run 저장 실제 TC·RBM은 미연동입니다. 장비와 운영 Dashboard 결과를 변경하지 않습니다.
- button "TC 검색 패널 숨기기" [expanded]
- complementary:
  - separator "TC 검색 패널 너비"
  - heading "Test cases" [level=3]
  - text: 5개 선택 TC 검색
  - textbox "TC 검색":
    - /placeholder: 이름 · 경로 검색
  - text: 유형
  - combobox "연결 유형 필터":
    - option "전체" [selected]
    - option "Single"
    - option "Dual"
  - button "트리 모두 펼치기"
  - button "트리 모두 접기"
  - text: 5/5개 선택 · 5/5개 표시
  - group "TC 목록 정렬":
    - checkbox "표시된 TC 전체 선택" [checked]
    - button "이름 정렬": 이름
    - button "유형 정렬": 유형
    - button "시간 정렬": 시간
    - button "실행 순서로 보기" [pressed]: ↶
  - group "테스트 케이스 목록":
    - list:
      - listitem:
        - checkbox "폴더 boot" [checked]
        - button "boot 폴더 목록" [expanded]: boot 2/2
        - list:
          - listitem:
            - checkbox "선택 01_boot" [checked]
            - text: 01_boot Single 10s
            - button "01_boot 실행 횟수 설정"
          - listitem:
            - checkbox "선택 02_smoke" [checked]
            - text: 02_smoke Single 10s
            - button "02_smoke 실행 횟수 설정"
      - listitem:
        - checkbox "폴더 extra" [checked]
        - button "extra 폴더 목록" [expanded]: extra 1/1
        - list:
          - listitem:
            - checkbox "선택 05_observation" [checked]
            - text: 05_observation Single 10s
            - button "05_observation 실행 횟수 설정"
      - listitem:
        - checkbox "폴더 network" [checked]
        - button "network 폴더 목록" [expanded]: network 2/2
        - list:
          - listitem:
            - checkbox "폴더 network/dual" [checked]
            - button "network/dual 폴더 목록" [expanded]: dual 1/1
            - list:
              - listitem:
                - checkbox "선택 04_pair" [checked]
                - text: 04_pair Dual 10s
                - button "04_pair 실행 횟수 설정"
          - listitem:
            - checkbox "선택 03_link" [checked]
            - text: 03_link Single 10s
            - button "03_link 실행 횟수 설정"
  - paragraph: 전체·폴더 선택은 검색·필터에 표시된 실행 가능한 TC에만 적용됩니다. 필터 밖 선택은 유지됩니다. 선택한 TC를 끌어 실행 순서를 바꿀 수 있으며 검색·정렬은 실행 순서를 유지합니다.
  - group: 현재 실행 순서 확인
- tablist "TC 작업 화면":
  - tab "결과" [selected]
  - text: 세션
  - combobox "Run 이력":
    - option "Run 선택"
    - option "b6f6196c · RUNNING · INCOMPLETE" [selected]
    - option "e5a7c83d · COMPLETED · PASS"
    - option "2e861b60 · COMPLETED · PASS"
  - tab "연결 및 실행 설정"
- tabpanel "결과":
  - region "실행 결과":
    - heading "결과" [level=3]
    - text: RUNNING · INCOMPLETE
    - strong: 20%
    - progressbar "TC 판정 진행률"
    - text: 완료 1/5회 비용 — · 모델 호출 없음
    - group: 토큰·비용 상세
    - group: 세션 정보 · 대상 · 상태별 집계
    - group:
      - text: 결과 상세
      - tablist:
        - tab "TC 결과 · 로그" [selected]
        - tab "결과 리포트"
        - tab "감사 이력"
      - table:
        - rowgroup:
          - row "TC 유형 현재 결과 실행 대상 Attempts 토큰 · 비용":
            - columnheader "TC"
            - columnheader "유형"
            - columnheader "현재 결과"
            - columnheader "실행 대상"
            - columnheader "Attempts"
            - columnheader "토큰 · 비용"
        - rowgroup:
          - row "01_boot Single PASS local 1":
            - cell "01_boot":
              - button "01_boot"
            - cell "Single"
            - cell "PASS"
            - cell "local"
            - cell "1"
            - cell:
              - group: 토큰·비용 상세
          - row "02_smoke Single RUNNING local 1":
            - cell "02_smoke":
              - button "02_smoke"
            - cell "Single"
            - cell "RUNNING"
            - cell "local"
            - cell "1"
            - cell:
              - group: 토큰·비용 상세
          - row "05_observation Single PENDING 기록 없음 0":
            - cell "05_observation":
              - button "05_observation"
            - cell "Single"
            - cell "PENDING"
            - cell "기록 없음"
            - cell "0"
            - cell:
              - group: 토큰·비용 상세
          - row "03_link Single PENDING 기록 없음 0":
            - cell "03_link":
              - button "03_link"
            - cell "Single"
            - cell "PENDING"
            - cell "기록 없음"
            - cell "0"
            - cell:
              - group: 토큰·비용 상세
          - row "04_pair Dual PENDING 기록 없음 0":
            - cell "04_pair":
              - button "04_pair"
            - cell "Dual"
            - cell "PENDING"
            - cell "기록 없음"
            - cell "0"
            - cell:
              - group: 토큰·비용 상세
      - group: 실시간 로그 · 과거 Attempt 포함
  - heading "실행" [level=3]:
    - button "실행" [expanded]: 실행 TC 5개 · 총 5회 예정 · RUNNING
  - text: TC 5개 · 전체 1회 · 총 5회 실행 · 1× · pass · demo-board-a
  - button "Preflight 검사"
  - button "▶ 테스트 시작" [disabled]
  - button "Ⅱ 일시 정지" [disabled]
  - button "▶ 재개" [disabled]
  - button "■ 테스트 중단" [disabled]
  - button "데모 연결 / 종료 확인" [disabled]
  - button "다음 TC 오류 주입" [disabled]
  - button "제어권 요청"
  - button "만료된 제어권 인수"
```

# Test source

```ts
  117 |   const response=await route.fetch();const catalog=await response.json();
  118 |   catalog.tests=catalog.tests.map((tc:any)=>tc.name==='01_boot'?{...tc,disabled_reason:'Test fixture: unavailable'}:tc);
  119 |   await route.fulfill({response,json:catalog});
  120 |  });
  121 |  await openTest(page);
  122 |  const all=page.getByRole('checkbox',{name:'표시된 TC 전체 선택',exact:true});
  123 |  const boot=page.getByLabel('선택 01_boot',{exact:true});
  124 |  await expect(boot).toBeDisabled();await expect(boot).not.toBeChecked();
  125 |  await expect(all).toBeChecked();
  126 |  await all.uncheck();await all.check();
  127 |  await expect(boot).not.toBeChecked();
  128 |  await page.getByLabel('TC 검색',{exact:true}).fill('01_boot');
  129 |  await expect(all).toBeDisabled();await expect(all).not.toBeChecked();
  130 |  await expect(all).toHaveJSProperty('indeterminate',false);
  131 |  await expect(page.getByLabel('TC 실행 순서').locator('li')).toHaveCount(4);
  132 | });
  133 | async function openTest(page:any){
  134 |  await page.goto('/');
  135 |  if(!standalone)await page.getByRole('navigation').getByRole('button',{name:'Test 현황',exact:true}).click();
  136 |  await expect(page.getByRole('heading',{name:'Test 현황',exact:true})).toBeVisible();
  137 |  await expect(page.getByLabel('선택 04_pair')).toBeChecked();
  138 | }
  139 | async function openSettings(page:any){
  140 |  const settings=page.getByRole('tab',{name:'연결 및 실행 설정',exact:true});
  141 |  if(await settings.getAttribute('aria-selected')!=='true')await settings.click();
  142 |  for(const name of ['연결 및 실행 준비','실행 설정']){
  143 |   const panel=page.getByRole('button',{name,exact:true});if(await panel.getAttribute('aria-expanded')==='false')await panel.click();
  144 |  }
  145 | }
  146 | async function launch(page:any,scenario='pass',speed='5'){
  147 |  await openSettings(page);
  148 |  await page.getByLabel('데모 시나리오',{exact:true}).selectOption(scenario);
  149 |  await page.getByLabel('데모 속도',{exact:true}).selectOption(speed);
  150 |  await page.getByRole('tab',{name:'결과',exact:true}).click();
  151 |  await page.getByRole('button',{name:'Preflight 검사',exact:true}).click();
  152 |  await expect(page.getByRole('status').filter({hasText:'Preflight 통과'})).toBeVisible();
  153 |  await page.getByRole('button',{name:'▶ 테스트 시작',exact:true}).click();
  154 | }
  155 | async function control(page:any,name:string,action:string){
  156 |  // Worker transitions can invalidate a polled version before a user clicks.
  157 |  // Only retry a rejected version, after a fresh snapshot; keep all server gates.
  158 |  for(let attempt=0;attempt<3;attempt++){
  159 |   const pending=page.waitForResponse((r:any)=>r.request().method()==='POST'&&r.url().endsWith('/actions/'+action));
  160 |   await page.getByRole('button',{name,exact:true}).click();
  161 |   const response=await pending;
  162 |   if(response.status()===200)return;
  163 |   expect(response.status()).toBe(409);expect((await response.json()).code).toBe('VERSION_CONFLICT');
  164 |   const runUrl=response.url().replace('/actions/'+action,'');
  165 |   await page.waitForResponse((r:any)=>r.request().method()==='GET'&&r.url()===runUrl&&r.status()===200);
  166 |  }
  167 |  throw Error('Control action repeatedly rejected a stale version: '+action);
  168 | }
  169 | 
  170 | test('GUI-UI-01 TC filters, suites, profiles, Single/Dual, report downloads',async({page})=>{
  171 |  const errors:string[]=[];page.on('pageerror',e=>errors.push(e.message));
  172 |  await openTest(page);
  173 |  await page.getByLabel('TC 검색',{exact:true}).fill('pair');
  174 |  await expect(page.getByLabel('선택 04_pair')).toBeChecked();
  175 |  await page.getByLabel('TC 검색',{exact:true}).fill('');
  176 |  await expect(page.getByLabel('선택 01_boot')).toBeChecked();
  177 |  await openSettings(page);
  178 |  const suitePanel=page.getByRole('button',{name:'Suite 관리',exact:true});if(await suitePanel.getAttribute('aria-expanded')==='false')await suitePanel.click();
  179 |  await page.getByLabel('Suite 이름').fill('Browser suite');
  180 |  await page.getByRole('button',{name:'Suite 저장 / 수정',exact:true}).click();
  181 |  await expect(page.getByRole('status')).toContainText('Suite를 저장');
  182 |  await openSettings(page);
  183 |  await page.getByRole('button',{name:'프로파일 저장',exact:true}).click();
  184 |  await expect(page.getByRole('status')).toContainText('연결 프로파일 저장');
  185 |  await launch(page);
  186 |  await expect(page.getByTestId('run-state')).toHaveText('COMPLETED · PASS',{timeout:20000});
  187 |  await page.getByRole('tab',{name:'결과 리포트',exact:true}).click();
  188 |  const waiting=page.waitForEvent('download');await page.getByRole('link',{name:'JSON 다운로드',exact:true}).click();
  189 |  const download=await waiting;const report=JSON.parse(readFileSync((await download.path())!,'utf8'));
  190 |  expect(report.overall_result).toBe('PASS');expect(report.attempts).toHaveLength(5);
  191 |  const pair=report.attempts.find((a:any)=>a.tc_id.includes('dual'));
  192 |  expect(pair.resolved_command_argv.slice(-2)).toEqual(['COM3','COM4']);
  193 |  await page.screenshot({path:'../../.local-reports/gui-test/'+(standalone?'standalone':'dashboard')+'-desktop.png',fullPage:true});
  194 |  await page.setViewportSize({width:680,height:1000});
  195 |  await page.screenshot({path:'../../.local-reports/gui-test/'+(standalone?'standalone':'dashboard')+'-narrow.png',fullPage:true});
  196 |  expect(errors).toEqual([]);
  197 | });
  198 | 
  199 | test('GUI-UI-02 disconnect, reload, explicit recovery and new attempt',async({page})=>{
  200 |  await openTest(page);await launch(page,'disconnect');
  201 |  await expect(page.getByTestId('run-state')).toContainText('PAUSED',{timeout:20000});
  202 |  await page.reload();if(!standalone)await page.getByRole('navigation').getByRole('button',{name:'Test 현황',exact:true}).click();
  203 |  await expect(page.getByTestId('run-state')).toContainText('PAUSED');
  204 |  await expect(page.getByRole('button',{name:'▶ 재개',exact:true})).toBeDisabled();
  205 |  await page.getByRole('button',{name:'데모 연결 / 종료 확인',exact:true}).click();
  206 |  await page.getByRole('button',{name:'▶ 재개',exact:true}).click();
  207 |  await expect(page.getByTestId('run-state')).toHaveText('COMPLETED · PASS',{timeout:20000});
  208 |  await page.locator('.gt-log-fold>summary').click();
  209 |  await expect(page.locator('.gt-logs')).toBeVisible();
  210 |  await expect(page.locator('.gt-logs')).toContainText('Attempt 2');
  211 | });
  212 | 
  213 | test('GUI-UI-03 pause/cancel and observer control transfer',async({page,context})=>{
  214 |  await openTest(page);await launch(page,'pass','0.2');
  215 |  await expect(page.getByTestId('run-state')).toContainText('RUNNING');
  216 |  const observer=await context.newPage();await openTest(observer);
> 217 |  await expect(observer.getByText('관찰 모드',{exact:false})).toBeVisible();
      |                                                          ^ Error: expect(locator).toBeVisible() failed
  218 |  await control(observer,'제어권 요청','request-control');
  219 |  await expect(page.getByRole('button',{name:'제어권 이전 승인',exact:true})).toBeVisible();
  220 |  await control(page,'제어권 이전 승인','grant-control');
  221 |  await expect(observer.getByRole('button',{name:'Ⅱ 일시 정지',exact:true})).toBeEnabled();
  222 |  await control(observer,'Ⅱ 일시 정지','pause');
  223 |  await expect(observer.getByTestId('run-state')).toContainText('PAUSED',{timeout:20000});
  224 |  await control(observer,'■ 테스트 중단','cancel');
  225 |  await expect(observer.getByTestId('run-state')).toHaveText('CANCELLED · INCOMPLETE');
  226 |  await observer.close();
  227 | });
  228 | 
  229 | test('GUI-UI-04 FAIL continues and isolated Dashboard synchronization',async({page})=>{
  230 |  await openTest(page);
  231 |  if(!standalone){await openSettings(page);await page.getByRole('button',{name:'격리 데모 Job 준비',exact:true}).click();await expect(page.getByLabel('GUI Test Job')).not.toHaveValue('');}
  232 |  await launch(page,'fail');
  233 |  await expect(page.getByTestId('run-state')).toHaveText('COMPLETED · FAIL',{timeout:20000});
  234 |  await expect(page.getByLabel('TC 판정 진행률')).toHaveAttribute('value','5');
  235 |  if(!standalone){await page.getByRole('tab',{name:'결과 리포트',exact:true}).click();await expect(page.getByRole('heading',{name:'판정 FAIL · 동기화 SUCCEEDED'})).toBeVisible();
  236 |   const jobId=await page.getByLabel('GUI Test Job').inputValue();const j=await (await page.request.get('/api/v1/gui-test/demo/jobs/'+jobId)).json();
  237 |   expect(j.modules.map((m:any)=>m.stages.device_test.status)).toEqual(['FAILED','SUCCEEDED']);}
  238 | });
  239 | 
  240 | test('GUI-UI-05 catalog drag invalidates Preflight and preserves completed Run',async({page})=>{
  241 |  await openTest(page);
  242 |  await expect(page.getByRole('button',{name:/(위로|아래로) 이동$/})).toHaveCount(0);
  243 |  const names=page.getByLabel('TC 실행 순서').locator('li');
  244 |  const original=await names.allTextContents();
  245 |  await page.getByRole('button',{name:'Preflight 검사',exact:true}).click();
  246 |  const start=page.getByRole('button',{name:'▶ 테스트 시작',exact:true});await expect(start).toBeEnabled();
  247 |  const last=page.locator('.gt-tree-case').filter({hasText:'04_pair'}),first=page.locator('.gt-tree-case').filter({hasText:'01_boot'});
  248 |  await last.locator('.gt-drag-handle').dragTo(first,{targetPosition:{x:40,y:6}});
  249 |  await expect(names).toHaveText(['04_pair',...original.slice(0,-1)]);await expect(start).toBeDisabled();
  250 |  const bottom=page.locator('.gt-tree-case').filter({hasText:'03_link'});
  251 |  await bottom.scrollIntoViewIfNeeded();const bounds=await bottom.boundingBox();
  252 |  expect(bounds!.y+bounds!.height).toBeLessThanOrEqual(page.viewportSize()!.height);
  253 |  // Move through the native drag threshold and across the target before releasing.
  254 |  // Scroll the full target into view before measuring; a lower-half drop can otherwise be outside the viewport.
  255 |  const handleBounds=await last.locator('.gt-drag-handle').boundingBox();
  256 |  await page.mouse.move(handleBounds!.x+handleBounds!.width/2,handleBounds!.y+handleBounds!.height/2);
  257 |  await page.mouse.down();
  258 |  await page.mouse.move(handleBounds!.x+handleBounds!.width/2+12,handleBounds!.y+handleBounds!.height/2,{steps:4});
  259 |  await page.mouse.move(bounds!.x+40,bounds!.y+bounds!.height*0.6,{steps:8});
  260 |  await page.mouse.move(bounds!.x+40,bounds!.y+bounds!.height*0.75,{steps:2});
  261 |  await page.mouse.up();
  262 |  await expect(names).toHaveText(original);
  263 |  await expect(page.getByLabel(/실행 위치/)).toHaveCount(0);
  264 |  await launch(page);await expect(page.getByTestId('run-state')).toHaveText('COMPLETED · PASS',{timeout:20000});
  265 |  const id=await page.getByLabel('Run 이력').inputValue();
  266 |  const snapshot=await (await page.request.get('/api/v1/gui-test/runs/'+id)).json();expect(snapshot.tests.map((t:any)=>t.name)).toEqual(original);
  267 |  await last.locator('.gt-drag-handle').dragTo(first,{targetPosition:{x:40,y:6}});
  268 |  const after=await (await page.request.get('/api/v1/gui-test/runs/'+id)).json();expect(after.tests).toEqual(snapshot.tests);
  269 | });
  270 | 
  271 | test('GUI-UI-06 nested search sort and settings persistence',async({page})=>{
  272 |  await openTest(page);
  273 |  const network=page.locator('.gt-case-group').filter({has:page.getByRole('button',{name:'network 폴더 목록',exact:true})}).first();
  274 |  await expect(network.getByRole('button',{name:'network/dual 폴더 목록',exact:true})).toBeVisible();
  275 |  const order=await page.getByLabel('TC 실행 순서').locator('li').allTextContents();
  276 |  await page.getByRole('button',{name:'이름 정렬',exact:true}).click();
  277 |  await page.getByRole('button',{name:'이름 정렬',exact:true}).click();
  278 |  const boot=page.locator('.gt-case-group').filter({has:page.getByRole('button',{name:'boot 폴더 목록',exact:true})});
  279 |  await expect(boot.locator('.gt-tc-name')).toHaveText(['02_smoke','01_boot']);
  280 |  await page.getByRole('button',{name:'트리 모두 접기',exact:true}).click();
  281 |  await page.getByLabel('TC 검색',{exact:true}).fill('network/dual');await expect(page.getByLabel('선택 04_pair')).toBeVisible();
  282 |  await page.getByLabel('폴더 network', {exact:true}).uncheck();
  283 |  await page.getByLabel('TC 검색',{exact:true}).fill('');await expect(page.getByLabel('선택 03_link')).toBeChecked();
  284 |  await page.getByLabel('선택 04_pair').check();
  285 |  await expect(page.getByLabel('TC 실행 순서').locator('li')).toHaveText(order);
  286 |  await openSettings(page);
  287 |  const suitePanel=page.getByRole('button',{name:'Suite 관리',exact:true});if(await suitePanel.getAttribute('aria-expanded')==='false')await suitePanel.click();
  288 |  await page.getByLabel('Suite 이름').fill('Preserved input');
  289 |  await page.getByRole('button',{name:'설정 모두 접기',exact:true}).click();
  290 |  await expect(page.getByLabel('Suite 이름')).toBeHidden();await expect(page.getByLabel('선택 01_boot')).toBeVisible();
  291 |  await page.getByRole('button',{name:'설정 모두 펼치기',exact:true}).click();await expect(page.getByLabel('Suite 이름')).toHaveValue('Preserved input');
  292 |  await page.getByRole('button',{name:'설정 모두 접기',exact:true}).click();await page.reload();
  293 |  if(!standalone)await page.getByRole('navigation').getByRole('button',{name:'Test 현황',exact:true}).click();
  294 |  await page.getByRole('tab',{name:'연결 및 실행 설정',exact:true}).click();
  295 |  await expect(page.getByRole('button',{name:'연결 및 실행 준비',exact:true})).toHaveAttribute('aria-expanded','false');
  296 |  await page.setViewportSize({width:375,height:900});
  297 |  await expect(page.getByLabel('TC 검색',{exact:true})).toBeVisible();
  298 |  expect(await page.evaluate(()=>document.documentElement.scrollWidth)).toBeLessThanOrEqual(375);
  299 | });
  300 | 
  301 | test('GUI-UI-07 failed TC only rerun retains original and displays usage',async({page})=>{
  302 |  await openTest(page);await launch(page,'fail');await expect(page.getByTestId('run-state')).toHaveText('COMPLETED · FAIL',{timeout:20000});
  303 |  const id=await page.getByLabel('Run 이력').inputValue();
  304 |  const original=await (await page.request.get('/api/v1/gui-test/runs/'+id)).json();
  305 |  const failed=original.tests.find((t:any)=>original.results[t.id]==='FAIL');
  306 |  const retry=page.getByRole('button',{name:failed.name+' 재실행',exact:true});
  307 |  await expect(retry).toHaveText('Retry');await expect(retry.locator('..')).toContainText('FAIL');
  308 |  await expect(page.getByRole('columnheader',{name:'재실행',exact:true})).toHaveCount(0);
  309 |  await retry.click();
  310 |  await expect(page.getByLabel('Run 이력')).not.toHaveValue(id);await expect(page.getByTestId('run-state')).toHaveText('COMPLETED · PASS',{timeout:20000});
  311 |  const childId=await page.getByLabel('Run 이력').inputValue();
  312 |  const child=await (await page.request.get('/api/v1/gui-test/runs/'+childId)).json();
  313 |  expect(child.parent_run_id).toBe(id);expect(child.tests.map((t:any)=>t.id)).toEqual([failed.id]);expect(child.link).toBeNull();
  314 |  const after=await (await page.request.get('/api/v1/gui-test/runs/'+id)).json();expect(after.results).toEqual(original.results);expect(after.attempts).toEqual(original.attempts);
  315 |  await expect(page.getByLabel('진행 요약',{exact:true})).toContainText('모델 호출 없음');
  316 |  const usage=page.locator('.gt-usage').first();await expect(usage).not.toHaveAttribute('open','');
  317 |  await usage.locator('summary').click();await expect(usage).toContainText('모델 호출 없음');
```