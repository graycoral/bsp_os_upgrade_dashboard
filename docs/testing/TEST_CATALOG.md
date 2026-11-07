# 테스트 목록

2026-11-06 RQ-30~34/D-58: 기존 T-71~84를 여섯 schema/fixture, v1 호환·v2 capability, 후보/보류·needs_decision, 정확한 소스/diff·별도 리뷰, 영속 큐/제안·재시작/receipt, 백업/변조·별도 복원, UI 설정/제안/상세 조회 시험으로 보강한다. T-85 실제 외부 인수는 별도 NOT_RUN이다. 시험 파일은 `tests/test_orchestration_contracts.py`, `test_orchestration_runtime.py`, `test_orchestration_worker.py`, `test_recovery_bundle.py`, `tests/e2e/orchestration.spec.ts`이며 [실행 기록](runs/20261106-orchestration-v2.md)의 실제 결과만 인정한다. 초기 schema smoke로 T-71~84 전체 PASS를 선언하지 않는다.

## 2026-11-04 결과 조작과 상시 표시

추가 시험: T-162(RQ-52)은 실제 TC 경로의 읽기 전용 Git 정보·URL 자격 증명 제거·비 Git/detached/미설치/시간 초과·기존 Runner 호환과 스냅샷 불변을 검증한다. T-163(RQ-53)은 서버 모듈 테스트 진입에 따른 TC 자동 목록, 명시적 연결 우선·대소문자/오탐, 0건·선행 조건, 오래된 응답/반복 조회·선택/Preflight·기존 Run 보존과 자동 파이프라인 중복 방지를 검증한다. 실제 장비를 실행하지 않으며 실행 상태는 별도 기록한다.

| ID | 요구사항 | 수준 | 시험 | 절차 | 통과 조건 |
|---|---|---|---|---|---|
| T-161 | RQ-20/39 | ui/e2e | 탭 소개 정리·작은 진행 집계·상시 결과 | GUI-UI-06/14/18 및 전체 탭 fixture; 빈 Run/완료 Run/설정 복귀/좁은 화면 | 제목 아래 소개와 중복 결과 버튼/제목 없음; ＋/−는 이름 헤더 체크박스 옆; 실행 전 시작 접근 가능; 진행률·상태별 개수는 작은 같은 행; 집계 아래 조작과 작은 세션 정보·결과·로그 상시 표시; 기존 Preflight·중단 확인·선택·키보드와 설정 포커스 복원 보존 |
| T-162 | RQ-52 | unit/ui | TC 소스 Git 조회와 표시 | 임시 로컬 Git·일반 폴더, 누락/오류/timeout·환경 주입·정제된 remote·구버전 Runner fixture | TC 원본만 조사; 자격 증명 미노출; detached/unborn 구분; 조회 실패가 기존 카탈로그/스냅샷을 변경하지 않음; Git HEAD와 파일 스냅샷 별도 표시 |
| T-163 | RQ-53 | unit/contract/ui | 모듈 테스트 TC 자동 목록 | 서버 device_test 문맥·혼합 카탈로그·명시 소속·선행 조건·작업 전환·반복 조회·자동 소유 상태 | 대상 TC만 자동 구성; 0건/잘못된 의존은 차단; 오래된 문맥/위조 TC 거부; Preflight 무효화·사용자 수정·과거 Run 보존; 자동 파이프라인 중복 배정 없음 |

실행과 독립 리뷰 결과: [화면 정리 기록](runs/20261104-test-results-cleanup.md). 기존 접힘 기대값은 D-54의 새 사용자 요구로 대체한다.

T-161 정렬 후속: GUI-UI-08/18에서 1440/1024px의 좌우 패널 상단 차이 1px 이하를 빈/완료 Run·설정·목록 복원 상태로 확인한다. 375px에서는 세로 배치와 가로 넘침 방지를 유지한다. REG-0047.

## 2026-11-04 UI 규칙 회귀

| ID | 요구사항 | 수준 | 시험 | 절차 | 통과 조건 |
|---|---|---|---|---|---|
| T-153 | RQ-19/20/50 | ui | 모달·진행률·탐색 | guidelines.spec.ts의 native modal/contextual progress/sidebar 시나리오 | 숨김·비활성 입력 제외, 배경 포커스 차단·Escape 복귀, 0/N/A 구분, 새 탭·재로드·뒤로가기·기존 URL 매개변수 보존 |
| T-154 | RQ-20 | ui | 설정 입력 보호 | guidelines.spec.ts의 keyboard import 시나리오 | 키보드·동일 파일 재선택, 잘못된 JSON 저장/점검 차단, 화면 왕복 입력 및 이탈 보호 |
| T-155 | RQ-38/39 | ui | 실행 순서·중단 확인 | guidelines.spec.ts의 keyboard and touch ordering/stop confirmation 시나리오 | 필터 밖 선택 포함 순서 변경, 키보드·터치 조작, 접힌 행 미생성, 중단 취소 시 요청 0·확인한 Run만 요청 |

코드·실패·재시험 근거: [20261104-web-guidelines-audit](runs/20261104-web-guidelines-audit.md).

모든 시험의 초기 상태는 NOT_RUN이다. 실제 대상·환경 값은 설정에서 주입한다. ID는 재사용하지 않는다. 각 시험은 아래 조건을 fixture 또는 지정 실제 환경으로 구성한 뒤 실행한다. 수준이 live/hardware인 항목을 mock 결과로 PASS 처리하지 않는다.

