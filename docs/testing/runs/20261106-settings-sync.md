# 전체·탭별 설정 동기화 · 2026-11-06

상태: **LOCAL_VERIFIED / INDEPENDENT_REVIEW_APPROVED**. RQ-55/D-59 및 후속 RQ-56/D-60. 환경 설정에서 기존 화면 편집 가능 설정을 모두 제공하고 대시보드·사람 검토/Jira·Test 현황에서도 관련 항목을 같은 편집 상태로 수정한다. 그룹별·전체 접기/펼치기와 서버 폴더/Git URL 소스 등록·실제 브랜치 조회·불변 소스 전달을 추가했다. 사용자가 완료 후 재빌드·재실행·머지·푸시를 명시적으로 요청했다. 실제 장비·모델·Jira·외부 저장소 인증 인수 및 운영 baseline 변경은 범위 밖이다.

## 기준과 역할

- 시작 기준: `main`, `cd124ae` 및 이번 미커밋 변경. 기존 사용자 변경 `apps/gui-test/config/device-test.example.json`, `.vscode/`는 보존한다.
- 요구 분석: 지정 Requirements Analysis / GPT-6 Astra XHigh.
- 상세 설계: 지정 Detailed Design / GPT-6 Astra High.
- 구현: 지정 Implementation / GPT-6.1 Sol High.
- 시험 작성: 지정 Unit Test Development / GPT-6.1 Sol Medium. 상태 보존·검증 경계를 브라우저 행동 시험으로 확인한다.
- 독립 코드 검토·시험 실행 결과는 실제 수행 후 아래에 기록한다.

## 검증할 동작

단일 BSP 폼과 단일 TestPage를 유지해 양쪽 위치에서 같은 초안·JSON 오류·명령 템플릿·연결·반복·Suite 입력을 편집한다. 실행 기록·다이어그램에 새 설정을 만들지 않는다. 보기 모드는 명시적 적용·재로드와 모드별 데이터 분리를 유지한다. BSP 설정 저장, GUI 프로파일/명령/Suite 저장, 브라우저 보기 모드 적용은 각각 기존 저장 범위를 유지한다.

접기·펼치기는 키보드와 보조기술로 조작 가능해야 하며 접힌 잘못된 입력을 저장하면 해당 영역을 열고 입력 위치를 안내한다. Test 현황과 전체 설정에서만 해당 화면의 조회/heartbeat를 활성화하고 중복 타이머를 만들지 않는다. 설정 편집·화면 이동은 실행을 시작·중단하거나 기존 작업 snapshot을 변경하지 않는다.

## 실행·검토 기록

### RQ-55 초기 실행과 정적 리뷰

별도 Luna Low 실행의 `.local-reports/settings-sync-20261106/104929770/`에서 `npm.cmd run build --prefix apps/web`와 `npm.cmd run build --prefix apps/gui-test`는 각각 exit0이다. 새 `settings-sync.spec.ts` 최초 실행은 Playwright 기본 브라우저 캐시가 없어 7개 모두 페이지 실행 전 실패(exit1)했다. 설치된 Chrome을 `BSP_BROWSER_EXECUTABLE`로 지정한 재실행은 **4 PASS / 3 FAIL, exit1**이다. T-169/173은 잘못된 JSON의 검증 문구가 label 이름에 추가되는 선택자 오류, T-175는 option의 암시적 value를 명시적 HTML 속성으로 찾은 시험 오류였다. 별도 시험 작성자가 기존 검증을 유지하며 선택자를 수정했고 비활성 조회·접기 저장소 실패·중복 ID 검증을 보강해 9개 시험으로 확장했다. 수정 후 재시험은 아직 NOT_RUN이다.

새 독립 Sol High의 RQ-55 정적 코드 리뷰는 **APPROVED**다. 시험 실행·시각 검증을 대신하지 않으며 RQ-56의 후속 소스 변경은 별도 최종 리뷰 대상이다. 전체 로그·스크린샷·manifest는 `.local-reports/`의 고유 실행 폴더에 로컬 전용으로 보존하며 Git에 포함하지 않는다. 실패와 재시험은 별도 실행으로 추가한다.

