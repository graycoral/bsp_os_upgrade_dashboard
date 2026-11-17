# PORT-011 · 플러그인 사용자 명령과 연결·설정 동기화

## 범위와 고정 기준

2026-11-17 사용자 요청에 따른 **설계·회사 포팅 안내**다. `/bsp-upgrade` 사용자 명령의 등록·파서·화면 adapter는 이번 변경에서 구현하지 않는다. 아래 명령은 구현 예정 권고안이며 현재 실행 가능한 명령으로 안내하지 않는다. 사용자 확정은 **보드 커넥터 연결 시 connect의 준비 완료 알림**, **플러그인·Agent Monitor·보드 커넥터의 상호 설정 갱신**, **별도 세션 리뷰와 문서 커밋·머지**다. 세부 명령 이름은 리뷰 반영 권고다.

- 원본: `graycoral/bsp_os_upgrade_dashboard`.
- 문서 작업 기준 및 재사용 API 조사 기준: `f0fd97c88548de4896aac350444336293a768e8f`.
- 신규 명령 adapter의 대상 코드 커밋: 없음(미구현). 기존 API 조사 기준을 신규 명령 구현·제품시험 완료로 해석하지 않는다. 문서 변경 커밋은 이 파일의 Git 이력으로 확인한다.
- 관련 요구: RQ-60/67/68/69/70, 기존 D-64/71/72/73/75. 비상 종료는 이번 설계의 일상 명령 범위에서 제외한다. 기존 시험 추적은 T-240~246, T-260~269이며 새 명령 인수 사례는 아래 CMD-A01~08이다. CMD-A는 이 문서의 설계 사례이며 전역 T 시험 PASS를 추가하지 않는다.
- 선행: [PORT-007](PORT-007.md)의 PluginClient·설치/identity, [PORT-009](PORT-009.md)의 Windows Manager·Host·미러·설정 적용. 두 PORT의 기능별 고정 커밋과 회사 부분 적용 이력을 대조하고 위 기준 전체를 무조건 덮어쓰지 않는다.
- 의존성: 기존 Python/HTTP 클라이언트와 설치 lock을 재사용한다. 새 라이브러리·서비스·Worker·DB 이전·설정 기본값 변경 없음.
- 별도 세션 검토와 문서 검사: [실행·리뷰 기록](../testing/runs/20261117-plugin-command-porting.md). 회사 플러그인 소스와 실제 설치/장비 인수는 미확인이다.

## 권고 명령과 기존 API 연결

공통 접두사는 `/bsp-upgrade`다. 회사 플러그인의 명령 등록 방식에 대응하되 기존 명령과 이름이 겹치면 회사 adapter에서 조정한다. API 스키마는 [공개 연동 안내](../agents/PLUGIN_CONTROL_API.md)와 연결 코드가 원문이며 여기서 복제하지 않는다.

