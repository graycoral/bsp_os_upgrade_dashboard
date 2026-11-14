# 플러그인 중심 요구사항 독립 리뷰 · 2026-11-14

## 리뷰 기준과 범위

- `review_id`: `20261114-plugin-centric-requirements-01`
- 검토자: 별도 Codex 세션 `plugin_requirements_review`. 부모 세션이 도구에 명시한 모델은 `gpt-6-astra`, reasoning effort는 `xhigh`, `fork_turns=none`이며 호출이 수락되었다. 로컬 `/Users/younghokim/.codex/config.toml`에서 확인한 기준은 `gpt-6.1-sol` / `high`다. 부모 실행의 런타임 override는 확인할 수 없으므로 실제 부모 effort를 확인했다고 주장하지 않는다. 확인 가능한 로컬 기준보다 한 단계 높은 리뷰 요청이다. Claude 리뷰가 아니다.
- 소스 기준: `main`, `e4f53ca1ec288feb3eb1b9ccff8335a398ad321c`. 최초 검토 시 제품 코드 변경은 없고 설계/PORT 문서 WIP만 있었다. 최초 12개 요구사항·계약 문서의 SHA256 목록은 `.local-reports/plugin-centric-implementation-20261114/review-input.json`이다. 로컬 전용 증거이며 Git 전달물에 포함하지 않는다.
- 최초 판정: **CHANGES_REQUESTED**. 아래 PC-R01~10은 최초 입력에 대한 발견 사항이다. 후속 구현 계약 재검토는 마지막 절에 별도 기록하며 최초 발견을 지우지 않는다.
- 수행: 요구사항·결정·현재/과거 계약, 실제 코드와 기존 시험을 읽는 정적 리뷰. 제품 코드 작성, 실제 모델/SSH/보드/회사 ACON 호출, 설치, 커밋/푸시는 수행하지 않았다. 제품시험 **NOT_RUN**. 과거 PASS를 이번 코드의 PASS로 사용하지 않았다.
- 적용 지침: `AGENTS.md`, `CLAUDE.md`, `.agents/skills/portable-feature/SKILL.md`, 문서 지도, 현재 상태/해당 진행 기록, 변경·검토 절차, 이식 절차 및 개발 로그 처리 규칙.

읽은 범위는 [최신 목표](../../design/PLUGIN_CENTRIC_INTERFACE_PLAN.md), [요구사항](../../requirements/REQUIREMENTS.md)의 RQ-14/47/53/58/60/63~66과 관련 결정, [플러그인 계약](../../design/BSP_UPGRADE_PLUGIN_INTEGRATION.md)의 역사적 §1~12 및 공개 §13~14, [커넥터 계약](../../design/BOARD_CONNECTOR_CONTRACT.md), [자동 퓨징](../../design/AUTOMATIC_FLASH_TEST.md), [오케스트레이터](../../design/ORCHESTRATOR_SPEC.md)와 [모듈 보고 계약](../../design/AGENT_STATUS_CONTRACT.md)의 권한/버전 경계, [설치·화면 계획](../../design/PLUGIN_TEST_DASHBOARD_MONITOR_PLAN.md), [PORT-007](../../porting/PORT-007.md), [PORT-009](../../porting/PORT-009.md), [플러그인 요청서](../../agents/BSP_UPGRADE_PLUGIN_REQUEST.md)다. 관련 Python core/worker/integration/timeout, API/standalone client, connector/supervisor/registry, Windows Host/FlashService, 패키징, 공유 TestPage와 기존 시험을 대조했다.

## 사용자 결정과 공학적 선택

사용자 확정은 플러그인 중심 운영, 플러그인이 관리하는 선택 Agent Monitor 화면, ACON/Monitor/커넥터의 공통 설정·상태 공유, 커넥터 설정 편집, 자동 이미지 전송→퓨징→새 부팅 확인→TC, 창 종료 후 실행 지속, TC 기본 600초·화면/파일 편집, 첫 TC 실패 시 후속 TC 차단 및 플러그인 분석, 복사 가능한 소스 전달·새 EXE 없음이다.

리뷰 도중 부모 세션이 전달한 후속 사용자 답변은 **“원인 조치와 실행 조건 확인 후 자동 재실행, 같은 원인 재발 시 중단”**이다. 이를 사용자 결정으로 반영한다. 앞선 분석 후 항상 수동 재실행 제안은 대체된다. 별도 세션 리뷰 후 즉시 구현 지시도 확인했다. 이 구현 승인이 실제 회사 모델·장비 실행 또는 게시 승인으로 확대되지는 않는다.

