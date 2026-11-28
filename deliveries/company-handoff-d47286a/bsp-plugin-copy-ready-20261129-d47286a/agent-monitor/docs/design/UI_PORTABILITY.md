# GUI 호스트 이식·화면 동일성 계약

RQ-57/D-61/DEVPORT02. 현재 GUI 세 경로를 회사 구조에 재사용하는 계약이며 다이어그램·종합 화면은 독립 [PORT-001](../porting/PORT-001.md)·[PORT-002](../porting/PORT-002.md)로 선택한다. 현재 코드·시험·리뷰 상태는 [실행 기록](../testing/runs/20261106-portability.md), 전달 기준은 [PORT-004](../porting/PORT-004.md)다.

## 공유 소스와 호스트 책임

`packages/gui-test-ui/src/index.ts`는 TestPage, ExecutionViewSettings, SettingsSection, AuditDialog, createBrowserGuiTestHost와 GuiTestHost/GuiTestModuleContext 타입을 공개한다. index가 tokens.css, baseline.css, test.css, motion.css를 함께 import한다. 내부 CSS 파일을 다른 버전으로 교체하거나 TestPage를 별도 사본으로 유지하지 않는다. source-settings·audit-dialog 등 하위 스타일도 같은 소스 버전을 유지한다. GUI root의 선택 theme token은 --gt-ink/muted/line/teal/surface/font/font-size/line-height/focus/catalog-width(각 항목에 gt- prefix)다. 기본 scope는 14px/1.5이고 GUI dialog는 guiTest variant를 사용한다. React 단일 인스턴스를 사용하고 호스트 전역 button/input/table 규칙과 충돌하는지 fixture로 검사한다.

`GuiTestHost` adapter는 request(path, method?, data?, signal?), download(path), mode(default/live), applyMode(mode), storage(getItem/setItem/removeItem)를 제공한다. 선택 ownsSession(controller)는 실행 제어권 표시를 허용하며 생략하면 Run 실행 제어는 observer-only다. source/settings는 별도로 편집할 수 있다. 서버가 항상 최종 권한을 검증한다. createBrowserGuiTestHost를 앱 시작 시 한 번 생성해 안정된 객체로 주입한다. adapter는 transport와 실행 보기·설정 mount 등 호스트 연결만 담당한다. `apps/web/src/guiTestHost.ts`가 원래 BSP job을 공통 화면의 평탄한 `GuiTestModuleContext`로 변환한다. context는 job_id/plan_version/fingerprint·paused/session_status와 modules의 id/name/status/attempt_id/automatic·request_hash/frozen_run_id/source_revision/automation_blocked/blocked_reason을 사용한다. 공통 화면에서 앱의 job 내부 객체를 직접 import하지 않는다. public 타입 원문을 기준으로 회사 필드만 대응한다.

Python 공통 `make_manager(runtime, mode, *, dashboard=None, module_selection_service=None)`는 DashboardPort(pin/validate/submit)를 받는다. 호스트의 `backend/services/gui_test_host.py`가 `make_dashboard_manager(runtime, *, engine=None, module_selection_service=None)`로 조립한다. `demo_router(manager, live=False)`는 common API router 옆의 기존 `/api/v1/gui-test` 및 `/live` 위치에 별도로 mount한다. `automatic_result`는 저장된 Run을 검증하는 내부 결과 접점이다. 회사의 인증·오류 처리·worker tick/recover/outbox·최종 검토·서버 게이트를 유지한다. 실행 adapter는 Runner뿐 아니라 branches/readiness/catalog/boards/verify/prepare_source를 제공하는 ExecutionAdapter 계약을 따른다.

## 회사 적용과 동일성 확인

