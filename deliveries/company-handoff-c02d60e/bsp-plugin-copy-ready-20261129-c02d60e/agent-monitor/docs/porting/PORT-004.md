# PORT-004 · GUI 호스트·공유 UI 이식

RQ-57/D-61/DEVPORT02. GUI 앱·공통 Python·공유 UI를 회사 호스트에 재사용한다. [공통 절차](README.md)와 [UI 이식·동일성 계약](../design/UI_PORTABILITY.md), [소스 경계](../design/GUI_TEST_LAYOUT.md)를 따른다. 다이어그램/종합 화면 PORT-001/002는 독립 선택이며 GUI 선행 기능이 아니다.

## 현재 기준과 상태

기존 GUI 호스트 전달 대상 코드 커밋은 `16882f497bce09b767ba71f0df1f7b92cfb53e95`, 원본 main 기준은 `9b42e634667265a5a296408a019d46e675a01a85`, 최초 구현 커밋은 `99d46dc55cdffad1dbfb8a7b1ba2a5a8a4ce9557`이다. 선행 기능은 통합된 RQ-55/56이다. 기존 T-183~189 로컬 PASS와 독립 리뷰 APPROVED는 최초 구현에 포함된 변경을 검증한 당시 작업 트리 manifest에 대한 결과다. [병합 코드 검증 기록](../testing/runs/20261106-portability-merge.md)은 별도 독립 리뷰 APPROVED와 로컬 재시험·제약을 기록한다. 회사 인수 T-190은 NOT_RUN이다. `HOST_INTEGRATION.json`의 HEAD는 ancestry이고 dirty·파일 SHA256 및 `SHA256SUMS.json`이 전달 bytes 기준이다. [이전 실행 기록](../testing/runs/20261106-portability.md)에 당시 리뷰·시험 코드 기준과 실패 이력을 보존한다.

```sh
python apps/gui-test/package.py --host-integration --target bsp-dashboard-host-v1 --output .local-reports/gui-test-host-integration.zip
```

누적 patch `--base`는 source 수집/출력 변경 전에 거부한다. 호스트 ZIP은 static·wheel 없는 source-only이며 npm/Python 의존성과 UI build가 필요하다. 단독 `--standalone`과 설치 `--stage-wheel`의 Git 독립 계약은 유지한다. 이미 승인된 Runner ZIP은 그대로 보존하며 RQ-56 source_snapshot_v1 지원 근거가 없는 이전 배포본으로 취급한다. 새 바이너리 검증 전 capability 지원을 주장하지 않는다.

## 반입 파일과 회사 연결점

| 위치 | 역할·회사 조정 |
|---|---|
| apps/gui-test/ | 단독 launch/build·lock·설정 예제; 앱이 static/config 경로 주입 |
| backend/gui_test/ | 공통 core/API/실행 adapter·단독 서비스·시험; 소스 namespace backend.gui_test |
| packages/gui-test-ui/src/ | public index·GuiTestHost/context·공통 component/CSS/token 동일 버전 |
| host-reference/backend/services/gui_test_host.py | 기존 domain/services import를 보존한 검토용 조립·demo_router·automatic_result; 자동 overwrite 금지 |
| host-reference/apps/web/src/guiTestHost.ts | 원본 호스트가 제공하는 경우 함께 전달하는 UI context adapter; 원래 apps/web/src 위치로 대응 후 상대 import 유지 |
| ui-verification/ | 원본 browser 시험과 같은 canonical fixture·수동 preview HTML/Vite config/설명; 기존 단독 npm toolchain 사용 |
| HOST_INTEGRATION.json | schema/target·HEAD/dirty/파일 hash·roots·host 대응·필수 계약·lock·시험 명령·실제 검증 범위 |
| INSTALL.md, RELEASE_SUMMARY.md, docs/HOST_CONTRACT.md | ZIP 내 독립 설치/범위/호스트 계약; 저장소 문서 graph 불필요 |
| SHA256SUMS.json | 자신을 제외한 모든 archive entry hash |

