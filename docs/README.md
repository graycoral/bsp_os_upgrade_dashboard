# 문서 지도

재사용 기능 개발과 회사 이식은 [portable-feature 스킬](../.agents/skills/portable-feature/SKILL.md)과 [이식 절차](porting/README.md)를 따른다.

2026-11-06 RQ-55/D-59 Test 설정 간결화: [공통 화면 명세](design/UI_SPEC.md), [실행·독립 리뷰 기록](testing/runs/20261106-compact-test-settings.md). 전역 환경 설정과 Test 현황 내부 설정을 같은 단일 카드·항목 콤보·기본값으로 제공하며 상세 입력은 필요할 때 펼친다. TC 목록·실행·결과는 Test 현황에만 유지한다.

2026-11-06 RQ-57/D-61/DEVPORT02: [GUI host·UI 이식 계약](design/UI_PORTABILITY.md), [고정 코드 기준 PORT-004](porting/PORT-004.md), [기존 작업 트리 기록](testing/runs/20261106-portability.md), [병합 코드 검증](testing/runs/20261106-portability-merge.md). --base 누적 patch는 폐기하고 명시적 source-only host target을 사용한다. 병합 코드 독립 리뷰 APPROVED, 로컬 시험과 Linux CI 대기 범위는 실행 기록에 구분하며 회사 인수 T-190은 NOT_RUN이다.

2026-11-06 TC 소스 설정 RQ-56/D-60: [소스 준비·실행 계약](design/GUI_TEST_CONTRACT.md), [소스 편집 화면](design/UI_SPEC.md), [실행·독립 리뷰 기록](testing/runs/20261106-settings-sync.md). 서버 폴더 또는 GitHub/Gerrit clone URL을 확인하고 실제 ref를 선택·적용한다. Runner 연결과 소스 준비를 구분하고 legacy/Mock/실제 연결 및 과거 Run의 고정 기준을 보존한다.

2026-11-06 전체 설정·탭별 편집 공유 RQ-55/D-59: [화면 명세](design/UI_SPEC.md), [요구사항](requirements/REQUIREMENTS.md), [설정 동기화 실행·독립 리뷰 기록](testing/runs/20261106-settings-sync.md). BSP 폼과 GUI 편집기를 유지하여 미저장 입력을 공유하고 그룹/전체 접기를 제공한다. 보기 모드는 환경 설정과 Test 현황 내부 설정에서 같은 선택을 편집하며 명시적 적용/재로드를 유지한다.

2026-11-06 O1~O4·모듈 v2·복구: [현재 구현/도입·백업 절차](agents/ORCHESTRATION_V2_OPERATIONS.md), [로컬 검증·독립 리뷰 기록](testing/runs/20261106-orchestration-v2.md). 기본 v1·조정 OFF이며 새 job에만 opt-in한다. 실제 Linux/모델/장비/Jira 인수와 운영 baseline은 미완료다.

2026-11-05 GUI Test 구조 분리 RQ-54/D-57: [앱·Python·공유 UI 경계](design/GUI_TEST_LAYOUT.md), [독립 Windows 빌드·설치](gui_test/WINDOWS_BUILD.md), [검증·독립 리뷰 진행 상태](testing/runs/20261105-gui-test-layout.md). 소스는 `backend.gui_test.*`, 설치 wheel은 기존 `gui_test.*`이며, 이전 한 폴더 복사는 세 경로 독립 내보내기로 대체한다.

2026-11-05 Test 현황 후속: [모듈별 TC 자동 목록·서버 문맥 검증](design/MODULE_TC_SELECTION.md), [TC 소스 Git 계약](design/GUI_TEST_CONTRACT.md), [화면 명세](design/UI_SPEC.md), [현재 구현·검증 기록](testing/runs/20261104-test-results-cleanup.md). 모드 선택의 환경 설정 전용 배치는 위 RQ-55의 공유 편집으로 대체하며 실제 Runner/장비 인수는 로컬 시험과 구분한다.

