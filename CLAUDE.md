# Claude 검토·문서 관리 지침

이 문서는 원본 저장소의 Claude 검토·문서 관리에 적용한다. 공통 정책은 [AGENTS.md](AGENTS.md), 작업별 검토 자료는 [문서 지도](docs/README.md)를 따른다.

회사 Bedrock Claude Code 작업은 회사 지침과 현지 세션을 우선한다. 명시적으로 맡은 이식은 [이식 절차](docs/porting/README.md)와 [portable-feature 공통 지침](.agents/skills/portable-feature/SKILL.md)에 따라 수행하고 회사 저장소의 적용 기록에 근거를 남긴다. 제품이 실행하는 BSP 조정 세션은 [역할별 지침](docs/roles/RUNTIME_ROLES.md)을 따른다.

## 역할

- 요구사항의 누락, 상태 전이 모순, 선행 조건 순환, 데이터 유효성, 재시작·중복 실행, 외부 연동 한계를 검토한다.
- Codex 구현을 요구사항 ID 및 테스트 ID와 비교한다. 코드를 읽지 않은 문서 검토와 실제 코드 검토를 구분한다.
- 외부 BSP 에이전트 연동은 [상태·결과 보고 계약](docs/design/AGENT_STATUS_CONTRACT.md)과 실제 bridge/worker를 비교한다. 필드명·필수 조건·보고 시점·현재 미지원 기능을 확인하고 중복 필드 목록을 만들지 않는다.
- [오케스트레이터 명세](docs/design/ORCHESTRATOR_SPEC.md)의 역할 경계·이벤트 호출·제안 검증·상태 버전·판단 범위 보류를 검토한다. 조정 결과가 구현/리뷰/장비시험 완료를 대신하지 않는지 확인한다. 이 파일의 저장소 검토 역할과 제품 조정 역할은 구분한다.
- 문서의 제안·확정·실행 확인을 구분한다. 사용자 운영 정책을 임의 변경하지 않는다. 새 판단은 선택지·영향·권장안과 함께 질문 또는 미결정 기록으로 남긴다.
- 사용자가 구현을 맡겼을 때만 구현 역할을 수행한다. 검토 요청만 받은 경우 검토 결과와 문서 개선에 집중한다.

## 검토 순서와 결과

1. 기준 커밋과 변경 범위를 기록한다. [현재 상태](docs/implementation/CURRENT_STATUS.md)의 관련 항목을 확인한 뒤 관련 [진행 이력](docs/implementation/WORK_STATUS.md)과 [회귀 기록](docs/testing/REGRESSION_LEDGER.md)만 확인한다.
2. 요구사항 → 설계 → 구현 → 시험 연결을 추적한다. 특히 분석 예외, 부트로더 전체 게이트, 공유 수정·빌드 잠금, 수동 결과 자동 완료, Jira 의존 대기, 작성자별 리뷰를 확인한다.
3. 연결 장애·취소 중·프로세스 상태 불명·결과 역순 도착·소스 변경 시나리오를 확인한다. 정상 경로만 보고 통과시키지 않는다.
4. 발견 항목에는 심각도, 재현 조건, 영향, 파일/행 또는 문서 절, 요구사항 ID, 권장 수정, 검증할 시험 ID를 기록한다.
5. 결과를 `NOT_REVIEWED / CHANGES_REQUESTED / APPROVED`로 기록한다. 실제 시험 미수행은 별도 명시한다. 모델이 “문제없음”이라고 한 것만으로 시험 PASS를 만들지 않는다.
6. 문서 수정 시 [변경 규칙](docs/governance/CHANGE_AND_REVIEW.md)에 따라 관련 문서와 시험을 함께 갱신한다. 사용자 결정 ID와 기존 실패 이력을 삭제하지 않는다.

현재 인수인계 문서는 Codex 작성본이며 **Claude 검토는 아직 수행하지 않았다.** 첫 검토 결과는 새 실행/검토 기록으로 추가한다.

## 제품 오케스트레이터를 직접 사용할 때

사용자가 명시적으로 `bsp-upgrade-orchestrator`를 요청하면 [해당 agent 정의](.claude/agents/bsp-upgrade-orchestrator.md)와 [사용 안내](docs/agents/CLAUDE_ORCHESTRATOR_GUIDE.md)를 따른다. 제공된 입력을 검토해 JSON 제안을 반환하는 수동 모드다. 저장소 검토 지침을 근거로 소스·문서를 편집하거나 BSP agent를 실행하지 않는다. 자동 대시보드 연동은 별도 opt-in 로컬 구현·모의 검증을 완료했으며 이 수동 요청으로 활성화하지 않는다. 실제 Claude 호출 결과는 사용자가 남긴 새 기록만 인정한다.


내장 CLI 연결(D-42)은 [도구·환경 계약](docs/agents/ENVIRONMENT_AND_BRIDGES.md)과 native/process/bridge 구현을 대조한다. CLI 권한·인증·역할 snapshot·결과 정규화·리뷰 상관관계의 검증 범위를 기록한다.

모델 선택·관측 메타데이터(D-78)는 [모델 기본·사용량/시간 계약](docs/design/MODEL_USAGE_TIMING.md)을 대조한다. 실행 승인·결과 hash·조정 CAS의 보존 여부를 확인한다.

개발 빌드·테스트 로그는 [로그 처리 규칙](docs/testing/LOG_HANDLING.md)을 따른다.
