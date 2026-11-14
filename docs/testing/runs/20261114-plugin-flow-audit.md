# 2026-11-14 플러그인 전체 흐름 독립 검토

최종 독립 판정은 **APPROVED — RQ-69/D-73 공통 로컬 구현 범위**다. 아래 최초 CHANGES_REQUESTED와 재검토 중 발견·수정 이력은 보존한다. 실제 회사 인수 T-264는 NOT_RUN이다.

## 기준과 판정

- 최초 검토 기준: `5775661ddcf7b6f9020fdc9ee058b2a12098f819`와 기존 커넥터 배치·제목 미커밋 수정. 기존 사용자 UI 수정은 보존했다.
- 검토자: 별도 `gpt-6-astra`, `xhigh` 세션. 실행 주체가 실제 spawn 설정을 확인했다. 이전 APPROVED 판정을 재사용하지 않았다.
- 범위: RQ-67/68, D-71/72, T-240~246·T-251~256과 관련 커넥터 계약. 최초 설치 → 연결 → 설정 → TC 선택 → 이미지/플래싱 → 실행/실패 분석 → 조회/기록 → 복구를 코드와 대조했다.
- **최초 판정: CHANGES_REQUESTED.** 아래 공통 구현 누락을 회사 인수 항목으로 넘길 수 없다. 후속 수정 검토와 최종 판정은 별도 절에 기록한다.
- 검토 agent는 제품 실행 코드를 수정하지 않았다. 후속 요청으로 실제 전체 호스트 경로를 검증하는 `backend/gui_test/tests/test_full_host_profile_workflow.py`만 추가했다. 실제 OS 설치·SSH·Windows 장비·TC·회사 모델·ACON 호출은 수행하지 않았다.

## 최초 발견 항목

| ID | 심각도 | 재현·영향 | 근거와 권장 수정 | 관련 검증 |
|---|---|---|---|---|
| FLOW-01 | P1 | 새 runtime의 플러그인이 TC 명령 프로파일을 저장할 수 없다. `PUT /api/v1/gui-test/live/saved/command`가 403이다. 중앙 설정에는 프로파일 이름/해시만 넣을 수 있고 실행 수락은 실제 저장 프로파일을 요구한다. | `IntegrationService.frozen_config`, `Manager.command_snapshot`, `service_mutation_allowed`, `router.save`. 기존 검증기를 재사용하는 공통 프로파일 저장·선택 경로가 필요하다. | T-240/242, 새 runtime에서 공개 클라이언트만으로 준비 완료 |
| FLOW-02 | P1 | 공개 설정으로 Windows 플래싱 프로파일을 준비할 수 없다. `ConnectorDesired.settings.flashing`과 로컬 `Settings.save`가 거부한다. 기존 콘솔 마법사만 별도 입력 경로다. | `ConnectorDesired.safe`, `connector.settings.Settings.save`, `scripts/setup_flashing.windows`. 고정 단계·BAT 해시·보드/serial·마커·제한시간을 검증하는 공개 설정과 안전 적용/receipt가 필요하다. 기존 프로파일과 실행 snapshot은 보존한다. | T-240/243, PENDING/APPLIED·CAS·실행 중/UNKNOWN 적용 거부 |
| FLOW-03 | P1 | 잘못된 runtime을 고정한 `PluginClient.health()`는 `SERVICE_IDENTITY_MISMATCH`지만 같은 클라이언트의 `save_settings()`가 다른 runtime에 성공한다. 포트 재사용/서비스 교체 뒤 오접속 변경을 막지 못한다. | `PluginClient.request`는 식별자를 강제하지 않고 `health`에서만 검사한다. 변경 처리 시 서버가 기대 runtime/package를 확인하도록 한다. 단순 사전 health 조회만으로는 확인과 변경 사이 경합이 남는다. | T-242, 잘못된 pin의 설정/실행/삭제 무변경 |
| FLOW-04 | P2 | 단독 integration 화면에서 settings/control scope와 정상 Origin·CSRF로도 저장 공간 기준 저장 및 정리 미리보기가 403이다. | `standalone.integration.boundary`의 `settings_path`에 storage API가 누락됐다. 좁은 scope 경로를 추가하고 읽기 전용/CSRF 거부는 유지한다. | T-255, settings scope 성공·읽기 전용 거부 |
| FLOW-05 | P1 | 플래싱 실패의 batch stdout/stderr/console이 DB에는 있지만 등록 명령 분석기 JSON에는 모두 빠진다. 실패 TC가 없는 준비/부팅 실패는 `attempts=[]`, 일반 reason만 전달한다. | `analysis_runtime.context`의 run 필드 선택이 integration 전체를 제외한다. batch·console·diagnostic·입력 식별자를 제한된 크기와 마스킹으로 전달한다. | T-241/251, FLASH_FAILED/부팅 실패의 실제 영속 근거 전달·비밀 마스킹 |
| FLOW-06 | P1 | 등록 identity/inventory는 갱신되지만 console 수집이 실패하면 `console.stale=True`인데 readiness/verify 및 inventory fresh가 참이다. 새 작업 허용 조건이 계약과 다르다. | `ConnectorRegistry.register`는 console fetch 이전에 시각을 저장하고 `RegisteredWindows.target(fresh=True)`는 등록 시각만 검사한다. 등록과 동일 runner console 수신의 두 시각을 함께 검사한다. 기존 작업 조회·취소·복구는 계속 허용한다. | T-242·커넥터 회귀, console 실패/재수신 경계의 새 배정 차단 |

