# 문서 지도

기준일: 2026-10-11. 문서 작성 완료와 제품 구현 완료는 별개다. 이 문서 묶음은 기존 계획 v0.8의 운영 정책을 유지하고 구현 가능한 상세안으로 분리했다. 기술 선택은 별도 채택 기록 전까지 제안이다.

| 문서 | 내용 | 주 갱신 책임 |
|---|---|---|
| [종합 계획](BSP_OS_UPGRADE_DASHBOARD_PLAN.md) | 사용자 합의·기존 결정 이력 | Claude 검토 / 변경자 |
| [요구사항](requirements/REQUIREMENTS.md) | 범위·필수 동작·인수 조건 | Claude 검토 / Codex 반영 |
| [시스템 구조](architecture/SYSTEM_ARCHITECTURE.md) | 실행 위치·구성요소·기술 기준안 | Claude 검토 / Codex 검증 |
| [상태와 실행 순서](design/WORKFLOW_AND_STATE.md) | 게이트·잠금·복구·진행률 | Codex 구현 / Claude 검토 |
| [데이터 모델](design/DATA_MODEL.md) | 영속 정보·불변 조건·이전 | Codex 구현 / Claude 검토 |
| [API와 외부 연동](design/API_AND_INTEGRATIONS.md) | 명령·상태·SSH·Jira·수동 결과 | Codex 구현 / Claude 검토 |
| [에이전트 운영](design/AGENT_ORCHESTRATION.md) | 도구 선택·전환·리뷰·세션 | Codex 구현 / Claude 검토 |
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

`NOT_RUN`은 아직 시험하지 않았다는 뜻이다. `PASS`는 해당 실행 증거가 있는 결과만 의미한다. Claude 검토와 실제 Linux/장비/Jira 검증은 아직 완료하지 않았다.