| 사용자 명령(권고) | 동작·기존 접점 | 구현 시 주의 |
|---|---|---|
| `help` | 명령·예시·지원 capability 안내 | 로컬 도움말, 연결을 강제하지 않음 |
| `connect` | `connect`, `connector_inventory`, `connector_mirror` | 아래 연결 준비 판정·감시·알림 적용 |
| `status [--boards / --diagnose]` | health/inventory/mirror와 선택 Run의 `run` | 현재 공통 상태, stale·선택 Run·설정 실제 적용 상태 요약; 보드/진단 상세 옵션 |
| `settings [show / edit / export / import]` | `settings/save_settings`, `export_settings/import_settings`, `paths` | 기본 show, edit는 명시 저장; CAS/JSON 검증·초안 보존 |
| `settings connector` | `save_connector_settings`, 미러 `apply-settings`·receipt | 중앙 요청과 Windows 실제 적용을 구분 |
| `settings profiles [commands / flash]` | 프로파일 조회·저장·검증·`select_profile` | 최초 설치의 TC/flash 프로파일 준비·revision 선택 보완 |
| `test list` | 설정된 integration `tc_root`의 선택·준비 목록 | 일반 `catalog()`와 integration 경로가 같다고 가정하지 않음; 아래 목록 제약 참조 |
| `test preview` | `preview` → `preparation` 조회 | 비동기 준비 완료 후 고정 목록·순서·설정 revision·token 확인 |
| `test run` | `start(key, installer_path, patterns, prepared_token)` | 이미지 준비→전송→플래싱→부팅 확인→TC, 실제 실행 승인 범위와 서버 gate 유지 |
| `test runs` | `runs()`에서 integration 실행만 분류 | 이력·현재 선택·실행ID 표시; 일반/Mock 이력을 장비 Run으로 오인하지 않음 |
| `test select <실행ID>` | `runs/run` 확인 후 회사 선택 문맥 저장 | 명시 선택과 identity/controller 확인; 서버 실행/소유권 변경 없음 |
| `test status [실행ID] [--report]` | `run/events`와 기존 로그 참조 | 단계·TC 결과·보류 사유·확인 시각; report는 기존 근거 요약 |
| `test logs [실행ID] [--follow]` | `events/attempt_log/board_console/connector_errors` | TC/콘솔/오류 구분, follow는 읽기 폴링; 닫아도 Run 지속 |
| `test pause/resume/cancel [실행ID]` | `action` + expected version·stable key | 접수와 실제 상태를 구분, 안전한 단계 전이만 허용 |
| `test reconcile [실행ID]` | `action(..., 'reconcile')` 후 같은 Run 조회 | 상태 재확인 요청, 강제 UNKNOWN 해제나 새 장비 실행 아님 |
| `test analyze [실행ID] [--requeue]` | Run 연계 분석 조회·`analysis_status`; 명시 재요청은 `requeue_analysis` | 기본 조회, 중복 소비자/분석기 생성 금지; 재요청에 analysis ID·최신 version 필요 |
| `monitor` | `browser_access` | 기본 읽기 화면, 편집 진입은 필요한 settings/control scope·CSRF 재사용 |
| `connect export` | `export_connector_bootstrap` | Windows 최초 접속 JSON, 명시된 접근 가능 서버·SSH 계정·포트만 사용 |

`test list`의 integration 전체 스크립트 목록은 현재 `catalog()`만으로 보장되지 않는다. 최초 adapter는 BAT·패턴이 준비된 경우 `preview/preparation`의 **이번 실행 대상 목록**을 표시하고 그 범위를 제목에 알린다. 전체 스크립트 조회가 필요하면 선택 integration 경로와 고정 소스를 대조하는 읽기 계약의 지원 여부를 먼저 확인하고 지원하지 않는 설치에서는 미지원으로 표시한다. 다른 세션의 TC 상태 조회 WIP를 이 문서의 고정 기준에서 구현된 API로 전제하지 않는다. `test list --all`은 그 계약이 준비된 뒤 별도 구현·검증한다.

`test preview`를 매번 별도로 실행할 의무는 없다. token 없는 `start`도 서버의 같은 준비를 거친다. 미리보기가 있으면 해당 token을 유지하고, 만료·소스/설정 변경 시 새 대상을 조용히 실행하지 않는다. 저장된 installer·패턴을 생략값으로 사용할 수 있으나 누락값은 구체적으로 안내한다.

## CONNECT의 준비 완료와 상태 갱신

