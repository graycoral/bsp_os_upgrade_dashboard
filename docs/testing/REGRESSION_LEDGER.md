# 회귀·결함 기록

## 2026-11-03 병합 브라우저 회귀

- REG-0015: GUI-UI-03에서 worker 전이와 제어권/일시정지 클릭이 겹치면 서버가 VERSION_CONFLICT로 거부한다. 시험은 유효한 재시도 없이 PAUSED만 기다려 실패했다. 서버 정책은 유지하고 정확한 409/VERSION_CONFLICT에만 GET snapshot 후 동일 UI 조작을 최대 3회 재시도하도록 시험을 수정했다. RQ-11/RQ-38, `tests/e2e/gui-test.spec.ts` control/GUI-UI-03. 최초/두 번째 실패와 재시험은 [20261103-merge](runs/20261103-merge.md), 수정 기준은 해당 source manifest와 병합 커밋이다. 실제 제품 동시성 결함으로 확대하지 않으며 재시험 결과는 증거 JSON으로 확인한다.

  최종 VERIFIED: 수정 커밋 `d551492`, [20261103-merge-ci](runs/20261103-merge-ci.md)의 통합 브라우저18/단독13 PASS. 기존 실패 기록과 서버 버전 게이트를 보존했다.

확인된 로컬 결함과 수정은 아래 이력으로 관리한다. 실제 연동 미검증 위험을 발생한 버그로 작성하지 않는다.

| 필드 | 필수 내용 |
|---|---|
| regression_id | REG-0001부터 증가, 재사용 금지 |
| 증상·재현 | 입력·상태·동작·실제/기대 결과 |
| 영향 | RQ ID, 모듈/경로, 사용자 영향 |
| 최초 실패 | run_id, 코드/시험 revision, 증거 |
| 원인 | 확인 근거 또는 아직 미확인임을 명시 |
| 수정 | 수정 revision, 변경 요지, 대안/주의 |
| 방지 시험 | 기존/신규 T ID, 자동화 경로 |
| 재시험 | 새 run_id, PASS/FAIL, 증거 |
| 상태 | OPEN / FIXED_PENDING_VERIFICATION / VERIFIED / REOPENED |
| 정상 기준 | 검증 후 갱신한 baseline ID 또는 미반영 사유 |

같은 증상이 다시 발생하면 기존 REG를 REOPENED로 만들고 새 실패 실행을 연결한다. 이전 수정 기록을 지우지 않는다. 근본 원인이 다르면 새 REG를 생성하고 관련성을 연결한다.

## 2026-10-12 검증된 수정 기록

공통 수정 기준은 [구현 검증 기록](runs/20261012-implementation.md)의 code_revision/파일 manifest다. 새 코드가 커밋되기 전의 내용 해시로 시험 대상과 결과를 연결한다. 운영 baseline은 미등록이다.

| ID | 재현 / 원인 | 수정 / 방지 시험 | 최초 실패 → 재시험 | 상태 |
|---|---|---|---|---|
| REG-0001 | 첫 UI 빌드에서 nullable 객체 타입 검사 실패 | 명시적 null 보호 / TypeScript 빌드 | initial-build-failed → build PASS | VERIFIED |
| REG-0002 | 수동시험 select label 탐색이 선택지 텍스트와 충돌 | aria-label 명시 / T-59 UI | initial-browser-01-failed → 현재 browser PASS | VERIFIED |
| REG-0003 | 다른 모듈 상태 갱신 중 재시도 요청의 job version 충돌 | 동일 attempt/계획 명령에 한해 최신 버전 재접수, 서버 게이트 유지 / T-59, T-66 | initial-browser-02-failed → initial-browser-passed 및 현재 PASS | VERIFIED |
| REG-0004 | 시험 API bind 실패 후 기존 서버의 health를 성공으로 수용 | 사전 포트 확인, 새 runtime/키, 자식 프로세스 상태 확인 / 전체 UI runner | browser-failed 3 FAIL → 격리 재시험 3 PASS | VERIFIED |

RQ-14/15 입력 간소화와 RQ-28 데모 예외는 사용자 정책 변경이며 기존 필수 입력 계약을 버그로 기록하지 않는다. 새 정책의 방지 시험은 T-61~67이다.