초기 SSH host/account/port/profile 전달 누락은 루트 세션에서 먼저 확인한 공통 bootstrap 항목이다. 중앙 설정은 이미 연결된 커넥터를 대상으로 하므로 최초 연결을 해결하지 못한다. 이 검토는 위 여섯 항목을 추가로 확인했다.

## 전체 흐름 대조

| 단계 | 확인한 공통 구현 | 최초 누락 또는 현지 경계 |
|---|---|---|
| F01 서비스 준비 | 소스 전달 manifest, 고정 환경, 관리 서비스 수명, Worker 소유권, health·runtime 분리 | 최초 접속 정보 handoff 및 FLOW-03. 실제 회사 설치 정책은 현지 인수 |
| F02 보드 연결 | registry·왕복 identity·Windows Manager·보드 inventory·수동 제어/UNKNOWN 게이트 | 최초 연결 handoff, FLOW-06. COM/USB·SSH 인증은 실제 환경 인수 |
| F03 화면 연동 | 같은 서버 API, 커넥터 공통 설정, 창 종료와 상주 수명 분리 | ACON의 실제 API/인증/화면 mapping은 회사 접점 |
| F04 공통 설정 | DB CAS, JSON import/export, timeout snapshot, Windows desired/receipt | FLOW-01/02/04. 로컬 적용을 중앙 저장 성공으로 오인하지 않도록 유지 |
| F05 TC 목록 | 기존 source inspect/select, catalog·metadata·timeout, Linux 경로 범위, 명령 검증 | 공개 클라이언트 facade 보강 대상. 원본 실행 코어를 다시 구현할 필요 없음 |
| F06 이미지/부팅 | immutable 업로드, batch 예약, 고정 BAT/serial 검증, 현재 부팅 근거, UNKNOWN | FLOW-02/05/06. 회사 BAT 내용·마커·보드 인수는 현지 사항 |
| F07 실행/재실행 | 원자 실패 latch/outbox, lease/CAS, 신뢰 검증기, 동일 원인 중단·chain 3회 제한, 자식 Run의 운영 게이트 | 검증기 구현/인증은 회사 접점. 분석기가 쓸 영속 근거 전달은 공통 책임(FLOW-05) |
| F08 상태/로그 | Run events·TC stdout/stderr·console cursor/오류 큐·끊긴 구간 표시 | PluginClient의 JSON 전용 request와 원문 로그/보고서의 응답 형식 불일치는 루트 세션 확인·수정 대상 |
| F09 기록/정리 | 보호 참조 기반 cache 정리, 명시 세션 삭제, 재실행 chain 기록 | 플러그인 전용 삭제 경로/소유권 전달은 루트 세션 확인·수정 대상. FLOW-04 |
| F10 BSP 연동 | 기존 Engine/Worker·계획/선행 그룹/수정·빌드 배타/최종 검토 게이트 | 현재 GUI 전용 plugin scope로 `/api/jobs`를 호출할 수 없다. 별도 명시 BSP 클라이언트가 기존 API와 게이트를 재사용할 공통 진입점이 필요하며 회사 ACON만의 문제는 아님 |
| F11 갱신/복구 | 설치 pointer, active/UNKNOWN 차단, runtime inspection/adopt backup, rollback·release cleanup | 실제 OS 설치·장비 복구 인수는 별도. 읽은 구현에서 이 단계의 추가 공통 결함은 발견하지 않음 |

## 재현과 시험

원본 로그는 아래 `.local-reports/20261114-flow-audit/`에만 보관하며 Git에 포함하지 않는다.