1. 서비스 runtime/package identity·Worker 준비를 확인한다. Linux 서비스만 떠 있으면 `서비스 준비 · 보드 커넥터 연결 대기`라고 표시한다.
2. 현재 `PluginClient.connect()`는 `ensure_service` 후 `capabilities.connection.ready`를 한 번 확인한다. 연결 대기·뒤늦은 접속·재접속 알림은 **회사 플러그인의 상태 감시 adapter 추가 작업**이며 현재 메서드만으로 구현 완료라고 하지 않는다.
3. 회사 플러그인이 활성 상태일 때 기존 조회 API를 제한된 주기(권고 3초, 오류 시 backoff)로 읽는다. 등록·콘솔·Manager projection의 최신성, 해당 runner/서비스 identity, capability 일치를 [미러 계약](../design/BOARD_CONNECTOR_MIRROR.md)과 [커넥터 계약](../design/BOARD_CONNECTOR_CONTRACT.md) 기준으로 확인한다. endpoint 응답만 왔다거나 과거 캐시가 있다는 이유로 준비로 표시하지 않는다.
4. 커넥터가 붙고 위 연결 조건을 만족하면 `보드 커넥터 연결됨 · 연결 준비 완료`를 표시하고 해당 전이에서 한 번 알린다. 보드 수/COM과 연결된 runner를 함께 표시한다. 보드 미선택은 별도 `보드 설정 필요`로 표시하며 연결 준비 알림을 숨기지 않는다.
5. 이 준비는 플러그인↔서비스↔커넥터 통신 준비다. 보드 부팅·이미지/BAT·TC·장비 예약/UNKNOWN·설정 실제 적용의 실행 조건은 별도 표시하고 `preview/start`에서 서버가 검증한다. 연결만으로 `장비 시험 준비 완료`나 PASS를 만들지 않는다.
6. 연결 단절·stale에는 즉시 대기/오래된 정보 표시로 낮추고 마지막 확인 시각·원인·조치를 보인다. 같은 정상 상태 폴링마다 알림을 반복하지 않으며 복구 전이에만 다시 알린다. 플러그인 재실행은 기존 Run/명령 ID로 재조회하고 수락된 작업을 다시 start하지 않는다.
7. 사용자 명령을 다시 입력하지 않아도 플러그인 상태 패널이 갱신된다. 플러그인이 비활성·종료 상태인 동안 OS 알림이나 Windows 자동 실행은 요구하지 않는다. 종료해도 상주 서비스/Run은 유지한다.

## SETTINGS의 상호 갱신과 적용 확인

- 플러그인·Agent Monitor·보드 커넥터의 공통 TC/이미지 경로·기본 패턴·프로파일·제한시간은 Linux 공통 설정 API를 사용한다. 어느 화면에서 바꿔도 다른 활성 화면은 재조회해 저장 revision과 값을 갱신한다. 플러그인을 유일한 덮어쓰기 기준으로 삼지 않는다.
- 편집 시작 revision을 보관하고 저장 시 CAS를 사용한다. 동시 저장의 409는 충돌과 최신 서버값/사용자 초안을 표시하고 다시 편집하게 한다. 폴링으로 미저장 초안을 덮거나 충돌한 요청을 새 revision으로 자동 재전송하지 않는다.
- Windows 보드/COM/PuTTY/TC Python/플래싱의 로컬 설정은 Windows가 소유한다. 플러그인·Agent Monitor에서 변경하면 중앙 desired 저장 `PENDING` → 미러 `apply-settings` → 실제 Windows/Host receipt `APPLIED`를 확인한다. `BLOCKED/FAILED/EXPIRED/UNKNOWN`은 그대로 사유와 조회 경로를 표시하고 자동 재실행하지 않는다. 명령 접수와 설정 적용 receipt는 각각 확인한다.
- Windows에서 바꾼 로컬 설정은 현재 projection/revision으로 플러그인·Agent Monitor에 표시한다. 로컬 실제 설정을 과거 중앙 desired로 자동 덮지 않으며 Windows 최신 revision과 충돌한 적용 요청은 거부한다. 공통 설정 문서와 실제 Windows projection의 소유권을 합쳐 새 설정 저장소를 만들지 않는다.
- SSH 자격·키·계정과 Windows 파일 선택은 Windows 로컬 최초 연결 경계를 따른다. Linux 경로와 Windows 실제 작업 경로를 구분하고 비공개 값은 공유 payload/로그에 넣지 않는다.
- 수락된 Run은 source/config/timeout/profiles snapshot을 유지한다. 상호 변경은 이후 준비/Run에 적용하며 진행 중·예약·UNKNOWN에 안전하지 않은 Windows 적용을 강제하지 않는다. 기존 명시 timeout/기존 기록과 다른 세션의 기본값 변경 WIP는 보존한다.

