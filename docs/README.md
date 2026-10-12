# 문서 지도

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
| [오케스트레이터 명세](design/ORCHESTRATOR_SPEC.md) | 작업별 Claude의 책임·권한·호출·제안 계약·장애/중복 처리. 미구현 설계 | Codex 구현 / Claude·외부 에이전트 담당 검토 |
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

외부에서 개발한 에이전트를 연결할 때는 **오케스트레이터 명세 → 상태·결과 보고 계약 → BSP 역할 지침 → 에이전트 운영** 순으로 읽는다. 조정 호출/제안 필드는 오케스트레이터 명세, 모듈 요청/보고 필드는 상태·결과 보고 계약에서 단독 관리한다. 모듈 v1은 현재 구현, 모듈 v2와 오케스트레이터 판단 계약은 미구현 설계다.

`NOT_RUN`은 아직 시험하지 않았다는 뜻이다. `PASS`는 해당 실행 증거가 있는 결과만 의미한다. Claude 검토와 실제 Linux/장비/Jira 검증은 아직 완료하지 않았다.

## Claude에서 직접 실행할 오케스트레이터

- [사용·입력 준비·응답 검사·다른 서버로 내보내기](agents/CLAUDE_ORCHESTRATOR_GUIDE.md)
- [Claude agent 정의](../.claude/agents/bsp-upgrade-orchestrator.md)
- [패키지 및 기존 기능 회귀 시험](testing/runs/20261012-claude-agent-package.md)

수동 호출 패키지는 제공되며, 자동 대시보드 조정 O1~O5와 보고 v2는 아직 구현 전이다.

[작업 폴더 기반 내장 도구 연결·환경 설정](agents/ENVIRONMENT_AND_BRIDGES.md): 기본은 native 자동 탐지이며 사용자 브리지 제작은 불필요하다. 기존 브리지는 고급 호환 모드다. 실제 Linux/모델/BSP 인수는 별도 확인한다.