### RQ-56 설계와 구현 범위

추가 요구 분석 Astra XHigh, 구조 Astra XHigh, 상세 Astra High를 수행했다. Manager 소유 소스 서비스가 서버 폴더/관리 Git 저장소에서 불변 snapshot을 준비하고 적용 버전·실제 ref/commit을 영속화한다. Windows 실행기에는 선택적 snapshot capability와 인증된 전송 경로를 추가하며 기존 공유 소스·자동 퓨징의 Host.root는 유지한다. 같은 목록을 보여주고 다른 파일을 실행하는 fallback을 금지한다. 실제 원격 저장소 대신 임시 로컬 Git·모의 전송으로 검증할 예정이다.

### 소스 통합 중간 실행·독립 검토

별도 Luna의 `.local-reports/settings-sync-20261106/110151656-source/`에서 두 UI 빌드는 exit0이다. Python 최초 기본 TEMP는 접근 거부로 중단됐고, 저장소 내부 TEMP로 바꾼 실행은 **26 PASS/14 FAIL**이었다. 일반 폴더 fixture가 저장소 안의 Git 하위 폴더가 된 것이 12건의 원인이었다. 저장소 밖의 별도 TEMP에서 실행한 **43 PASS/2 FAIL**은 이 원인을 확인했다. 남은 두 건은 실제 HTTPS를 로컬 Git으로 치환한 mock이 production의 file protocol 금지에 걸린 시험 경계 문제였으며 시험 mock에서만 로컬 전송을 허용했다. production의 경로 판별·protocol 제한은 유지한다.

브라우저 중간 실행은 **12 PASS/3 FAIL**이다. 새 소스 시험 6개는 모두 통과했고, 기존 설정 시험의 오류 도움말 label 결합과 취소한 초기 요청의 재시도 횟수 기대값을 수정했다. 입력 보존·포커스·한 번의 성공 초기화·비활성 polling 금지 검증은 유지한다. 이 실패들은 최종 성공으로 덮지 않고 각 실행 로그에 보존한다.

새 독립 Sol High의 전체 RQ-56 및 RQ-55 통합 정적 리뷰는 **APPROVED**다. 리뷰 중 REG-0062의 Windows 디렉터리 접두어 대소문자 충돌, REG-0063의 legacy 복귀 API 종류 누락을 수정하고 독립 재확인 exit0을 받았다. 원래 재현은 `.local-reports/source-review-20261106-casing/full.log`, 재확인은 `.local-reports/source-review-20261106-final/full.log`에 로컬 전용 보존한다. 별도 시험 작성자가 manifest 생성/수신 양쪽의 접두어 충돌 방지 시험을 추가했다. 수정 후 최종 전체 실행 결과는 아래에 추가한다.

### 동시 작업 감지와 기능 분리

원래 `bsp_os_upgrade_dashboard` 작업 폴더에서 별도 호스트 추출 작업이 같은 파일을 동시에 변경한 것을 감지했다. HostContext/ports/호스트 adapter 분리, worker·CI·패키징 변경은 이번 RQ-55/56 범위가 아니다. 다른 작업과 사용자 설정은 덮어쓰지 않고 `.local-reports/settings-sync-20261106/concurrent-state-20261106/`에 당시 변경 스냅샷을 보존했다. 해당 시점 이후 원래 폴더의 소스는 이전 시험·리뷰가 검증한 것과 동일하다고 주장하지 않는다.

`cd124ae`에서 별도 `bsp_settings_source_isolated` 작업 트리와 `feature/settings-source-isolated` 브랜치를 만들어 설정·소스 기능만 복원한다. 구현 담당자들이 본인 변경을 분리하고 독립 리뷰·현재 소스 재시험을 수행한 뒤 이 브랜치만 머지한다. 원래 작업 폴더·별도 작업 브랜치·미커밋 파일과 `.vscode/`는 보존한다. 최종 서비스도 검증된 분리 작업 트리를 기준으로 시작한다.