## 리뷰로 줄이거나 분리한 동작

- 전체 요약은 `status`, 보드 상세는 `status --boards`, 진단은 `status --diagnose`, Run 요약은 `test status --report`로 묶는다. 초기 제안 `boards/doctor/test report`가 회사 UI 별칭으로 필요해도 같은 내부 조회/결과 형식을 재사용하고 별도 처리기를 만들지 않는다. 진단은 연결을 시작하거나 설정을 변경하지 않으며 연결 준비가 실패해도 원인을 읽을 수 있다.
- `analyze`는 기본 조회다. 첫 실패의 영속 분석과 기존 단일 소비자를 재사용하고 사람이 조회할 때마다 AI 분석을 새로 실행하지 않는다. `--requeue`는 명시 재분석 의도이며 조치 검증·종료 확인·재실행 gate를 우회하지 않는다.
- `pause`는 진행 중 BAT/TC를 즉시 동결하는 명령이 아니다. 요청/안전 경계 대기/실제 PAUSED를 나눠 표시한다. `cancel`도 종료 확인 전 취소 완료로 표시하지 않는다. `resume`은 분석 latch·UNKNOWN·예약을 지우지 않는다.
- `test status --report`는 기존 근거 요약으로 충분하다. 별도 결과 schema, 플러그인 임의 PASS 쓰기, standalone flash/임의 shell 실행 명령은 초기 범위에 넣지 않는다.
- `test runs`, `test reconcile`, 최초 연결 `connect export`, 프로파일 설정은 누락 보완이다. 새 BSP 작업 전체 명령은 기존 회사 플러그인과 `BspPluginClient`를 재사용하며 이번 TC 명령 설계로 대체하지 않는다.
- 설치/start는 기존 설치 hook에서 처리한다. update/restart/reset/delete/force-stop은 별도 유지보수 범위이며 초기 일상 명령에 혼합하지 않는다. 특히 연결 실패나 창 닫기로 reset/강제 종료를 호출하지 않는다. 비상 종료의 다른 세션 미게시 구현·안내는 이번 고정 코드 기준의 기능으로 전제하지 않으며 별도 전달 단위에서 다룬다.

## 회사 변경 위치·이전·복원

| 원본 접점 | 재사용/회사 조정 | 확인할 근거 |
|---|---|---|
| `backend/gui_test/standalone/plugin_client.py` | HTTP·identity·멱등·CAS·Run 조회는 재사용, 회사 slash 등록/인자·선택/감시/알림 adapter 추가 | `connect`, `start`, `action`, `runs`, settings/profile/analysis/bootstrap 메서드 |
| `backend/gui_test/core/shared_settings.py`, `api/shared_control.py` | 공통 설정·Windows desired/receipt 계약 유지 | revision 충돌, 기존 Run snapshot·실제 Host 적용 |
| `backend/gui_test/core/integration.py`, `api/router.py` | 기존 준비·실행·제어만 호출, 실행 엔진 재작성 없음 | 고정 token, 버전·중복 키, pause/cancel/reconcile |
| `backend/gui_test/connector/supervisor.py`, `connector/mirror.py` | 기존 Windows 상태 게시·명령 claim·receipt 재사용 | 최신성·session/revision·pending/unknown; 전체 필드는 미러 계약 참조 |
| `packages/gui-test-ui/src/SharedControl.tsx`, `ConnectorMirror.tsx` | 회사 설정/상태 화면 접점 대응 | 초안·CAS·적용 receipt·서비스 인증/브라우저 CSRF |
| `backend/gui_test/tests/test_plugin_integration_http.py`, `test_plugin_integration_diagnostics.py`, `test_plugin_control_workflow.py`, `test_shared_control.py`; `tests/test_connector_mirror_http.py` | 기존 시험을 회사 adapter 회귀에 연결 | 아래 CMD-A 및 원본 T-240~246/260~269와 별도 회사 증거 |