API 경로/필드, 동일 Run 차단 범위, CAS/lease, 설정 우선순위, 기본 재실행 총량, 파일 import 방식, 설치 staging 등은 아래 공학적 기본값으로 구현할 수 있다. 필드 하나마다 사용자 확인을 다시 받을 사유는 없다. 회사 배포 저장소·OS/서비스 관리자·ACON 접점·실제 BAT/보드 값은 회사 사실이며 로컬 계약 구현의 선행 승인 문제가 아니다.

## 최초 발견 사항

### PC-R01 · P1 · 새 실패 정책과 현재 요구사항/실행 분기 충돌

- 요구: RQ-60, 새 첫 실패 중단/자동 조치 후 재실행 결정.
- 근거: 최초 `REQUIREMENTS.md:257`은 최대 3회/PASS 2회다. `core/repetition.py:2~14`는 최초 FAIL에 `RETRY`; `core/manager.py:509~526`은 이를 다음 Attempt로 즉시 배정한다. 일반 Run은 같은 파일 `:544~553`에서 FAIL 후 index를 증가시켜 다음 TC로 진행한다. TestPage `:434`도 기존 정책을 고정 문구로 표시한다.
- 영향: integration 한 곳만 바꾸거나 전역 집계 함수를 교체하면 일반 화면에서 요구를 우회하거나 과거 Run 의미가 바뀐다.
- 수정: 새 대상 Run에 `fail-stop-analysis-v1`을 수락 시 고정하고 saved policy로 분기한다. 정책 없음/기존 retry policy는 기존 의미, 미지원 policy는 실행 거부다. 실패 raw Attempt와 미실행 PENDING을 유지한다. RQ/D/시험 추적과 UI/보고서 정책 설명을 함께 바꾼다.
- 검증: 신규 일반/integration 첫 FAIL에서 다음 claim 없음, 구형 F/P/P 결과 유지, 새 정책 UNKNOWN 거부, 실패 이력·PENDING/전체 INCOMPLETE 보존. 기존 T-206은 legacy 회귀로 남기고 신규 T-240 이후 시험을 추가한다.

### PC-R02 · P1 · 영속 분석 인계와 지연 결과의 실행 차단 계약 없음

- 근거: `Manager.finish`, `IntegrationService.prepare_run:304~315`, `record_batch:328~363`은 실패 상태만 저장한다. `Worker.tick`에는 분석 인계가 없다. `Manager.act:325~333`의 resume, `IntegrationService.record_batch:342~352`의 READY 조정은 별도 분석 latch를 알지 못한다.
- 영향: 실패 저장 뒤 프로세스 중단으로 분석 요청이 유실되거나, 분석 중 READY/다른 화면의 재개로 TC가 실행될 수 있다. 플러그인 창이 닫히면 분석 담당이 사라지는 구성도 사용자 요구를 만족하지 않는다.
- 수정: 실패 기록과 동일 DB 트랜잭션에서 안정적인 요청 ID·evidence revision·중단 latch를 저장한다. TC뿐 아니라 준비/플래싱/부팅 실패 및 UNKNOWN을 인계한다. 분석 소비는 lease/CAS를 쓰는 at-least-once 전달이며 같은 요청 재전달을 허용하되 결과 저장은 멱등이다. 완료 전에 ACK하지 않는다. 분석 응답/조회는 PASS/FAIL·물리 종료·예약 해제 권한이 아니다.
- 검증: 실패와 enqueue의 crash 경계, duplicate receipt, 소비 중 종료와 lease 만료, 재접속 후 재전달, stale 결과, cancel/pause/control change 우선, READY/recover/resume 우회 거부. 단순 “분석 요청됨” 표시만으로 자동 분석 연결 완료를 기록하지 않는다.

### PC-R03 · P1 · 자동 재실행의 근거·동일 원인·snapshot 경계 필요

