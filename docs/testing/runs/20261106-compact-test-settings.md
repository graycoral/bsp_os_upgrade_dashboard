# Test 설정 간결화 · 2026-11-06

상태: **LOCAL_VERIFIED / INDEPENDENT_REVIEW_APPROVED**. RQ-55/D-59 후속 사용자 지시다. 전역 환경 설정과 Test 현황 내부 설정을 동일한 단일 접기 및 설정 항목 콤보박스로 정리하고 기본값을 제공한다. TC 목록·실행·결과의 전역 비표시는 유지한다.

기준은 `037b98f5d2b275e913bbd83a1429e3220ed7c497`, 작업 트리는 `bsp_compact_settings`, 브랜치는 `ui/compact-test-settings`다. 다른 작업 트리의 설정 마법사 변경·사용자 미커밋 파일은 수정하지 않는다. RQ-57 portable host와 RQ-58 목록 제한시간/비동기 보호를 보존한다.

상세 설계는 Astra High, 구현은 Sol High, 별도 회귀 작성은 Sol Medium으로 분담했다. 새로운 Sol High 독립 리뷰는 최초 P2 변경 요청 후 REG-0073을 수정하고 APPROVED로 재검토했으며, 별도 Luna Low가 실행 검증을 수행한다.

API·DB·외부 연동 계약은 변경하지 않는다. 저장된 값을 기본값으로 덮어쓰지 않으며 실제 서버 경로·보드·인증정보를 만들어 넣지 않는다. 소스 확인·적용, 프로파일/명령/Suite 저장과 보기 모드 적용은 명시적인 조작으로 유지한다.

전체 로그·JSON·스크린샷은 `.local-reports/compact-test-settings-20261106/` 아래 로컬 전용으로 보관하며 Git에 포함하지 않는다. 실제 실행·리뷰·서비스 반영 결과는 완료 후 이 문서에 기록한다.

## 변경·회귀 증거

기본 연결·실행, TC 소스, 실행 명령, Suite, 보기 모드는 단일 카테고리 콤보로 전환하며 편집기를 계속 mount한다. 보드/COM·반복 선택을 짧은 기본 행에 두고 수동 입력·명령 편집·소스 메타데이터·조회 제한시간을 상세로 접었다. 반복1회·조회100초·기존 명령 템플릿을 사용하며 legacy를 포함한 적용 소스 종류와 위치를 초기값으로 표시한다. 실제 연결의 빠진 보드 값을 데모 값으로 보완하지 않는다.

첫 구현의 비동기 오류 reveal은 결과 화면으로 돌아간 경우 설정 작업 영역까지 열지 못했다. REG-0073 수정은 현재 activity/presentation ref를 확인하여 활성 로컬 설정 화면도 열고, 다른 탭으로 강제 이동하지 않는다. T-181은 지연된 소스 적용 실패와 결과 화면 이동 후 오류 표시·draft 보존·적용 소스 불변을 검증한다.

생산 UI 코드 고정 커밋은 `5bef331`이며 이후 `f9189ba`의 설정 실행·진단 스크립트 변경을 `e8d5591`로 통합했다. 제품 UI 소스에는 중복 변경이 없고 WORK_STATUS의 두 진행 기록을 함께 보존했다. 패키지 후속 수정을 포함한 소스/시험18개 manifest는 위 로컬 폴더의 `source-test-manifest.json`, SHA256 `d2f5327bc6d55785ffec1655268078d3476be0c97208d50e2b3e9f3a915b577d`다. UI 파일은121개 브라우저 PASS를 확인한 바이트와 동일하고 추가 패키지 변경은 아래 별도19개 시험으로 확인한다.

| 명령·범위 | 결과 | 로컬 증거 폴더 |
|---|---|---|
| `npm.cmd run build --prefix apps/web` | PASS / exit0 / 1612 modules | `web-build-final/` |
| `npm.cmd run build --prefix apps/gui-test` | PASS / exit0 / 45 modules | `gui-build-final/` |
| Playwright settings-sync/source-settings/catalog-loading | 28 PASS / exit0 | `settings-source-catalog-final/` |
| 단독 GUI 최초 실행 | 17 PASS / 1 FAIL / exit1 | `standalone-gui-final/` |
| 단독 GUI 전체 재시험 | 18 PASS / exit0 | `standalone-gui-retry/` |
| 통합 실제 보기 전환·격리 | 1 PASS / exit0 | `gui-live-view-confirmed/` |
| 합성 전체 탭·portable host 회귀 | 74 PASS / exit0 | `workflow-fixture-final/` |
| CI 후속 package/layout 재시험 | 19 PASS / 2 SKIP / exit0 | `package-fix/` |

단독 GUI 최초 GUI-UI-13 실패는 재로드 후 명령 오류가 자동 표시되는 도중 시험이 설정 버튼을 다시 눌러 접는 탐색 경합이었다. 시험에서 오류 자동 표시를 직접 기다리고 설정 열림·명령 카테고리·명령 입력 표시를 확인하도록 수정했으며 좁은 시험 변경도 독립 리뷰 APPROVED다. 최초17 PASS/1 FAIL은 보존하고 전체 재시험18 PASS로 확인했다.

