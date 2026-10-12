# Instructions

- Following Playwright test failed.
- Explain why, be concise, respect Playwright best practices.
- Provide a snippet of code with the fix, if possible.

# Test info

- Name: dashboard.spec.ts >> T-95 source auto mode and bridge defaults preserve custom settings
- Location: ../../tests/e2e/dashboard.spec.ts:106:5

# Error details

```
Error: expect(locator).toHaveValue(expected) failed

Locator:  getByLabel('codex 실행 배열', { exact: true })
Expected: "[\"/srv/new bsp/.bsp-dashboard/bridges/codex\"]"
Received: "[\"/workspace/bsp-upgrade/.bsp-dashboard/bridges/codex\"]"
Timeout:  5000ms

Call log:
  - Expect "toHaveValue" getByLabel('codex 실행 배열', { exact: true }) with timeout 5000ms
  - waiting for getByLabel('codex 실행 배열', { exact: true })
    - locator resolved to <input value="[]" aria-invalid="false"/>
    - unexpected value "[]"
    13 × locator resolved to <input aria-invalid="false" value="["/workspace/bsp-upgrade/.bsp-dashboard/bridges/codex"]"/>
       - unexpected value "["/workspace/bsp-upgrade/.bsp-dashboard/bridges/codex"]"

```

```yaml
- textbox "codex 실행 배열": "[\"/workspace/bsp-upgrade/.bsp-dashboard/bridges/codex\"]"
```

# Test source