- 근거: 새 사용자 결정은 조치와 실행 조건 확인을 전제하지만 최초 목표에는 재실행 조건이 미결정이었다. 기존 `manager.py`는 FAILED slot을 재개할 별도의 조치 증명이나 원인 chain을 갖지 않는다. 기존 `IntegrationService`는 source/config/runner/flash profile을 고정한다.
- 수정: 결과는 stable cause key, 원인/조치 요약, 근거 참조, 기준 실패/상태 revision, 제안 행동을 포함한다. 서버 또는 등록된 검증 adapter가 근거와 현재 종료·보드·예약·게이트를 확인해야 한다. 분석기의 boolean 선언이나 임의 셸 명령을 실행 근거로 쓰지 않는다. verifier 없음/근거 불충분은 HOLD다.
- 같은 입력이면 실패 slot에 새 Attempt를 만들고 검증 PASS 후 원래 후속 순서로 이어간다. 소스/이미지/프로파일을 고쳤다면 기존 snapshot을 바꾸지 않고 정상 재준비/필요한 퓨징을 거친 자식 Run을 생성한다. 선행 TC와 기존 BSP 게이트를 생략하지 않는다. 이 자식도 같은 retry chain에 연결한다.
- 동일 normalized cause가 chain에서 재발하면 중단한다. 서로 다른 cause가 반복되는 경우에도 자동 재실행 최대 **3회/chain**을 공학적 기본값으로 두며 원래 시도는 별도다. 새 key/자식 Run/재시작으로 횟수를 초기화하지 않는다. 서버 정규화와 total cap을 함께 사용하며 의미가 같은 임의 자연어를 완벽히 판별한다고 주장하지 않는다.
- 검증: 조치 미완료/없는 ref/다른 Run ref/현재 기준 불일치 거부, 같은 원인 재발 중단, 서로 다른 원인 총량 한도, retry PASS 뒤만 후속 실행, 입력 변경 시 새 preparation/chain 보존, UNKNOWN 강제 해제 없음. 실제 회사 분석/조치 검증 adapter는 별도 인수다.

### PC-R04 · P1 · 600초 기본값·설정 파일·기존 설정 이전 기준 미정

- 근거: `core/discovery.py:40` 기본은 10초다. `core/timeouts.py`는 DB의 공통값/소스 revision별 override와 CAS를 이미 제공한다. `IntegrationService.start:239~259` 및 `Manager.start`는 timeout snapshot을 이미 보존한다. `Host.start/execute`는 TC timeout과 프로세스 종료 확인을 지원한다. 목록 timeout RQ-58은 별도 100초다.
- 수정: 개별 override → 명시 중앙 공통값 → 명시 TC metadata → 600초 fallback. 명시 10초 및 과거 Run은 보존한다. 600초를 lease/HTTP/catalog/flash timeout으로 전파하지 않는다. 명시 metadata 여부를 보존해 과거에 채워진 기본 10초와 혼동하지 않게 한다. Windows와 server discovery/전송 계약이 동일 값을 사용하도록 검사한다.
- 편집 파일은 중앙 DB revision을 포함한 JSON import/export 계약으로 제공한다. 별도 권위 파일·last-write-wins를 만들지 않는다. 조회/검증/적용 명령과 충돌 응답을 제공하고 서비스가 읽지 않는 예제 파일을 “설정 편집 지원”으로 표현하지 않는다.
- 검증: 무설정 600, 명시 metadata/중앙/개별 우선순위, 기존 Run 고정, 오래된 preview 거부, 파일/화면 동시 편집 충돌, connector에 유효값 전달, 강제 종료 미확인 UNKNOWN. 기존 `test_execution_timeouts.py`의 CAS/Run pin 시험을 재사용한다.

### PC-R05 · P1 · 설정 없는 bootstrap 및 standalone connector 등록 불가

- 근거: `runtime.py:69~76`은 integration 설정 또는 파일이 없으면 시작을 거부한다. `ServiceRegistry.snapshot:45~51`은 완전한 실행 config를 요구하는 `frozen_config()`를 호출한다. `PluginClient.__init__:36~38`은 config와 runner pin을 필수로 하고 health에서 모두 비교한다. standalone `create_app:190~191`은 GUI router만 연결하고 connector router를 연결하지 않는다.
- 영향: 설치 직후 보드/TC 없이 health·설정/등록을 사용하는 F01을 수행할 수 없다. 합법적인 공통 설정 변경도 이전 client에서 다른 서비스처럼 거부될 수 있다.
- 수정: 안정적인 서비스/runtime/package/지원 capability 검증과 변경 가능한 config revision·runner/TC 실행 준비를 분리한다. board/TC 미설정에서도 bootstrap/설정/등록/기록 조회가 동작해야 한다. 수락/preview 시 실행 기준을 고정한다. 등록 identity 변경 및 과거 Run pin 검사는 유지한다. 기존 GUI DB lock을 사용하고 두 Worker를 띄우지 않는다.
- 검증: 빈 runtime 첫 시작, 보드 없음 health/설정, connector 등록 후 준비 전환, 중앙 설정 변경 후 같은 client 사용, 실제 다른 runtime/runner 거부, 두 서비스 시작의 단일 소유권, 창 종료 후 상태 지속.