Windows Runner 포터블 EXE: [사용·빌드 안내](gui_test/WINDOWS_RUNNER_PORTABLE.md), [패키징 설계](design/WINDOWS_RUNNER_BUNDLE.md). RQ-51/D-53의 로컬 빌드·모의 검증과 회사 인수 T-160를 구분한다.

현재 전달 코드 기준은 `ab4580c36f1aad2ab627a1f12beb440da7004845`다. [다이어그램 이식](porting/PORT-001.md), [종합 화면·공통 모션 이식](porting/PORT-002.md)을 참조한다. 이전 다이어그램 검증 이력: [화이트 테마·37개 회귀](testing/runs/20261104-workflow-diagram-light-groups.md), [배율·36개 회귀](testing/runs/20261104-workflow-diagram-zoom.md), [오른쪽 펼침](testing/runs/20261104-workflow-diagram-rightward.md). 회사/ACON 인수는 별도다.

별도 생성한 과거 참고 자료는 [다이어그램 디자인](diagram-design-20261103/README.md), [시스템 다이어그램](system-diagram-20261103/README.md)에 보존한다.

실제 사용 시작: [단계별 Linux/Windows 설정 마법사](gui_test/SETUP_WIZARD.md). 설치·빌드·입력 저장/변경·보호된 토큰·연결 점검·이미지 설정을 제공한다.

회사판으로 기능을 가져갈 때: [이식 절차·Claude/OpenCode 요청문](porting/README.md). 해당 기능 안내서와 회사 구조 차이·적용 이력부터 확인하고 관련 코드·시험·설계로 범위를 넓힌다. 일반 원본 개발의 읽기 순서는 아래와 같다.

2026-11-03 다이어그램 탭 **로컬 구현·모의 검증 완료**: [RQ-50 상세 설계](design/WORKFLOW_DIAGRAM.md), [PORT-001 이식 안내](porting/PORT-001.md), [32개 시험·두 빌드·독립 리뷰 결과](testing/runs/20261103-workflow-diagram-implementation.md). 이전 [문서 작성·검사 기록](testing/runs/20261103-workflow-diagram-docs.md)은 설계 당시 이력으로 보존한다. 실제 회사/ACON 인수 T-149는 별도다.

후속 [동작·효율성·연동 리뷰](testing/runs/20261103-workflow-diagram-review.md): 현재 코드와 대조해 상태/연결 표시·조회 신선도·호스트 접점·100개 모듈 효율/이식 시험 기준을 보완했다. 문서 개선이며 제품 구현·회사 인수 완료가 아니다.

2026-11-03 최신 추가: [Windows 공유 TC 실행기](gui_test/WINDOWS_RUNNER.md), [빌드 스크립트](../scripts/README.md), [사용자 요구사항 RQ-46](requirements/REQUIREMENTS.md), [D-47 결정](governance/DECISIONS.md), [검토·시험 기록](testing/runs/20261103-windows-runner.md).

기준일: 2026-10-12. 로컬 1차 구현의 실행 방법은 [루트 README](../README.md), 실제 구현/검증 범위는 [진행 기록](implementation/WORK_STATUS.md)을 따른다. 문서 작성 완료와 제품 구현 완료는 별개다. 이 문서 묶음은 기존 계획 v0.8의 운영 정책을 유지하고 구현 가능한 상세안으로 분리했다. 기술 선택은 별도 채택 기록 전까지 제안이다.

