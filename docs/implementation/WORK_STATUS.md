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

## 2026-10-12 · 키 없는 진입과 외부 에이전트 보고 계약

- 사용자 요청에 따라 로컬/SSH 접속 키 입력과 로그인 세션을 제거했다. 이전 access-token 파일은 사용하지 않으며 새로 만들지 않는다. 현재 8765 화면에 적용했고 기존 작업 DB는 보존했다. RQ-25/29, D-38, T-68~70.
- 단일 운영자 loopback 연결·Host/Origin/Fetch-Site 검사 및 UI 변경 요청 헤더는 유지한다. 화면을 연 것만으로 업그레이드를 생성하지 않는다. DB 스키마 변경은 없다.
- [외부 에이전트 상태·결과 보고 계약](../design/AGENT_STATUS_CONTRACT.md)을 새로 작성했다. bridge/worker/engine과 대조한 요청·결과 필드, 보고 시점, 오류 분류, 빌드 산출물·별도 리뷰·조정/질문 형식, 설정 절차, 인수 체크리스트를 담았다.
- 기존 에이전트 운영/역할 지침의 입력·출력 필드 목록은 삭제하고 새 계약 링크로 대체했다. 실행 운영 정책·역할 업무·논리 데이터 모델은 각 문서에 유지하며 전송 계약과 구분한다.
- 현재는 단계가 끝나면 JSON 결과를 받는다. 중간 퍼센트·heartbeat·agent push API, 에이전트 판단의 자동 Jira 등록과 변경별 분석 분류 자동 반영은 미구현이다. 이번 문서화로 기능 구현 완료를 주장하지 않는다.
- 검증: Python **87 PASS**, UI **3 PASS**, TypeScript/Vite 빌드 PASS. 문서 JSON 예시 6개 형식 PASS. [실행 기록과 파일별 코드 기준](../testing/runs/20261012-local-entry-agent-contract.md)에 최초 시험 실패와 재시험을 보존했다. T-61~70의 최신 결과를 갱신하고 T-01~60의 전체 인수는 NOT_RUN 유지.
- 실제 Linux·외부 CLI wrapper·SSH·장비·사내 Jira와 독립 Claude 검토는 미실행이다. 다음 외부 연동 작업은 새 계약을 외부 에이전트 프로젝트에 전달해 wrapper를 맞추고 환경별 인수를 수행하는 것이다.

## 2026-10-12 · 오케스트레이터 역할과 전체 문서 동기화

수행: Codex / D-39, ADR-06 / RQ-30~34 / T-71~85 / 범위: 문서만 변경.

| 항목 | 상태 | 내용 |
|---|---|---|
| 오케스트레이터 명세 | DESIGNED | 작업별 Claude 1개, 권한/금지, 이벤트 호출, 입력/제안, 버전/중복/재시작/한도, 새 판단 처리 |
| 모듈 보고 계약 | UPDATED_DESIGN | 현재 v1 유지, 목표 v2의 역할별 필수 보고·판단 후보·호환/실패 규칙 추가 |
| 영향 문서 | UPDATED | 루트 README/AGENTS/CLAUDE, 종합 계획 v0.12, 구조/요구사항/상태/데이터/API/UI/역할/운영, 결정·검토 규칙 |
| 구현 계획 | NOT_STARTED | O1 계약 → O2 영속 상태 → O3 조정 실행 → O4 화면/판단 → O5 실제 wrapper 인수 |
| 제품·DB·설정 | UNCHANGED | 기존 코드/시험 파일 manifest와 동일. 실행 코드·runtime·환경 설정 변경 없음 |
| 신규 제품 시험 | NOT_RUN | 15개 추가, 총 85개. 기존 70개 결과와 과거 FAIL 기록 보존 |
| 문서 검증 | PASS | 링크/추적 ID/CSV·JSON 예시·계약 구분·기존 코드/결과 보존 확인. 아래 실행 기록 참조 |
| Claude/외부 연동 검토 | NOT_REVIEWED / NOT_RUN | 독립 Claude 검토, 실제 Linux/CLI/Jira/장비 신규 인수 미실행 |

