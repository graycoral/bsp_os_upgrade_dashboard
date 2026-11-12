# 문서 지도

공통 정책은 [AGENTS.md](../AGENTS.md), 현재 범위와 미완료는 [현재 상태](implementation/CURRENT_STATUS.md), 누적 증거는 [진행 기록](implementation/WORK_STATUS.md)을 따른다. 작업에 해당하는 절과 코드·시험부터 확인한다.

| 작업 | 읽기 경로 |
|---|---|
| Git 정리·커밋·머지·푸시 | 공통 정책과 Git 상태·대상 변경을 확인한다. 충돌 해결에 제품 수정이 필요하면 관련 계약·코드·시험으로 확장한다. |
| 문서만 변경 | 관련 원문 절과 변경 범위를 확인하고 링크·ID를 검증한다. |
| 일반 개발 | 관련 [요구사항](requirements/REQUIREMENTS.md)·[결정](governance/DECISIONS.md) → 관련 [구조](architecture/SYSTEM_ARCHITECTURE.md)·설계·코드 → [구현 계획](implementation/IMPLEMENTATION_PLAN.md)·[시험 목록](testing/TEST_CATALOG.md)과 관련 결과 |
| 상태·데이터·연동 | [상태](design/WORKFLOW_AND_STATE.md), [데이터](design/DATA_MODEL.md), [API](design/API_AND_INTEGRATIONS.md) 중 관련 계약 → 코드·시험 |
| 외부 BSP 에이전트·조정 | [오케스트레이터 명세](design/ORCHESTRATOR_SPEC.md) → [보고 계약](design/AGENT_STATUS_CONTRACT.md) → [역할](roles/RUNTIME_ROLES.md)·[운영](design/AGENT_ORCHESTRATION.md) → 코드·시험. 현재/목표 버전을 구분한다. |
| GUI Test·화면 | [GUI Test 문서](gui_test/README.md) → [화면](design/UI_SPEC.md)·[실행 계약](design/GUI_TEST_CONTRACT.md) → 관련 코드·시험 |
| TEST BOARD CONNECTOR (구 Windows Runner) | [TEST BOARD CONNECTOR 사용 안내](gui_test/WINDOWS_RUNNER.md)·[편집 가능한 배포](gui_test/WINDOWS_RUNNER_EDITABLE.md) → 관련 [실행 계약](design/GUI_TEST_CONTRACT.md)·코드·시험 및 해당 PORT |
| 회사 전달·이식 | [portable-feature](../.agents/skills/portable-feature/SKILL.md)·[이식 절차](porting/README.md) → 해당 PORT → 회사 구조·적용 이력 → 코드·시험 → 필요한 설계 |
| 검증·회귀 | [시험 계획](testing/TEST_PLAN.md)·[목록](testing/TEST_CATALOG.md) → [결과](testing/TEST_RESULTS.csv)·[회귀 기록](testing/REGRESSION_LEDGER.md)·[기준](testing/BASELINE.md) 및 해당 실행 기록 |

공통 구조, 데이터 이전, 계약 충돌 또는 불명확한 의존성이 영향을 받으면 필요한 원문으로 확장한다. [변경·검토 절차](governance/CHANGE_AND_REVIEW.md)와 [문서 검증](testing/DOC_VALIDATION.md)을 적용한다. `PASS`는 해당 실행의 증거에 한하며 `NOT_RUN`은 미실행이다. 날짜별 기존 지도 내용은 [진행 기록](implementation/WORK_STATUS.md#2026-11-07--문서-지도-이력-보존)에 보존한다.

## Claude에서 직접 실행할 오케스트레이터

- [사용·입력 준비·응답 검사·다른 서버로 내보내기](agents/CLAUDE_ORCHESTRATOR_GUIDE.md)
- [Claude agent 정의](../.claude/agents/bsp-upgrade-orchestrator.md)
- [패키지 및 기존 기능 회귀 시험](testing/runs/20261012-claude-agent-package.md)

수동 호출 패키지는 제공된다. 자동 조정 O1~O4와 보고 v2는 별도 opt-in 로컬 구현·모의 검증을 완료했으며 O5 실제 외부 인수는 미완료다. 수동 패키지는 자동 경로와 연결되지 않는다.

[작업 폴더 기반 내장 도구 연결·환경 설정](agents/ENVIRONMENT_AND_BRIDGES.md): 기본은 native 자동 탐지이며 사용자 브리지 제작은 불필요하다. 기존 브리지는 고급 호환 모드다. 실제 Linux/모델/BSP 인수는 별도 확인한다.

## GUI Test 요구사항 원본

[GUI Test 문서 모음](gui_test/README.md): 공통 요구사항, Dashboard 통합 요구사항, GitHub 모듈 구현 계획 및 현재 구현 문서 링크.

## GUI Test 현재 기준

[요구사항 RQ-39~43](requirements/REQUIREMENTS.md) → [화면](design/UI_SPEC.md) → [실행·저장·어댑터 계약](design/GUI_TEST_CONTRACT.md) → [게시 검증](testing/runs/20261102-publication.md). 중간 시안과 과거 PASS는 해당 실행 시점의 이력이며 현재 실환경 인수를 의미하지 않는다.

## 자동 이미지 퓨징·TC

[RQ-47/D-48 자동 퓨징 계약과 환경 설정](design/AUTOMATIC_FLASH_TEST.md), [구현·검증 기록](testing/runs/20261103-automatic-flash-test.md). 사용자 승인한 자동 프로파일에만 적용하며 기본 수동 방식과 최종 검토는 유지한다. 실제 배치·보드 인수는 별도다.

RQ-59 실행·진단: [명령 계약](design/SETUP_COMMANDS.md), [사용 안내](gui_test/RUN_AND_DIAGNOSE.md), [PORT-006](porting/PORT-006.md).

RQ-60 회사 역할별 적용·사용: [BSP 업그레이드 플러그인 안내](gui_test/BSP_UPGRADE_COMPANY_GUIDE.md), [PORT-007](porting/PORT-007.md).

현재 RQ-59 ZIP 및 로컬 검증 결과는 [실행 기록](testing/runs/20261106-setup-commands.md)에 있다. 회사 인수는 별도다.

## BSP Upgrade 플러그인 연동 · RQ-60 / D-64

[설계](design/BSP_UPGRADE_PLUGIN_INTEGRATION.md), [구현 요청서](agents/BSP_UPGRADE_PLUGIN_REQUEST.md), [PORT-007](porting/PORT-007.md), [설계 문서 작업 기록](testing/runs/20261107-bsp-upgrade-integration-docs.md). 최초 문서 단계는 DESIGN_ONLY / IMPLEMENTATION_NOT_STARTED였고 후속 지시로 구현이 승인되었다.

후속 로컬 구현·독립 리뷰 및 모의 시험은 [구현 검증 기록](testing/runs/20261107-bsp-upgrade-integration.md)을 따른다. T-208은 부분 패키지 근거만 확보했고 T-209 회사 인수는 NOT_RUN이다.

## TEST BOARD CONNECTOR · RQ-61 / D-65

[계획](design/EDITABLE_WINDOWS_RUNNER_PLAN.md), [실행 안내](gui_test/WINDOWS_RUNNER_EDITABLE.md), [PORT-008](porting/PORT-008.md), [최종 시험](testing/runs/20261107-editable-windows-runner.md). 독립 리뷰 APPROVED 및 T-210~216 로컬 PASS, T-217 회사 인수 NOT_RUN이다.