회사 필수 정책과 COMPANY_MAP/APPLIED를 먼저 읽는다. 기존 backend 전체·minimal __init__·호스트 예제를 자동 교체하지 않는다. 공통 make_manager의 dashboard/module-selection 주입과 host make_dashboard_manager, 기존 API prefix의 common router+별도 demo_router, worker tick/recover/outbox, 내부 automatic_result 연결을 회사 구조에 대응한다. 공개 PASS endpoint를 만들거나 서버 게이트·최종 검토를 생략하지 않는다.

UI는 index와 같은 버전의 모든 CSS/token을 사용하고 company adapter에서 데이터/콜백만 변환한다. `apps/web/src/guiTestHost.ts`의 원본 대응은 참고하되 전체 앱 main.tsx의 누적 변경을 적용하지 않는다. 고정 브라우저/viewport/device scale·승인 폰트·동일 shared fixture로 로컬 동일성을 먼저 확인하고 회사 production build/실제 연결 결과를 별도로 기록한다.

## 검증과 복원

T-183~189의 공통 경계·API/worker·source/legacy·fail-fast·ZIP manifest/hash/오프라인 링크·단독 설치·UI fixture와 기존 RQ-55/56 회귀를 회사 구조에 맞게 실행한다. 시험 의도와 실제 실행 결과를 구분하며 원본 PASS를 회사 결과로 복사하지 않는다. T-190 및 기존 실장비/회사 인수는 별도다. 명령과 현재 결과는 실행 기록을 따른다.

DB/runtime schema migration은 없다. 적용 전에 source/settings/DB를 백업하고 복원 시 정상 종료 뒤 reviewed source만 되돌린다. 사용자 설정·Run/Attempt·UNKNOWN 이력은 삭제하지 않는다. 커밋/푸시·서비스·모델·장비·Jira 실행은 이 문서로 승인하지 않는다.

## source-only ZIP의 시험 범위

ZIP `HOST_INTEGRATION.json.test_commands[0]`과 INSTALL/HOST_CONTRACT의 동일 명령은 portable 파일 목록을 명시한다. 전체 test directory를 직접 수집하면 test_live_view의 backend.api import 등 source-only ZIP에 없는 호스트 의존성에서 실패하므로 그렇게 안내하지 않는다. portable 명령은 core/API/commands/fake Windows/source snapshot·transport/local Git/package 경계를 검사하며, Dashboard demo/API source 연결과 full-host ZIP 재생성 3개 사례만 명시적으로 제외한다. 이는 호스트 의존 범위 구분이며 시험을 통과로 낮춰 기록하는 것이 아니다. complete original/company host에서는 `python -m pytest backend/gui_test/tests -q`로 제외 사례와 live_view/module_selection 등 전체 호스트 회귀를 별도로 실행한다. extracted-only 실제 명령·결과는 실행 기록에 연결한다.

## 같은 Test 현황 fixture로 회사 화면 비교

호스트 ZIP은 `ui-verification/portable-ui-host.tsx`·`index.html`·`vite.config.mjs`·`README.md` 네 파일을 포함한다. canonical 원문은 `workflow_diagram/tests/portable-ui-host.tsx`이며 별도 구현을 만들지 않는다. 내보낼 때 shared UI 상대 import 한 곳만 `../../packages`에서 `../packages`로 대응하고 원문/전달 hash·정확한 치환·모든 fixture asset·명령을 manifest ui_verification에 기록한다. 전체 workflow 모듈·apps/web·backend·Playwright는 필요하지 않다.

추출 루트에서 승인된 npm cache/registry로 `npm ci --prefix apps/gui-test` 후 다음 명령을 실행한다.

```sh
node apps/gui-test/node_modules/vite/bin/vite.js --config ui-verification/vite.config.mjs --host 127.0.0.1 --port 18779 --strictPort
```

`http://127.0.0.1:18779/?observer&terminal`은 읽기 전용 완료 Run fixture다. `?observer`는 중단된 observer, 기본 URL은 가짜 소유자가 있는 중단 Run이다. 모든 API/storage/download/session은 in-memory fixture adapter이며 실제 서버·장비를 호출하지 않는다. Ctrl+C로 preview만 종료한다.