| ID | 요구사항 | 수준 | 시험 | 조건·동작 | 기대 결과 |
|---|---|---|---|---|---|
| T-01 | RQ-01 | live | 두 모드 공통 상태 | 같은 Linux job을 Windows/Linux 화면에서 조회하고 Windows 연결을 종료 | 동일 job/version을 보고 Linux 실행은 유지 |
| T-02 | RQ-02 | live | 실행 설정 점검 | 없는 경로·쓰기 불가 폴더·비대화형 PATH 차이로 Start | 구체적인 점검 실패, 실행 미시작 |
| T-03 | RQ-03 | integration | Start 중복 | 같은 키/내용 Start를 동시 2회, 같은 키/다른 내용 1회 전송 | job 하나, 기존 응답 재사용, 다른 내용 409 |
| T-04 | RQ-04 | unit | 분석 병렬 허용 | 부트로더 미완료 상태에서 나머지 모듈 분석 두 개 배정 | 둘 다 준비 가능, 수정 권한 없음 |
| T-05 | RQ-04 | unit | 분석 재시도 예외 | 부트로더 실패 중 다른 모듈 실패 분석 재시도 | 새 분석 attempt 허용 |
| T-06 | RQ-05 | unit | 최초 확인 게이트 | 전체 분석 완료 전후 확인 없이 부트로더 설계 요청 | 확인 전 차단, 현재 계획 확인 후 허용 |
| T-07 | RQ-05 | contract | 오래된 계획 확인 | plan v2 생성 후 v1 확인 요청 | 409, v2 미확인 유지 |
| T-08 | RQ-06 | unit | 선행 전체 완료 | 선행 2개 중 하나 장비 시험 미완료, 나머지 설계/재시도 요청 | 모두 차단, 분석만 허용 |
| T-09 | RQ-06 | unit | 숫자 기반 해제 금지 | 반올림 100%지만 필수 결과 무효/미결정 상태 | 게이트 닫힘, 이유 표시 |
| T-10 | RQ-06 | unit | 순환 의존 | 선행 이미지가 잠긴 후속 모듈 변경에 의존하는 계획 입력 | 순환 감지, 범위 판단 요청, 임의 우회 없음 |
| T-11 | RQ-07 | integration | 수정과 빌드 배타 | 동일 작업 공간에서 A 수정 중 B 빌드 요청 | B 대기, 동시 writer/build 없음 |
| T-12 | RQ-07 | integration | 작업 간 자원 충돌 | 서로 다른 job이 같은 작업 폴더 수정 요청 | 작업 폴더 자원 키로 직렬화 |
| T-13 | RQ-08 | integration | 모듈 ID 유지 | 세션 종료·재시도·재조회 후 모듈 목록 확인 | 모듈 ID/행 유지, 새 attempt만 추가 |
| T-14 | RQ-09 | contract | 허위 성공 거부 | exit 0이나 필수 결과/근거 누락 응답 제출 | SUCCEEDED 거부, 명시적 검증 오류 |
| T-15 | RQ-10 | integration | 재시도 중복 | 실패 단계 재시도 동시 클릭 및 반복 요청 | 새 attempt 하나, 이전 FAIL 보존 |
| T-16 | RQ-10 | integration | 불명 실행 재시도 | 실행 상태 UNKNOWN에서 retry | 새 실행 차단, 상태 조회 필요 안내 |
| T-17 | RQ-11 | integration | 역순 이벤트 | 새 성공 결과 뒤 이전 attempt 실패/성공 도착 | 현재 상태 불변, 늦은 이벤트 감사 기록 |
| T-18 | RQ-11 | integration | 재연결 snapshot | 이벤트 누락·오래된 cursor 후 재접속 | snapshot 복구, 상태/진행률 일치 |
| T-19 | RQ-12 | unit | 실패 2회 전환 | 동일 원인 수정 실패 2회와 중복 이벤트 입력 | 실패 2회에서 Opus 선택, 중복 미계수 |
| T-20 | RQ-12 | unit | 환경 오류 분리 | 인증/네트워크 실패 두 번 입력 | 수정 실패로 세지 않고 환경 복구 처리 |
| T-21 | RQ-12 | integration | 안전 인계 | OpenCode 실행 중 Opus 전환 요청 | 이전 writer 종료 확인 후 diff/근거 인계 |
| T-22 | RQ-13 | unit | 작성자별 리뷰 | OpenCode 작성/Claude 작성/Claude 분석만 수행 케이스 | 각각 Claude/Codex/Claude 리뷰 선택 |
| T-23 | RQ-13 | contract | 도구 미설치 대체 | OpenCode 또는 리뷰 Codex 미설치 probe | Claude 대체, 구현·리뷰 별도 실행, 대체 표시 |
| T-24 | RQ-13 | unit | 리뷰 기준 변경 | revision A 리뷰 PASS 뒤 코드 B로 변경 | A 승인 보존, B 재리뷰 필요 |
| T-25 | RQ-03, RQ-12 | live | 세션 재개 실제 확인 | 실제 도구에서 생성/중단/조회/재개 기능 시험 | 지원 기능만 등록, 기존 작업 중복 생성 없음 |
| T-26 | RQ-14 | contract | 다운로드 미완료 | 이미지 bundle 다운로드만 수행 | 장비 시험 WAITING_INPUT, PASS 아님 |
| T-27 | RQ-15 | contract | 정상 수동 결과 | 현재 이미지 기준 필수 사례 PASS 제출, 보드/근거 선택 | 추가 승인 없이 해당 단계 완료 |
| T-28 | RQ-15 | contract | 누락/불일치 결과 | 필수 PASS/FAIL 누락·입력한 해시 다름·시험 계획 오래됨 각각 제출 | 완료 거부, 필드별 사유, 원본 제출 보존 |
| T-29 | RQ-10, RQ-14 | contract | 수동 시험 재시도 | 수동 FAIL 뒤 retry | 새 수동 attempt 대기, 자동 플래시 없음 |
| T-30 | RQ-14, RQ-15 | hardware-manual | 실제 보드 시험 | 지정 보드에 지정 이미지 수동 적용 후 필수 사례 수행 | 보드/이미지/근거 일치 결과 등록, 실패 시 완료 차단 |
| T-31 | RQ-16 | integration | 의존 범위 대기 | A 판단 대기 중 독립 B 분석/허용 작업 배정 | A 의존 작업만 대기, B 계속 |
| T-32 | RQ-16 | unit | 일반 오류 분류 | 재시도 가능한 빌드 실패와 새 설계 판단 각각 입력 | 일반 실패는 자동 Jira 아님, 새 판단만 Decision |
| T-33 | RQ-17 | contract | 연결 상태 구분 | MCP 등록됐으나 인증/기능 확인 실패 | 등록/인증/기능 상태 분리, 생성 가능으로 오표시 안 함 |
| T-34 | RQ-17 | live | 실제 Claude MCP 범위 | 지정 Linux 계정/프로젝트 목록 조회 | 그 환경 목록 표시, 미지원이면 수동 프로필/미지원 안내 |
| T-35 | RQ-19 | unit | 진행률 집계 | 5모듈 중 분석3, 설계2, 코드2 완료 등 고정 fixture | 분석60%, 구현40%, 실행 중 임의 가산 없음 |
| T-36 | RQ-19 | unit | 대기/N/A 분모 | 선행 대기 모듈·승인 N/A·대상 없음 입력 | 대기는 분모 포함, N/A 제외, 0분모 해당 없음 |
| T-37 | RQ-19 | unit | 정의 전 집계 | 필수 사례 미정 또는 계획 작업 추가 | 미정은 산정 중, 변경 후 재계산과 사유 표시 |
| T-38 | RQ-24 | unit | 최종 완료 별도 | 모듈 5집계 100%, 통합/최종 검토 미완료 | job COMPLETED 금지, 전체100% 금지 |
| T-39 | RQ-20 | ui/e2e | 접이식 표 | 접힌 행 조회 후 키보드 펼치기/필터/상태 갱신 | 현재 단계/사유 표시, 펼침·선택 유지, 색 외 상태 구분 |
| T-40 | RQ-21 | contract | 프롬프트 우회 차단 | 선행 미완료인데 강제로 구현하라는 prompt | 서버 게이트 차단, 명령/거부 이유 기록 |
| T-41 | RQ-26 | integration | 시작 경계 crash | DISPATCHING 저장 직후/프로세스 시작 직후 worker 중단 | 재시작 조회/복구, 확인 전 중복 실행 없음 |
| T-42 | RQ-26 | integration | lease 만료 | 기존 writer 살아 있는 상태에서 heartbeat 만료 | 새 writer 배정 금지, UNKNOWN/reconcile 처리 |
| T-43 | RQ-26 | integration | 취소 확인 | 실행 취소 접수 후 프로세스 종료를 지연 | CANCEL_REQUESTED 유지, 종료 전 잠금 해제 안 함 |
| T-44 | RQ-25 | contract | 경로/명령 주입 | 경로 이탈·심볼릭 링크·셸 특수문자 포함 입력 | 허용 경로 검증과 인자 분리, 임의 명령 미실행 |
| T-45 | RQ-25 | ui/e2e | 비밀/스크립트 노출 | 비밀 값과 HTML script가 든 오류/로그 fixture | 비밀 마스킹, 텍스트 표시, script 미실행 |
| T-46 | RQ-25 | contract | 권한과 다운로드 | 다른 사용자/작업 artifact ID로 조회·다운로드·취소 | 정책에 따른 접근 거부, 감사 기록 |
| T-47 | RQ-22 | unit | 벤더 변경 누락 | 변경 하나 미분류/근거 없는 제외 상태로 최종 완료 | 완료 차단, 누락 변경 ID 표시 |
| T-48 | RQ-23 | integration | 결과 무효화 전파 | 소스/설정/시험 계획 변경 후 기존 PASS 조회 | 영향 리뷰·빌드·시험 INVALIDATED, 과거 이력 보존 |
| T-49 | RQ-23 | integration | 선행 재무효화 | 선행 완료 후 변경으로 무효화, 후속 배정 요청 | 신규 배정 중지, 후속 결과 현재 근거로 사용 금지 |
| T-50 | RQ-24 | unit | 이미지 순환 대기 방지 | 선행 코드 준비, 후속 모듈 장비 시험 미완료 | 선행 검증 이미지 빌드 허용, 미래 시험 완료 요구 안 함 |
| T-51 | RQ-18 | integration | Jira 응답 유실 | 원격 생성 성공 후 응답 유실 주입 | 내부 ID 검색 후 기존 티켓 연결, 중복 생성 없음 |
| T-52 | RQ-18 | integration | Jira 상태와 반영 | Jira Done 수신, 코드 반영·재시험 미완료 | Decision 결정/반영 분리, 의존 완료 안 됨 |
| T-53 | RQ-18 | integration | Jira 장애/역순 | 연결 끊김과 오래된 원격 상태 도착 | outbox/내부 판단 유지, 최신 상태 덮어쓰기 없음 |
| T-54 | RQ-17 | live | 직접 Jira 비파괴 probe | 실제 설정으로 조회/기능 확인 | 정확한 capability, 시험용 티켓 임의 생성 없음 |
| T-55 | RQ-26 | integration | 저장 장애 | 디스크 부족·DB 쓰기 실패·산출물 누락 주입 | 신규 배정 보류, 성공 오표시 없음, 복구 사유 보존 |
| T-56 | RQ-26, RQ-27 | integration | 이전과 복구 | fixture DB migration/백업/복원 후 manifest 검증 | 데이터/이력/해시 일치, 누락 근거 성공 처리 안 함 |
| T-57 | RQ-27 | integration | FAIL 이력 보존 | 한 시험 FAIL 후 수정/재시험 PASS 기록 | 별도 run 2개, 최신 요약 PASS, 최초 FAIL/REG 유지 |
| T-58 | RQ-27 | integration | 오래된 PASS/기준 | 코드 변경 후 이전 결과로 baseline 갱신 시도 | 현재 검증 없으면 거부/INVALIDATED, 기존 정상 기준 보존 |
| T-59 | RQ-01, RQ-24 | ui/e2e | 통합 정상 경로 | fake 도구로 분석/확인/선행/나머지/통합/최종 검토 | 정확한 순서와 상태·집계, fixture임을 명시 |
| T-60 | RQ-01, RQ-27 | live | 실제 인수 경로 | 승인된 Linux/도구/보드/Jira 범위에서 전체 시나리오 | 실제 증거로 필수 결과 확인, 미연동은 BLOCKED로 보고 |
| T-61 | RQ-14, RQ-15 | contract | 수동 결과 최소 입력 | demo/bridge fixture에서 사례별 PASS만 제출 | 완료, 기타 정보 null, 이미지/소스/계획/등록시각 자동 연결, 최종 검토 유지 |
| T-62 | RQ-10, RQ-15 | contract | 최소 FAIL과 재시도 | 추가 정보 없이 FAIL 후 새 attempt에 PASS | 실패/성공 두 이력 보존, 새 결과 완료 |
| T-63 | RQ-14, RQ-15 | contract | 선택값 검증 | 필수 결과 누락/잘못된 결과, 입력한 해시/소스/계획/시각/파일 오류, 과거 attempt | 거부하고 현재 WAITING_INPUT 보존 |
| T-64 | RQ-28 | integration | 데모 선행 완료와 재조회 | 선행 두 모듈을 차례로 수동 완료하고 저장소 재조회 | 전체 완료 후에만 후속 설계 허용, 모의 이력 보존, 최종 검토 미완료 |
| T-65 | RQ-28 | contract | 데모 완료 범위 제한 | 실제 작업에 demo 위장 요청, 나머지 그룹, 계획 미확인, 판단 대기, 일시 중지, 오래된 기준 | 서버 거부, 완료 상태 불변 |
| T-66 | RQ-28, RQ-10 | integration | 데모 대체 경쟁·이력 | 실행 중 데모 수동 완료, 동일 요청 중복, 늦은 완료, 별도 작업 잠금 | 이전 실행 취소 이력/기존 실패 보존, 새 모의 완료 하나, 늦은 결과 거부, 다른 잠금 유지 |
| T-67 | RQ-20, RQ-28 | ui/e2e | 데모 완료 UI | 계획 전 버튼 비활성, 선행 둘 완료, 새로고침, 나머지 그룹 펼치기 | 선행 전체 완료 후 해제, 모의 표시, 나머지 그룹 버튼 없음, 최종 검토 유지 |
| T-68 | RQ-29 | integration | 키 없는 로컬 API | 빈 runtime으로 시작·작업 조회/생성, 과거 키/쿠키가 남은 runtime 조회 | 키 생성/읽기·로그인 세션 없이 동작, 조회만으로 새 작업 없음 |
| T-69 | RQ-25, RQ-29 | contract | 접속/출처 경계 유지 | 원격 peer·위조 forwarded·외부 Host/Origin/Fetch-Site·임의 폼 요청 | 거부, 로컬 IPv4/IPv6와 정상 출처는 허용 |
| T-70 | RQ-20, RQ-29 | ui/e2e | 키 없는 첫 화면 | 새 브라우저 진입·설정 저장·새로고침 | 로그인 입력 없이 화면 표시, 설정 유지, 키 파일/쿠키/자동 작업 없음 |
| T-71 | RQ-30 | contract | 조정 권한 경계 | 미확인 계획·선행 미완료·잠금 경합에 실행/완료/Jira 직접 전송 제안, 임의 kind/셸 입력 | 서버 거부, 별도 리뷰/수동시험/최종 검토 유지, 실제 배정자는 하나 |
| T-72 | RQ-31 | integration | 트리거와 호출 직렬화 | 같은 이벤트 재접수, 일반 성공/조회 반복, 조정 중 추가 이벤트·같은 세션 질문 | 필요한 이벤트만 유일 접수, job별 active 1, 미소비 이벤트 보존, 정상 진행은 LLM 호출 없이 계속 |
| T-73 | RQ-31 | contract | 오래된 제안 | 순수 응답 저장과 실행 상태 변경을 구분, 응답 중 plan/source/state version 또는 근거 해시 변경 | 자기 감사 기록만으로 무효화 안 함, STALE/CONTRACT 구분, 현재 상태 미변경, 원래 트리거별 제한된 재검토 |
| T-74 | RQ-31 | integration | 제안 중복과 장애 구간 | 같은 proposal_key 동일/다른 내용, 명령 commit 전후 재시작, 여러 제안 중 일부만 적용 | 동일 명령 1회, 다른 내용 충돌, 제안별 적용 결과 유지, 바뀐 기준 재검사 |
| T-75 | RQ-30, RQ-31 | integration | 계획 제안과 사람 확인 | 분석 누락 상태 최초 계획, 모듈 이름 변경/추가/그룹 변경/시험 제외 제안 | 누락 최초 확인 차단, 기존 ID 보존, 새 판단 범위만 확인, 정상 단계 추가 승인 없음 |
| T-76 | RQ-30, RQ-34 | unit | 재시도와 전환 한도 | 기본 자동 재시도 0·설정 한도·동일 FIX 2회·환경 오류·UNKNOWN 제안 | 사용자 선택/한도 유지, 실제 FIX만 계산, 기존 Opus/교차 리뷰 정책, UNKNOWN 재실행 금지 |
| T-77 | RQ-32 | contract | v2 보고의 상관관계 | 성공/실패/리뷰의 ID/계획/fingerprint/입력 참조 불일치, 같은 report ID 다른 내용 | 모두 검증, 중복 1회, 충돌/오래된 결과가 최신 완료/보류를 만들지 않음 |
| T-78 | RQ-32 | contract | 역할별 실제 근거 | 변경별 분석 분류, 코드 revision/diff와 리뷰 불일치, 빌드 파일/해시 오류, 필수 검증 NOT_RUN, 실행 전 실패의 null+이유 | 역할 필수 보고 검증, 분석 일괄 port_required 금지, 실패의 자료 부재 보존, 근거 없는 성공/시험 PASS 거부 |
| T-79 | RQ-33 | integration | 판단 후보와 배정 경쟁 | 후속 단계 배정과 blocking 후보 접수 동시 실행, nonblocking 후보, 분석 성공+후속 설계 판단, stale 후보 | 결과/후보/보류 원자 저장, blocking 영향 범위만 대기, 분석 성공 유지, 오래된 후보 미반영 |
| T-80 | RQ-33 | integration | 판단과 Jira 중복 | 같은 후보 재시도·기존 Decision 존재·일반 오류·원격 응답 유실·Jira Done | 새 판단만 내부 Decision/Jira, 중복 없음, 결정과 반영 구분, 독립 작업 유지 |
| T-81 | RQ-30, RQ-34 | integration | 조정 장애 격리 | 조정 timeout/잘못된 JSON/도구 장애/한도 도달 중 독립 모듈 결과 수신 | 모듈 결과 저장·기존 승인 작업 유지, 새 판단 범위만 대기, 호출 실패 별도 표시 |
| T-82 | RQ-31, RQ-34 | integration | 복구와 기존 기록 | 조정 프로세스 불명·CLI resume 불가·writer UNKNOWN, migration/backup/restore | 중복 세션/writer 없음, 새 세션 snapshot 복구, 기존 명령/FAIL/PASS/후보/보류 이력 보존 |
| T-83 | RQ-32, RQ-34 | contract | v1/v2 호환 | v1 기존 job, v2 미지원 wrapper, 모르는 필드 묵살, legacy 자료의 필수 데이터 부족 | capability와 job 계약 고정, 조용한 하향/가짜 자료 보완 금지, 필요한 범위만 보완 대기 |
| T-84 | RQ-34 | ui/e2e | 조정 화면·설정 | 제안/명령 접수/실제 성공·STALE·판단 후보·호출 한도·v1 자료·읽기 질문 표시 | 상태 구분, 이전 제안 적용 차단, 조회/질문만으로 실행 없음, 새 설정은 새 job부터 |
| T-85 | RQ-30, RQ-32, RQ-33, RQ-34 | live | 외부 에이전트 조정 인수 | 지정 Linux wrapper로 분석→계획 확인→선행/나머지→실패 재작업→판단→통합, 승인된 Jira/수동 장비 범위 | 실제 버전·호출·보고 근거 기록, 단일 배정/교차 리뷰/사람 시험·최종 검토 유지, 미연동은 구분 |

