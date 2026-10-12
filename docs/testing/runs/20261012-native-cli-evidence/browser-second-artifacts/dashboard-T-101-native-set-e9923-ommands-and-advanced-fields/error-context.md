# Instructions

- Following Playwright test failed.
- Explain why, be concise, respect Playwright best practices.
- Provide a snippet of code with the fix, if possible.

# Test info

- Name: dashboard.spec.ts >> T-101 native setup has no bridge requirement and persists commands and advanced fields
- Location: ../../tests/e2e/dashboard.spec.ts:139:5

# Error details

```
Error: expect(locator).toHaveValue(expected) failed

Locator: getByLabel('빌드 명령', { exact: true })
Expected: "./build.sh"
Timeout: 5000ms
Error: element(s) not found

Call log:
  - Expect "toHaveValue" getByLabel('빌드 명령', { exact: true }) with timeout 5000ms
  - waiting for getByLabel('빌드 명령', { exact: true })

```

```yaml
- complementary:
  - img
  - text: BSP UPGRADE ENGINEERING WORKSPACE WORKSPACE
  - navigation:
    - button "대시보드":
      - img
      - text: 대시보드
    - button "사람 검토 · Jira":
      - img
      - text: 사람 검토 · Jira
    - button "실행 기록":
      - img
      - text: 실행 기록
    - button "환경 설정":
      - img
      - text: 환경 설정
  - img
  - text: 실행 관리자 API 연결됨
- main:
  - text: 프로젝트
  - img
  - text: BSP OS Upgrade 수동 장비 테스트 U UPGRADE CONTROL ROOM
  - heading "환경 설정" [level=1]
  - paragraph: 실행 환경을 저장하고, 설정 파일로 내보내거나 가져올 수 있습니다.
  - button "환경 설정":
    - img
    - text: 환경 설정
  - button "새 업그레이드":
    - img
    - text: 새 업그레이드
  - text: 설정 v4 · 새 작업부터 적용
  - button "설정 파일 내보내기":
    - img
    - text: 설정 파일 내보내기
  - img
  - text: 파일 가져오기
  - heading "실행 환경" [level=2]:
    - img
    - text: 실행 환경
  - paragraph: 실행 관리자는 Linux에서 운영하고 Windows에서는 SSH 터널로 같은 화면에 접속합니다. 호스트·계정은 접속 참고 정보이며 여기서 SSH를 자동 연결하지 않습니다.
  - text: 실행 방식
  - combobox "실행 방식":
    - option "모의 실행 · 실제 서버 변경 없음" [selected]
    - option "실제 Linux 도구 실행"
  - text: Linux 호스트
  - textbox "Linux 호스트":
    - /placeholder: "예: bsp-build.internal"
    - text: test-build.internal
  - text: SSH 계정
  - textbox "SSH 계정":
    - /placeholder: "예: developer"
  - text: 프로젝트 작업 폴더
  - textbox "프로젝트 작업 폴더":
    - /placeholder: /workspace/bsp
    - text: /srv/bsp/work
  - text: 소스 기준 (선택)
  - textbox "소스 기준 (선택)":
    - /placeholder: 비워 두면 신규 OS 원본의 Git 커밋 자동 기록
  - text: 기존 원본 경로
  - textbox "기존 원본 경로":
    - /placeholder: /sources/old
  - text: 벤더 수정본 경로
  - textbox "벤더 수정본 경로":
    - /placeholder: /sources/vendor
  - text: 신규 OS 원본 경로
  - textbox "신규 OS 원본 경로":
    - /placeholder: /sources/new
  - paragraph: 소스 기준은 빌드·리뷰·시험 결과를 같은 버전에 연결하기 위한 기록입니다. 비워 두면 새 작업 시작 시 신규 OS 원본의 Git 커밋을 자동으로 읽습니다. Git을 사용하지 않는 고정 소스 묶음만 해시를 직접 지정하세요. 모의 실행은 자동으로 시연용 기준을 사용합니다.
  - heading "에이전트 · 빌드 연결" [level=2]:
    - img
    - text: 에이전트 · 빌드 연결
  - paragraph: 작업 폴더에서 설치된 도구를 자동으로 찾고 실행합니다. 별도 bridges 폴더나 연결 스크립트는 필요하지 않습니다. 같은 Linux 계정의 PATH와 기존 로그인을 사용합니다.
  - text: 도구 연결 방식
  - combobox "도구 연결 방식":
    - option "내장 연결 · 설치된 CLI 자동 탐지 (기본)" [selected]
    - option "기존 JSON 브리지 · 고급 호환 설정"
  - text: 에이전트 지침 폴더 (선택)
  - textbox "에이전트 지침 폴더 (선택)":
    - /placeholder: 비워 두면 프로젝트 작업 폴더
    - text: /srv/bsp/agents
  - text: 빌드 환경 초기화 파일 (선택)
  - textbox "빌드 환경 초기화 파일 (선택)":
    - /placeholder: "예: /srv/bsp/env.sh"
  - text: 빌드 명령
  - textbox "빌드 명령":
    - /placeholder: "예: ./build.sh"
    - text: ./build.sh
  - text: 산출물 파일 경로
  - textbox "산출물 파일 경로":
    - /placeholder: "예: out/firmware.img"
    - text: out/firmware.img
  - text: 검증 명령
  - textbox "검증 명령":
    - /placeholder: "예: ./verify.sh"
    - text: ./verify.sh
  - text: 최종 통합 · 회귀 명령
  - textbox "최종 통합 · 회귀 명령":
    - /placeholder: "예: ./integration-test.sh"
    - text: ./integration.sh
  - paragraph: 기존 AGENTS.md·CLAUDE.md와 roles/단계명.md를 읽습니다. 빌드·검증 명령은 작업 폴더에서 실행하며 실제 프로젝트의 명령을 한 번 등록합니다. 환경 점검에서는 모델이나 빌드를 실행하지 않습니다.
  - group: 고급 설정 · 도구 경로와 역할 지침
  - text: 분석 동시 실행 수
  - spinbutton "분석 동시 실행 수": "3"
  - text: 실행 제한 시간 (초)
  - spinbutton "실행 제한 시간 (초)": "900"
  - heading "모듈 목록 · 선행 그룹" [level=2]:
    - img
    - text: 모듈 목록 · 선행 그룹
  - paragraph: 새 작업의 초기 목록입니다. 최초 분석 후 계획 확인을 거칩니다.
  - textbox "모듈 1 이름": Bootloader
  - combobox "모듈 1 그룹":
    - option "부트로더 선행 그룹" [selected]
    - option "나머지 그룹"
  - button "모듈 1 삭제":
    - img
  - textbox "모듈 2 이름": Kernel / BSP
  - combobox "모듈 2 그룹":
    - option "부트로더 선행 그룹" [selected]
    - option "나머지 그룹"
  - button "모듈 2 삭제":
    - img
  - textbox "모듈 3 이름": Ethernet
  - combobox "모듈 3 그룹":
    - option "부트로더 선행 그룹"
    - option "나머지 그룹" [selected]
  - button "모듈 3 삭제":
    - img
  - textbox "모듈 4 이름": Display
  - combobox "모듈 4 그룹":
    - option "부트로더 선행 그룹"
    - option "나머지 그룹" [selected]
  - button "모듈 4 삭제":
    - img
  - textbox "모듈 5 이름": Camera
  - combobox "모듈 5 그룹":
    - option "부트로더 선행 그룹"
    - option "나머지 그룹" [selected]
  - button "모듈 5 삭제":
    - img
  - button "모듈 추가":
    - img
    - text: 모듈 추가
  - heading "사내 Jira 연결" [level=2]:
    - img
    - text: 사내 Jira 연결
  - text: 연결 방식
  - combobox "연결 방식":
    - option "직접 연결" [selected]
    - option "Claude MCP 등록 프로필"
  - text: Jira 주소
  - textbox "Jira 주소"
  - text: 프로젝트 키
  - textbox "프로젝트 키"
  - text: 토큰을 읽을 서버 환경변수 이름
  - textbox "토큰을 읽을 서버 환경변수 이름": BSP_JIRA_TOKEN
  - text: Claude MCP 등록 이름
  - textbox "Claude MCP 등록 이름"
  - text: Jira REST API 버전
  - combobox "Jira REST API 버전":
    - option "2" [selected]
    - option "3"
  - text: Claude MCP 조회/연결 브리지 실행 배열
  - textbox "Claude MCP 조회/연결 브리지 실행 배열": "[]"
  - text: Jira 이슈 유형
  - textbox "Jira 이슈 유형": Task
  - paragraph: 비밀번호·토큰 값은 서버 환경변수로 관리합니다. 실제 Linux 실행에서 새 판단이 생기면 Jira 연결을 시도합니다. 모의 실행은 티켓을 만들지 않습니다.
  - button "읽기 연결 확인"
  - button "저장 후 환경 점검":
    - img
    - text: 저장 후 환경 점검
  - button "설정 저장":
    - img
    - text: 설정 저장
  - text: BSP UPGRADE · 상태는 서버 기록을 기준으로 표시됩니다. v0.1 · LOCAL BUILD
```

# Test source

```ts
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
  114 |   await expect(page.getByLabel('codex 실행 배열',{exact:true})).toHaveValue('["/srv/new bsp/.bsp-dashboard/bridges/codex"]');
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
> 159 |   await expect(page.getByLabel('빌드 명령',{exact:true})).toHaveValue('./build.sh');
      |                                                       ^ Error: expect(locator).toHaveValue(expected) failed
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