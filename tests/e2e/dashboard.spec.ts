import { test, expect } from '../../apps/web/node_modules/@playwright/test';
import { readFileSync, mkdirSync, existsSync } from 'node:fs';
import path from 'node:path';
const root=path.resolve(process.cwd(),'../..');
const runtime=process.env.BSP_E2E_RUNTIME||path.join(root,'.local-reports/e2e-runtime');

test.beforeEach(async({page})=>{
 await page.goto('/');
 await expect(page.getByRole('heading',{name:'OS 업그레이드 대시보드',exact:true})).toBeVisible();
 await expect(page.getByLabel('접속 키',{exact:true})).toHaveCount(0);
 expect(existsSync(path.join(runtime,'access-token'))).toBe(false);
});

test('T-39 T-70 direct entry, settings persistence, JSON export, narrow navigation',async({page})=>{
 expect(await (await page.request.get('/api/v1/jobs')).json()).toEqual([]);
 expect(await page.context().cookies()).toEqual([]);
 await page.getByRole('navigation').getByRole('button',{name:'환경 설정',exact:true}).click();
 await page.getByLabel('Linux 호스트',{exact:true}).fill('test-build.internal');
 await page.getByRole('button',{name:'설정 저장',exact:true}).click();
 await expect(page.getByRole('status')).toContainText('설정을 저장');
 const download=page.waitForEvent('download');
 await page.getByRole('button',{name:'설정 파일 내보내기'}).click();
 const file=await download;const filePath=await file.path();
 expect(JSON.parse(readFileSync(filePath!,'utf8')).host).toBe('test-build.internal');
 await page.reload();
 await expect(page.getByLabel('접속 키',{exact:true})).toHaveCount(0);
 await page.getByRole('navigation').getByRole('button',{name:'환경 설정',exact:true}).click();
 await expect(page.getByLabel('Linux 호스트',{exact:true})).toHaveValue('test-build.internal');
 await page.setViewportSize({width:640,height:900});
 await expect(page.getByRole('navigation').getByRole('button',{name:'대시보드',exact:true})).toBeVisible();
 await page.getByRole('navigation').getByRole('button',{name:'대시보드',exact:true}).click();
 await expect(page.getByRole('heading',{name:'OS 업그레이드 대시보드',exact:true})).toBeVisible();
});

test('T-59 start, approval, boot gate, failed manual test and retry',async({page})=>{
 const errors:string[]=[];page.on('pageerror',e=>errors.push(e.message));
 await page.getByRole('button',{name:'새 업그레이드',exact:true}).click();
 await page.getByLabel('작업 이름',{exact:true}).fill('자동 검증 · 수동 시험 회귀');
 await page.getByRole('button',{name:'분석 시작',exact:true}).click();
 await expect(page.getByRole('button',{name:'계획 검토 · 확인',exact:true})).toBeVisible({timeout:20000});
 await expect(page.locator('.progress-card').first()).toContainText('100%');
 await expect(page.getByRole('row').filter({has:page.getByRole('button',{name:/Ethernet 나머지 그룹/})})).toContainText('선행 대기');
 await page.getByRole('button',{name:'계획 검토 · 확인',exact:true}).click();
 await page.getByRole('button',{name:'이 계획으로 진행',exact:true}).click();
 await expect(page.getByRole('button',{name:/Bootloader 선행 그룹 · 장비 테스트/})).toBeVisible({timeout:20000});
 await page.getByRole('button',{name:/Bootloader 선행 그룹 · 장비 테스트/}).press('Enter');
 await expect(page.getByRole('button',{name:/Bootloader 선행 그룹/})).toHaveAttribute('aria-expanded','true');
 await expect(page.getByRole('row').filter({has:page.getByRole('button',{name:/Ethernet 나머지 그룹/})})).toContainText('선행 대기');
 await page.getByRole('button',{name:'결과 등록',exact:true}).click();
 let dialog=page.getByRole('dialog');
 await dialog.getByRole('button',{name:'결과 등록',exact:true}).click();
 await expect(dialog).toBeVisible();
 await expect(dialog.getByLabel('보드 ID (선택)',{exact:true})).not.toBeVisible();
 await dialog.getByLabel('boot 결과',{exact:true}).selectOption('FAIL');
 await dialog.getByLabel('functional 결과',{exact:true}).selectOption('PASS');
 await dialog.getByRole('button',{name:'결과 등록',exact:true}).click();
 await expect(page.getByRole('dialog')).toHaveCount(0);
 await expect(page.getByRole('button',{name:'재시도',exact:true})).toBeVisible();
 await page.getByRole('button',{name:'재시도',exact:true}).click();
 await expect(page.getByRole('button',{name:'결과 등록',exact:true})).toBeVisible({timeout:10000});
 await page.getByRole('button',{name:'결과 등록',exact:true}).click();
 dialog=page.getByRole('dialog');
 await dialog.getByLabel('boot 결과',{exact:true}).selectOption('PASS');
 await dialog.getByLabel('functional 결과',{exact:true}).selectOption('PASS');
 await dialog.getByRole('button',{name:'결과 등록',exact:true}).click();
 await expect(page.getByRole('button',{name:/Bootloader 선행 그룹 · 전체 완료/})).toBeVisible();
 await expect(page.getByRole('row').filter({has:page.getByRole('button',{name:/Ethernet 나머지 그룹/})})).toContainText('선행 대기');
 await page.getByRole('button',{name:/Bootloader 선행 그룹/}).click();
 await page.getByRole('textbox',{name:'작업 명령',exact:true}).fill('왜 Ethernet이 기다리는지 알려줘');
 await page.getByRole('button',{name:'요청 보내기',exact:true}).click();
 await expect(page.locator('.prompt-history')).toContainText('모의 응답',{timeout:15000});
 expect(errors).toEqual([]);
 mkdirSync(path.join(root,'.local-reports'),{recursive:true});
 await page.screenshot({path:path.join(root,'.local-reports/dashboard-desktop.png'),fullPage:true});
 await page.setViewportSize({width:640,height:1000});
 await expect(page.getByRole('navigation').getByRole('button',{name:'환경 설정',exact:true})).toBeVisible();
 await page.screenshot({path:path.join(root,'.local-reports/dashboard-narrow.png'),fullPage:true});
});