회사 명령 등록 파일·알림 API·세션 저장 경로는 원본에 없으므로 추정하지 않는다. 회사 `COMPANY_MAP.md`에 각 대응 경로와 차이를, `APPLIED.md`에 명령별 구현·부분 적용·시험·원본/회사 커밋을 남긴다. 이 문서 추가에 따른 API/DB/설정 이전은 없다. 후속 adapter의 선택 문맥은 서비스/runtime/runner/프로젝트/Run을 함께 저장하고 다른 프로젝트나 서비스의 마지막 ID를 재사용하지 않는다. 실행ID 생략은 `test select`로 명시 선택한 동일 문맥의 Run에만 허용한다. 명시 선택이 없거나 실행 대상이 여러 개면 ID 또는 선택을 요구하며 임의의 최신 Run을 취소하지 않는다. 제어 직전 최신 version과 controller를 다시 확인한다. 제어권 충돌은 기존 `transfer-control` 절차를 따른다.

복원은 회사 명령 등록/adapter와 관련 안내의 해당 변경만 역변경한다. runtime·DB·설정·Run·실패/명령 receipt·기존 Windows Manager를 초기화하지 않는다. 단일 Worker·기존 BSP 운영 게이트·최종 사람 검토와 회사 추가 기능을 보존한다.

## 구현 후 인수할 사례

현재 아래 사례는 모두 **NOT_RUN**이다. 설계 읽기·문서 검사·리뷰가 제품 인수를 대체하지 않는다.

| 설계 사례 | 검증 내용 | 현재 결과 |
|---|---|---|
| CMD-A01 | Linux만 준비→커넥터 대기, 뒤늦은 Windows 연결→한 번 준비 알림, 보드 미선택 별도 표시 | NOT_RUN |
| CMD-A02 | stale/단절→준비 표시 해제, 재연결→한 번 알림, identity 불일치/구형 capability 거부 | NOT_RUN |
| CMD-A03 | 세 화면 각각 공통 설정 변경→다른 화면 갱신, 초안 유지, 동시 CAS 저장 409·값 손실 없음 | NOT_RUN |
| CMD-A04 | 양방향 Windows 로컬 설정 표시, PENDING/APPLIED 구분, busy/UNKNOWN/EXPIRED·revision 충돌·오래된 receipt | NOT_RUN |
| CMD-A05 | preview 비동기·token 만료/변경, integration 목록 scope, HTTP 응답 유실의 같은 key, 재접속에서 중복 실행 없음 | NOT_RUN |
| CMD-A06 | 여러 Run/프로젝트/서비스·제어권 선택, pause 안전 경계·cancel 종료 확인·UNKNOWN reconcile·분석 latch 보존 | NOT_RUN |
| CMD-A07 | 기본 분석 조회는 실행 없음, 명시 requeue의 ID/version·단일 소비자, 보고서와 실제 Run 결과 일치 | NOT_RUN |
| CMD-A08 | 회사 slash 등록·bootstrap 전달·로그 follow·브라우저 scope·설정 편집·플러그인 닫은 뒤 Run 지속, 실제 Windows/SSH/COM/BAT/TC | NOT_RUN |

회사 적용 담당자는 명령 adapter 구현 후 기존 T 시험과 CMD-A를 실행하고 실제 Linux/Windows·장비 인수는 승인된 범위에서 별도 기록한다. 이 문서는 구현/자동 장비 실행/모델 호출의 추가 승인이 아니다.