## 후속 로컬 진입 검증

| ID | 재현 / 원인 | 수정 / 방지 시험 | 최초 실패 → 재시험 | 상태 |
|---|---|---|---|---|
| REG-0005 | 제거된 로그인 POST 경로를 무조건 404로 예상했으나 UI static mount가 있으면 405. 시험 기대값 오류 | T-68에서 정적 UI 유무에 따른 404/405 및 쿠키 미발급 확인. 다른 출처 차단 검증 유지 | backend-01: 86 PASS/1 FAIL → backend-02: 87 PASS | VERIFIED |

이번 수정 기준/실행별 결과/원문 출력은 [키 없는 진입 검증](runs/20261012-local-entry-agent-contract.md)에 있다. 첫 실패 당시 시험과 최종 수정 시험은 구분한다. D-38 접속 키 제거는 사용자 정책 변경이며 그 자체를 결함으로 기록하지 않는다. REG-0004의 시험 서버 식별은 새 runtime/키 방식에서 새 runtime/instance_id 대조로 갱신했고 UI 3개 PASS를 확인했다. 실제 운영 baseline은 미등록이다.

## 오케스트레이터 문서 확장

2026-10-12 D-39는 신규 설계이며 제품 코드 변경/결함 수정이 아니다. REG-0001~0005와 최초 FAIL·재시험 기록을 그대로 보존한다. T-71~85는 향후 회귀/인수 목록으로 추가했으며 아직 NOT_RUN이다. 실제 구현에서 결함이 재현되면 별도 REG와 실행 증거를 연결한다.

## 2026-10-12 M0 추가 확인

[Claude 패키지 실행](runs/20261012-claude-agent-package.md)에서 새 수동 계약의 ID/해시/권한/오래된 기준/UNKNOWN/덮어쓰기 거부 시험을 추가했다. 이 변경의 시험에서 발견되지 않은 결함을 새 REG로 만들지 않는다. 기존 REG-0001~0005와 최초 실패 기록은 그대로 유지하고 기존 기능 회귀를 함께 확인한다.

소스 기준/브리지 편의 변경은 T-92~95와 [20261012 실행](runs/20261012-settings-defaults.md)에 연결한다. 입력 편의 변경이 기존 job 기준이나 사용자 지정 명령을 바꾸지 않는 회귀 시험을 추가했다. 이번 시험 FAIL은 없고 기존 결함 이력은 유지한다.


## D-42 내장 연결 회귀

| ID | 재현 / 원인 | 수정 / 방지 시험 | 최초 실패 → 재시험 | 상태 |
|---|---|---|---|---|
| REG-0006 | 새 select/textarea의 중첩 텍스트가 정확한 label 탐색에 포함됨. 이전 REG-0002와 같은 유형이 새 필드에서 발생 | 명시 aria-label, 저장/재접속 T-101 및 고급 모드 T-95 | browser-initial/second → browser 최종 기록 | VERIFIED |
| REG-0007 | 브리지 추천 API 응답 중 workspace 편집 시 이전 workspace 기본 경로가 늦게 적용됨 | 응답 반영 때 현재 workspace로 기본값 정렬, 사용자 배열/현재 모드 보존 / T-95 | browser-second → browser 최종 기록 | VERIFIED |
| REG-0008 | 종료된 전경 프로세스의 회수한 PGID에 다시 killpg 호출, macOS 경계에서 PermissionError | 정상 종료 후 신호 생략. 종료 권한 실패면 UNKNOWN·잠금 유지 / T-100 | backend-process-failed → Python 217 PASS | VERIFIED |

실행별 최초 FAIL과 재시험은 [내장 연결 실행 기록](runs/20261012-native-cli.md)에 보존한다. 운영 baseline은 NONE이며 실제 Linux 인수와 구분한다.

## 2026-10-25 GUI Test 신규 모듈