T-71~85는 오케스트레이터/모듈 보고 v2의 인수 목록이다. 2026-11-06 최종 소스 `1899e034120447559fd8d87129b220936f797895`에서 로컬·모의 시험, Linux/Windows CI, 독립 코드 검토 APPROVED를 확인해 T-71~84를 해당 로컬·모의 범위 PASS로 기록했다. [조건별 시험 연결·최종 CI](runs/20261106-orchestration-v2.md)를 확인한다. 실제 외부 인수 T-85는 NOT_RUN이며 문서 검사는 제품 PASS의 근거로 사용하지 않는다.

## Claude 수동 호출 패키지 (M0)

| ID | 요구사항 | 수준 | 시험 | 절차 | 통과 조건 |
|---|---|---|---|---|---|
| T-86 | RQ-35, RQ-30 | contract | 실제 agent 정의 | 이름/설명/모델/도구 및 기준 문서 확인, 도구 권한 변조 | 구조 유효, Read/Glob/Grep 외 권한·모델 변경 감지. 모델 실행 성공과 구분 |
| T-87 | RQ-35 | unit/contract | 수동 입출력과 다섯 제안 | 정상/실패 JSON, 계획 add/update/deactivate, 재시도/전환/판단/검증 계획 | ID/근거 연결, 모든 응답 검토 전용·실행 없음, 성공/실패 결과 구분 |
| T-88 | RQ-35, RQ-32 | unit/contract | 잘못된 응답·파일 | 다른 ID/시도/원인/해시, 중복 키·ID, 임의 명령/완료 필드, 경로 이탈·변조·외부 링크 | INVALID/오류, 부작용 없음, 누락 근거를 생성하지 않음 |
| T-89 | RQ-35, RQ-34 | unit | 오래된 기준과 재시도 미리보기 | 최신 입력 비교, UNKNOWN/종료 미확인/중지/계획/선행/판단 보류, 독립 분석 | STALE/BLOCKED 구분, 분석의 선행 예외, 자동 실행 없음. 실제 worker 게이트 인수의 대체 아님 |
| T-90 | RQ-35 | integration | 이동 가능한 패키지 | 빈 새 폴더로 내보내기, manifest 확인, 원본 밖 CLI 실행, 같은 경로 재내보내기 | 기준 문서 포함·단독 검사 통과, 기존 파일/DB/CLAUDE.md 덮어쓰기 없음 |
| T-91 | RQ-35 | live | 사용자 Claude 인수 | 지정 환경에서 agent 검색·호출, 실제 응답 검사·제안 타당성 검토 | CLI/모델/시각/입력/응답/검사 근거 존재, 권한과 품질 확인. 사용자가 직접 수행 |