| 실행 | 결과 | 로컬 근거 |
|---|---|---|
| 새 standalone TestClient에서 명령 저장·scope·runtime 오접속 재현 | 종료 0; FLOW-01/03/04의 실제 차단 누락/잘못된 403을 확인. PASS 판정이 아닌 결함 재현 | `api-gaps.log` |
| 분석 근거 재현 첫 실행 | 종료 1; macOS 임시 `/var` symlink를 LaunchLock이 거부. 제품 결함으로 분류하지 않음 | `analysis-evidence.log` |
| 임시 디렉터리 resolve 후 분석 근거 재현 | 종료 0; 영속 batch는 존재하고 `batch_evidence_retained=False` | `analysis-evidence-r2.log` |
| 등록/console 서로 다른 수신 시각 재현 | 종료 0; console stale인데 inventory fresh/readiness/verify 성공 | `console-freshness.log` |
| `.venv/bin/python -m pytest -q backend/gui_test/tests/test_failure_analysis.py backend/gui_test/tests/test_analysis_runtime.py backend/gui_test/tests/test_shared_control.py backend/gui_test/tests/test_plugin_integration_recovery.py tests/test_agent_monitor_lifecycle.py tests/test_agent_monitor_recovery.py` | **138 PASS**, 종료 0, 7.80초 | `existing-core-regression.log` |

위 회귀는 최초 검토 중 실행한 기존 시험의 결과다. 다른 구현 agent가 후속 수정을 병행하므로 최종 변경 전체를 검증한 결과로 재사용하지 않는다. 결함 재현과 기존 시험 통과는 양립하며 새로운 재현 회귀가 필요하다.

## 후속 수정 독립 검토

### 재검토에서 확인한 수정

RQ-69/D-73, T-260~264로 후속 구현을 추적한다. 구현 범위·회사 적용 안내는 [실행 기록](20261114-plugin-flow-implementation.md)과 [공개 연동 안내](../../agents/PLUGIN_CONTROL_API.md)를 따른다.

| 항목 | 현재 확인 |
|---|---|
| 최초 접속 handoff | 비밀 없는 Linux endpoint·서비스 식별 JSON을 서버에서 내보내고 Windows가 실행/예약/UNKNOWN·Manager 소유권을 확인한 뒤 가져온다. 기존 키·미지 설정·백업을 보존한다. |
| FLOW-01/02 | 명령 프로파일 검증/저장/선택 CAS, 플래싱 프로파일·도구/장치 탐색, Windows 실제 파일·COM·serial·observer 검증, desired/Host receipt를 제공한다. 새 설정부터 플래싱 준비·모의 TC까지 단독/전체 호스트에서 검증했다. |
| FLOW-03 | PluginClient와 imported connector 요청에 기대 runtime/package pin을 보내고 처리 서버가 비교한다. health 선조회와 변경 사이 서비스 교체도 거부한다. |
| FLOW-04 | 단독 화면의 settings scope가 저장 공간 설정·정리 경로에 적용된다. 읽기 전용/잘못된 CSRF 거부는 유지한다. |
| FLOW-05 | 분석 명령 JSON에 제한된 integration batch·플래싱 출력·console·입력 snapshot·진단 근거를 전달한다. TC와 플래싱 문자열은 자르기 전에 마스킹하고 입력 식별자를 큰 로그보다 먼저 보존한다. |
| FLOW-06 | 등록과 동일 의미 revision의 console 수신 시각을 함께 검사하고 미래/잘못된 시각을 거부한다. 오래된 상태는 새 준비/실행을 차단하지만 조회·취소·기존 복구를 차단하지 않는다. |
| F08/F09/F10 | 원문 TC 로그, 공개 Run 동작·소유권/버전/종료 확인을 재사용한 명시 삭제, 별도 `BspPluginClient`의 좁은 전체 호스트 scope를 확인했다. BSP 작업은 기존 Engine 정책과 Worker를 사용하고 standalone은 거부한다. |

재검토 중 추가 지적도 반영했다. imported connector의 health 요청에 서비스 헤더가 없어 실제 standalone에서 401이던 문제는 실제 경계 왕복 시험으로 수정했다. 지연된 console 응답이 새 등록 revision으로 표시되던 경합은 저장 transaction의 기대 등록 비교로 막았다. 최초 공개 FlashBoard에 observer가 없어 실제 준비 단계가 거부되던 문제는 필수 observer 모델과 공통 `validate_observers` 재사용으로 수정하고 native/proxy의 실제 `start_prepare` 검증을 실행했다. 기존 고급 프로파일의 nested `login_steps`·observer 마스킹/로그 설정을 지울 수 있던 편집은 명시 `FLASH_PROFILE_ADVANCED`로 거부하고 원본을 보존한다. 기존 프로파일 선택과 새 이름의 공개 프로파일 생성은 계속 가능하다.