### PC-R06 · P1 · 공통 설정의 데이터 소유와 실제 적용 범위 구체화 필요

- 근거: `IntegrationService.config`는 현재 `gui-test.json`에서 읽은 별도 값이며 `PatternDefaults`는 client-side 단일 writer 파일이다. connector `Settings.save`는 Windows local profile만 변경하고 `supervisor.py:208~212`는 연결 중 저장을 거부한다. `paths.py`는 표시 전용이다. 이들을 그대로 두고 timeout API만 추가하면 이미지/BAT·TC·보드/프로파일 공유 요구가 남는다.
- 수정: 중앙 실행 설정은 허용 source/installer roots와 선택 참조, 모듈/전역 TC 패턴, timeout, 선택 보드/등록 profile 참조를 typed schema와 revision으로 관리한다. 실행 설정 변경은 새 preparation/Run부터 적용한다. server root와 Windows 경로를 서로 번역하지 않는다. Linux 경로는 server 허용 범위에서 검증/조회한다.
- Windows COM/SSH/도구·TC Python 및 물리 mapping의 실제 소유자는 connector다. 공통 API는 connector identity와 desired revision을 지정하고 실제 검증/적용 응답을 받는다. 중앙 저장과 Windows 적용을 구분하고 미연결·active/UNKNOWN에서는 pending/blocked를 표시한다. 편집 가능한 공통 설정과 연결을 끊어야 하는 로컬 mapping을 구분한다. source 선택/명령 profile 같은 기존 서비스는 adapter로 재사용한다.
- 검증: 플러그인/웹/ACON reference/Qt 네 경로에서 같은 revision 조회·저장, stale 충돌, offline 저장을 적용 완료로 표시하지 않음, 실행 중 입력 고정, 다른 runner ACK 거부. ACON private UI를 구현했다고 표시하지 않는다.

### PC-R07 · P1 · 현재 인증/권한 계약은 새 편집 경로를 차단함

- 근거: standalone middleware `:121~138`은 browser 모든 mutation과 `/integration/` 외 service mutation을 거부한다. full host `backend/api/main.py:95~107`도 service mutation을 제한한다. 현재 `PUT /execution-timeouts`, source 설정, connector 등록을 붙이는 것만으로 plugin/브라우저 편집이 되지 않는다. 현재 공개 설명 `BSP_UPGRADE_PLUGIN_INTEGRATION.md:301,305` 및 `AUTOMATIC_FLASH_TEST.md:49`에는 제거된 공유 토큰 설정이 남았다.
- 수정: 필요한 service/connector mutation 경로를 좁은 allowlist로 연결하고 읽기/설정/실행 제어 scope를 명시한다. 선택 화면은 기존 same-origin/HttpOnly session을 명시 편집 scope로 확장하고 CSRF 방어와 version/controller 검증을 유지한다. 공유 연결 토큰을 되살리지 않는다. IPC 제어 자격·Run lease는 별도 목적이며 유지한다. 현재 공개 절의 stale 토큰 지시를 현재 코드와 일치시키고 역사적 설명은 이력임을 표시한다.
- 검증: 정상 각 client 저장, cross-origin/Origin 없는 browser mutation/허용 외 경로 거부, 읽기 session 권한 유지, 제어권 없이 retry/resume 불가, 같은 호스트 비브라우저 trust 경계 명시.

### PC-R08 · P1 · 전달 소스의 의존성 및 전체 Agent Monitor 범위 불완전

