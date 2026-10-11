# 작업 진행 기록

기준일: 2026-10-11

| 항목 | 상태 | 근거/다음 작업 |
|---|---|---|
| 기존 운영 정책 수집 | COMPLETE | 종합 계획 v0.8 기준, 사용자 후속 문서 요청 반영 |
| 구현 인수인계 문서 | WRITTEN | AGENTS/CLAUDE 및 분리 문서. 문서 검사는 testing/DOC_VALIDATION.md 참고 |
| Claude 검토 | NOT_REVIEWED | 실제 Claude 검토 결과 없음 |
| P0~P7 제품 구현 | NOT_STARTED | 애플리케이션 코드/DB/테스트 러너 없음 |
| 제품 테스트 | NOT_RUN | TEST_RESULTS.csv 초기 상태 |
| Linux·에이전트 실제 연동 | NOT_VERIFIED | OpenCode/Codex 설치는 사용자 진술; 실제 호출 미확인 |
| 보드 시험 | NOT_RUN | 초기 수동 방식 확정, 실제 보드/시험 기준 미설정 |
| Jira 실제 연동 | NOT_VERIFIED | 직접 설정/MCP 선택 정책만 확정 |
| 정상 제품 기준 버전 | NONE | 검증된 코드 기준 아직 없음 |

다음 구현 작업: P0 환경·설계 확인 후 P1 도메인/저장 계층. 이 기록의 “문서 작성” 완료는 구현 착수나 실제 운영 실행 승인이 아니다.

## 후속 기록 형식

날짜 / 수행자·도구 / 기준 커밋 / 단계 / 변경 요약 / RQ·T ID / 실행 ID / 미해결·차단 / 다음 작업. 과거 기록은 삭제하지 않고 새 항목을 추가한다. “완료”에는 확인 가능한 근거를 붙인다.

## 2026-10-12 · 1차 구현 및 후속 변경

위 2026-10-11 표는 구현 전 이력이다. 최신 상태는 아래와 같다.

| 항목 | 상태 | 구현/검증 범위 |
|---|---|---|
| P1 도메인·영속 기록 | IMPLEMENTED_LOCAL | 명령 중복 방지, 계획/선행 게이트, attempt 이력, SQLite WAL |
| P2 worker·잠금·복구 | PARTIAL | 독립 worker, 공유 수정/빌드 잠금, 불명 실행 재시도 차단. 실제 프로세스 재접속 미구현 |
| P3 화면·설정 | IMPLEMENTED_LOCAL | 진행률, 접이식 모듈 표, 설정 UI/JSON, 질문/명령, 실패 재시도 |
| P4 도구 연결 | PARTIAL | JSON 브리지와 도구 선택·교차 리뷰 정책. 실제 CLI wrapper/인증/세션 live 검증 미실행 |
| P5 수동 시험 | IMPLEMENTED_LOCAL | 사례별 PASS/FAIL만 필수. 기타 입력 선택, 현재 작업 기준 자동 연결. 실제 장비 시험 미실행 |
| 데모 선행 수동 완료 | IMPLEMENTED_LOCAL | 계획 확인 후 선행 모듈별 모의 완료. 실제 모드와 나머지 그룹 거부. T-64~67 |
| P6 판단/Jira | PARTIAL | 내부 판단·의존 대기, 직접/MCP 어댑터, 생성 유실 중복 방지 모의 시험. 사내 연동/자동 상태 polling 미검증 |
| P7 회귀·운영 | PARTIAL | Python 78개 PASS, 브라우저 3개 PASS, UI 빌드 PASS. CI/운영 서비스/실제 인수 미완료 |
| README 사용법 | UPDATED | 설치·실행, Windows SSH, 설정 관리, 결과 등록, 데모 완료, 문제 해결 |
| Claude 검토 | NOT_REVIEWED | 독립 Claude 검토는 수행하지 않음 |
| 실제 Linux·SSH·보드·사내 Jira | NOT_RUN | 환경별 브리지와 실제 시험 필요 |

이번 정책 변경은 RQ-14/15/28과 D-36/37에 연결한다. 기존 테이블 schema_version=1을 유지하며 JSON 결과 필드 추가로 이전 결과를 보존한다. 로컬 코드 내용 식별자와 시험별 PASS, 실패 후 재시험 이력은 [20261012 구현 검증](../testing/runs/20261012-implementation.md)에 기록했다.

남은 범위: 모듈별 세부 DAG, Claude 모듈 제안 diff/승인, 시험 사례 편집, 다중 이미지 묶음, 소스 snapshot OS 격리, 최소 영향 무효화, 실제 프로세스 복구, 다중 사용자 권한. 위 PARTIAL 항목을 전체 완료로 승격하지 않는다.