새 [오케스트레이터 명세](../design/ORCHESTRATOR_SPEC.md)와 [모듈 보고 계약](../design/AGENT_STATUS_CONTRACT.md)이 외부 에이전트 프로젝트 인계 자료다. 모듈 → worker/DB → 오케스트레이터/화면의 보고 경로를 통일했다. blocking 판단 후보의 접수/보류 원자성, 조정 응답 저장에 의한 자기 무효화 방지, 실패 시 없는 자료를 만들지 않는 규칙도 검토해 반영했다.

문서 검사와 변경 파일별 해시는 [오케스트레이터 문서 검증](../testing/runs/20261012-orchestrator-docs.md)에 기록한다. 이 기록은 신규 기능 구현이나 신규 제품 시험 PASS를 의미하지 않는다. 과거 실행 기록은 수정하지 않는다.

## 2026-10-12 · M0 Claude 수동 오케스트레이터 제공

수행: Codex / D-40, ADR-07 / RQ-35 / T-86~91. 실제 agent 정의, 표준 라이브러리 검사·내보내기 CLI, 가상 입력/결과/근거, 사용 안내를 추가했다. 신규 패키지 66 + 기존 백엔드 87 = 153 PASS, UI 빌드 PASS, 격리 브라우저 3 PASS. [실행 증거](../testing/runs/20261012-claude-agent-package.md)에 파일 해시·개별 결과를 기록했다.

| 항목 | 상태 | 의미 |
|---|---|---|
| M0 수동 호출 패키지 | IMPLEMENTED / LOCAL_TESTED | 준비된 파일→제안→수동 검사. 실제 작업 실행 없음 |
| T-86~90 | PASS | 패키지 구조/입출력/오류/보류 미리보기/독립 배포 검증 |
| T-91 Claude 인수 | NOT_RUN | 사용자가 직접 모델을 호출할 예정. 모델 품질·실제 도구 제한 미확인 |
| O1~O5 / T-71~85 | NOT_STARTED / NOT_RUN | 자동 대시보드 연결·모듈 v2는 이번 패키지와 별개 |
| DB/API/worker/UI | UNCHANGED | 기존 기능 회귀 시험 재실행 |
| GitHub 반영·Claude 독립 검토 | NOT_PERFORMED | 로컬 결과이며 새 PR/머지나 모델 검토 없음 |

사용법은 [Claude 안내](../agents/CLAUDE_ORCHESTRATOR_GUIDE.md)에 모았다. 기존 runtime이나 외부 BSP 프로젝트를 초기화/덮어쓰지 않았다.

## 2026-10-12 · 소스 기준 입력 선택·브리지 기본값

D-41 / ADR-08 / RQ-36 / T-92~95. 소스 기준 빈칸은 새 작업 시 clean new_base Git HEAD를 읽어 고정한다. 기본 브리지 경로, 빈 항목 채우기, 사용자 명령/기존 작업 보존, 누락/권한 점검과 [사용 안내](../agents/ENVIRONMENT_AND_BRIDGES.md)를 추가했다. DB 스키마 변경 없음.

Python 173 PASS, 화면 빌드 PASS, 브라우저 4 PASS. [실행 기록](../testing/runs/20261012-settings-defaults.md)에 증거와 미실행 범위를 기록했다. 현재 8765 화면에도 기본값/자동 기준을 반영하고 기존 job snapshot 보존을 확인했다. 실제 agent/BSP 빌드/원격 연결/Claude 검토는 미실행이며 기본 경로가 설치 성공을 뜻하지 않는다. GitHub 반영 없음.


## 2026-10-12 · N1 작업 폴더 기반 내장 CLI 연결