| 문서 | 내용 | 주 갱신 책임 |
|---|---|---|
| [종합 계획](BSP_OS_UPGRADE_DASHBOARD_PLAN.md) | 사용자 합의·기존 결정 이력 | Claude 검토 / 변경자 |
| [요구사항](requirements/REQUIREMENTS.md) | 범위·필수 동작·인수 조건 | Claude 검토 / Codex 반영 |
| [시스템 구조](architecture/SYSTEM_ARCHITECTURE.md) | 실행 위치·구성요소·기술 기준안 | Claude 검토 / Codex 검증 |
| [상태와 실행 순서](design/WORKFLOW_AND_STATE.md) | 게이트·잠금·복구·진행률 | Codex 구현 / Claude 검토 |
| [데이터 모델](design/DATA_MODEL.md) | 영속 정보·불변 조건·이전 | Codex 구현 / Claude 검토 |
| [API와 외부 연동](design/API_AND_INTEGRATIONS.md) | 명령·상태·SSH·Jira·수동 결과 | Codex 구현 / Claude 검토 |
| [에이전트 운영](design/AGENT_ORCHESTRATION.md) | 도구 선택·전환·리뷰·세션 | Codex 구현 / Claude 검토 |
| [오케스트레이터 명세](design/ORCHESTRATOR_SPEC.md) | 작업별 Claude의 책임·권한·호출·제안 계약·장애/중복 처리. opt-in 로컬 구현·모의 검증 완료 | Codex 구현 / Claude·외부 에이전트 담당 검토 |
| [에이전트 상태·결과 보고 계약](design/AGENT_STATUS_CONTRACT.md) | 외부 에이전트 전달용: 필수 필드·보고 시점·JSON 예시·실제 지원 범위 | Codex 구현 / Claude·외부 에이전트 담당 검토 |
| [화면 명세](design/UI_SPEC.md) | 종합 진행도·모듈 표·상세·설정 | Codex 구현 / 사용자 확인 |
| [BSP 역할 지침](roles/RUNTIME_ROLES.md) | 실행 중 각 에이전트의 입력·출력·제약 | Claude 검토 / Codex 연결 |
| [구현 계획](implementation/IMPLEMENTATION_PLAN.md) | 단계별 수정 파일·종료 조건 | Codex |
| [진행 기록](implementation/WORK_STATUS.md) | 수행·미수행·다음 작업 | 작업 수행자 |
| [결정 기록](governance/DECISIONS.md) | 확정 정책·제안·환경 미결정 | 결정/검토 담당 |
| [변경·검토 규칙](governance/CHANGE_AND_REVIEW.md) | 변경 영향·리뷰·문서 동기화 | 모든 작업자 |
| [테스트 계획](testing/TEST_PLAN.md) | 시험 구분·증거·통과 규칙 | Codex / 실제 시험자 |
| [테스트 목록](testing/TEST_CATALOG.md) | 요구사항별 구체적 시험 | Codex / Claude 검토 |
| [최신 결과 CSV](testing/TEST_RESULTS.csv) | 현재 기준 시험 결과 요약 | 시험 실행자 |
| [실행 이력 규칙](testing/runs/README.md) | 실패와 재시험 보존 형식 | 시험 실행자 |
| [회귀 기록](testing/REGRESSION_LEDGER.md) | 재발 원인·수정·방지 시험 | 수정자 |
| [정상 기준](testing/BASELINE.md) | 검증된 버전과 롤백 기준 | 검증 담당 |
| [문서 검사](testing/DOC_VALIDATION.md) | 링크·추적성·결과 형식 점검 | 문서 변경자 |

읽는 순서: 지침 → 요구사항 → 구조 → 해당 상세 설계 → 구현 단계 → 시험 목록·결과·회귀 기록. 기존 종합 계획은 합의의 출처이며, 상세 문서는 구현 계약이다. 충돌 시 확정 운영 정책을 우선하고 충돌을 해소한 뒤 구현한다.

외부에서 개발한 에이전트를 연결할 때는 **오케스트레이터 명세 → 상태·결과 보고 계약 → BSP 역할 지침 → 에이전트 운영** 순으로 읽는다. 조정 호출/제안 필드는 오케스트레이터 명세, 모듈 요청/보고 필드는 상태·결과 보고 계약에서 단독 관리한다. 모듈 v1은 기본 경로이며 v2와 조정 판단은 새 job opt-in 로컬 구현·모의 검증 완료이다. 현재 capability와 실제 인수 범위는 위 도입 안내를 따른다.

`NOT_RUN`은 아직 시험하지 않았다는 뜻이다. `PASS`는 해당 실행 증거가 있는 결과만 의미한다. Claude 검토와 실제 Linux/장비/Jira 검증은 아직 완료하지 않았다.

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