T-86~90의 실행 증거는 [패키지 시험 기록](runs/20261012-claude-agent-package.md)에 있다. T-91은 실제 Claude를 실행하기 전 NOT_RUN이며 자동 연동 T-71~85와 별도다.

## 소스 기준 자동 기록·브리지 기본값

| ID | 요구사항 | 수준 | 시험 | 절차 | 통과 조건 |
|---|---|---|---|---|---|
| T-92 | RQ-36 | unit/integration | 소스 자동 기록 | 임시 Git HEAD로 실제 모드 job 생성, 이후 HEAD 변경/중복 시작, 빈 데모 기준 | 최초 job 기준 고정, 동일 요청 재사용, 새 작업만 새 HEAD, 데모 Git 불필요 |
| T-93 | RQ-36 | unit | 미확정/직접 기준 | 수정/미추적 파일·Git 없음·커밋 없음·수동 해시·Git 환경변수 오염 | 불명 기준에서 job 미생성·파일 미변경, 유효한 직접 해시만 허용, 지정 폴더의 Git만 참조 |
| T-94 | RQ-36 | unit/api | 브리지 기본값·점검 | 사용자 workspace, 기존 명령/빈 배열, 파일 누락/권한/선택 도구 해제, 추천 API | 경로 제안만 수행, 미설치/실제 연결 구분, 설정/외부 프로세스 부작용 없음 |
| T-95 | RQ-36 | ui/e2e | 설정 화면 사용 | 자동 기준, 작업 폴더 변경, 빈 항목 채우기, 사용자 지정 보존, 저장/재접속/환경 점검 | 기본 경로 갱신·사용자 값 보존·누락 파일 안내, 자동 기준 의도 유지 |


## 작업 폴더 기반 내장 CLI 연결

| ID | 요구사항 | 수준 | 시험 | 절차 | 통과 조건 |
|---|---|---|---|---|---|
| T-96 | RQ-37, RQ-36 | unit | 새 기본·기존 호환 | native 기본, 기존 JSON/사용자 브리지/생성된 미설치 기본값 조회 | 기존 설치/사용자 값과 job 보존, 기본 native, 자동 파일 생성 없음 |
| T-97 | RQ-37 | contract | 도구 탐지·인증 구분 | 모의 --version/--help/auth, 누락/옵션 불일치/로그인 필요/명시 해제 | 모델 호출 없이 상태 구분, 선택 미설치만 대체, 인증 오류 묵살 금지 |
| T-98 | RQ-37, RQ-13 | contract | CLI 실행·결과·권한 | Claude/OpenCode/Codex 모의 프로세스, ID/JSON/세션/근거 누락·오류·권한, 역할 경로, Opus | 지정 cwd와 역할, 구조화 결과만 수용, 실패 echo 검사, 세션 분리, 비밀 실행 토큰 제외 |
| T-99 | RQ-37, RQ-09 | integration | 등록 빌드·검증·통합 | 임시 파일 생성·hash/import, 초기화 파일, nonzero/timeout, 이전 파일/이탈/symlink | 실제 명령/갱신 파일만 성공, 사용자 값 셸 삽입 없음, 외부 BSP 실행 없음 |
| T-100 | RQ-37, RQ-07, RQ-10 | integration | 실행 관리자·고정·복구 | 분석→계획→선행 코드/리뷰/빌드/검증, 같은 잠금, 설정/지침 고정, UNKNOWN·연결 재시도 | 기존 게이트/단일 writer/교차 리뷰 유지, 역할 snapshot, UNKNOWN 자동 재실행 없음, 실패 이력 보존 |
| T-101 | RQ-37, RQ-20 | ui/e2e | 내장 설정 사용 | 기본 내장, 고급 설정, 지침/명령 저장·재접속·사용 해제 | 기본 화면 브리지 배열 없음, 입력 보존, 기존 데모/수동/고급 브리지 회귀 |
| T-102 | RQ-37 | live | 실제 Linux CLI/BSP 인수 | 지정 계정의 도구/인증/권한/모델·지침·BSP 빌드/검증·장비 결과 확인 | 실제 버전과 입력/응답/이미지/시험 증거. 사용자가 직접 실행 전 NOT_RUN |

## GUI Test 공통 모듈

| ID | 요구사항 | 수준 | 시험 | 절차 | 통과 조건 |
|---|---|---|---|---|---|
| T-103 | RQ-38 | unit/contract | TC·COM·소스 | 폴더/Git snapshot, Dual 동일 호스트/다른 보드, 인자 배열, Suite/순서/소스 변경 | 정확한 COM 전달, 임의 셸 실행 없음, 잘못된 매핑/순서 거부 |
| T-104 | RQ-38, RQ-26 | integration | Run·예약·제어·복구 | 동시 시작/중복 명령/정지/재개/취소/UNKNOWN/manager 재시작/제어권 | 종료 증거와 원자 예약, 과거 Attempt 보존, 완료 불변 |
| T-105 | RQ-38, RQ-25 | contract/api | 판정·리포트·안전 | strict parser/exit code/출력 한도/escape/export 및 API 출처 검사 | 모호한 PASS 없음, PDF/HTML/CSV/JSON/log, 경계 거부 |
| T-106 | RQ-38, RQ-23 | integration | Dashboard 자동 결과 | 모듈 독립 결과/미매핑 오류/기준 변경/수동 이력/완료 Job/outbox/격리 | 전체 Run 완료 뒤 반영, 새 Attempt/승인, 운영 DB 무변경 |
| T-107 | RQ-38, RQ-20 | ui/e2e | 공통 웹 데모 | 단독/통합 TC 선택·Suite·프로파일·실행·복구·탭 이전·내보내기 | 실제 브라우저 Mock 흐름 및 기존 Dashboard 5개 회귀 통과 |
| T-108 | RQ-38 | live | 회사 Windows/TC/RBM 인수 | 실제 OS COM/기존 명령/SSH/보드 이미지 증빙/API/Dashboard Delta 확인 | 승인된 실환경에서 결과/배타 사용/보존 정책 검증. Mock 통과로 대체 불가 |

## GUI Test 사용성 후속 변경