합성 회귀 최초 시도는 Chrome 환경변수 누락으로21 PASS/53 브라우저 실행 실패였으며 제품 통과 근거로 사용하지 않는다. 올바른 Chrome 설정의 다음 시도에서는 기존 RQ-58 목록 조회 설정 endpoint가 합성 fixture5곳에서 빠져 404 오류가 자동 표시되는 것을 발견했다. 구 fixture를 읽은 실행은34번째 사례까지 진행 후 중단하고 부분 로그를 `workflow-chrome-final/`에 보존했다. 정상100초 응답을 fixture에 보완하고 새 전체 실행에서74 PASS/실패0을 확인했다. 기존 검증 조건은 제거하지 않았으며 fixture 변경도 독립 리뷰 APPROVED다. 깊은 Windows 경로로 아티팩트 복사 시 발생한 경로 길이 오류는 canonical 원본에서 ZIP을 만들어 전체 원본을 보존했다.

보기 모드 첫 launcher는 Windows에서 BSP worker의 fcntl 제약으로 제품 시험을 시작하지 못했다. 해당 GUI 시험에는 BSP worker가 필요 없어 새 임시 API만 실행해 검사했다. 최초 실제 시험은 새 빈 보드 placeholder로 인해 기존 option count0 조건에서 실패했다. Board A/B 모두 숨김·빈 값·정확한 `등록 보드 없음` 옵션 하나임을 확인하도록 시험을 강화하고, Mock TC/Run 격리·실행 차단·위조 실행503 거부를 유지해 재시험1 PASS했다. 원래 시도는 `gui-live-view-final/`와 `gui-live-view-api-only-final/`에 보존하고 좁은 변경도 독립 리뷰 APPROVED다. 사용자8766 runtime을 시험에 사용하지 않았다.

T-172는 전역/지역·데스크톱/375px 캡처4개를 남겼다. 조정자가 전역 데스크톱과 지역 모바일 캡처를 직접 확인해 단일 짧은 카드·선택식 기본값·가로 넘침 없음을 확인했다. 지역 테스트가 임의 반복37회도 그대로 표시하는 것을 포함한다. 캡처는 위 설정 시험의 `browser-artifacts/settings-sync-T-172-one-co-6781e--safe-defaults-in-both-tabs/` 아래 로컬 전용이다.

## 실제 서비스 반영

기존8766 listener와 launcher의 명령줄/소유관계를 확인하고 원래 `bsp_os_upgrade_dashboard/.runtime`을 그대로 사용해 `bsp_compact_settings`의 서버로 숨김 재시작했다. 새 instance `ac03148da24240d4b3b0f1f1b9431f5b`, launcher52472/listener46732에서 health 정상·root/JS200을 확인했다. 설정·작업·default/live GUI 실행 이력의 응답 해시는 재시작 전후 동일하다. SQLite5개를 전후 별도로 백업하고 모두 integrity_check=ok를 확인했다.

제공 asset은 `index-tn3HQkpC.js`, SHA256 `268425ff59176a6ca547c59ea2b75f411e81772697885ee67186cc7a92e7db56`로 새 빌드와 일치한다. 전체 증거는 위 로컬 폴더 `live-restart/`에 보존한다. 첫 긴 restart inline 명령이 도구 검토에서 실행 전 거절되어 짧은 소유권 확인·중지·시작 호출로 나눠 완료했다. 거절 시점에는 프로세스를 중지하지 않았고 추가 권한이나 정책을 변경하지 않았다. 실제 외부 Git·장비·모델·Jira 호출은 수행하지 않았다. 원격 CI·main 머지/푸시는 연결된 PR의 실제 결과로 확인한다.

별도 Luna의 최종 문서 검사는 PASS(exit0)로 링크1013개·요구사항59개·시험199개·기존 NOT_RUN72개·오류0을 확인했다. 로그는 `docs-validation/`에 로컬 전용 보존한다. 이 검사는 문서 추적성 결과이며 실제 회사·장비 인수나 운영 baseline을 변경하지 않는다.

## CI 패키지 회귀 후속 · REG-0074

PR #18의 `ec00b80` 첫 CI Linux run42235838753/job127953082530는1123 PASS/15 SKIP/1 FAIL이었다. RQ-58이 추가한 `catalog_settings.py`가 기존 source/wheel 공통 수집 목록에서 빠져 실제 추출 host ZIP을 import할 수 없었다. 원본 전체 로그는 위 로컬 폴더 `ci-linux-initial.log`다.

지정 Terra Low가 `apps/gui-test/package.py`의 명시적 루트 파일 목록에 해당 모듈만 추가했다. 이는 표준 라이브러리만 사용하는 파일이며 기존 경로·symlink·suffix 제한은 그대로다. 새 독립 Sol High 검토 APPROVED와 별도 Luna의 `backend/gui_test/tests/test_package.py tests/test_gui_test_layout.py`19 PASS/2 SKIP를 확인했다. UI·실행 API·DB 로직과 제공 중인 asset은 바뀌지 않아121개 브라우저/재시작을 불필요하게 반복하지 않는다. 수정 head의 원격 CI는 실제 PR 체크로 확인하며 첫 실패를 지우지 않는다.

첫 Windows package도 같은 누락으로410 PASS/3 SKIP/1 FAIL, 두 셸 standalone도 소스143 PASS/4 DESELECT 후 설치된 `gui_test.catalog_settings` import에서 실패했다. job127953082257/127953081799/127953082260 로그 역시 위 로컬 폴더 `ci-initial-<job>.log`에 보존했다. 모두 동일한 공통 수집 목록을 사용하므로 단일 누락 수정 대상으로 처리한다. 후속 문서 검사는 별도 Luna 실행에서1014링크/59요구사항/199시험/기존72 NOT_RUN·오류0, diff 검사 exit0으로 통과했으며 `docs-validation-package/`와 `diff-check-package/`에 기록한다.
