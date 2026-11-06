# 2026-11-06 · TC 목록 읽기 제한시간

RQ-58/D-62/REG-0071/PORT-005. 원본 기준 `0a378cda23262cafaa8f962c3c7eae5765a18755`, 시험은 미커밋 작업 트리에서 실행했고, 검증 후 코드·시험 바이트를 변경하지 않고 커밋 `7cad856f65798e3891e200d60e1301057161e3b8`로 고정했다. 아래 manifest는 그 검증 기준이다. 커밋 후 재시험을 뜻하지 않는다. 과거 PASS를 이번 코드의 결과로 재사용하지 않는다.

## 구현 범위와 상태

목록 전용 기본100초·1~600초 정수 설정, 전용 runtime JSON 원자 저장, normal/live 설정 API, API·worker 다음 요청 반영, WindowsRemote 요청별 timeout과 typed 오류, 웹 설정·목록 로딩 표시, 소스 마법사 단계별 flush·메뉴8·임시 CLI override를 다룬다. 기존 HTTP 제어5초·TC 실행·lease·source version/Run과 DB schema를 보존한다.

| 시험 | 상태 | 검증 범위 |
|---|---|---|
| T-191 | PASS | 설정 store/API strict validation·기본값·원자 저장·normal/live 공유·기존 상태 보존 |
| T-192 | PASS | WindowsRemote/catalog만 요청별 시간·다음 호출 반영·진행 중 값 고정·timeout 구분·마법사 단계/CLI |
| T-193 | PASS | 브라우저 목록 로딩·실패 중 설정·입력 draft·저장/재조회·오래된 응답·모드 전환 |
| T-194 | NOT_RUN | 실제 회사 공유 폴더·기존 EXE와 Linux 호출자·SSH 인수 |

시험 작성 Sol Medium, 실행 Luna Low, 독립 리뷰 Sol High. 최종 제품과 네 번째 source GET 회귀 포함 독립 리뷰 APPROVED. 리뷰어는 git diff --check만 실행했다.

## 실행 증거

코드·시험 manifest SHA-256 `2de699e4bfa84211860844468e495a687e1eff34d3e1862cedb6a469eedbde82`. 전체 로그 및 manifest는 로컬 전용 `.local-reports/20261106-catalog-timeout/bf1c8f8218de4cbdab6d9c2f0e1e9771/`에 보존한다.

- Python 10파일 최초 exit 1, 175 PASS/8 FAIL/8 SKIP. 네 실패는 PowerShell 정책으로 자식 환경에만 PSExecutionPolicyPreference=Bypass를 적용했다. 나머지 네 실패는 runner ports fake 2건과 live view fake 2건의 새 catalog_timeout 인자를 반영해 assertion을 약화하지 않고 수정했다. 최종 exit 0, 183 PASS/8 SKIP, 191 collected, 26 warnings. 최초 pytest.* 및 최종 pytest-final.* 로그/XML 보존.
- 최종 UI 변경 후 web 및 GUI 빌드 exit 0 (web-build-final2.*, gui-build-final2.*).
- 브라우저 catalog-loading, source-settings, settings-sync 세 spec 24 PASS/0 FAIL/0 SKIP/0 flaky, exit 0 (browser-final.*, browser-results-final.json). 최초 시도는 잘못된 Start-Process 작업 디렉터리로 시험 시작 전 실패해 NOT_RUN. 정적 fixture만 사용했다. coordinator가 browser-artifacts-final/catalog-loading-T-193-init-debec-rves-initial-auto-selection/catalog-loading.png에서 spinner와 문구를 확인했다.
- 독립 리뷰 P2: 화면 이탈 중 source PUT 완료가 폐기되는 문제를 수정하여 비활성 상태에서도 PUT을 보존하고 성공 시 이전 source GET을 무효화했다. 네 source 비동기 경합 회귀 포함 최종 APPROVED다.

### 재현 명령과 환경

Windows, Python 3.13.5, Node 24.21.0. 아래 `<evidence>`는 이 기록의 로컬 전용 증거 디렉터리 절대 경로다. Python 실행 시에만 자식 프로세스 환경 `PSExecutionPolicyPreference=Bypass`를 사용했다. 최종 실행 시각은 2026-11-06T19:47:47.643583+09:00이다.

```powershell
.venv/Scripts/python.exe -m pytest -p no:cacheprovider --basetemp C:/Users/grayc/AppData/Local/Temp/catalog-pytest-final-bf1c8f8218de4cbdab6d9c2f0e1e9771 tests/test_catalog_timeout.py backend/gui_test/tests/test_catalog_settings.py tests/test_setup_runtime.py tests/test_runner_ports.py backend/gui_test/tests/test_api.py backend/gui_test/tests/test_windows_runner.py backend/gui_test/tests/test_live_view.py backend/gui_test/tests/test_source_transport.py tests/test_gui_test_layout.py tests/test_gui_source_portability.py --junitxml=<evidence>/pytest-final.xml
npm.cmd run build --prefix apps/web
npm.cmd run build --prefix apps/gui-test
```

브라우저는 `apps/web`에서 `node_modules/.bin/playwright.cmd test catalog-loading.spec.ts source-settings.spec.ts settings-sync.spec.ts --output <evidence>/browser-artifacts-final --reporter=json`으로 실행하고 Chrome 실행 파일 override 및 JSON 출력 환경을 지정했다. JSON 결과는 `<evidence>/browser-results-final.json`이다. Python 8 SKIP은 Windows 사용자 symlink 생성 권한 5건과 POSIX/Bash 플랫폼 시험 3건으로, PASS가 아니다.

## 배포·미실행 경계

사용자 변경 `apps/gui-test/config/device-test.example.json`와 `.vscode/`를 보존한다. 승인된 Runner ZIP/EXE는 재빌드·교체하지 않는다. Linux API/worker·웹의 새 호출 대기는 기존 Runner catalog 서버와 호환되고, 기존 EXE 자체 메뉴4는 이전5초 동작을 유지한다. 새 진행·CLI·메뉴8은 소스 마법사에만 제공한다. 새 binary나 `source_snapshot_v1` capability를 검증했다고 주장하지 않는다.

실제 BSP/SSH/TC 실행·공유 폴더·장비/Jira 인수는 수행하지 않았다. 회사 인수 T-194와 운영 baseline NONE을 유지한다. 회사 실제 배포·인수는 [PORT-005](../../porting/PORT-005.md)에 따른다.