| ID | 요구사항 | 수준 | 시험 | 절차 | 통과 조건 |
|---|---|---|---|---|---|
| T-109 | RQ-39, RQ-20 | ui/e2e | 설정 접기·복원 | 소스/Suite/연결/실행 설정의 마우스·Enter/Space 조작, 입력 후 접기/펼치기, 새로고침 | 입력/선택 유지, 요약과 결과 표시, 접힘 상태 복원, 숨긴 입력에 포커스 없음 |
| T-110 | RQ-39, RQ-38 | ui/e2e | TC 목록 정돈·선택 | 폴더 일부/전체 선택, 폴더 접기, 검색·유형 필터·결과 없음·초기화, 좁은 화면 | 부분 선택/개수 정확, Single/Dual 구분, 필터 밖의 선택 보존, 클릭과 펼침이 독립 |
| T-111 | RQ-39, RQ-38 | ui/e2e | 실행 순서 드래그 | TC 위/아래/처음/끝 드래그, 취소/동일 위치, 위아래 이동 버튼 없음, Preflight 후 순서 변경 | TC 유실/중복 없이 기대 순서, 삽입 위치 표시, 이전 Preflight 해제·재검증, 기존 Run 순서 불변 |
| T-112 | RQ-39 | ui/e2e | TC 경로 트리·표시 정렬·패널 | 다단 폴더 검색/이름·시간 정렬/숨김·너비/새로고침/좁은 화면·GUI-UI-18 진행률 아래 조작/세션 선택/상시 결과 | 선택·실행 순서 유지, 설정 접힘/너비 복원; D-54의 실행·세션·결과·로그 상시 표시 |
| T-113 | RQ-43, RQ-38 | unit/ui | 실패 TC 단독 재실행 | 완료 FAIL TC 하나를 새 Run 실행 | 단일 TC·원본 snapshot·parent 연결·원본 실패 보존·부분 Dashboard 무반영 |
| T-114 | RQ-42 | unit/ui | 모델별 사용량 | 복수 모델/누적 갱신/중복·오래된 snapshot/비용 미수집/재시작·GUI-UI-17 상세 접기/진행 요약 | 중복 합산 없음·TC별 영속 집계·미집계/부분/0 구분·진행률 아래 완료 수/비용 표시 |
| T-115 | RQ-39 | ui | 설정 탭·복귀 경로 | 소스/Suite/연결/실행 설정 이동·입력 보존·돌아가기/톱니바퀴/Esc | 기본 결과 화면·설정 중 입력 유지·복귀 후 포커스·시작은 결과에서 가능 |
| T-116 | RQ-40, RQ-38 | unit/api/ui | TC별·전체 반복 | 기본1·개별2/전체2·복구·중단·Suite·잘못된 값/한도·FAIL 후 PASS | 고정 plan/정확 진행률·이전 FAIL 보존·동일 slot 복구·서버 검증·구버전 호환 |
| T-117 | RQ-39 | ui | 작은 탐색기형 TC 목록 | 32px 행·반복 편집·이름/유형/시간 헤더 방향 전환·표시 순서 복원 | 표시 정렬로 실행 순서 불변·드롭다운 제거·키보드 접근·좁은 화면 |
| T-118 | RQ-41 | unit/ui | 실제 실행 대상 기록 | local/Single·Dual 이름/연결 불일치/변경·완료 후 callback/DB 재열기/과거 미기록 | 실행 당시 대상만 표시·보드 pin 대조·기록 없음 구분·Mock local |


## GUI Test Windows 단독 빌드

| ID | 요구사항 | 수준 | 시험 | 절차 | 통과 조건 |
|---|---|---|---|---|---|
| T-119 | RQ-44 | integration | 독립 빌드 | Windows PowerShell 5.1/7에서 gui_test 폴더만 공백 경로로 복사 후 build 실행 | Dashboard/.git 없이 UI/wheel/ZIP 생성, 기본 모듈 시험·설치 wheel E2E 성공 |
| T-120 | RQ-44 | integration | 오프라인 설치 | ZIP을 별도 폴더에 풀어 새 venv에 --no-index 설치, 소스 밖에서 start/status/restart/stop | health 및 JS 제공, Mock 5 시나리오 성공 |
| T-121 | RQ-44, RQ-25 | unit/contract | 패키지 경계 | standalone ZIP manifest 및 로컬 데이터 제외, legacy --base 동작 시험 | 해시 일치, 실행 DB/로컬 설정/빌드 캐시 제외, 기존 통합 patch 모드 보존 |

## TC 명령 템플릿

| ID | 요구사항 | 수준 | 시험 | 절차 | 통과 조건 |
|---|---|---|---|---|---|
| T-122 | RQ-45 | unit/contract | 명령 치환·거부 | TC 이름/파일/경로, Single/Dual COM, 공백 경로, 미등록/중복/누락 변수 | argv 정확, 임의 셸 실행 없음, 잘못된 형식 거부 |
| T-123 | RQ-45 | integration | 프로파일·snapshot | 저장/조회/재시작, 오래된 버전, Run 중 변경 및 복구 | 현재/후속 Attempt의 snapshot 유지, 이전 Run 호환, hardware 차단 |
| T-124 | RQ-45 | ui/e2e | 명령 설정 화면 | Single/Dual 편집·저장·조회·미리보기·Mock 실행 | 치환 결과 표시, 수정 시 Preflight 무효, Run argv와 로그 일치 |

## 2026-11-03 빌드·전체 선택·Windows 실행기

| ID | 요구사항 | 수준 | 시험 | 절차 | 통과 조건 |
|---|---|---|---|---|---|
| T-125 | RQ-39 | ui/e2e | 전체 선택 | GUI-UI-14/15; 이름과 같은 행 왼쪽 전체/부분 선택·필터·빈 결과·비활성·키보드·좁은 화면 | 선택·순서·Preflight 상태 정확; 필터 밖 선택 유지 |
| T-126 | RQ-44 | integration | scripts 빌드 | PowerShell/CMD/Bash 진입점과 대상·오류 종료; Windows Restricted 정책에서 CMD 호출 확인 | 지정 화면 빌드 및 실패 비정상 종료; LF/CRLF·공백 경로·인자·정책 비영속 확인 |
| T-127 | RQ-46 | unit/contract | Windows 실행 근거 | 가짜 TC/COM7·n295/n296 노드명으로 Single -p·Dual -n/-n2·python/python3 고정 실행 파일·source·인증·argv·중복·취소·timeout·로그·종료 코드 검사 | 위조 PASS/중복 실행 없이 마지막 근거 보존 |
| T-128 | RQ-46, RQ-38 | integration | Dashboard 실행 관리자 | 새 adapter Run·반복·실패·복구 및 Mock/과거 Run 회귀 | 종료 불명 예약 유지; 실제 Job 미연동; 기존 기록 호환 |
| T-129 | RQ-46 | ui/e2e | Windows 모드 UI | capabilities fixture로 배너·Single -p/Dual -n/-n2 기본값 저장·노드명 요청·프로파일·hardware 요청·Job 차단 확인 | Mock 오표시/암묵 실행 없이 Windows 모드 요청 |
| T-130 | RQ-46 | live | 실제 Linux/Windows/COM 인수 | 사용자 환경에서 공유 소스·SSH·Single/Dual·중단·복구 검증 | 환경·실보드 증거와 함께 검증; 미실행은 NOT_RUN |

## 자동 이미지 퓨징·TC

| ID | 요구사항 | 수준 | 시험 | 절차 | 통과 조건 |
|---|---|---|---|---|---|
| T-131 | RQ-47 | unit/contract | 이미지·설정 고정 | manifest 생성/검사, 경로·해시·용량·미설정·TC 변경 시험 | 콘솔 명령 전 거부; 검증된 snapshot만 실행 |
| T-132 | RQ-47 | integration | 콘솔·퓨징·TC 순서 | 가짜 Single/Dual 콘솔/fastboot/배치/TC로 정상·실패·부팅 timeout | 확정 명령 순서, 고유 대상, 부팅·포트 해제 후 TC; 실패 후 TC 차단 |
| T-133 | RQ-47 | integration | 중복·복구·예약 | 응답 유실/지연 요청/재시작/실행 종료 불명/동시 TC/endpoint 변경 | 재퓨징 없음; UNKNOWN 예약 유지; 기존 결과 조회 복구 |
| T-134 | RQ-47 | integration | BSP 동일 Attempt 결과 | 검증 단계 진입·필수 사례·stale baseline·lease·raw 결과 검사·수동/Mock 회귀 | 일치하는 전체 근거만 반영; 최종 사람 검토 유지 |
| T-135 | RQ-47 | ui/e2e | 자동 상태 표시 | 단계·완료 수·사례·접이식 로그·기존 Dashboard 표시 | 저장된 상태 표시와 키보드 접기, 기존 수동 UI 유지 |
| T-136 | RQ-47 | live | 실제 이미지 퓨징 인수 | 실제 배치/콘솔/serial/공유 폴더/재부팅/TC/단절·복구 검증 | 실제 보드 근거 필요; 미실행 NOT_RUN |

## 실제 연결 설정 마법사

| ID | 요구사항 | 수준 | 시험 | 절차 | 통과 조건 |
|---|---|---|---|---|---|
| T-137 | RQ-48 | unit/integration | 최초 입력·저장·변경 | 임시 경로에서 입력·취소·재실행·원자 교체 실패·백업·기존 추가 필드 검사 | 저장한 선택 재사용; 취소/실패 시 원본 보존; SSH/runner 단일 저장 |
| T-138 | RQ-48 | unit/contract | 인증·명령 경계 | Windows DPAPI/Linux600·토큰 비노출·고정 argv·COM/노드·HTTP redirect/proxy 거부 | 보호 저장/복원; SSH로 토큰 미전달; 입력 셸 실행 없음 |
| T-139 | RQ-48 | integration | 설치·진입점·프로세스 | 가짜 설치/서비스/SSH 및 작은 POSIX 자식으로 오류·종료·포트·wrapper 반환 검증 | 기존 서비스 미종료; 소유 자식 정리; 종료 코드 보존; Mock 대체 없음 |
| T-140 | RQ-48 | unit/integration | 이미지 설정·manifest | 임시 배치 해시·활성 확인·기존 모듈/콘솔 매핑·legacy Dual·TC 순서·manifest 명령 검사 | 설정만 저장; 실제 장비 호출 없음; 기존 계약 보존 |
| T-141 | RQ-48 | live | 실제 양쪽 설치·연결 | 사용자 Linux/Windows에서 최초 설정·재사용·변경·SSH·실제 TC/퓨징 인수 | 실제 환경 증거 필요; 모의 시험으로 대체하지 않음 |