### 독립 재시험과 현재 기준

| 실행 | 결과 | 로컬 근거 |
|---|---|---|
| bootstrap·freshness·공개 제어·분석·BSP 집중 | 65 PASS, 종료 0, 3.37초 | `new-code-regression-01.log` |
| 프로파일·플래싱·observer·공통 커넥터 및 전체 호스트 첫 검증 | 77 PASS / 시험 helper 1 FAIL. FastAPI의 nested router를 `app.routes`의 flat path로 가정한 검토 helper 결함이다. 실제 HTTP 경로 요청으로 고쳤으며 실패 로그 보존 | `profiles-regression-01.log` |
| 수정한 실제 전체 호스트 경로와 독립 집중 회귀 | 143 PASS, 종료 0, 6.35초 | `final-independent-regression.log` |
| 마지막 오류 코드 전달·실제 standalone router 등록까지 반영한 최종 독립 회귀 | **144 PASS, 종료 0, 6.42초** | `final-independent-regression-02.log` |

최종 명령:

```text
.venv/bin/python -m pytest -q backend/gui_test/tests/test_full_host_profile_workflow.py backend/gui_test/tests/test_integration_profiles.py backend/gui_test/tests/test_flashing.py backend/gui_test/tests/test_plugin_integration_observer.py backend/gui_test/tests/test_shared_connector_control.py backend/gui_test/tests/test_connector_bootstrap.py backend/gui_test/tests/test_connector_freshness.py backend/gui_test/tests/test_plugin_control_workflow.py backend/gui_test/tests/test_analysis_runtime.py tests/test_bsp_plugin_client.py
```

최종 시험 시작 전 수정/신규 Python·실행 스크립트·시험 **35개**의 SHA256을 `.local-reports/20261114-flow-audit/final-code-manifest-02.json`으로 고정했다. manifest SHA256은 `1c5d82f890186cc7e55435ef15cb437e3f19c349a377c625a19c283e2181e199`이며 시험 완료 후 **35개 모두 바이트 변경 없음**을 확인했다. 원본 로그·manifest는 로컬 전용으로 Git에 포함하지 않는다. `git diff --check`도 PASS다.

최종 판정은 **APPROVED**다. 검토한 RQ-69 공통 코드 범위에서 미해결 P1/P2는 없다. 사용자 기존 커넥터 UI 배치 수정은 이번 코드 승인 범위에 포함하지 않는다. 광역 회귀·패키징 결과는 루트 실행 기록에 별도로 남기며 독립 144건과 중복 합산하지 않는다. 실제 Windows/Linux 설치·SSH·COM/USB·회사 BAT/TC·모델·ACON·장비 복구와 T-264는 **NOT_RUN**이며 로컬 승인으로 대체하지 않는다.

### macOS 광역 시험 실패의 범위

루트의 추가 광역 실행 `.local-reports/20261114-plugin-flow/final-01.log`는 **1148 PASS / 19 SKIP / 18 FAIL**이며, 실패 18건은 모두 변경하지 않은 `tests/test_setup_active_endpoints.py`다. 독립 확인에서 변경하지 않은 `execution/launch.py:62`의 `process_identity()`는 Windows 생성 시각 또는 Linux `/proc`를 사용하며 현재 `darwin`의 살아 있는 자기 PID에 `None`을 반환했다. 시험 fixture와 실제 자식 프로세스 소유권 확인이 이 값으로 영수증을 구성하여 `Invalid receipt process identity` 또는 시작 실패에 도달한다. 따라서 macOS에서 네이티브 실행 소유권을 검증하지 못한 플랫폼 제약으로 분류하며, 이번 공통 API 회귀로 판단하지 않는다. 커넥터 production은 Windows만 허용하고 Mac `--preview`는 격리 모의 화면이다.

실패는 해소하거나 PASS로 바꾸지 않았고 로그를 보존한다. Mac 통과만을 위한 제품 변경이나 시험 조건 완화도 하지 않았다. 해당 파일을 제외한 후속 관련 회귀는 별도 시험 집합이며 전체 시험 PASS를 뜻하지 않는다. Windows/Linux 실제 실행 소유권·설치 인수는 여전히 별도 검증 대상이다.
