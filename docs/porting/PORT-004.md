# PORT-004 · GUI 호스트·공유 UI 이식

RQ-57/D-61/DEVPORT02. GUI 앱·공통 Python·공유 UI를 회사 호스트에 재사용한다. [공통 절차](README.md)와 [UI 이식·동일성 계약](../design/UI_PORTABILITY.md), [소스 경계](../design/GUI_TEST_LAYOUT.md)를 따른다. 다이어그램/종합 화면 PORT-001/002는 독립 선택이며 GUI 선행 기능이 아니다.

## 현재 기준과 상태

대상 코드 커밋은 `16882f497bce09b767ba71f0df1f7b92cfb53e95`, 원본 main 기준은 `9b42e634667265a5a296408a019d46e675a01a85`, 최초 구현 커밋은 `99d46dc55cdffad1dbfb8a7b1ba2a5a8a4ce9557`이다. 선행 기능은 통합된 RQ-55/56이다. 기존 T-183~189 로컬 PASS와 독립 리뷰 APPROVED는 최초 구현에 포함된 변경을 검증한 당시 작업 트리 manifest에 대한 결과다. [병합 코드 검증 기록](../testing/runs/20261106-portability-merge.md)은 별도 독립 리뷰 APPROVED와 로컬 재시험·제약을 기록한다. 회사 인수 T-190은 NOT_RUN이다. `HOST_INTEGRATION.json`의 HEAD는 ancestry이고 dirty·파일 SHA256 및 `SHA256SUMS.json`이 전달 bytes 기준이다. [이전 실행 기록](../testing/runs/20261106-portability.md)에 당시 리뷰·시험 코드 기준과 실패 이력을 보존한다.

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