| ID | 재현 / 원인 | 수정 / 방지 시험 | 최초 실패 → 재시험 | 상태 |
|---|---|---|---|---|
| REG-0009 | 빈 연결 프로파일 JSON 저장에서 KeyError로 500 반환 | 필수 connection 검증 후 422 반환 / GUI API test_invalid_saved_document_is_validation_error | feature-initial 2 FAIL 중 1건 → feature-second 63 PASS | VERIFIED |
| REG-0010 | 신규 폴더 탐색 시험이 이름 정렬상 첫 TC를 Dual로 잘못 가정 | path로 대상 식별, 분류/중복/메타데이터 충돌 검증 유지 / test_discovery_conflict_duplicates_and_symlink | feature-initial 2 FAIL 중 1건 → feature-second 63 PASS | VERIFIED |

실행 증거는 [GUI Test 기록](runs/20261025-gui-test.md)에 연결한다. 기존 REG-0001~0008의 수정/실패 이력을 보존한다.

- REG-0011: GitHub Actions 최초 실행에서 `--only-binary=:all:`로 끝나는 YAML scalar가 파싱 오류를 일으켜 job 생성 전 실패(run 40146320582). 해당 `run`을 block scalar로 수정하고 YAML 구문을 검증했다. 제품 로컬 시험 PASS와 CI 시작 실패를 구분하며 재실행 결과를 PR에 기록한다.

## 2026-11-01 업데이트 환경 재시험

[실행 기록](runs/20261101-local-update.md): 최초 281 PASS/3 FAIL은 ReportLab 누락과 Git 2.15.1의 init -b 미지원이었다. 공식 패키지 설치 및 이미 설치된 Git 2.54 선택 후 동일 3개 시험과 전체 284개 시험이 통과했다. 제품 코드/시험 기대값 변경은 없으며 신규 제품 결함으로 등록하지 않는다. 서버 바인딩 차단과 설치 미완료는 별도 환경 제약으로 유지한다.

## 2026-11-01 TC 화면 후속

- REG-0012: 375px에서 확장된 결과 표가 카드/페이지 폭을 넘침. 내부 grid minmax(0,1fr)와 결과 표 전용 가로 스크롤로 수정. 수정 커밋: 로컬 미커밋(source manifest 참조). 방지: GUI-UI-06 좁은 화면 검사 및 직접 Chrome 375px 재검사. 실행 ID 20261101-tc-workspace. 전체 자동 E2E는 환경 권한으로 BLOCKED.
- 개발 중 TS null 검사 실패 및 Python DB 재열기 fixture 실패는 [이번 실행 기록](runs/20261101-tc-workspace.md)에 최초 실패와 재시험 결과를 보존한다.

- REG-0013: 설정 톱니바퀴를 다시 눌러도 이전 화면으로 복귀하지 않음(사용자 제보). 원인: onClick이 settings만 설정하고 닫기 동작 없음. 수정: 결과 탭 복귀 버튼·톱니바퀴 toggle·Esc 및 포커스 복원. 방지: GUI-UI-11. 재시험: 20261101-repeat-settings Chrome 직접 3경로 PASS, 전체 자동 UI BLOCKED. 수정 커밋: 로컬 미커밋, [소스 manifest](runs/20261101-repeat-settings-evidence/source-manifest.json).

## 2026-11-02 게시 CI 회귀

