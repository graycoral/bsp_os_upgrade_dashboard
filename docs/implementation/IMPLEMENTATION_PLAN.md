# 단계별 구현 지시

현재 모든 제품 구현 단계는 NOT_STARTED다. 사용자 구현 착수 지시 후 P0부터 진행한다. 아래 경로는 제안 구조이며 기존 코드가 생기면 보존·확장한다.

```text
apps/web/                  화면, API client, 접근성·UI 시험
backend/domain/            게이트, 상태, 진행률, 유효성, 도구 선택
backend/api/               명령·조회·인증·수동 결과 API
backend/storage/           repository, migration, transaction, outbox
backend/worker/            scheduler, lease, reconcile, cancellation
backend/adapters/          agents/, build/, jira/, manual_test/
contracts/                 OpenAPI, result schema, fixture schema
tests/                     unit/, contract/, integration/, e2e/, regression/
config/examples/           비밀 값 없는 설정 예시
docs/                      요구사항·설계·기록
```

| 단계 | 구현 내용·변경 위치 | 종료 조건·검증 |
|---|---|---|
| P0 환경·설계 확정 | 실제 저장소 상태, Linux/Windows 버전, 도구 기능, 경로·빌드·시험·Jira 설정 양식. ADR-01~03 검증/채택. WORK_STATUS 갱신 | 미확인 항목을 가짜 값으로 채우지 않음. 호출/재개 지원 여부와 모의·실제 시험 경계 확정 |
| P1 도메인·저장 | domain, storage, migrations, contracts. ID·상태·게이트·입력 유효성·진행률·계획 버전 | T-01~18, T-35~38, T-47~50 중 단위/저장 시험. 실패/역순/중복 상황 통과 |
| P2 명령·실행 관리 | api, worker, fake adapters. command/outbox, 공유 자원 잠금, 재시작, 취소, UNKNOWN 복구 | T-03, T-13~18, T-40~43. 장애 주입으로 중복 writer가 없음을 검증 |
| P3 화면 | web, fixture API. 종합 진행도, 모듈 표, 상세·명령·설정·검토·수동 양식 | T-35~39, T-44~46. 모의 화면임을 명시. 버튼/오류/키보드/재연결 확인 |
| P4 Linux·도구 연동 | agents/build adapters, capability probe, 역할 템플릿. 실제 인증/세션/결과 수집 | T-01~02, T-19~25. 허용된 시험 프로젝트에서 실행. 설치 진술과 live 확인 구분 |
| P5 수동 시험·산출물 | manifest/download/upload, manual validator, 결과 무효화 | T-26~30, T-47~50. 가짜 fixture 시험과 실제 보드 결과 구분 |
| P6 Jira | direct/MCP adapters, discovery/probe, outbox, decision sync | T-31~34, T-51~54. mock 후 지정 환경 읽기 점검; 실제 생성 시험은 승인된 시험 범위에서 수행 |
| P7 통합·인수 | E2E, migration/restore, regression suite, 운영 안내 | T-55~60 및 필수 기존 시험. 실제 환경 미검증 항목은 BLOCKED/NOT_RUN 유지 |

각 단계 종료는 범위 내 필수 시험 통과, 증거 저장, 문서 일치, 차단 결함 없음으로 판정한다. 표에 언급한 시험은 대표 연결이며 전체 목록의 requirement/level을 기준으로 필요한 시험을 선택한다. 단계가 끝났다는 이유로 아직 실행하지 않은 live 시험까지 통과 처리하지 않는다.

## 매 단계 제출할 것

변경 파일, 연결 RQ/T ID, DB 변경 유무, 실제 실행한 시험과 evidence, 실패와 해결/미해결 내역, 외부 연동 확인 범위, 다음 단계. 구현 전 존재하지 않는 실행 명령을 README에 동작하는 명령처럼 적지 않는다. 테스트 러너를 도입하면 정확한 명령과 버전을 TEST_PLAN에 추가한다.

## 실제 환경에서만 확인할 입력

Linux 주소·계정·작업/원본/결과 경로, OS/도구 버전·재개 지원, 빌드 초기화/명령/출력, 실제 모듈과 선행 그룹, 보드와 필수 시험, 이미지 구성, Jira 프로젝트/필드/권한/MCP 기능. 설정 없이도 도메인·API·화면 fixture 작업은 진행 가능하다. 실제 연동이 필요한 단계에서만 필요한 입력을 모아 확인한다.