test('T-67 demo-only boot completion unlocks the remaining group',async({page})=>{
 await page.getByRole('button',{name:'새 업그레이드',exact:true}).click();
 await page.getByLabel('작업 이름',{exact:true}).fill('자동 검증 · 데모 선행 수동 완료');
 await page.getByRole('button',{name:'분석 시작',exact:true}).click();
 await expect(page.getByRole('button',{name:'계획 검토 · 확인',exact:true})).toBeVisible({timeout:20000});
 await page.getByRole('button',{name:/Bootloader 선행 그룹/}).click();
 await expect(page.getByRole('button',{name:'데모에서 이 모듈 완료',exact:true})).toBeDisabled();
 await page.getByRole('button',{name:'계획 검토 · 확인',exact:true}).click();
 await page.getByRole('button',{name:'이 계획으로 진행',exact:true}).click();
 await page.getByRole('button',{name:'데모에서 이 모듈 완료',exact:true}).click();
 await expect(page.getByRole('button',{name:/Bootloader 선행 그룹 · 전체 완료/})).toBeVisible();
 await expect(page.getByRole('row').filter({has:page.getByRole('button',{name:/Ethernet 나머지 그룹/})})).toContainText('선행 대기');
 await page.getByRole('button',{name:/Kernel \/ BSP 선행 그룹/}).click();
 await page.getByRole('button',{name:'데모에서 이 모듈 완료',exact:true}).click();
 await expect(page.locator('.table-footer')).toContainText('선행 그룹 완료');
 await expect(page.getByRole('button',{name:/Kernel \/ BSP 선행 그룹 · 전체 완료/})).toBeVisible();
 await page.reload();
 await expect(page.locator('.table-footer')).toContainText('선행 그룹 완료');
 await page.getByRole('button',{name:/Bootloader 선행 그룹/}).click();
 await expect(page.locator('.stage-details').first()).toContainText('데모 수동 완료');
 await page.getByRole('button',{name:/Ethernet 나머지 그룹/}).click();
 await expect(page.getByRole('button',{name:'데모에서 이 모듈 완료',exact:true})).toHaveCount(0);
 await expect(page.getByRole('button',{name:'최종 검토 기록',exact:true})).toBeDisabled();
});