## 최종 분리본 실행·독립 검토

별도 Luna Low가 `bsp_settings_source_isolated`에서 새로 실행했다. 원래 폴더의 PASS를 재사용하지 않았다. 근거는 분리본 `.local-reports/settings-sync-isolated-20261106/112705720-final/`에 로컬 전용 보존한다. 소스·시험29개 파일 manifest는 `.local-reports/settings-sync-isolated-20261106/final-source-test-manifest.json`, SHA256은 `86ff743072a5a373a4ae750fc86d23ec410504f9d5f0f66509bbe19b9beee8f8`이며 최종29개 모두 현재 파일과 일치했다.

| 명령·범위 | 결과 | 로그 |
|---|---|---|
| `npm.cmd run build --prefix apps/web` | PASS / exit0 | `apps-web-build-rerun.log` |
| `npm.cmd run build --prefix apps/gui-test` | PASS / exit0 | `apps-gui-test-build-rerun.log` |
| `python -m pytest -q` 신규 소스3개 시험 파일 | 47 PASS / exit0 | `source-python-targeted.log` |
| `python -m pytest -q backend/gui_test/tests tests/test_gui_test_layout.py tests/test_hardware_pipeline.py` | 355 PASS / 2 SKIP / exit0 | `backend-regressions.log` |
| `npx.cmd playwright test source-settings.spec.ts settings-sync.spec.ts` | 15 PASS / exit0 | `browser-targeted.log` |
| `npx.cmd playwright test orchestration.spec.ts` | 6 PASS / exit0 | `orchestration.log` |
| `python -m backend.gui_test.demo.browser_e2e` | 18 PASS / exit0 | `standalone-gui-browser.log` |
| `node workflow_diagram/tests/run.cjs` | 66 PASS / exit0 | `workflow-diagram.log` |

문서 검사는 Windows 기본 CP949에서 UTF-8 문서를 읽지 못한 최초 실패를 보존하고 `PYTHONUTF8=1`로 재실행했다. 최종 PASS(exit0): 상대 링크919개·요구사항56개·시험182개·기존 NOT_RUN69개·오류0개다. `git diff --check`도 exit0이다. 문서 검사는 제품 시험 결과와 구분한다.

Windows의 접근 거부 기본 TEMP 대신 저장소 밖의 고유 TEMP/TMP·basetemp를 사용하고 pytest cache를 비활성화했다. 브라우저는 설치된 Chrome을 명시했다. 신규47개는 백엔드355개에 포함되며 브라우저 합계는105개다. 새 독립 Sol High의 분리본 검토는 APPROVED다. REG0064는 원래 경로 재현 외에300자 이상 source 저장·재조회·archive·attempt 복사와 실제 인증 HTTP 업로드 경계를 검증했다.

분리본 최초 빌드는 남아 있던 다른 세션의 `guiTest` prop 때문에 TS2322(web exit1/단독 exit2)로 실패했다. 지정 Minor Changes/Terra Low가 해당 prop만 제거했고 두 빌드와 전체 회귀를 다시 통과했다. 이 실패도 최초 `apps-*-build.log`에 보존한다. 원래 폴더의 합성65 PASS/1 FAIL 및 API/worker 시작의 Windows `fcntl` 부재는 별도 이력이다. 실제 Linux worker 부팅·잠금과 외부 Git 인증·SSH·장비·모델·Jira는 이 로컬 결과로 PASS 처리하지 않는다.

## 게시 상태

기능 커밋 `ab3ce8771a2f3b8682437df151110292e78d3ca0`을 푸시하고 PR #15를 열었다. 최초 CI `42151288449`는 Linux Python1006 PASS/15 SKIP·모의 demo7 PASS, Windows package SUCCESS였다. 별도 Windows standalone `42151288368`의 PowerShell/pwsh 두 작업도 SUCCESS였다. Linux 통합 브라우저는43 PASS/3 FAIL로 중단했다. 원인은 T-39/70·95·101의 범용 status 선택자가 BSP 저장 완료와 유지된 GUI 초기 조회 status를 동시에 찾은 것이며 저장 실패가 아니었다.