2026-11-06 포트 인자 후속: T-138은 기본8771·alias·범위 검증과 독립 SSH 매핑·token 비전달, T-139/158은 CLI 전달·사용자 포트 준비 조회/실행·포트 충돌·저장값 비변경·소유 자식 정리를 포함한다. T-140은 Linux 이미지 설정의 읽기 전용 조회와 저장 URL이 유효한 역방향 포트를 따르는지 확인한다. 실제 회사 SSH/보드는 T-141/160에 남긴다. [이번 실행 기록](runs/20261106-runner-ports.md).


## Test 현황 실제 연결 보기

| ID | 요구사항 | 수준 | 시험 | 절차 | 통과 조건 |
|---|---|---|---|---|---|
| T-142 | RQ-49 | unit/integration | 실제 보기 API 격리 | 미설정/단절/가짜 응답과 위조 실행·기존 manager 재사용 검사 | 빈 목록·새 실행 차단·오프라인 중단 유지·Mock 기록 분리 |
| T-143 | RQ-49 | ui/e2e | 실제 보기 전환 | 전환·재로드·상태·실행 비활성·복귀 검사 | 선택 유지; 가짜 TC/보드 없음; Mock 기록 보존 |

## 다이어그램 탭 · 로컬 모의 검증과 실제 인수

| ID | 요구사항 | 수준 | 시험 | 절차 | 통과 조건 |
|---|---|---|---|---|---|
| T-144 | RQ-50 | ui | 구조·IP 펼침 | 복수 선행/일반 IP·loading/빈 그룹·동명 다른 id·잘못된 group fixture; 개별 클릭/키보드·탭 왕복·작업 전환 | 4개 상위 노드 가로 연결; 실제 소속 IP; 그룹 독립 접기/펼치기와 요약·하위 펼침 보존; 독립 5단계 오른쪽 가로 펼침; 축소/확대·영역 집중/전체 복귀; 그룹/단계 겹침 없음; 같은 작업 펼침 유지/새 대상 초기화; 가짜 IP/그룹 추정 없음 |
| T-145 | RQ-50 | unit/ui | 상태·유효성·진행률 | 첫 미완료와 RUNNING 구분; code/build 조합; RUNNING+paused/blocked_reason; CANCEL_REQUESTED/UNKNOWN; 수동/자동 Test; 무효화·N/A·미집계·누락/미지원 상태·계획 변경 fixture | 연결 상태와 무관한 실제 실행 보존; 유효 성공만 완료; 빌드/퓨징만으로 단계 완료 없음; 서버 진행률 하락 보존; 5등분/게이트/최종 완료 추정 없음; 기존 상단 집계 불변 |
| T-146 | RQ-50 | unit/integration | 연결·조회 수명 | 최초 응답 전·ACON/API 독립 상태·같은 version 반복 성공·장시간 상태 불변·지연/실패·이벤트만 실패·역순·A→B→A·명령 충돌 복구 중 작업 전환·영구 pending/늦은 응답·지속 version 역행 재현 | 조회/저장/ACON 시각 구분; 모든 snapshot 유입에 세대/version 보호; 신선한 동등 version 관찰 수용; 기존 명령 정책 보존; 모션 신선도 검사; 중복 조회 병합·timeout 잠금 해제·재조회 복구 |
| T-147 | RQ-50 | ui/visual | 연결 점·경로·접근성 | 연결 정상+대기/단절+실행; 일반 IP 병렬 분석+선행 대기; 독립 IP 실패·복수 실행·100개/80자/375px·모션 줄이기/일시정지/페이지 숨김 검사 | 연결 점/실행 문구 분리; 해당 활동 경로만 흐름; 실행 진입선 화살촉의 실제 위치 변화; 일반 분석이 그룹 게이트를 열지 않음; 취소 중·불명·stale 흐름 정지; 키보드/aria·포커스 보존; 배율/집중·창 크기 변경 중앙 유지; 겹침/잘림 없음 |
| T-148 | RQ-50 | integration/build | 폴더 이식·효율·기존 회귀 | apps/web/gui_test 없는 격리 호스트; 통합/GUI 빌드; 회사 전역 CSS fixture; 100개 접힘/모두 펼침/반복 snapshot/비활성 탭·전체 보기 스크롤 왕복; 빈/대표 Attempt·자동 보고 이력의 비용·요청 수 비교 | 앱 역참조/숨은 의존 없음; CSS·SVG id 격리; 명시된 시험 러너로 실행 가능; 추가 polling/모듈별 fetch/실행 명령 0; 접힌 단계 DOM 없음; 환경/응답 bytes/파싱·변환·렌더 시간/렌더 수 기록; 기존 탭 보존 |
| T-149 | RQ-50 | live | 회사·ACON 인수 | 실제 ACON 제공자·작업/IP 대응·관찰/만료·단절과 BackEnd 실행 지속·서버 상태/진행률 대조 | 회사 커밋·환경·근거 기록; 공통/개별 연결 구분; 만료를 실제 모듈 실패로 바꾸지 않음; 미지원은 미확인; 로컬 Mock로 대체하지 않음 |

## 메인 화면 가독성 · D-52

| ID | 요구사항 | 수준 | 시험 | 절차 | 통과 조건 |
|---|---|---|---|---|---|
| T-150 | RQ-19, RQ-20, RQ-39 | ui | 요약 띠·모듈 조작·반응형·TC 아이콘 | 격리된 API fixture로 다섯 집계·N/A·전체/상태 수 확인; 검색/그룹 필터/Enter·Space 펼침; 긴 작업명·소스·경로를 320/375/414/768/1280px에서 표시; GUI-UI-06으로 트리와 설정 조작 확인 | 서버 수치·분모·N/A 보존; 단일 진행률 강조색; 모듈 조작 유지; 페이지 가로 넘침 없음(표 내부 스크롤 허용); 1280px에서 5개 집계 한 줄·높이160px 이하; TC ＋/− 이름·동작 유지 및 설정 텍스트 버튼 잘림 없음. 실제 장비/운영 인수와 구분 |

## 전체 탭 모션

| ID | 요구사항 | 수준 | 시험 | 절차 | 통과 조건 |
|---|---|---|---|---|---|
| T-151 | RQ-19, RQ-20, RQ-39, RQ-50 | ui | 버튼·모달·탭·흐름 모션 | motion.spec.ts의 MOTION-01~04로 전체 6개 탭·GUI 내부 탭, 실제 모달 transition, 키보드·reduced-motion, 카메라·흐름 검사 | 탐색 즉시; 포커스 복원; reduced-motion에서 축소 없음; pan 지연 없음; 흐름 transform/opacity만 사용; 예상하지 않은 실행 명령 없음 |

## TC 트리 단일 토글 · D-52 후속 정정

| ID | 요구사항 | 수준 | 시험 | 절차 | 통과 조건 |
|---|---|---|---|---|---|
| T-152 | RQ-39 | ui | 펼침 상태 기반 단일 ＋/− 토글 | GUI-UI-06에서 전체/부분 접힘, 클릭·Enter·Space, 빈 검색 결과, 선택/실행 순서 검사 | 버튼1개; 모두 펼침이면 −/전체 접기, 접힌 폴더가 있으면 ＋/전체 펼치기; 접근성 이름/title/aria-expanded와 아이콘 일치; 폴더 없으면 비활성; 선택/순서 보존 |

## Windows Runner 포터블 배포 · RQ-51/D-53

| ID | 요구사항 | 수준 | 시험 | 절차 | 통과 조건 |
|---|---|---|---|---|---|
| T-156 | RQ-51 | package | 실제 EXE 오프라인 기동 | 저장소 밖 공백/한글 경로에 ZIP 해제; Python/pip 없는 PATH에서 실행 | 시스템 Python·저장소·pip 다운로드 없이 내장 의존성 로딩 및 메뉴 실행 |
| T-157 | RQ-51 | integration | 설정·토큰·이력 호환 | 최초 설정/--home/기존 JSON 추가 필드와 DPAPI·runtime 재사용 검사 | 저장 확인·백업·기존 이력 보존; 명시적 외부 TC Python; EXE 기본값 금지 |
| T-158 | RQ-51 | integration | Runner와 터널 생명주기 | 실제 EXE 인증 API·가짜 SSH·실패·종료·포트 충돌 검사 | 소유 자식만 정리; 토큰 비전달; 실패 명시; Mock 전환 없음 |
| T-159 | RQ-51 | integration | frozen TC 격리·복구 | 실제 EXE와 무해한 외부 Python TC로 gate/Job Object·중복·취소·timeout·재시작 검사 | 실행 전 격리; 전체 자식 종료 확인; UNKNOWN/중복 방지 계약 유지 |
| T-160 | RQ-51 | live | 회사 환경 인수 | 실제 회사 PC/공유 폴더/SSH/기존 TC Python으로 실행 확인 | 회사 정책·경로·인증·보드 인수 근거 존재; 이번 로컬 작업에서는 NOT_RUN |