test('T-95 source auto mode and bridge defaults preserve custom settings',async({page})=>{
 const original=await (await page.request.get('/api/v1/config')).json();
 try{
  await page.getByRole('navigation').getByRole('button',{name:'환경 설정',exact:true}).click();
  await expect(page.getByLabel('소스 기준 (선택)',{exact:true})).toHaveValue('');
  await page.getByLabel('도구 연결 방식',{exact:true}).selectOption('bridge');
  await page.getByRole('button',{name:'빈 항목에 기본 경로 넣기',exact:true}).click();
  await page.getByLabel('프로젝트 작업 폴더',{exact:true}).fill('/srv/new bsp');
  await expect(page.getByLabel('codex 실행 배열',{exact:true})).toHaveValue('["/srv/new bsp/.bsp-dashboard/bridges/codex"]');
  await page.getByLabel('claude 실행 배열',{exact:true}).fill('["/custom/claude-bridge"]');
  await page.getByLabel('opencode 실행 배열',{exact:true}).fill('[]');
  await page.getByRole('button',{name:'빈 항목에 기본 경로 넣기',exact:true}).click();
  await expect(page.getByRole('status')).toContainText('기본 경로를 넣었습니다');
  await expect(page.getByLabel('claude 실행 배열',{exact:true})).toHaveValue('["/custom/claude-bridge"]');
  await expect(page.getByLabel('opencode 실행 배열',{exact:true})).toHaveValue('["/srv/new bsp/.bsp-dashboard/bridges/opencode"]');
  await page.getByRole('button',{name:'설정 저장',exact:true}).click();
  await expect(page.getByRole('status')).toContainText('설정을 저장');
  await page.reload();
  await page.getByRole('navigation').getByRole('button',{name:'환경 설정',exact:true}).click();
  await expect(page.getByLabel('소스 기준 (선택)',{exact:true})).toHaveValue('');
  await expect(page.getByLabel('claude 실행 배열',{exact:true})).toHaveValue('["/custom/claude-bridge"]');
  await page.getByRole('button',{name:'저장 후 환경 점검',exact:true}).click();
  await expect(page.locator('.probe-list')).toContainText('브리지 파일이 없습니다');
  await expect(page.locator('.probe-list')).not.toContainText('FILE_READY');
  await page.screenshot({path:path.join(root,'.local-reports/settings-defaults.png'),fullPage:true});
 }finally{
  const latest=await (await page.request.get('/api/v1/config')).json();
  const restored=await page.request.put('/api/v1/config',{headers:{'X-BSP-Client':'dashboard'},data:{version:latest.version,profile:original.profile}});
  expect(restored.ok()).toBe(true);
 }
});


test('T-101 native setup has no bridge requirement and persists commands and advanced fields',async({page})=>{
 const original=await (await page.request.get('/api/v1/config')).json();
 try{
  await page.getByRole('navigation').getByRole('button',{name:'환경 설정',exact:true}).click();
  await expect(page.getByLabel('도구 연결 방식',{exact:true})).toHaveValue('native');
  await expect(page.getByLabel('claude 실행 배열',{exact:true})).toHaveCount(0);
  await expect(page.getByRole('button',{name:'빈 항목에 기본 경로 넣기',exact:true})).toHaveCount(0);
  await page.getByLabel('프로젝트 작업 폴더',{exact:true}).fill('/srv/bsp/work');
  await page.getByLabel('에이전트 지침 폴더 (선택)',{exact:true}).fill('/srv/bsp/agents');
  await page.getByLabel('빌드 명령',{exact:true}).fill('./build.sh');
  await page.getByLabel('산출물 파일 경로',{exact:true}).fill('out/firmware.img');
  await page.getByLabel('검증 명령',{exact:true}).fill('./verify.sh');
  await page.getByLabel('최종 통합 · 회귀 명령',{exact:true}).fill('./integration.sh');
  await page.getByText('고급 설정 · 도구 경로와 역할 지침',{exact:true}).click();
  await page.getByLabel('codex 사용',{exact:true}).selectOption('disabled');
  await page.getByLabel('analysis 지침 파일 (선택)',{exact:true}).fill('roles/analysis-custom.md');
  await page.getByRole('button',{name:'설정 저장',exact:true}).click();
  await expect(page.getByRole('status')).toContainText('설정을 저장');
  await page.reload();
  await page.getByRole('navigation').getByRole('button',{name:'환경 설정',exact:true}).click();
  await expect(page.getByLabel('빌드 명령',{exact:true})).toHaveValue('./build.sh');
  await expect(page.getByLabel('도구 연결 방식',{exact:true})).toHaveValue('native');
  await page.getByText('고급 설정 · 도구 경로와 역할 지침',{exact:true}).click();
  await expect(page.getByLabel('codex 사용',{exact:true})).toHaveValue('disabled');
  const config=await (await page.request.get('/api/v1/config')).json();
  expect(config.profile.role_instructions.analysis).toBe('roles/analysis-custom.md');
  expect(config.profile.agents.claude).toEqual([]);
  await page.screenshot({path:path.join(root,'.local-reports/native-settings.png'),fullPage:true});
 }finally{
  const latest=await (await page.request.get('/api/v1/config')).json();
  expect((await page.request.put('/api/v1/config',{headers:{'X-BSP-Client':'dashboard'},data:{version:latest.version,profile:original.profile}})).ok()).toBe(true);
 }
});