별도 시험 작성자가 해당 파일의 저장 완료3개와 같은 원인의 브리지 기본값 안내1개를 예상 메시지로 한정했고 독립 리뷰 APPROVED를 받았다. 기존 값·내보내기·재접속·기본 경로/사용자 명령 보존 검증은 유지한다. 로컬의 별도 API-only 재시험은 T-39/70·101 PASS, T-95는 기존 Linux 경로 기대값을 Windows 서버에서 검증할 수 없어422로 중단했다. trace의 `/workspace/bsp-upgrade`는 POSIX 절대 경로지만 기존 `Path.is_absolute()`의 Windows 판정에서는 절대 경로가 아니다. 이 시험을 완화하거나 production 경로 검증을 변경하지 않고 Linux CI에서 재시험한다.

첫 CI 전체 로그는 분리본 `.local-reports/settings-sync-isolated-20261106/ci-42151288449-linux-failure.log`, API-only 기록은 `114042540-dashboard-api/`에 로컬 전용 보존한다. 최종 게시·체크·머지 이력은 [PR #15](https://github.com/graycoral/bsp_os_upgrade_dashboard/pull/15)를 따른다.

### CI 재시험과 서비스 재시작

수정 커밋 `403997dab9bb3809ffa490e06d3aa9c463848961`의 CI `42152139317`은 SUCCESS다. Linux 전체1006 PASS/15 SKIP, 모의 demo7 PASS, 통합 브라우저46 PASS·단독18 PASS, wheel/배포 묶음을 확인했다. 같은 실행의 Windows package는390 PASS/3 SKIP와 설치 smoke SUCCESS다. 별도 standalone `42152139370`의 PowerShell/pwsh 두 작업도 SUCCESS다. 기본 경로를 포함한 원래 세 실패 시험은 Linux 통합46개에 포함된다. 이 결과는 실제 Git 인증·SSH·보드·모델·Jira 인수를 의미하지 않는다.

기존8766 API를 종료하고 검증한 `bsp_settings_source_isolated`에서 같은 원래 `.runtime`을 지정해 숨김 프로세스로 재시작했다. Windows에서 기존 Linux worker를 새로 시작하지 않았다. 재시작 전 SQLite5개를 별도로 백업했고 새 health instance·정적 JS 빌드 해시 일치·작업1개/GUI Run2개/실제 모드0개 이력·기존 작업 버전/프로필·config 원문/버전 보존과 DB integrity_check=ok를 확인했다.

실행 중이던 구 API와 현재 main 기준의 차이로 기존 BSP DB의 schema1→2 이전이 시작 시 적용됐다(D-58). 원시 config 데이터는 변경되지 않았으며 GET 응답에는 현재 Profile의 기본 필드와 모듈 stable_key/target_paths 기본값이 추가됐다. 응답 전체 비교가 처음 불일치한 기록을 보존한 뒤 원시 DB 데이터와 기존 사용자 필드가 그대로임을 재확인했다. 최종 근거는 `.local-reports/settings-sync-deploy-20261106/restart/verification-final.json`, 백업은 `prestop/databases/`에 로컬 전용 보존한다. 서버가 제공하는 JS SHA256은 `d3350d7c6563f2c590baf9305938eb05997b6065548b9c60b23852fbe1e10d6f`다.

별도 Luna의 실제8766 읽기 전용 화면 확인에서 세 소스 유형, Test 현황→환경 설정 간 Git URL draft 공유, 페이지 오류0·GET/HEAD 외 요청0,375px 화면의 scroll/client 폭375/375를 확인했다. 소스 확인·적용·설정 저장이나 실행은 하지 않았다. 이전 헬퍼의 숨긴 버튼/영문 검색 선택자 오류는 별도 로그로 보존하고 실제 소스 패널을 열어 다시 확인했다. 화면·헬퍼 근거는 `.local-reports/settings-sync-deploy-20261106/smoke-followup/`에 로컬 전용 보존한다.