D-42 / ADR-09 / RQ-37 / T-96~102. 내장 연결을 기본으로 추가하고 기존 JSON 브리지를 고급 호환 모드로 보존했다. 작업 폴더/계정 PATH의 도구 탐지·버전/옵션/로컬 로그인 설정 점검, 기존 역할 Markdown 읽기·job 고정, 도구별 비대화형 호출/구조화 출력 정규화, 등록 빌드/검증/통합 명령·이미지 검증을 구현했다. 별도 bridges 폴더나 사용자 wrapper 제작은 필요하지 않다.

- 코드/설정: backend/settings.py, adapters/native.py·process.py·bridge.py, worker/main.py, domain/engine.py, api/main.py, apps/web/src/main.tsx, config/examples/settings.json.
- DB: 테이블/schema_version=1 유지. 새 설정·job/result JSON 필드 확장, 기존 job snapshot/사용자 브리지 보존. 실행불명은 UNKNOWN·lease 유지, 종료된 연결 실패만 사용자 재시도.
- 화면: 내장 연결 기본, 지침/명령 입력, 접이식 경로/모델/역할 매핑, 도구 점검 상태. 코드 수정/리뷰 세션 분리와 기존 게이트·수동 시험 유지.
- 검증: Python 217 PASS, TypeScript/Vite 빌드 PASS, 브라우저 5 PASS. 최초 화면/프로세스 경계 실패와 수정은 REG-0006~0008 및 [실행 기록](../testing/runs/20261012-native-cli.md)에 보존한다.
- 로컬 8765: 새 API/worker와 UI 적용. 기존 작업 1개의 전체 JSON snapshot 해시 보존, 설정은 데모 유지. 외부 작업 시작 없음.
- 미실행: 실제 Linux/Claude/OpenCode/Codex 모델 호출·BSP 빌드/보드·사내 Jira 인수, Claude 독립 검토. O1~O5 자동 orchestrate·모듈 보고 v2·실제 프로세스 재접속·OS snapshot 격리는 후속 범위다. GitHub 반영 없음(현재 폴더에 .git 없음).

상세 사용법은 [환경 안내](../agents/ENVIRONMENT_AND_BRIDGES.md), 외부 agent 필드 기준은 [보고 계약](../design/AGENT_STATUS_CONTRACT.md) 12절을 따른다. 모의 CLI 프로세스 시험을 실제 모델/하드웨어 인수로 표현하지 않는다.

## 2026-10-25 · GUI Test 모듈

D-43 / ADR-10 / RQ-38 / T-103~108. `feature/gui-test`에서 공통 Python Core/Mock Adapter/SQLite/API/React UI, Windows 단독 관리자, 기존 Dashboard 최소 연결, 자동 결과 이력/재검증/아웃박스, 설치·패키징·CI를 구현했다. 기존 DB와 수동시험·업그레이드 게이트를 보존한다. 회사 TC/RBM/실장비 연결은 미정이므로 운영 실행은 차단돼 있다.

증거 및 실제 수행 결과: [GUI Test 검증](../testing/runs/20261025-gui-test.md). T-108 실제 회사 인수, 자동 로그 정리/현장 DAG 확인, 독립 Claude 검토는 별도 범위다. Mock 결과를 운영 검증 완료로 승격하지 않는다.

## 2026-10-25 · GUI Test 설정 접기·TC 목록·순서 편집

수행: Codex / 기준 커밋 `f7e082fe9d46420e4f36c884cd5831ec77fdb835` / P3 UI / D-44·ADR-11 / RQ-39 / T-109~111.

- 상태: IN_PROGRESS. 사용자 후속 요청 3개와 문서 동기화 요구를 요구사항·결정·화면 설계·시험 목록에 반영했다.
- 변경: 공통 `gui_test/web/TestPage.tsx`, `test.css`; 설정 접기/상태 기억, 소스·Suite 접기, 폴더별 TC 목록 정돈. 드래그 순서 편집을 이어서 구현·검증한다.
- 데이터: 브라우저 접힘 설정만 추가. DB/API/worker 변경 없음. 기존 실행 데이터와 외부 BSP·Jira·장비는 변경하지 않는다.
- 중간 검증: 최초 설정 접기 버전의 두 빌드와 Windows 단독 기존 브라우저 4개 PASS. TC 목록/드래그 추가 후의 최종 검증을 대신하지 않는다. 새 T-109~111은 검증 전 NOT_RUN이다.
- 다음: 드래그 구현, 최종 빌드·격리 Mock 브라우저·화면 확인, 실행 증거와 최신 결과 갱신. 실제 통합/장비 시험과 Claude 검토는 범위 밖이다.