```ts
  14  | test('T-39 T-70 direct entry, settings persistence, JSON export, narrow navigation',async({page})=>{
  15  |  expect(await (await page.request.get('/api/v1/jobs')).json()).toEqual([]);
  16  |  expect(await page.context().cookies()).toEqual([]);
  17  |  await page.getByRole('navigation').getByRole('button',{name:'환경 설정',exact:true}).click();
  18  |  await page.getByLabel('Linux 호스트',{exact:true}).fill('test-build.internal');
  19  |  await page.getByRole('button',{name:'설정 저장',exact:true}).click();
  20  |  await expect(page.getByRole('status')).toContainText('설정을 저장');
  21  |  const download=page.waitForEvent('download');
  22  |  await page.getByRole('button',{name:'설정 파일 내보내기'}).click();
  23  |  const file=await download;const filePath=await file.path();
  24  |  expect(JSON.parse(readFileSync(filePath!,'utf8')).host).toBe('test-build.internal');
  25  |  await page.reload();
  26  |  await expect(page.getByLabel('접속 키',{exact:true})).toHaveCount(0);
  27  |  await page.getByRole('navigation').getByRole('button',{name:'환경 설정',exact:true}).click();
  28  |  await expect(page.getByLabel('Linux 호스트',{exact:true})).toHaveValue('test-build.internal');
  29  |  await page.setViewportSize({width:640,height:900});
  30  |  await expect(page.getByRole('navigation').getByRole('button',{name:'대시보드',exact:true})).toBeVisible();
  31  |  await page.getByRole('navigation').getByRole('button',{name:'대시보드',exact:true}).click();
  32  |  await expect(page.getByRole('heading',{name:'OS 업그레이드 대시보드',exact:true})).toBeVisible();
  33  | });
  34  | 
  35  | test('T-59 start, approval, boot gate, failed manual test and retry',async({page})=>{
  36  |  const errors:string[]=[];page.on('pageerror',e=>errors.push(e.message));
  37  |  await page.getByRole('button',{name:'새 업그레이드',exact:true}).click();
  38  |  await page.getByLabel('작업 이름',{exact:true}).fill('자동 검증 · 수동 시험 회귀');
  39  |  await page.getByRole('button',{name:'분석 시작',exact:true}).click();
  40  |  await expect(page.getByRole('button',{name:'계획 검토 · 확인',exact:true})).toBeVisible({timeout:20000});
  41  |  await expect(page.locator('.progress-card').first()).toContainText('100%');
  42  |  await expect(page.getByRole('row').filter({has:page.getByRole('button',{name:/Ethernet 나머지 그룹/})})).toContainText('선행 대기');
  43  |  await page.getByRole('button',{name:'계획 검토 · 확인',exact:true}).click();
  44  |  await page.getByRole('button',{name:'이 계획으로 진행',exact:true}).click();
  45  |  await expect(page.getByRole('button',{name:/Bootloader 선행 그룹 · 장비 테스트/})).toBeVisible({timeout:20000});
  46  |  await page.getByRole('button',{name:/Bootloader 선행 그룹 · 장비 테스트/}).press('Enter');
  47  |  await expect(page.getByRole('button',{name:/Bootloader 선행 그룹/})).toHaveAttribute('aria-expanded','true');
  48  |  await expect(page.getByRole('row').filter({has:page.getByRole('button',{name:/Ethernet 나머지 그룹/})})).toContainText('선행 대기');
  49  |  await page.getByRole('button',{name:'결과 등록',exact:true}).click();
  50  |  let dialog=page.getByRole('dialog');
  51  |  await dialog.getByRole('button',{name:'결과 등록',exact:true}).click();
  52  |  await expect(dialog).toBeVisible();
  53  |  await expect(dialog.getByLabel('보드 ID (선택)',{exact:true})).not.toBeVisible();
  54  |  await dialog.getByLabel('boot 결과',{exact:true}).selectOption('FAIL');
  55  |  await dialog.getByLabel('functional 결과',{exact:true}).selectOption('PASS');
  56  |  await dialog.getByRole('button',{name:'결과 등록',exact:true}).click();
  57  |  await expect(page.getByRole('dialog')).toHaveCount(0);
  58  |  await expect(page.getByRole('button',{name:'재시도',exact:true})).toBeVisible();
  59  |  await page.getByRole('button',{name:'재시도',exact:true}).click();
  60  |  await expect(page.getByRole('button',{name:'결과 등록',exact:true})).toBeVisible({timeout:10000});
  61  |  await page.getByRole('button',{name:'결과 등록',exact:true}).click();
  62  |  dialog=page.getByRole('dialog');
  63  |  await dialog.getByLabel('boot 결과',{exact:true}).selectOption('PASS');
  64  |  await dialog.getByLabel('functional 결과',{exact:true}).selectOption('PASS');
  65  |  await dialog.getByRole('button',{name:'결과 등록',exact:true}).click();
  66  |  await expect(page.getByRole('button',{name:/Bootloader 선행 그룹 · 전체 완료/})).toBeVisible();
  67  |  await expect(page.getByRole('row').filter({has:page.getByRole('button',{name:/Ethernet 나머지 그룹/})})).toContainText('선행 대기');
  68  |  await page.getByRole('button',{name:/Bootloader 선행 그룹/}).click();
  69  |  await page.getByRole('textbox',{name:'작업 명령',exact:true}).fill('왜 Ethernet이 기다리는지 알려줘');
  70  |  await page.getByRole('button',{name:'요청 보내기',exact:true}).click();
  71  |  await expect(page.locator('.prompt-history')).toContainText('모의 응답',{timeout:15000});
  72  |  expect(errors).toEqual([]);
  73  |  mkdirSync(path.join(root,'.local-reports'),{recursive:true});
  74  |  await page.screenshot({path:path.join(root,'.local-reports/dashboard-desktop.png'),fullPage:true});
  75  |  await page.setViewportSize({width:640,height:1000});
  76  |  await expect(page.getByRole('navigation').getByRole('button',{name:'환경 설정',exact:true})).toBeVisible();
  77  |  await page.screenshot({path:path.join(root,'.local-reports/dashboard-narrow.png'),fullPage:true});
  78  | });
  79  | 
  80  | 
  81  | test('T-67 demo-only boot completion unlocks the remaining group',async({page})=>{
  82  |  await page.getByRole('button',{name:'새 업그레이드',exact:true}).click();
  83  |  await page.getByLabel('작업 이름',{exact:true}).fill('자동 검증 · 데모 선행 수동 완료');
  84  |  await page.getByRole('button',{name:'분석 시작',exact:true}).click();
  85  |  await expect(page.getByRole('button',{name:'계획 검토 · 확인',exact:true})).toBeVisible({timeout:20000});
  86  |  await page.getByRole('button',{name:/Bootloader 선행 그룹/}).click();
  87  |  await expect(page.getByRole('button',{name:'데모에서 이 모듈 완료',exact:true})).toBeDisabled();
  88  |  await page.getByRole('button',{name:'계획 검토 · 확인',exact:true}).click();
  89  |  await page.getByRole('button',{name:'이 계획으로 진행',exact:true}).click();
  90  |  await page.getByRole('button',{name:'데모에서 이 모듈 완료',exact:true}).click();
  91  |  await expect(page.getByRole('button',{name:/Bootloader 선행 그룹 · 전체 완료/})).toBeVisible();
  92  |  await expect(page.getByRole('row').filter({has:page.getByRole('button',{name:/Ethernet 나머지 그룹/})})).toContainText('선행 대기');
  93  |  await page.getByRole('button',{name:/Kernel \/ BSP 선행 그룹/}).click();
  94  |  await page.getByRole('button',{name:'데모에서 이 모듈 완료',exact:true}).click();
  95  |  await expect(page.locator('.table-footer')).toContainText('선행 그룹 완료');
  96  |  await expect(page.getByRole('button',{name:/Kernel \/ BSP 선행 그룹 · 전체 완료/})).toBeVisible();
  97  |  await page.reload();
  98  |  await expect(page.locator('.table-footer')).toContainText('선행 그룹 완료');
  99  |  await page.getByRole('button',{name:/Bootloader 선행 그룹/}).click();
  100 |  await expect(page.locator('.stage-details').first()).toContainText('데모 수동 완료');
  101 |  await page.getByRole('button',{name:/Ethernet 나머지 그룹/}).click();
  102 |  await expect(page.getByRole('button',{name:'데모에서 이 모듈 완료',exact:true})).toHaveCount(0);
  103 |  await expect(page.getByRole('button',{name:'최종 검토 기록',exact:true})).toBeDisabled();
  104 | });
  105 | 
  106 | test('T-95 source auto mode and bridge defaults preserve custom settings',async({page})=>{
  107 |  const original=await (await page.request.get('/api/v1/config')).json();
  108 |  try{
  109 |   await page.getByRole('navigation').getByRole('button',{name:'환경 설정',exact:true}).click();
  110 |   await expect(page.getByLabel('소스 기준 (선택)',{exact:true})).toHaveValue('');
  111 |   await page.getByLabel('도구 연결 방식',{exact:true}).selectOption('bridge');
  112 |   await page.getByRole('button',{name:'빈 항목에 기본 경로 넣기',exact:true}).click();
  113 |   await page.getByLabel('프로젝트 작업 폴더',{exact:true}).fill('/srv/new bsp');
> 114 |   await expect(page.getByLabel('codex 실행 배열',{exact:true})).toHaveValue('["/srv/new bsp/.bsp-dashboard/bridges/codex"]');
      |                                                             ^ Error: expect(locator).toHaveValue(expected) failed
  115 |   await page.getByLabel('claude 실행 배열',{exact:true}).fill('["/custom/claude-bridge"]');
  116 |   await page.getByLabel('opencode 실행 배열',{exact:true}).fill('[]');
  117 |   await page.getByRole('button',{name:'빈 항목에 기본 경로 넣기',exact:true}).click();
  118 |   await expect(page.getByRole('status')).toContainText('기본 경로를 넣었습니다');
  119 |   await expect(page.getByLabel('claude 실행 배열',{exact:true})).toHaveValue('["/custom/claude-bridge"]');
  120 |   await expect(page.getByLabel('opencode 실행 배열',{exact:true})).toHaveValue('["/srv/new bsp/.bsp-dashboard/bridges/opencode"]');
  121 |   await page.getByRole('button',{name:'설정 저장',exact:true}).click();
  122 |   await expect(page.getByRole('status')).toContainText('설정을 저장');
  123 |   await page.reload();
  124 |   await page.getByRole('navigation').getByRole('button',{name:'환경 설정',exact:true}).click();
  125 |   await expect(page.getByLabel('소스 기준 (선택)',{exact:true})).toHaveValue('');
  126 |   await expect(page.getByLabel('claude 실행 배열',{exact:true})).toHaveValue('["/custom/claude-bridge"]');
  127 |   await page.getByRole('button',{name:'저장 후 환경 점검',exact:true}).click();
  128 |   await expect(page.locator('.probe-list')).toContainText('브리지 파일이 없습니다');
  129 |   await expect(page.locator('.probe-list')).not.toContainText('FILE_READY');
  130 |   await page.screenshot({path:path.join(root,'.local-reports/settings-defaults.png'),fullPage:true});
  131 |  }finally{
  132 |   const latest=await (await page.request.get('/api/v1/config')).json();
  133 |   const restored=await page.request.put('/api/v1/config',{headers:{'X-BSP-Client':'dashboard'},data:{version:latest.version,profile:original.profile}});
  134 |   expect(restored.ok()).toBe(true);
  135 |  }
  136 | });
  137 | 
  138 | 
  139 | test('T-101 native setup has no bridge requirement and persists commands and advanced fields',async({page})=>{
  140 |  const original=await (await page.request.get('/api/v1/config')).json();
  141 |  try{
  142 |   await page.getByRole('navigation').getByRole('button',{name:'환경 설정',exact:true}).click();
  143 |   await expect(page.getByLabel('도구 연결 방식',{exact:true})).toHaveValue('native');
  144 |   await expect(page.getByLabel('claude 실행 배열',{exact:true})).toHaveCount(0);
  145 |   await expect(page.getByRole('button',{name:'빈 항목에 기본 경로 넣기',exact:true})).toHaveCount(0);
  146 |   await page.getByLabel('프로젝트 작업 폴더',{exact:true}).fill('/srv/bsp/work');
  147 |   await page.getByLabel('에이전트 지침 폴더 (선택)',{exact:true}).fill('/srv/bsp/agents');
  148 |   await page.getByLabel('빌드 명령',{exact:true}).fill('./build.sh');
  149 |   await page.getByLabel('산출물 파일 경로',{exact:true}).fill('out/firmware.img');
  150 |   await page.getByLabel('검증 명령',{exact:true}).fill('./verify.sh');
  151 |   await page.getByLabel('최종 통합 · 회귀 명령',{exact:true}).fill('./integration.sh');
  152 |   await page.getByText('고급 설정 · 도구 경로와 역할 지침',{exact:true}).click();
  153 |   await page.getByLabel('codex 사용',{exact:true}).selectOption('disabled');
  154 |   await page.getByLabel('analysis 지침 파일 (선택)',{exact:true}).fill('roles/analysis-custom.md');
  155 |   await page.getByRole('button',{name:'설정 저장',exact:true}).click();
  156 |   await expect(page.getByRole('status')).toContainText('설정을 저장');
  157 |   await page.reload();
  158 |   await page.getByRole('navigation').getByRole('button',{name:'환경 설정',exact:true}).click();
  159 |   await expect(page.getByLabel('빌드 명령',{exact:true})).toHaveValue('./build.sh');
  160 |   await expect(page.getByLabel('도구 연결 방식',{exact:true})).toHaveValue('native');
  161 |   await page.getByText('고급 설정 · 도구 경로와 역할 지침',{exact:true}).click();
  162 |   await expect(page.getByLabel('codex 사용',{exact:true})).toHaveValue('disabled');
  163 |   const config=await (await page.request.get('/api/v1/config')).json();
  164 |   expect(config.profile.role_instructions.analysis).toBe('roles/analysis-custom.md');
  165 |   expect(config.profile.agents.claude).toEqual([]);
  166 |   await page.screenshot({path:path.join(root,'.local-reports/native-settings.png'),fullPage:true});
  167 |  }finally{
  168 |   const latest=await (await page.request.get('/api/v1/config')).json();
  169 |   expect((await page.request.put('/api/v1/config',{headers:{'X-BSP-Client':'dashboard'},data:{version:latest.version,profile:original.profile}})).ok()).toBe(true);
  170 |  }
  171 | });
  172 | 
```