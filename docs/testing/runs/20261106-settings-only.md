# 환경 설정의 Test 설정 전용 표시 · 2026-11-06

상태: **LOCAL_VERIFIED / INDEPENDENT_REVIEW_APPROVED**. RQ-55/D-59 사용자 정정, REG-0070. 환경 설정에 Test 현황 전체를 가져온 초기 해석을 수정했다. Test 설정 입력만 전역에 표시하고 TC 검색·목록·선택·순서·개별 반복, 세션·실행·진행·결과는 Test 현황에서만 제공한다.

## 변경과 기준

기준은 main `d8bc08d08a331d46323709229e6da92acee26ca9`, 작업 위치는 `bsp_settings_source_isolated`, 브랜치는 `fix/settings-only-panel`이다. 원래 `bsp_os_upgrade_dashboard`의 동시 작업은 수정하지 않는다. 설정의 단일 컴포넌트·저장 범위·미저장 입력·TC 선택·기존 Run은 유지하고 전역 표시 범위와 한 열 배치만 바꾼다. API·DB·실제 외부 호출 변경은 없다.

지정 Minor Changes/Terra Low가 구현했고 별도 Unit Test Development/Sol Medium이 동기화·전역 비표시 회귀를 작성한다. 새 Independent Code Review/Sol High와 별도 Unit Test Execution & Reporting/Luna Low의 실제 결과를 아래에 기록한다. 실행 전 PASS로 표시하지 않는다.

## 검증·게시 기록

별도 Luna Low의 `.local-reports/settings-only-20261106/` 결과는 다음과 같다. 로그·스크린샷은 로컬 전용이며 Git에 포함하지 않는다.

| 범위 | 실제 결과 | 근거 폴더 |
|---|---|---|
| `npm.cmd run build --prefix apps/web` | PASS / exit0 | `web-build/` |
| `npm.cmd run build --prefix apps/gui-test` | PASS / exit0 | `gui-build/` |
| 프로젝트 Playwright 설정으로 source/settings 회귀 | 16 PASS / exit0 | `settings-source-final/` |
| `.venv` Python의 단독 GUI 브라우저 회귀 | 18 PASS / exit0 | `standalone-gui-e2e-venv/` |
| 합성 전체 탭 회귀 | 65 PASS / 1 TIMEOUT / exit1 | `workflow-final/` |
| 같은 코드의 실패 sidebar 사례 단독 재시험 | 1 PASS / exit0 | `workflow-sidebar-retry-local/` |

첫 source/settings 실제 실행은15 PASS/1 FAIL이었다. Test 현황의 설정 화면에서 TC 선택을 수행한 뒤 같은 탭으로 다시 이동하면 설정 화면이 보존되므로 실행 버튼은 보이지 않는 것이 맞다. 시험이 명시적으로 `← 결과로 돌아가기`를 누른 뒤 Preflight 무효화와 Suite/요청 검증을 이어가도록 수정해16개를 모두 통과했다. 원래 실패는 `settings-source-corrected/`에 보존한다. 전체 합성 회귀의 sidebar 팝업/탐색 대기는 단독 재시험에서 통과했으며 한 번의 전체66 PASS로 표현하지 않는다.

프로젝트 실행 위치/Chrome 설정을 빠뜨린 최초 기본 Playwright 브라우저 실행 실패, 시스템 Python3.10의 의존성 부족 실패, 중복 출력 폴더를 사용한 trace 정리 오류 등 헬퍼 시도는 별도 폴더에 보존한다. 설치된 Chrome과 프로젝트 `.venv`·정확한 작업 경로로 실행한 결과만 위 표에 집계했다. 앱·서버 구현을 이 실패에 맞춰 변경하지 않았다.

새 독립 Sol High의 코드·회귀 시험 정적 검토는 APPROVED다. 변경한 소스·시험4개 manifest는 `.local-reports/settings-only-20261106/source-test-manifest.json`, SHA256은 `8bbb72130ec0311b962f3e66e6df095408e0e71c688156f2ded81d4ee8ed6c90`이다. 백엔드·DB·외부 어댑터가 바뀌지 않아 해당 Python 회귀를 불필요하게 반복하지 않았다. 실제 Git 인증·장비·모델·Jira 실행은 범위 밖이다.

최종 문서 검사는 `PYTHONUTF8=1`로 PASS(exit0), 상대 링크923개·요구사항56개·시험182개·기존 NOT_RUN69개·오류0개다. `git diff --check`도 exit0이며 로그는 `docs-validation/`와 `diff-check/`에 보존한다.

## 실제 화면·재시작

별도 Luna의 실제8766 읽기 전용 화면 확인은 PASS(exit0)다. 전역에서 TC 목록·소개·데모 배너·세션/실행 toolbar·결과 영역이 숨겨지고 Test 설정만 단일 열로 전체 폭1158/1158px를 사용하는 것을 확인했다. 소스 유형3개와 `/preview-only/tc` draft가 Test 현황 왕복 후에도 유지되고, TC 목록은 지역 Test 현황에서 보였다.375px 화면에서 source 입력과 페이지가 가로로 넘치지 않았으며35개 요청은 모두GET, 페이지 오류0·config 동일·작업 수1→1이었다. 처음 펼친 source를 다시 눌러 접은 헬퍼는 수정해 재실행했고 앱 코드를 변경하지 않았다. 캡처와 최종 JSON은 `.local-reports/settings-only-20261106/helper-artifacts/settings-only-20261106/live-smoke/`에 로컬 전용 보존한다.

이후 기존8766 API를 같은 원래 runtime으로 숨김 재시작하고 새 health instance, 설정·작업·default/live GUI 이력 동일, schema2 유지·DB integrity_check=ok, 제공 JS와 새 빌드 일치를 확인했다. SQLite5개를 재시작 전에 별도로 백업했다. 서버 JS SHA256은 `1ad2ef8c43c54446f4a16fe2bb9a86f7713f3d0c1408e2454ff799ee60f5be20`이며 근거는 `.local-reports/settings-only-20261106/restart/verification.json`이다. 원격 CI·머지·푸시는 연결된 PR에 실제 체크 결과를 남긴다.
