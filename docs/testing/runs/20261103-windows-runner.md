# 2026-11-03 빌드·전체 선택·Windows 실행기

기준 시작: main `03368c78fe249340d2a9e4511c01723509fcef93`. RQ-39/44/46, D-47, T-125~130. 코드 식별자는 인접 `20261103-windows-runner-evidence/source-manifest.json`에 기록한다. 실제 회사 TC/COM/SSH/Linux 운영 실행은 사용자 범위이며 **NOT_RUN**이다. 임시 TC는 출력과 대기만 하는 시험용 Python 코드다.

## 사용자 요청과 구현

- `scripts/build.ps1`, `build.cmd`, `build.sh`: Dashboard/단독 GUI/전체 웹 빌드, 실패 종료. 기존 Windows ZIP 빌드 유지.
- TC 전체 선택: 표시된 실행 가능 TC, 부분 선택, 필터 밖 선택 보존, 키보드·빈 결과·선택 불가 처리.
- 기존 사용 경로 확인: Windows 탐색기 → Linux 공유 파일 → Windows Python → Windows COM. Linux에서 COM 이름을 직접 여는 방식이 아니다.
- Windows 실행기 + Linux adapter, 공유 소스 snapshot, 고정 Python/COM argv, 요청 해시·중복 방지·로그·엄격 판정·중단/UNKNOWN을 구현했다. 실제 Run DB는 Mock와 분리한다. Job 자동 결과는 이미지·매핑 증거 미구현으로 차단한다.

## 독립 세션 분리

사용자 지시 후 구현 리뷰는 새 **gpt-6-astra** 세션 `/root/astra_review`, 시험은 별도 **gpt-6-sol** 세션 `/root/sol_testing`에서 수행했다. 주 작업자는 코드/시험/문서 작성과 결과 검토·수정·재시험 요청을 담당했다. 초기 일반 Codex 검토 세션은 Astra 지정 후 중단했고 완료 리뷰로 계산하지 않는다. Claude 독립 리뷰는 수행하지 않았다.

Astra 상태: **APPROVED (검토한 코드 범위)**. 아래 P1/P2를 발견하고 수정 후 재검토했다. 자체 수행은 문제 재현을 위한 가짜 프로세스/메모리 로그 확인에 한정한다. 전체 시험 결과와 실환경 인수의 대체가 아니다.

| 결함 | 원인·재현 | 수정·방지 시험 |
|---|---|---|
| REG-0016 | 과거 Run에는 command_snapshot이 없어 신규 claim context에서 KeyError | 기존 기본 Mock template fallback 유지; test_default_and_legacy_runs_keep_mock_template |
| REG-0017 · Astra P1 | Windows os.execv supervisor가 TC exit7 대신0을 반환해 PASS 오판 가능 | 격리 Python supervisor가 자식 반환값 전파; PASS 문구+exit7 → ERROR 및 잘못된 UTF8 결과 시험 |
| REG-0018 · Astra P1 | 마지막 로그 조회와 종료 확인 사이에 추가된 FAIL/초과 출력을 누락 | 프로세스 트리 종료 뒤 pipe EOF drain 및 최종 한도 재검사; 결정적 late conflicting result/overflow 시험 |
| REG-0019 · Astra P1 | 시작 전 거부 또는 claim 저장 후 전송 전 중단이 영구 UNKNOWN 예약으로 남음 | 거부 tombstone과 부재 ID 원자 reconcile, 뒤늦은 실행 차단; source rejected/claim-before-send 시험 |
| REG-0020 · Astra P2 | raw 출력 파일과 공백 기준 masking이 Bearer/공백 비밀값을 보존 | raw 파일 제거, 메모리 제한 수집·완성 줄 전체 masking 후 저장; split-write/Bearer/spaced-password DB·응답 검사 |

Astra의 16파일 검토 manifest 집계: `4d0f756f893cbadf8af8fbdb0a77b55fdec7617d7ea09de1fbc11578fbc1587b`. 개별 해시는 `astra-review.json`에 보존한다. 이후 추가된 GUI-UI-16은 하드웨어 capabilities UI fixture이며 새 제품 코드 변경은 없다.

## 최초 실행과 재시험 이력

실패 기록은 삭제하지 않는다. 아래 각 결과는 해당 시점의 코드에만 유효하다.

| 실행 | 수행 | 결과·범위 |
|---|---|---|
| 선택 UI 초기 | 주 세션 | 브라우저15 PASS, Dashboard/단독 화면 빌드 PASS. Windows 실행기 변경 전 |
| 실행기 Python 초기 | 주 세션 | 기본 pytest 임시 폴더 접근 거부로10 ERROR. 제품 시험 시작 전 환경 오류 |
| 실행기 Python 경로 수정 | 주 세션 | 새 임시 경로 지정 후10 PASS |
| 실행기 UI 첫 빌드 | 주 세션 | JSX 닫는 중괄호 누락으로 TypeScript FAIL; 수정 후 두 빌드 PASS |
| GUI 전체 초기 | 주 세션 |125 PASS/1 FAIL(REG-0016); legacy fallback 수정 |
| sol-gui-20261103-a | GPT-6-sol |126 PASS/1 deprecation warning; Astra 추가 결함 수정 전 코드 |
| sol-gui-20261103-b | GPT-6-sol |132 PASS/2 ERROR(같은 시험의 setup+teardown). 70KB parameter repr가 PYTEST_CURRENT_TEST에 들어가 Windows 환경변수 길이 한도 초과; 짧은 parameter ID로 수정. 제품 기대값 변경 없음 |