- 근거: `apps/gui-test/package.py:17,59~117`은 GUI Test 세 루트를 내보내고 전체 `apps/web`/backend host를 포함하지 않는다. `test_plugin_integration_package.py:17~62`는 추출/import만 확인한다. connector가 wheel에 포함돼도 `settings.py:16`, `supervisor.py:66,171,232`는 `scripts.setup_runtime`을 동적 import한다. 해당 scripts/launcher/Qt lock은 현재 GUI source export에 없다.
- 영향: import 성공을 복사 후 save/connect/실행 성공으로 오인하거나 GUI Test 단독 화면을 전체 Agent Monitor 전달이라고 부를 수 있다.
- 수정: Linux service/client, 선택 전체 Agent Monitor, Windows connector를 각각 실제 의존성까지 닫힌 소스 전달 단위로 고정한다. 기존 scripts를 포함하거나 명시 adapter로 옮기며 회사 backend를 덮어쓰지 않는다. optional 전체 UI에는 그 API/host 접점도 포함한다. standalone TestPage만 지원하는 경로는 명시적으로 구분한다. 설치 시 Node 빌드를 기본 요구하지 않고 공급자가 검증한 정적 자산을 사용할 수 있게 한다.
- 검증: 원본 없는 새 폴더/venv에서 설치·설정 저장·서비스 bootstrap·client 요청·분석 callback 계약·connector 의존 import·동봉 시험을 실행한다. import-only/원본 PYTHONPATH 혼입을 막는다. 파일 SHA·provenance·고정 의존성·실행 진입점과 범위별 PORT를 제공한다. 미커밋이면 commit pin을 꾸미지 않고 기준 HEAD+변경 파일 SHA를 쓰며 게시 후 pin을 갱신한다.

### PC-R09 · P2 · 자동 설치와 업데이트를 기존 start 호출로 대체할 수 없음

- 근거: `SystemdService.start`는 설치된 unit start만 실행한다. 현재 Windows 단일 launcher는 Python/OpenSSH/회사 TC 의존성을 선행 조건으로 둔다. 새 목표는 필요 의존성 자동 준비이며 기존 설치 계획에는 source/서비스 관리자·오프라인/원자 설치가 아직 제안 상태다.
- 수정: 고정 소스 manifest를 받는 설치 진입점, 전용 환경·정상 설치 재사용, 설치 잠금/staging/검증 후 게시, 영속 runtime 분리, 서비스 관리자 adapter와 identity 확인을 구현한다. 기존 수정/active/UNKNOWN 작업이 있으면 자동 활성 전환을 보류한다. Python/OpenSSH/fastboot 등 OS 도구를 자동 준비하지 않는 플랫폼은 해당 단계 미완료로 표시하고 기존 launcher 완료로 대체하지 않는다. 회사 권한/다운로드 정책을 추정하지 않는다.
- 검증: clean install/reuse/offline/partial failure/concurrent start/다른 서비스/기존 설정 보존/업데이트 유예/복원. 설치 확인 명목으로 모델·SSH·장비를 실행하지 않는다.

### PC-R10 · P2 · 표시·오류·문서 인수 범위 누락

- 근거: 목표 F08~F10 및 최신 PORT는 상세 대기이며 TestPage의 정책 문구와 기존 읽기 전용 계획이 섞여 있다. `Manager.emit`은 stdout/stderr를 갱신해도 제어 version을 올리지 않는다. `ORCHESTRATOR_SPEC`/`AGENT_STATUS_CONTRACT`는 기본 v1·조정 OFF, 유일 실행 관리자를 유지한다.
- 수정: 분석 대기/실행/조치 검증/자동 재실행/같은 원인 중단을 실제 저장 상태로 공통 표시한다. 로그는 별도 cursor로 조회하고 화면 재접속은 실행 요청이 아니다. 보드 전원 꺼짐을 로그 없음으로 단정하지 않는다. plugin TC 분석 outbox는 GUI Run 계약이며 모듈 보고 v2나 BSP 조정 runtime을 새로 켜는 근거가 아니다. 기존 BSP 계획·선행·수정/빌드 잠금·교차 리뷰·최종 사람 검토·Jira 기준을 보존한다.
- 문서 인수: 새 RQ/D/T, current contract/PORT/요청서/현재 상태/진행 기록을 같은 단위로 갱신한다. 과거 최대3회/PASS2 시험은 legacy 이력으로 유지하고 새 제품 PASS, 독립 리뷰, 회사 NOT_RUN을 구분한다.
- 검증: 같은 Run version의 로그 증가, 재접속·역순 snapshot, raw error와 분석 상태 구분, UI 닫기 후 worker/connector 유지, 기존 BSP 게이트 회귀. 문서 검사는 제품 PASS가 아니다.