1. 회사 AGENTS/운영 정책과 COMPANY_MAP/APPLIED를 먼저 읽고 현재 API·worker·domain·UI의 대응 위치·추가 기능을 기록한다. 기존 source/settings/DB·runtime을 백업한다.
2. 세 canonical roots를 상대 구조로 적용한다. minimal backend/__init__.py와 host-reference는 회사 파일의 자동 덮어쓰기 대상이 아니다. host-reference의 backend import 구조를 보존하면서 회사 경로와 주입 위치를 명시적으로 대응한다.
3. index를 통해 같은 component·CSS·token 버전을 함께 사용한다. 회사 데이터/콜백 adapter와 mount만 조정한다. 개별 화면을 비슷하게 다시 작성하거나 CSS 복사본을 따로 유지하지 않는다.
4. 승인한 동일 브라우저 버전, viewport/device scale, locale/timezone, 데이터 fixture, 승인 폰트 설치/로딩 완료를 고정한다. 폰트 미설치나 브라우저 차이를 화면 동일성 PASS로 숨기지 않는다. 회사 보안 정책에서 폰트를 승인하지 않았다면 해당 선행 조건을 미해결로 남긴다.
5. shared fixture에서 desktop/375px·빈 목록·정상/오류/오프라인·접힌/펼친 설정·긴 이름·기존 RQ-55/56 draft/선택/실행 차단을 비교한다. 상충하는 호스트 전역 CSS에서도 버튼·체크박스·테이블·dialog/focus·토큰이 유지되는지 확인한다.
6. 회사 production build와 기존 기능 회귀를 실행하고 실제 코드/시험 해시·환경·명령·결과·차이를 APPLIED에 남긴다. 로컬 shared fixture 검증과 실제 회사 연결·화면 인수는 별도 결과다.

현재 회사 환경 T-190은 NOT_RUN이다. 원본 빌드·합성 fixture PASS는 회사의 인증/실제 API/Runner/보드 인수를 증명하지 않는다. 승인된 이전 Runner ZIP에는 RQ-56 source_snapshot_v1 지원 근거가 없으며 등록 source는 capability 검사로 차단해야 한다. 새 바이너리 배포 검증 전 기존 승인 ZIP을 교체하지 않는다.

## 반입 도구와 복원

`python apps/gui-test/package.py --host-integration --target bsp-dashboard-host-v1 --output .local-reports/gui-test-host-integration.zip`은 GUI만 내보낸다. source-only라 static/wheel을 포함하지 않고 UI 빌드가 필요하다. INSTALL/RELEASE_SUMMARY/contract는 ZIP 안에서 읽으며 HEAD는 ancestry, dirty와 파일 해시가 실제 bytes 기준이다. SHA256SUMS는 자신 외 모든 entry를 검증한다. `--base`는 폐기하며 source 수집·output 변경 전에 실패한다. 단독 `--standalone`·`--stage-wheel`은 Git 독립 계약을 유지한다.

데이터 schema migration·설정 재생성은 없다. 복원 시 실행 중인 작업을 정상 종료한 다음 검토한 source만 되돌리고 Run/Attempt/UNKNOWN 이력·사용자 설정은 보존한다. 실제 서비스 조작·외부 운영 실행은 별도 승인 범위다.

## 배포 ZIP의 수동 shared fixture

PORT-004 호스트 묶음의 `ui-verification/`은 현재 browser 시험의 `workflow_diagram/tests/portable-ui-host.tsx`를 그대로 재사용한다. source-root 이동에 따른 import 한 곳만 명시적으로 바꾸고 canonical/exported SHA256·치환 내역을 manifest ui_verification에 남긴다. HTML/Vite config/README까지 네 파일을 포함하므로 apps/gui-test의 잠긴 npm toolchain만으로 읽기 전용 fixture를 띄운다. 명령과 company shell mount 절차는 [PORT-004](../porting/PORT-004.md)와 ZIP 내부 README를 따른다. 자동 screenshot 시험 도구와 전체 workflow 앱은 배포하지 않는다. 같은 fixture의 깨끗한 reference와 회사 shell의 정상 global CSS를 동일 조건으로 비교하며 실제 회사 인수는 별도 NOT_RUN이다.
