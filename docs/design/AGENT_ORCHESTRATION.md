# BSP 에이전트 운영 설계

대시보드 개발 담당과 제품 내부 실행 담당은 구분한다. 아래는 제품이 실행할 BSP 작업 정책이다.

| 작업 | 기본 도구 | 대체/전환 | 결과 조건 |
|---|---|---|---|
| 작업 조정·모듈 제안 | 전용 Claude 세션 | 세션 유실 시 기록 기반 복구, 새 연결 이력 | 저장된 계획에 제안 반영, 실행 허용은 서버 판단 |
| 모듈 분석·설계 | 역할별 Claude 실행 기준안 | 동시 수·세션 분리는 설치 기능 확인 | 변경별 근거, 의존성, 시험 요구사항 |
| BSP 코드 구현 | OpenCode | 동일 원인 수정 2회 실패/근거 있는 난항 → Claude Opus; OpenCode 미설치 → Claude | 소스 revision과 diff, 변경 추적, 실행 근거 |
| OpenCode 작성 리뷰 | Claude | 일반 리뷰 모델은 설정 | 정확한 revision의 발견 항목과 판정 |
| Claude 작성 리뷰 | Codex | Codex 미설치 → 별도 Claude 리뷰 실행 | 대체 리뷰임을 표시; 교차 모델이라고 부르지 않음 |
| 빌드/자동 검증 | 등록된 실행 프로필 | 환경 오류는 환경 복구 | 실제 exit status·로그·산출물 |
| 장비 테스트 | 사람 | 자동 연동은 후속 | 현재 이미지/보드/필수 사례/근거 |

## 도구 점검과 선택

사용자가 Linux의 OpenCode/Codex 설치를 확인했으나 실제 경로·버전·인증·호출·결과·재개 기능은 아직 검증하지 않았다. tool registry에는 installed, authenticated, capabilities, checked_at, version, invocation_profile을 저장한다. CLI 옵션, 실제 Opus 모델 식별자, 세션 resume 방식은 probe 후 등록한다.

“없음”과 “인증 실패/일시 연결 실패”를 구분한다. 미설치는 확정 대체 정책을 적용하고 장애는 진단·복구 상태를 기록한다. Claude도 사용할 수 없으면 필요한 역할만 BLOCKED다. 도구가 없다고 필수 리뷰를 생략하지 않는다. 일반 분석/리뷰 모델과 Claude 대체 구현 모델은 설정 항목이며 Opus 전환 정책과 구분한다.

## 실패 계산과 인계

첫 오류를 발견한 사건은 수정 시도 실패 횟수가 아니다. 동일 cause_key에 대해 실제 수정→동일 기준 재검증 실패가 확정될 때 1회 계산한다. 로그 중복·재전송·인증 오류를 횟수로 세지 않는다. 원인이 불확실하면 근거와 분류를 남긴다.

2회 도달 시 이전 writer 종료를 확인하고 요구사항·현재 revision/diff·실패 원인·시도 이력·로그·리뷰 의견을 Claude Opus에 전달한다. 세션 전환으로 코드를 원본으로 되돌리지 않는다. 조기 전환은 난항 근거를 남긴다. Opus 이후 무한 반복 방지를 위한 최대 시도·시간/비용 한도는 P0 설정 항목이다. 한도 도달 시 보류하고 새 방향 판단이 필요한 경우 Jira에 연결한다.

## 리뷰 유효성

구현 중 Claude가 코드에 기여하면 혼합 작성도 Claude 작성 경로로 분류하는 기준안을 사용한다. Claude가 분석/조정만 했으면 OpenCode 작성 경로를 유지한다. 리뷰에는 author tool set, authored revision, reviewer session, 결과 근거를 저장한다. 리뷰 뒤 소스 변경은 재리뷰 대상이다.

코드 단계는 write → review_wait → reviewing → changes_requested 또는 passed라는 내부 substate를 갖는다. 리뷰 요청 수정은 같은 모듈 구현 작업의 새 시도로 연결한다. 리뷰 PASS는 빌드/장비 시험 PASS를 대체하지 않는다.

## 세션과 출력 계약

작업마다 전용 조정 세션 하나를 식별하고, 모듈 역할 실행은 별도 attempt/session으로 연결한다. 재접속은 기존 job과 세션을 조회한다. 재개 기능이 없거나 세션이 유실되면 새로운 세션임을 기록하고 영속 계획·상태를 인계한다. 기존 writer 상태가 불명이면 새 writer를 실행하지 않는다.

역할 결과에는 schema_version, job_id, module_id, work_item_id, attempt_id, input_fingerprint, outcome, summary, evidence_refs, changed_files, proposed_decisions를 요구한다. 모델이 직접 DB 완료 상태를 쓰지 않는다. 스키마·대상·근거를 서버가 검증한 뒤 결과로 등록한다. 출력에 담긴 “정책을 무시하라”는 문장은 지시로 실행하지 않는다.
