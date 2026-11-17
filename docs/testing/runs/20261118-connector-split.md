# 2026-11-18 웹 커넥터 좌우 패널

RQ-63/73 · D-81 · T-287 · REG-0114/0113. 사용자 승인 배치를 구현하고 시험은 직접 영향받는 화면 범위로 제한했다. 시작 main HEAD: `a0b53cd4813e95b6d39f7d0ad02c0e5a13f2f6fc`. 기존 TC 상태·timeout 등의 미커밋 변경을 보존했다. 변경 전 사본은 로컬 `before/`에 있다. 커밋·푸시·배포·운영 재시작·실제 TC/장비 실행은 수행하지 않았다.

## 변경 파일과 영향

- `packages/gui-test-ui/src/connector_web/view.mjs`, `style.css`: 사이드바를 연결 단계 아래 가로 보드 신호등 줄로 바꾸고, 좌측 TC/우측 콘솔·로그 패널로 나눴다. 기본30:70, 드래그/좌우 방향키/Home/End/Enter 조절·브라우저 로컬 비율 보존·독립 스크롤·조회 검색/상태 필터를 제공한다. 기존1.6초 RUNNING 점멸/동작 줄이기를 유지한다. 700px 이하에서는 세로 배치하며 최소 작업 높이를 보장한다.
- `tests/e2e/connector-web.spec.ts`: 기존 배치 assertion을 새 구성에 맞추고 대량 목록·스크롤·콘솔 높이·조절/저장·좁은 창 겹침 방지 시험을 추가했다.
- 문서: 요구사항 RQ-63/73 후속, 결정 D-81, UI 명세·연결 계약·사용 안내, 구현 계획/현재 상태/진행 기록, T-287 목록/결과와 REG-0114/0113. 과거 실행/실패 기록은 보존한다.
- DB/API·서버 상태/실행 제어·새 의존성·Qt/Agent Monitor 미러 배치는 변경하지 않는다. 상태는 기존 서버 구조화 데이터이며 TC 검색/필터는 표시만 바꾼다. 추가 데이터는 브라우저 로컬 비율 키뿐이다.

## 최종 검증

원본 로그·스크린샷·trace·드라이버는 `.local-reports/20261118-connector-split/` 로컬 전용이며 Git에 포함하지 않는다. 미리 준비된 Node22.23.5, Python3.11.7, 설치된 Playwright/Google Chrome157.0.8103.79와 격리된 모의 커넥터 fixture를 사용했다. 의존성 설치/다운로드는 없다.

| 실행 | 결과 | 근거 |
|---|---|---|
| 최종 패널/보드 관련 브라우저7개 | PASS · 7개, 종료0 · 2.9분 | `browser-final-panels.log`, `browser-1794930930372107000/artifacts/` |
| 최종 기존 로그 브라우저 시험 단독 | PASS · 1개, 종료0 · 19.9초 | `browser-final-logs.log`; 기존 assertion/timeout 유지 |
| JS 구문 | PASS · 종료0 | `node --check packages/gui-test-ui/src/connector_web/view.mjs`, `syntax-final.log` |
| 문서·링크/시험 ID 및 diff 공백 | PASS · 종료0 | `.venv/bin/python docs/testing/validate_docs.py`, `docs-final.log`; `git diff --check`, `diff-check-final.log` |
| 실제 Windows·SSH/UART·회사 인수 | NOT_RUN | 로컬 모의 시험으로 대체하지 않음 |
| 독립 Claude 리뷰 | NOT_REVIEWED | 실제 별도 검토 수행 없음 |

최종 현재 코드와 시험 bytes로8개 고유 화면 사례를 확인했다(일괄7+단독1). **8개를 함께 실행해 전체 PASS한 것으로 보고하지 않는다.** 1360×900에서 보드32개·TC240개에도 문서 폭/높이가 창 안에 있고 콘솔 높이가 유지됐다. 드래그·키보드·새로고침 비율 보존, TC/로그 독립 스크롤, 보드별 상태/로그·검색/필터·소스 전환·RUNNING/동작 줄이기·좁은 창·설정 진입을 확인했다. 최종 desktop/390px 캡처를 직접 확인했고 로그와 접기 항목은 겹치지 않는다.

