# PORT-012 · 모듈 선택과 시작 자동 검사

RQ-75/76 · D-82 · T-288~290. 2026-11-18 작업 기록의 기준 HEAD는 `a0b53cd4813e95b6d39f7d0ad02c0e5a13f2f6fc`와 기존 WIP였다. 그 시점에는 변경이 미커밋이었고 묶음 전체의 게시 pin을 기록하지 않았다. 적용 대상 파일과 시험의 출처는 실제 전달 commit/manifest로 확인한다. 배포 전 이번 소스·시험 hash와 검증 결과를 [실행 기록](../testing/runs/20261118-dashboard-workflow.md)과 대조하고 전달 커밋을 고정해야 한다.

## 적용 위치와 선행 조건

full Agent Monitor와 `BspPluginClient`의 기존 `bsp-control-v1`·runtime/package pin·loopback 연결이 필요하다. GUI-only standalone에는 모듈 게시 기능을 추가하지 않는다.

| 담당 | 적용 위치 | 연결 |
|---|---|---|
| 서버 | `backend/services/module_catalog.py`, `backend/api/main.py` | 기존 `dashboard.db`/`meta`와 모듈 게시 API. [계약](../design/PLUGIN_MODULE_CATALOG.md) |
| 플러그인 | `backend/gui_test/standalone/bsp_plugin_client.py` | 회사 영속 모듈을 `module_catalog()`/`publish_modules()`에 연결. 세션·모델 응답으로 자동 대체 금지 |
| Dashboard | `apps/web/src/PluginModules.tsx`, `main.tsx` | 모듈 콤보박스·Jira 설정/검토 탭 숨김·구 URL의 대시보드 fallback |
| 공통 Test UI | `packages/gui-test-ui/src/TestPage.tsx` | 별도 Preflight 버튼 제거·시작 내부 서버 검사·차단 이유·동시 요청 방지 |

회사 모듈 이름·stable key·상대 대상 경로·선행 그룹을 기존 모듈 데이터에서 매핑한다. 게시 성공은 후보 목록 수신이며 저장된 선택이나 기존 job 변경을 뜻하지 않는다. 회사 구조 대응·부분 적용과 인수 결과는 현지 `COMPANY_MAP.md`/`APPLIED.md`에 기록한다.

## 보존과 복원

DB schema 이전과 새 의존성은 없다. 새 후보 JSON은 `meta.plugin_module_catalog` 한 항목이다. 기존 config/job/모듈/예약·Jira 설정/판단 이력은 보존한다. Jira 설정 패널과 별도 검토 탭 제거는 backend Jira 동작·판단 게이트 폐지가 아니다. 기존 자동 Jira 동기화 정책을 바꾸려면 별도 운영 정책 변경이 필요하다.

시작은 기존 `Manager.start()`의 Preflight·소스/revision·명령·연결·예약·UNKNOWN 검사를 사용한다. 단순 방문·TC 선택·후보 수신으로 Run을 만들지 않는다. UI·API·Worker 소유권을 함께 유지하며 새 hardware 실행권이나 자동 장비 실행을 부여하지 않는다.

복원은 이전 코드·UI 자산으로 되돌리고 같은 runtime을 유지한다. 추가 meta 항목은 이전 코드가 사용하지 않으며 삭제할 필요가 없다. 실제 실행 중에는 기존 안전 종료/복구 절차를 먼저 따른다.

## 검증

`tests/test_plugin_module_catalog.py`, `test_bsp_plugin_client.py`, `test_api.py`, `test_settings.py`, 공통 core/commands/sources/timeouts/module_selection 시험과 설정·소스·조정·GUI 브라우저 회귀를 사용한다. 실제 수행 결과는 [실행 기록](../testing/runs/20261118-dashboard-workflow.md)을 따른다. 회사 플러그인 callback 연결, Windows·SSH·실장비 T-290은 NOT_RUN이다.