최종 재시험 결과는 별도 아래 항목에 추가한다. 이전 PASS를 새 코드 전체 검증으로 재사용하지 않는다.

## 한계

- 실제 Linux/SSH 터널/공유 폴더/회사 Python 환경/물리 COM/Single·Dual 인수 T-130 NOT_RUN.
- Windows 실행기 비정상 종료 후 UNKNOWN은 종료 증거 없이 자동 해제하지 않는다. 운영 Job 자동 결과, RBC/RBM 이미지 식별, 외부 프로그램과 물리 COM 공통 예약은 미구현이다.
- 별도 Astra 코드 리뷰와 GPT-6-sol 자동 시험을 실제 Claude 리뷰나 장비 인수로 표현하지 않는다. 운영 baseline NONE 유지.
- Windows 자체에서 전체 BSP worker(fcntl/POSIX) 시험을 통과했다고 주장하지 않는다. 해당 Linux 회귀는 CI 증거가 있을 때 별도로 기록한다.

## 최종 독립 로컬 검증

GPT-6-sol `sol-gui-20261103-c`: **Python 133 PASS**, 경고1(Starlette TestClient deprecation). **브라우저16 PASS**(GUI-UI-14/15 전체 선택 및 GUI-UI-16 실제 모드 capabilities fixture 포함). PowerShell 두 화면 빌드, CMD 다른 cwd 단독 빌드, Git Bash Dashboard 빌드, 잘못된 대상·npm 실패 비정상 종료 PASS. Linux 운영 실행을 한 결과가 아니다. 명령·환경·파일 해시는 [독립 시험 manifest](20261103-windows-runner-evidence/sol-verification.json), 실제 결과는 같은 evidence 폴더의 sol XML/JSON/log gzip에 보존한다.

주 작업자는 결과와 원시 파일 해시를 대조했다. 최종 로컬 코드/시험 식별자 `sha256:66258605fda87b272b81a4bb0a0f0f4e44a1b8442d7cb0c70b3ac390ed9e3ac1`. T-125~129 PASS, T-130 NOT_RUN. 수정 전 결과·환경 오류·시험 harness 오류는 앞선 표 및 gzip으로 유지한다. Astra가 언급한 전용 hardware UI 시험 공백은 후속 GUI-UI-16 fixture 추가/16개 PASS로 보완했다. 이 fixture를 실제 Windows/COM 인수로 확대하지 않는다.

최종 문서 검사: 별도 GPT-6-sol 세션에서 PASS(상대 링크413, 요구사항46, 시험130, NOT_RUN79, 오류0). 제품 시험과 구분하며 evidence/sol-docs-final.json에 보존한다.

## CI 및 main 통합 완료

GPT-6-sol 별도 시험 세션이 GitHub connector의 workflow/job/step/log를 조회하고 주 작업자가 커밋과 증거를 대조했다. 검증 커밋 **0ad590d6080c13b3d9618baa18c4aa7b8751737f**, [PR #6](https://github.com/graycoral/bsp_os_upgrade_dashboard/pull/6)은 **a80371c35cee434429871ad8718f97d396710788**로 main에 머지했다. 머지 후 제품 코드·시험·워크플로가 검증 커밋과 동일함을 Git diff로 확인했다.

- [회귀 CI](https://github.com/graycoral/bsp_os_upgrade_dashboard/actions/runs/41577526076): Linux Python **350 PASS**, Dashboard 브라우저 **21 PASS**, 단독 브라우저 **16 PASS**, Bash 두 화면 빌드·Mock 데모·wheel/패키지 성공. Windows GUI Python **133 PASS**, wheel 설치·smoke 성공.
- [Windows 독립 CI](https://github.com/graycoral/bsp_os_upgrade_dashboard/actions/runs/41577525954): PowerShell5.1 및7 각각 **118 PASS / 3 deselected**, ZIP 생성과 소스 밖 오프라인 설치·smoke 성공. 제외3개는 Git/Dashboard 통합 시험이며 전체 GUI/회귀 job에서 검증한다.
- 두 workflow의4개 job과 모든 step 성공. 상세 URL·job ID·로그 발췌는 [CI 증거](20261103-windows-runner-evidence/sol-ci.json). 실제 회사 TC/물리 COM/운영 Linux 인수는 여전히 NOT_RUN이다.

REG-0016~0020의 수정 커밋은 `0ad590d`이다. 마지막 게시 기록 변경은 문서/증거만 포함하며 위 검증된 제품 코드를 변경하지 않는다.

게시 메타데이터 최종 문서 검사도 별도 GPT-6-sol 세션에서 PASS(링크414 / 요구사항46 / 시험130 / 오류0). 근거: 20261103-windows-runner-evidence/sol-docs-publication.json. 제품 코드 변경 없이 문서와 CI 근거만 기록한다.