회사 UI shell에 같은 fixture·TestPage/ExecutionViewSettings를 mount하고 정상 회사 전역 CSS와 adapter 연결을 적용해 비교한다. 같은 component/CSS/token bytes·고정 browser/viewport/device scale/locale/timezone/reduced-motion·승인 폰트 설치/로딩을 선행 조건으로 기록한다. 375/1024/1440×1000에서 설정/선택/키보드·observer 제어 차단을 비교한다. 회사 import/mount 차이만 명시적으로 대응하고 fixture 데이터나 화면 구현을 다시 작성해 맞추지 않는다. fixture 결과는 좁은 로컬 화면 근거이며 실제 회사 API/Runner·전체 인수 T-190은 별도다.


## 2026-11-10 후속 · 환경 탭 색상·저장 조작 배치

RQ-55/D-59, REG-0077, T-169~175. 환경 탭의 Test 설정을 BSP 카드와 같은 파란색·회색·흰색으로 맞추고 `저장 후 환경 점검`·`설정 저장`을 Test 설정 다음의 맨 아래로 이동한다. 이 변경은 **대시보드 호스트 연결부**이며 기존 Windows Runner PORT-008의 변경이 아니다.

### 기준과 전달 상태

- 원본 기준: `f93f5d91a26eddeaa0144221669b7cdfed722bbb`.
- 후속 대상 코드 커밋: `7cdc9fb6bcea18bd8f15ce7d8a72bb584a1e6b01`. 위의 기존 PORT-004 대상 커밋에는 이 수정이 포함되지 않는다. 로컬 시험한 코드와 고정 커밋의 두 소스 파일 SHA256이 아래 값과 동일함을 확인했다. 코드 커밋 뒤 이 안내를 고정하며 회사 적용과 독립 리뷰 상태는 별도다.
- 시험한 코드 결합 SHA256: `3305b8f6270469739ffc1b076052c44096a7df10e93c0765b45865ddaac5df98`. 개별 코드/시험 해시는 아래 표를 따른다. 이전 PORT의 독립 검토 APPROVED는 이번 후속 수정에 적용하지 않는다.
- 선행 조건: 회사 호스트의 RQ-55 단일 BSP 폼·문맥별 설정, 전역 TestPage presentation 및 PORT-004 공용 UI/테마 변수 연결이 대응되어 있어야 한다. 회사의 마지막 적용 커밋과 부분 반입 여부는 COMPANY_MAP/APPLIED로 확인한다.

| 원본 파일·접점 | 이식할 내용·보존 조건 | SHA256 |
|---|---|---|
| `apps/web/src/main.tsx` · `App`, `settingsForm`, `saveSettings`, TestPage 뒤 footer | 기존 단일 BSP 폼에 고유 ID를 부여하고 저장 버튼을 `form` 속성으로 연결. 점검 버튼의 기존 저장→점검 순서와 busy 차단 유지. 전역은 항상, 대시보드/Jira 문맥은 편집기가 열린 경우만 표시. 점검 결과도 같은 footer에서 표시 | `6bdc6070aa931bd0bc7645eef2feede17c3dd0500fe2cc28e015ef3df6ac6e87` |
| `apps/web/src/style.css` · `.bsp-settings`, `.gt.gt-global-settings`, `.bsp-settings-actions` | 호스트의 `--gt-*` 색상·글꼴 변수와 전역 Test 입력/hover/명령 미리보기 색상 지정. 맨 아래 우측 정렬·좁은 화면 줄바꿈. 회사 디자인 토큰에 대응하되 공용 GUI 기본 테마를 전역 변경하지 않음 | `305aec0a0456860d9253d8dec5f033891336a89a3f3cb7c5a20a32d532ebfe01` |
| `tests/e2e/settings-sync.spec.ts` | 설정·draft·개별 저장·숨은 필드 검증·접기·조회 생명주기의 기존 호스트 회귀. 회사 fixture/실행 진입점에 대응 | `01900c7c273169cd89eeb52f0de08cc8a788766c259e1326f53865088b92c3fe` |
| `tests/e2e/settings-controls.ts` | 같은 회귀의 설정 항목·상세 접기 조작 helper | `66c9b0eed3a888007fac5b9871cfdf6ff21499de4e51102981098611d182e87a` |