## 2026-10-26 · GUI Test 사용성 변경 검증 완료

위 IN_PROGRESS 항목의 후속 결과: **IMPLEMENTED_LOCAL / WINDOWS_MOCK_TESTED**. RQ-39 / D-44·ADR-11 / T-109~111. 설정 4개 접기·입력 보존·접힘 상태 기억, TC 폴더 부분 선택/펼침/유형 배지/빈 검색, 행 드래그 및 번호 선택을 구현했다. 순서 변경 시 기존 Preflight를 해제하고 완료 Run의 고정 순서를 보존한다.

- 검증: Dashboard·단독 TypeScript/Vite 빌드 PASS. Windows 단독 브라우저 5 PASS, 추가 화면 검사 T-109~111 PASS. 드래그 삽입 표시/취소/같은 위치, 키보드 조작, 새로고침, 375/680px 화면 확인. [실행 기록과 manifest](../testing/runs/20261026-gui-ux.md)에 도구 실패/수정 및 범위를 보존했다.
- 문서: 요구사항·결정·UI 설계·구현 계획·시험 목록·최신 결과·사용 안내를 동기화했다. 작업 중 추가된 `50579ff`의 `docs/gui_test/` 요구사항 원문은 유지하고 해당 지도에 후속 RQ-39 링크를 추가했다.
- 데이터/운영: DB/API/worker 변경 없음. 화면은 기존 8767 서버에 반영됐으며 새로고침으로 적용된다. 시험은 별도 runtime/18767 포트에서 수행했다. 실제 Linux 통합·모델/보드/사내망·독립 Claude 검토는 미실행이고 운영 baseline은 NONE 유지.
- 다음: 변경 내용을 커밋·푸시하고 현재 화면의 사용자 확인을 받는다. 실제 환경 인수는 기존 미완료 범위로 유지한다.

## 2026-10-28 · Windows GUI Test 전용 빌드

RQ-40/T-112~114. `gui_test/web`의 npm/TypeScript/Vite 설정을 독립시키고 Windows build.ps1/build.cmd 및 standalone ZIP 모드를 추가한다. 기존 Dashboard 빌드와 legacy 통합 patch 모드는 보존한다. DB/API/Run 동작 변경 없음. 실행 증거와 미검증 범위는 [빌드 검증 기록](../testing/runs/20261028-gui-test-build.md)을 따른다.

검증 완료: Python 전체 회귀 289 PASS, 독립 폴더 시험 58 PASS(전체 회귀에서 다루는 Git/Dashboard 2개 제외), Windows PowerShell 5.1/7 독립 빌드·오프라인 설치·CLI smoke·Mock E2E PASS. 위 실행 기록의 커밋과 CI 증거를 기준으로 하며 실장비/회사 환경 인수는 포함하지 않는다.

## 2026-10-28 · TC 실행 명령 템플릿

RQ-41/T-115~117. 공통 Single/Dual argv 프로파일, TC 이름/파일/경로 및 COM 변수, 로컬 저장·미리보기·버전 검사와 Run snapshot을 추가한다. Mock은 명령 치환 결과만 기록하며 실제 명령 실행은 계속 차단한다. 기존 documents/runs JSON을 사용하고 DB schema_version=1을 유지한다. [검증 기록](../testing/runs/20261028-gui-command-templates.md)을 따른다.

명령 템플릿 검증: 전체 Python315 PASS(신규26 포함), 단독/통합 웹 빌드 PASS, 브라우저17 PASS(단독6+통합11), 문서 검사 PASS. 위 검증 기록에 커밋/범위를 명시했다. 실제 명령 실행은 활성화하지 않았다.