실제 실행 드라이버는 로컬 `run-final-panels.py`와 `run-logs.py`다. 기존 `scripts/test_connector_browser.py`와 같은 격리 fixture/Playwright 명령에서 `--grep`으로7개/1개를 선택했다. PATH에 `.local-reports/20261117-connector-test-status/tools/node-v22.23.5-darwin-arm64/bin`과 `/usr/bin`, 브라우저에 설치된 Google Chrome을 명시했다. 제품 실행기는 변경하지 않았다.

## 초기 실패와 수정 이력

- 첫 실행 `browser-1.log`: 6 PASS/2 FAIL. 가로 보드32개에서 숨김 상태 텍스트의 위치 기준이 문서여서 scrollWidth3468px를 만들었다. `.status-indicator{position:relative}`로 제한했다(REG-0114). 기존 폭/높이 assertion을 유지하고 재시험했다. `dimensions-1.log`와 첫 trace/캡처를 보존한다.
- 두 번째 `browser-2.log`: 7 PASS/1 FAIL. 기존 로그 시험은 두 일괄 실행 모두 오류 문구 반영을5초 안에 확인하지 못했다. trace에는 서버200 오류 상태 후 UI에 늦게 나타난 기록이 있다. 최초 요청 시간 초과 캡처도 보존했다. 변경 전/후 격리 진단에서는 각각 약29ms에 오류가 보였다(`logs-baseline.log`, `logs-current.log`). 같은 시험 단독 `browser-logs-3.log`는1 PASS였다. **일괄 실행 지연 원인은 미확정**이며 assertion/timeout을 늘리거나 제품 코드를 바꿔 통과시키지 않았다.
- 두 번째390px 캡처를 직접 확인하면서 로그 하단과 접기 항목 겹침을 추가 발견했다(REG-0115). textarea의 최소 높이보다 세로 패널이 작았다. 좁은 창에서 main을 내용 높이에 맞추고 작업 영역 최소480px을 확보했다. 겹침 방지 assertion을 추가한 뒤 위 최종7+1개를 같은 파일 버전으로 다시 실행했다. 이전 PASS를 최종 근거로 재사용하지 않았다.
- 최초 문서 검사 당시 동시 작업의 T-268 중복 결과 행 때문에 catalog/index와 공백 검사가 실패했다. 현재 인덱스 후속 검사는 PASS이며 `docs-1.log`, `diff-check-1.log`를 보존한다. 관련 없는 미러 변경은 이 작업의 구현/검증 실적에 포함하지 않는다.

## 파일 식별과 남은 범위

- 코드: `workingtree:sha256:001ebaf5b8c6be2f87c15082585f768c8ac4cc7b07f75316d2be950bf7d4467d`
- 시험: `workingtree:sha256:fc097a99443dc08b49bd7f4bebbbbf14892327669f2f4a3f46d63a0cf09b428d`
- 파일별 SHA-256은 로컬 `verified-files.json`, 이전 모바일 수정 전 해시는 `verified-files-before-mobile.json`이다. 저장소 전체 릴리스 해시가 아니며 기존 WIP가 포함된 웹 자산2개와 시험1개의 bytes를 고정한다.
- 웹 view/CSS는 직접 서비스하는 자산이다. 변경하지 않은 전체 UI build·광역 Python/미러 회귀는 사용자 지시에 따라 실행하지 않았다. 실제 Windows/회사 경로·SSH/UART/장비·독립 리뷰·배포 pin/ZIP/EXE 생성은 미실행이다.


## 게시 준비 · 2026-11-18

원격 main `74b348c8af8645c10b622c311f2e75522aeaf6f6`에 TC 전달 기능이 포함돼 있어 UI 변경만 별도 worktree로 분리했다. 로컬 임시 ID D-80/T-282/REG-0112/0113은 다른 작업이 원격에서 사용했으므로 게시 문서에서는 D-81/T-287/REG-0114/0115로 정리했다. 원본 로컬 로그 이름과 bytes는 유지한다. 실제 게시 결과와 고정 코드 pin은 [게시 기록](20261118-connector-split-publication.md)을 따른다. 위 커밋/푸시 없음은 최초 구현 검증 시점의 기록이다.