- REG-0014: [CI 41441069153](https://github.com/graycoral/bsp_os_upgrade_dashboard/actions/runs/41441069153), GUI-UI-05에서 04_pair를 맨 앞으로 끈 후 03_link 아래로 되돌리면 순서가 그대로여서 FAIL(나머지16 PASS). 행 중앙 텍스트/경계 좌표에 의존한 native drag 경로를 확인하고 명시적 draggable 손잡이와 텍스트 선택 방지를 추가했다. 시험은 같은 위/아래 이동·Preflight 무효화·완료 Run 불변 기대값을 유지하면서 손잡이와 행 내부 하단을 사용한다. 수정: PR #5 후속 커밋. 재시험: CI 후속 실행 대기, 최초 실패 증거는 위 Actions artifact에 보존.

REG-0014 후속: CI 41442024136도 동일 GUI-UI-05에서 실패(16 PASS/1 FAIL). 손잡이 변경만으로 해결되지 않았다. 두 번째 드래그를 실제 포인터의 시작 임계 이동→대상 내부 이동→하단 이동→release로 나누고 native 이벤트를 기록하여 원인을 구분한다. 기대 순서/완료 Run 불변 검사는 유지한다.

REG-0014 원인 확정: CI 41442490944 native 이벤트에서 dragstart(y=969), 원본 행 dragover만 있고 dragend(y=1011), drop 없음. viewport 높이1000 밖으로 놓는 시험 좌표 오류였다. 손잡이/텍스트 선택은 주원인이 아니었다. 대상 행을 scrollIntoViewIfNeeded로 전체 노출한 다음 bounding box를 읽고 하단이 viewport 안인지 검사한다. 실제 포인터 drag와 순서 기대값은 유지한다.

## 2026-11-03 Windows 실행기 독립 리뷰 회귀

공통 수정 기준: [source manifest](runs/20261103-windows-runner-evidence/source-manifest.json), 실행 ID `20261103-windows-runner`. 독립 Astra가 재검토하고 GPT-6-sol이 Python133/브라우저16 PASS를 보고했으며 주 작업자가 결과를 확인했다. 실제 환경 baseline은 갱신하지 않는다.

| ID | 원인·재현 | 수정 / 방지 시험 | 재시험·상태 |
|---|---|---|---|
| REG-0016 | 명령 snapshot 없는 과거 Run claim에서 KeyError | 기본 Mock template fallback / 기존 test_default_and_legacy_runs_keep_mock_template | 최초125 PASS/1 FAIL → sol133 PASS; VERIFIED |
| REG-0017 | Windows os.execv supervisor가 TC exit7을0으로 전달 | 격리 subprocess supervisor와 종료 코드 전파 / test_exit_code_and_invalid_bytes_cannot_become_pass | Astra 독립 exit0→7 재현 및 sol133 PASS; VERIFIED |
| REG-0018 | 로그 조회 뒤 종료 사이 추가 FAIL/overflow 누락 | 종료 후 pipe EOF와 마지막 근거 확인 / test_final_pipe_tail_and_overflow_cannot_be_lost | sol133 PASS; VERIFIED |
| REG-0019 | 실행 전 거부/claim 후 전송 전 장애가 영구 UNKNOWN | durable rejection/reconcile tombstone / test_rejected_source_is_recorded_as_not_started_not_unknown 및 test_claim_before_send_recovery_fences_delayed_start | sol133 PASS; VERIFIED |
| REG-0020 | raw 파일 및 첫 공백까지만 가리는 masking으로 비밀값 잔존 | bounded in-memory capture 및 완성 credential line masking / test_secrets_split_across_writes_never_persist_in_logs | Astra Bearer 독립 재검사 및 sol133 PASS; VERIFIED |

자세한 최초 결함·수정·실패 이력·검토 모델·환경 한계는 [실행 기록](runs/20261103-windows-runner.md)을 따른다. 수정 커밋은 최종 게시 기록에 추가한다.

REG-0016~0020 게시 완료: 수정 커밋 `0ad590d6080c13b3d9618baa18c4aa7b8751737f`, PR #6 main 머지 `a80371c35cee434429871ad8718f97d396710788`. 별도 GPT-6-sol 확인 CI350/21/16 및 Windows133·PS5.1/7 패키지 모두 PASS. 이전 최초 실패·검토 근거는 보존한다.

## 2026-11-03 간결한 TC 목록 헤더

- REG-0021: 전체 선택을 이름 옆으로 이동한 최초 diff에서 최소240px 패널의 이름 셀이32px만 남아 체크박스와 정렬 화살표가 유형 제목에 겹칠 수 있었다. Astra 정적 리뷰 CHANGES_REQUESTED로 발견. 이름 열 최소64px와 끝 열24~70px 가변 너비로 수정했다. 방지 시험 GUI-UI-14는 최소 너비에서 체크박스/이름/유형 분리와 이름 버튼32px 이상·화살표 잘림 없음을 검증한다. 재시험 ID `20261103-compact-catalog`: 별도 GPT-6-sol UI16 및 240/300/375px geometry PASS; Astra 재검토 APPROVED. VERIFIED. 수정 코드 기준은 [실행 기록과 source manifest](runs/20261103-compact-catalog.md)에 보존하며 이 항목을 추가한 커밋이 수정 커밋이다.