## 최소 구현 단계와 완료 기준

| 단계 | 구현 단위 | 데이터/접점 | 종료 조건 |
|---|---|---|---|
| A | 새 정책, 실패 latch, 분석 outbox, 조치 검증·자동 retry | 기존 Run JSON/documents와 기존 Manager/Worker; additive schema, legacy dispatch | 최초 실패 차단, crash/duplicate/stale, same cause/총량, 기존 snapshot/예약 회귀 통과 |
| B | 공통 설정/600초/file CAS, unconfigured health, registry, client/분석 worker | 기존 settings/source/integration adapter; 실행 수락 snapshot | 네 client용 공통 계약, offline/적용 상태, 파일 충돌, 단일 worker, callback 없는 HOLD 통과 |
| C | Qt/선택 화면/ACON reference adapter | 기존 UI와 connector IPC; 실제 회사 adapter는 분리 | 동일 설정/상태·분석/retry 표시, scope/CSRF/제어권, 종료 후 지속·로그 cursor 통과 |
| D | 설치·복사 전달·문서/독립 코드 리뷰 | 실제 의존성 closure와 고정 manifest/entrypoint/PORT | 원본 없는 폴더에서 설치부터 API/시험까지 확인, 제품·회사 NOT_RUN 구분, 독립 코드 리뷰 지적 해결 |

위 단계는 한 변경 단위씩 진행할 수 있다. A/B 완료를 전체 설치·Windows/ACON 연결 완료로 표현하지 않는다. 이미 구현된 이미지 stream/immutable snapshot/부모 batch 예약/flash supervision/fresh boot/엄격 TC parser는 재사용한다. 분석 요청 때문에 별도 TC 스케줄러나 BSP orchestration 엔진을 작성하지 않는다.

## 수정 계약 재검토 · 2026-11-14

부모 세션이 추가한 [최신 목표의 “리뷰 후 구현 승인·채택할 기술 기준”](../../design/PLUGIN_CENTRIC_INTERFACE_PLAN.md#2026-11-14-리뷰-후-구현-승인채택할-기술-기준)을 다시 읽었다. 새 Run 정책/legacy 분기, 동일 트랜잭션 분석 요청, advisory result와 중단 우회 방지, 조치 검증 후 자동 재실행, 같은 원인/chain 한도, 변경 snapshot의 자식 Run, verifier 없는 HOLD, stale 결과보다 취소/중지 우선, 600초/CAS/file, bootstrap/단일 worker, 회사 adapter 분리와 복사 검증 기준을 반영했다.

**요구사항·구현 방향 재검토: APPROVED.** 이는 위 공학적 기본값과 검증 조건에 따라 로컬 제품 구현을 시작할 수 있다는 판정이며 제품 코드/패키지/회사 적용 승인 결과가 아니다. PC-R01~10의 코드·시험·현재 문서 갭은 구현 작업의 완료 조건으로 남는다. 공통 설정의 실제 필드·Windows 적용 응답 및 설치물별 포함 파일은 구현에서 명세와 같이 구체화해야 하며, 범위를 줄인 경우 누락 기능을 완료로 기록하지 않는다. 새 RQ/D/T 등록 및 현재 공개 토큰 지시 정리는 구현 문서 변경에 포함한다.

실제 회사 plugin/ACON 소스와 분석·조치 검증 연결, Windows GUI/SSH/UART/fastboot/BAT/TC, Linux 서비스 설치 정책·배포 저장소, 실장비 UNKNOWN 복구는 **NOT_RUN**이다. 추가 일반 기술 선택은 승인된 범위에서 진행 가능하며, 실제 회사 정책과 충돌하거나 새로운 운영 행동이 필요한 접점만 별도 판단 대상으로 남긴다. 다음 독립 검토는 구현된 코드와 새 시험 증거를 대상으로 수행한다.

리뷰 종료 직전 사용자 추가 범위인 프로젝트 스크립트 중복 제거·통합·직관적 이름 변경은 별도 script audit에서 조사한다. 새 설치 진입점을 기존 스크립트와 중복 생성하지 않고 실제 caller/문서/CI/패키징을 함께 변경하며, Windows 공개 진입점 `board-connector.cmd`는 보존한다. 이 별도 인벤토리 때문에 위 핵심 요구사항 리뷰 완료와 승인된 구현 착수를 보류하지 않는다.
