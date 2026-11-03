# 2026-11-02 Git 게시 검증

실행 ID: 20261102-publication. 수행: Codex. 사용자 승인 범위: 구현 변경을 Git에 반영하고 요구사항/관련 문서를 정리한다. 원격 기준 main `2e2d24b74d8464d432e118fd4a80646d6d7a6c9a`와 로컬 가져오기 기준이 일치함을 확인했다. 로컬은 .git 없는 내용 사본이며 GitHub blob/tree/commit/branch/PR 경로로 게시한다. 원격 기준 파일을 전체 대체하지 않고 변경된 경로만 적용하며 미다운로드 과거 스크린샷4개를 삭제하지 않는다.

## 최종 기능 및 추적성

| 요구사항 | 현재 동작 | 구현 / 시험 |
|---|---|---|
| RQ-39 | 작은 TC 트리·검색/열 정렬·목록 내 드래그·패널 숨김/너비·통합 설정/복귀 | CaseTree/TestPage/CSS, T-109~112/T-115/T-117 |
| RQ-40 | TC별/전체 반복, 기본1, 고정 plan/slot·실패 보존·Suite | models/repetition/manager/results, T-116 |
| RQ-41 | 실제 보드 이름 또는 local, 실행 당시 대상 pin | targets/manager/worker/MockRunner, T-118 |
| RQ-42 | 모델별 입력/출력 토큰·USD 비용, 중복 제외/미집계 구분 | usage/manager/worker, T-114 |
| RQ-43 | FAIL 옆 Retry, 해당 TC1회 새 Run, 원본 보존 | TestPage/manager, T-113 |

현재 UI/요청/데이터/어댑터 계약은 [요구사항](../../requirements/REQUIREMENTS.md), [화면](../../design/UI_SPEC.md), [GUI Test 계약](../../design/GUI_TEST_CONTRACT.md)에 정리했다. 과거 D-44~46/검증 이력은 보존하고 README/문서 지도/구조/API/데이터/상태/시험 계획/진행 기록을 연결했다.

## 현재 검증

- 전체 Python **299 PASS**, warning1(Starlette/httpx deprecation): [출력](20261102-publication-evidence/pytest.txt). 이번 코드에 대해 실행했으며 이전 284/82 PASS를 재사용하지 않았다.
- Dashboard/단독 TypeScript+Vite **PASS**: [출력](20261102-publication-evidence/build.txt).
- 문서 검사: [출력](20261102-publication-evidence/docs.json). 43 요구사항과118 시험의 연결/CSV/상대 링크를 확인한다. 문서 검사는 제품 인수가 아니다.
- [직전 Chrome 검증](20261101-repeat-settings.md): 기본 행32px, 헤더 정렬/실행 순서 보존, 설정 복귀3경로, 총6회 Mock 실행·FAIL 보존, 새 Mock 결과에 local 표시. 기존 사용자 Run과 원본 실패를 유지했다.
- 로컬 격리 자동 E2E는 socket.bind 권한 제한으로 BLOCKED였다. 브라우저 자동 회귀 GUI-UI-01~12는 PR의 GitHub Actions에서 별도로 확인한다. CI 결과를 실행 전 PASS로 쓰지 않는다.
- 실제 BCM/RBM/장비·회사 TC·모델 계량·Linux 모델 실행·독립 Claude 검토는 NOT_RUN/NOT_REVIEWED. 운영 baseline NONE 유지.

## 게시 범위와 증거 보존

코드·문서·시험과 해당 실행 증거만 포함한다. `.runtime`, `.local-update`, DB/백업, 가상환경, node_modules, 생성된 UI 빌드·로컬 report는 게시하지 않는다. 로컬 기본 포트8766과 무로그인 진입/loopback·출처 검증을 유지한다. 단독 GUI 기본8767은 별도다.

이전 JUnit 원본 두 개는 내용 동일한 gzip으로 게시하고 로컬 원본을 유지한다. 과거 PASS/FAIL 기록은 삭제하지 않는다. 새 source manifest와 Git blob hash를 대조해 업로드 누락·변형을 확인하며, 원격 head 변경 시 기존 작업을 덮어쓰지 않는다. 게시 커밋/PR/CI 상태는 Git 기록과 PR checks를 기준으로 확인한다.

## 최초 PR CI 및 후속 수정

[PR #5](https://github.com/graycoral/bsp_os_upgrade_dashboard/pull/5), 최초 코드 6d5965b. [CI 41441069153](https://github.com/graycoral/bsp_os_upgrade_dashboard/actions/runs/41441069153): Python299/두 빌드/Mock 시나리오/Windows 패키지 PASS. Dashboard 브라우저16 PASS/1 FAIL(GUI-UI-05 아래로 되돌리기). 단독 브라우저·Linux 배포 패키지 단계는 선행 실패로 SKIPPED. REG-0014의 손잡이 드래그 보강 후 동일 기대값으로 다시 검증한다.