공용 `packages/gui-test-ui/src/`와 Python 코어는 이번에 변경하지 않았다. 기존 호스트 ZIP을 다시 만드는 것만으로 회사의 main/style 연결부가 적용되지는 않는다. 회사의 전역 설정 페이지·BSP 폼·TestPage mount·디자인 토큰 위치에 위 접점만 반영한다. 전체 main.tsx/style.css를 덮어쓰거나 회사의 저장 범위·미저장 상태·접기·실행 정책을 바꾸지 않는다. 원본/회사 폼 ID 충돌과 버튼의 잘못된 폼 연결을 확인한다. BSP 저장은 GUI의 프로파일·명령·Suite를 대신 저장하지 않는다.

API·DB·설정 저장 형식·의존성 추가와 데이터 이전은 없다. 적용 전 회사 호스트의 관련 소스/빌드 산출물을 보존하고 복원할 때 해당 호스트 변경과 UI 산출물만 정상 절차로 되돌린다. runtime·설정·Run/Attempt·UNKNOWN 이력은 유지한다.

### 검증과 회사 인수

원본 로컬 결과: `bash scripts/build.sh dashboard --skip-install` PASS, `apps/web`에서 `npx playwright test settings-sync.spec.ts` 재시험12 PASS, 일회성 화면 수용 검사1 PASS. 첫 fixture 서버 listen EPERM과 권한 확보 후 재시험을 [실행 기록](../testing/runs/20261110-settings-appearance.md)에 분리했다. 화면 수용 검사는 1360/375px의 제목 색상 일치·파란 접기 강조·Test 카드 아래의 버튼 위치·폼 연결·모의 저장을 확인했고 캡처를 직접 확인했다. 일회성 검사와 원본 로그는 로컬 전용이며 회사 배포에 포함된 영속 시험으로 주장하지 않는다.

회사에서는 같은 설정 회귀를 회사의 승인된 Node/브라우저·모의 API로 실행하고 다음을 추가 확인해 APPLIED에 기록한다.

1. 환경 탭에서 Test 카드를 펼치고 접어도 주변 BSP 카드와 색상·테두리·hover가 맞고, 두 버튼이 Test 카드 아래에 위치한다. 1360px/375px에서 가로 넘침과 버튼 겹침이 없다.
2. 폼 밖의 `설정 저장`이 올바른 BSP 폼을 한 번만 제출하고, 점검은 저장 성공 후 실행된다. 잘못된 숨은 입력은 펼침·포커스로 안내하며 저장/점검 요청을 보내지 않는다.
3. 탭 왕복·접기 중 draft와 GUI 개별 저장 범위, 문맥별 버튼 표시가 유지된다. 회사 추가 설정·회사 디자인 토큰·실행 정책을 보존한다.

이번 후속 독립 리뷰는 **NOT_REVIEWED**, 실제 회사 화면·API 인수와 T-190은 **NOT_RUN**이다. 원본 로컬 PASS를 회사 인수로 복사하지 않는다.
## 2026-11-12 · TEST BOARD CONNECTOR 표시명 후속

사용자 표시명 Windows Runner를 TEST BOARD CONNECTOR로 바꾼다. 공유 `packages/gui-test-ui/src/TestPage.tsx`의 실제 연결 배너/역할 설명과 `SourceSettings.tsx`의 업데이트 안내, `tests/e2e/gui-test.spec.ts`의 기존 GUI-UI-16 기대 표시명을 함께 반영한다. 호스트 API/adapter/설정·CSS 구조는 유지한다. 후속 대상 코드는 `b122c57e40137be48b29dc5477ca462d5523facb`이며 위의 고정 코드/해시·과거 PASS와 구분한다. [명칭 검증 기록](../testing/runs/20261112-board-connector-name.md), [PORT-008](PORT-008.md)에 적용 범위와 미검증을 기록한다.