## GUI Test 구조 분리 · RQ-54/D-57

| ID | 요구사항 | 수준 | 시험 | 절차 | 통과 조건 |
|---|---|---|---|---|---|
| T-164 | RQ-54 | architecture | 소스 이동·의존 경계·변경 보존 | 이동 전 manifest 비교와 import/경로 정적 검사 | 미커밋 파일 보존; 루트 gui_test/shim 없음; backend 앱 역참조 없음; 공통 UI 호스트 역참조 없음 |
| T-165 | RQ-54 | ui | 공통 UI와 두 빌드 | apps/web 및 apps/gui-test TypeScript·production 빌드와 관련 브라우저 회귀 | 공통 React 소스 사용; 두 화면의 선택·설정·실행 표시 동작 보존; 단독 static 경로 일치 |
| T-166 | RQ-54 | package | 세 경로 독립 반입·Windows 빌드 | ZIP을 Dashboard/Git 없는 공백 경로로 반입; Windows 빌드 및 소스 launch smoke | 앱·공통 Python·공유 UI와 최소 backend 초기화만으로 빌드; 기존 serve/start/status/restart/stop/export CLI 동작 |
| T-167 | RQ-54 | package | wheel staging·설치 호환 | staging wheel 생성 후 저장소 밖 격리 설치·import·CLI·health/JS/config 확인 | 설치 gui_test namespace와 gui-test/gui-test-runner 유지; backend/apps 소스 없이 실행; runtime·비밀·Dashboard 코드 미포함 |
| T-168 | RQ-54 | regression | 기존 API·runtime·실행 계약 | Python/Mock/API·이력 복구 및 RQ-52/53/D-54 회귀·문서 검사 | URL·DB·runtime·설정·프로토콜·게이트 보존; 기존 미커밋 기능 회귀 없음; 실제 장비 호출 없음 |

## 공통 환경 설정·문맥별 편집 · RQ-55/D-59

| ID | 요구사항 | 수준 | 시험 | 절차 | 통과 조건 |
|---|---|---|---|---|---|
| T-169 | RQ-55 | ui | BSP 공통 draft 보존 | 전역→대시보드→Jira→전역 왕복; 잘못된 JSON과 호스트 편집; 전역 설정 전용 표시 확인 | 미저장 텍스트 손실 없음; 문맥별 관련 필드만 표시; 전역에서 TC·실행 작업 UI 숨김; 저장 요청 없음 |
| T-170 | RQ-55 | ui | GUI 중첩 편집기·TC 선택·생명주기 보존 | Test 현황에서 TC 순서·선택·개별 반복을 변경한 뒤 전역/로컬/이력 왕복; 명령·프로파일·Suite·COM·전체 반복 양방향 편집; 기존 Run 리포트 왕복; 지연 capabilities 응답 중 탐색·가상 시계로 polling 확인 | 같은 명령 textarea DOM 유지; 복귀 후 TC 선택·순서·개별 반복·열린 순서 미리보기와 Run/리포트 보존; 전역 TC 작업·진행률·결과·실행 조작 숨김; 양방향 설정 draft 보존; 초기화 중복 없음; 비활성 GUI 조회 0·활성 조회 재개 |
| T-171 | RQ-55 | ui | 보기 모드 pending 공유 | 전역 선택→로컬 확인·되돌림→전역 적용 | 명시적 적용 전 URL·실행 모드 유지; pending 공유; 적용 후 reload·저장된 모드 일치 |
| T-172 | RQ-55 | ui | 단일 Test 설정·항목 콤보·접기·반응형·저장소 장애 | 전역/로컬의 단일 Test 접기와 항목 콤보, 기본 연결·1회·기존 소스·조회100초 확인; 임의 반복37회 왕복·숨은 항목 Tab 제외; 1360px/375px 캡처와 폭 검사; Enter·Space·전체 접기/펼치기·reload·preference 예외 | 같은 콤보 DOM과 draft 유지; 기본 화면 높이640px 미만; 요청 없는 기본값·전환; 접기 상태 보존; 숨은 TC 작업 UI·sidebar 공간 없음; 가로 넘침·중복 ID 없음; 저장소 실패 중 조작 가능 |
| T-173 | RQ-55 | ui | 숨겨진 잘못된 필드·설정 조회 오류 표시 | 잘못된 BSP JSON 입력 후 전체 접기·Jira 문맥에서 저장; 숨은 Test 조회 설정 GET 실패 후 재시도 | 전역으로 이동·필드 펼침·포커스; 원문 유지; Test 오류의 항목·고급 접기 자동 열림과 재시도; 저장/점검 요청 0; not focusable 오류 없음 |
| T-174 | RQ-55 | ui | BSP 저장 왕복·Preflight 무효화 | 전역/로컬 각각 저장→reload; GUI Preflight 후 전역에서 반복 편집 | 서버 version envelope 저장·반대 위치 값 일치; GUI 편집 후 시작 비활성; 불필요한 BSP 저장 없음 |
| T-175 | RQ-55 | ui | GUI 개별 저장 범위·재로드 | GUI draft 작성→BSP 저장→명령/연결 명시 저장; 반대 위치 reload·명령 저장 | BSP 저장은 GUI를 저장하지 않음; GUI 명명 저장·재로드 양방향 보존 |

## TC 소스 등록·고정 스냅샷 전달 · RQ-56/D-60

| ID | 요구사항 | 수준 | 시험 | 절차 | 통과 조건 |
|---|---|---|---|---|---|
| T-176 | RQ-56 | unit/integration | 실제 폴더·Git 소스 준비 | 임시 폴더 binary 보조 파일, 여러 커밋 branch, Git TC 하위 폴더; 원격 ls-remote/fetch 경계만 local Git으로 대체 | 전체 bytes 고정·실제 refs/commit 사용; 상대 TC 경로; 원본 HEAD/index/미커밋 bytes 불변; 실제 원격 호출 0 |
| T-177 | RQ-56 | unit/integration | 소스 세대·CAS·실패·복원 | 같은 bytes 다른 경로/재등록, 서비스 재시작, stale version/누락 inspection/ref/원격 branch 변경, Legacy 복귀, 오래된 Suite·Preflight | revision 세대/소스 구분; 실패 시 active 보존; version 지속; 기존 snapshot 보존; 오래된 선택/시작 거부 |
| T-178 | RQ-56 | unit | 스냅샷 ZIP 무결성·경계 | 왕복·중복 upload, attempt 복사, bytes/manifest/ID 변조, traversal/ADS/장치명/case 충돌/symlink, 축소 파일/전체 byte 상한 | 정확한 bytes·반복 수신 일치; attempt간 변경 격리; 잘못된 입력 거부·부분 snapshot/경로 이탈 없음 |
| T-179 | RQ-56 | integration | Manager·API·Windows 소스 전달 계약 | normal/live API 등록·CAS·offline catalog; Run 생성 후 소스 변경; 임시 Host/가짜 COM 매핑으로 보조 파일을 읽는 무해한 Python; old capability/잘못된 ack/legacy hash | Run/attempt 고정 source 유지; 새 등록 bytes가 전달·실행됨; Host.root/원본 불변; old runner 명시 거부; legacy hash 호환; 실제 보드 I/O 없음 |
| T-180 | RQ-56 | ui | 공통 소스 draft·실제 refs·Legacy 복귀 | 전역/로컬 위치·종류·선택 refs 왕복, 입력 변경, 명시적 Legacy 확인/적용 | 같은 editor DOM·draft 유지; 확인된 refs만 표시; stale ref 적용 금지; Legacy 복귀와 입력 draft 보존 |
| T-181 | RQ-56 | ui | 늦은 조회·실패한 적용 | 지연 inspect 도중 입력 수정, 409 apply fixture | 예전 refs가 새 입력을 덮지 않음; 기존 active/catalog/선택 보존 |
| T-182 | RQ-56 | ui | 적용 reset·offline 준비·Preflight/Suite | 적용 중 input 잠금, 새 catalog, 명령 draft 유지, 선택/반복 reset, 통과했던 Preflight·이전 Suite, disconnected live 표시 | command DOM 유지; 새 TC 명시 선택·반복1·Preflight 재검사; 오래된 Suite 거부; catalog 읽기 가능·실행 비활성 |

## GUI 호스트 이식·UI 동일성 · RQ-57/D-61

| ID | 요구사항 | 수준 | 시험 | 절차 | 통과 조건 |
|---|---|---|---|---|---|
| T-183 | RQ-57 | architecture | 공통 Python 호스트 독립성 | imports/독립 source 실행·명시 주입 점검 | 공통 domain/services 역참조 없음; public factory와 실제 composite Runner 동작 |
| T-184 | RQ-57 | integration | 호스트 조립·API/worker 호환 | 일반/live router와 host demo mount, module selection/result 흐름 확인 | 기존 prefix·오류·runtime/DB·single worker·게이트 보존 |
| T-185 | RQ-57 | regression | RQ-56 source 오류·legacy 호환 | 폴더/Git/manifest·source 전달·기존 Windows capability/legacy 회귀 | 잘못된 source fail-closed; old capability 명시 거부; 원본/이력 보존 |
| T-186 | RQ-57 | package | fail-before-I/O | --base CLI/프로그램 호출·invalid target/충돌 옵션·기존 output sentinel | collection/Git/output 접근 전 실패; 승인된 artifact 보존 |
| T-187 | RQ-57 | package | 현재 source-only 호스트 ZIP | 현재 세 roots·미추적 소스·host-reference·manifest/entry hash·ZIP 링크 해석 | static/wheel/누적 patch 없음; 필요한 소스/잠금/contract 포함; 문서 내부 링크 해석; 모든 entry checksum |
| T-188 | RQ-57 | package | 단독/staging Git 독립성 | Git 없는 경로에서 standalone·stage-wheel·설치 smoke | 기존 static/wheel/namespace/CLI 보존; 호스트 코드 미포함 |
| T-189 | RQ-57 | ui | public UI·스타일 격리·fixture 동일성 | 두 UI build; 고정 browser/viewport/font에서 shared fixture·상충 host CSS | 같은 component/CSS/token·host adapter; 선택/draft/키보드/375px 보존; core 스타일 오염 없음 |
| T-190 | RQ-57 | live | 회사 GUI·호스트 실제 인수 | 회사 구조/정책·실제 browser/font·API/Runner 연결과 shared fixture 비교 | 회사 근거와 적용 이력 존재; 이번 로컬 구현에서는 NOT_RUN |

## TC 목록 조회 제한 시간·로딩 표시 · RQ-58/D-62

| ID | 요구사항 | 계층 | 시험 | 절차 | 통과 조건 |
|---|---|---|---|---|---|
| T-191 | RQ-58 | unit/API | 조회 설정 검증·영속 저장 | `backend/gui_test/tests/test_catalog_settings.py`: 기본값, 1/600 경계, 엄격 정수·추가 필드 거부, normal/live API, 독립 읽기, atomic replace 실패 | 기본 100초; 1~600 정수만 저장; 실패 전 bytes 유지; 별도 `gui-test-settings.json`; 연결 준비·장비 요청 없이 저장·재시작 복원 |
| T-192 | RQ-58 | unit/integration | 목록 요청·마법사 제한 시간 범위 | 위 Python 시험 및 `tests/test_catalog_timeout.py`: mock HTTP timeout 관찰, API/worker 독립 adapter, stdlib opener, Windows/Linux runtime, CLI override, 단계별 flush·오류 | 목록만 기본 100/저장값; 진행 중 값 고정·다음 요청에 변경 반영; identity/boards/control 5초; 안전한 목록 timeout 오류; 실제 TC·보드 실행 없음 |
| T-193 | RQ-58 | ui | 지연 목록 로딩·설정 draft·실패·오래된 응답 | `tests/e2e/catalog-loading.spec.ts`: deferred catalog, reduced-motion, global/local draft, 명시 저장·reload, refresh 실패·retry, 비활성 뒤 늦은 응답 | 완료 전 status/spinner; reduced-motion 회전 없음; 초기 자동 선택; 중복 조회 금지; 실패 시 목록/선택 보존; 설정 편집 가능; 오래된 응답 무시 ; source GET/PUT 비동기 경합 4개 사례 |
| T-194 | RQ-58 | live | 회사 공유 폴더·실제 Windows 실행기 인수 | 실제 회사 공유 소스 지연·설정 저장·API/worker 재조회·실제 브라우저 확인 | 실제 환경 증거 필요; 로컬 모의 검증으로 승격하지 않으며 현재 NOT_RUN |

## 실행·진단 명령 · RQ-59/D-63

| ID | 범위 | 기대 결과 |
|---|---|---|
| T-195 | 포트 프로파일 | 우선순위·원자 저장·오류 및 기존 설정 보존 |
| T-196 | doctor | 단계·선택·오류·timeout, TC/퓨징 미실행 |
| T-197 | 진입점·래퍼 | 인자 전달·종료 코드·대기 없음 |
| T-198 | 새 ZIP | 안내서·래퍼·실제 패키지 smoke |
| T-199 | 회사 인수 | 실제 SSH·공유 폴더 환경 별도 확인 |

## RQ-60 / D-64 · 인수 시험 계획

T-200~207은 Windows 로컬 모의 범위 PASS다. T-208은 일부 패키지 근거만 확보해 NOT_RUN이며 T-209 실제 회사 인수는 NOT_RUN이다. [구현 검증 기록](runs/20261107-bsp-upgrade-integration.md).

| ID | 요구사항 | 구분 | 범위 | 통과 조건 |
|---|---|---|---|---|
| T-200 | RQ-60 | 인수 | 수명주기 | Linux 백엔드와 선택 UI를 묶고 독립 단일 worker를 시작·재사용하며 플러그인 종료 후에도 실행 유지 |
| T-201 | RQ-60 | 인수 | 비동기 HTTP | 시작·상태·로그·보고 조회; 동일 요청 재전송은 같은 작업으로 멱등 처리하고 충돌 요청 거부; 미리 보기 토큰과 고정 설정·스냅샷을 시작 요청에 결속 |
| T-202 | RQ-60 | 인수 | 선택 | 저장된 전역·모듈 패턴으로 자동 선택, 미리 보기와 수동 수정; 확정된 선택·설정·스냅샷을 토큰에 결속하고 변경·오래된 미리 보기 거부; 매 실행 승인 강제 없음 |
| T-203 | RQ-60 | 인수 | 소스 스냅샷 | BAT 디렉터리 전체와 설정된 TC 루트·의존성 보존; 선택 glob에 일치 없음 또는 경로 이탈 시 실패; 미리 보기와 실행이 같은 고정 스냅샷·설정을 사용 |
| T-204 | RQ-60 | 인수 | 프로파일 | 저장된 명령 프로파일, Runner 보드·COM 기본값과 사전 점검 |
| T-205 | RQ-60 | 인수 | 퓨징·TC | 사전 로그인과 reboot lkshell·fast, 배치당 한 번 BAT 퓨징·재부팅, 새 로그인 프롬프트; TC가 로그인 담당; 가상 COM 분배 관찰자는 로그·panic 읽기 전용. 퓨징 중 시간 초과나 로그 넘침으로 프로세스를 종료하지 않고 분할된 panic을 감지하며 오래된 마커를 배제하고 관찰이 실행을 방해하지 않음 |
| T-206 | RQ-60 | 인수 | 재시도 | 최초 PASS면 다음 진행; 일반 FAIL은 총 최대 3회 중 2회 PASS 필요; 원시 시도 보존 및 반복 슬롯 비사용; boot panic 재시도 없음; 최종 FAIL 시 나머지 미완료로 중단 |
| T-207 | RQ-60 | 인수 | 연결·복구 | 플러그인 연결 해제는 실행 중 작업에 영향 없음; 안전하게 확인된 취소는 기존 취소 규칙 적용; Windows 상위 예약이 퓨징·TC·재시도 전체에 유지되고 D-48 교차 런타임 경합과 오래된 소유자를 차단. TC 전 UNKNOWN은 근거로 복구하며 무조건 재퓨징하지 않음 |
| T-208 | RQ-60 | 인수 | 패키지 | 고정 버전·잠긴 의존성·체크섬 manifest로 Linux 백엔드·선택 UI와 독립 Windows Runner 설치 검증; BSP worker 없이 시작·재사용하고 기존 호환성과 복원 검증 |
| T-209 | RQ-60 | 인수 | 회사 인수 | 실제 회사 보드와 가상 COM 분배기 연동 검증 |

| ID | 요구사항 | 유형 | 영역 | 검증 내용 |
|---|---|---|---|---|
| T-210 | RQ-61 | 인수 | 빌드 | 한 명령 빌드, 오프라인 캐시 검증 및 실패 처리 |
| T-211 | RQ-61 | 인수 | 실행 | 이동한 ZIP을 시스템 Python과 네트워크 없이 실행 |
| T-212 | RQ-61 | 인수 | 편집 | 소스 수정이 재시작에 반영되고 재포장 출처가 기록됨 |
| T-213 | RQ-61 | 인수 | 설정 | 기본값·저장값·CLI 우선순위와 endpoint 일치 |
| T-214 | RQ-61 | 인수 | 충돌 | 로컬 포트 대체, 원격 불변, 중복 실행과 경합 처리 |
| T-215 | RQ-61 | 회귀 | 격리 | 기존 home·보안·TC Python·실행 및 복구 정책 보존 |
| T-216 | RQ-61 | 인수 | 패키지 | manifest·체크섬·안내·민감정보 배제 및 기존 산출물 보존 |
| T-217 | RQ-61 | 인수 | 회사 | 회사 정책·공유 경로·SSH·TC Python·COM 및 장비 실제 인수 |
