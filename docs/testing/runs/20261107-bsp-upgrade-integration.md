# 2026-11-07 BSP Upgrade 플러그인 로컬 구현 검증

RQ-60/D-64 구현과 로컬 모의 검증 기록이다. 실제 회사 Linux·SSH·COM·보드·splitter 인수 T-209는 NOT_RUN이며 운영 baseline은 NONE이다. 원본 참조 커밋은 `476d95f08169d4a4fbb4a999a94d417d9e59cef3`, 대상 구현 커밋은 `1a18ea6fab8b1caead3935ce70cb1e30153d631b` (38개 소스·시험 파일, 브랜치 `feature/bsp-upgrade-gui-test`)이다. 구현은 Sol High가 수행했다. 실제 모델 호출이나 장비 실행은 하지 않았다.

새 독립 Sol High 코드 리뷰는 최초 CHANGES_REQUESTED 후 수정 재확인하여 APPROVED다. 근거 `.local-reports/rq60-code-review/review-summary.txt`와 `source-sha256.json`, 25개 파일 집계 SHA-256 `f41f936e7b75c14fdba52d0114245061dfeae47a58c1d0e530a1f99bb853bb1f`. `.local-reports/pvt2/source-compare.log`의 38개 파일 대조에서 시험 manifest의 raw 차이, 줄끝 정규화된 리뷰 소스와 고정 커밋의 차이, 누락 파일이 모두 없었다. 이는 범위가 고정된 소스 리뷰이며 실제 장비 인수가 아니다. 최종 콘솔 drain의 panic·관찰 공백을 논리 결과에 반영하고 안전 준비 취소, 제어 이전 인증, 플래시 프로파일 고정, UNKNOWN→READY 복구, RELEASE 확인 전 FINALIZING을 재확인했다. runner_id 누락 지적은 검토자가 철회해 결함으로 기록하지 않는다.

독립 Luna Low 실행 `.local-reports/pvt2`: 집중 시험 169 PASS, 전체 backend 494 PASS. 집중 시험은 전체의 부분집합이므로 합산하지 않는다. runner-setup 최초 실행은 PowerShell 정책 제한으로 131 PASS / 7 SKIP / 5 FAIL; 해당 프로세스의 `PSExecutionPolicyPreference=Bypass`로 재실행해 136 PASS / 7 SKIP이다. 최초 실패와 재실행 로그를 보존한다. UI 두 빌드, 통합 ZIP, headless wheel 격리 설치는 로컬 PASS다. 전체 Dashboard `npm run build --prefix apps/web`도 1612개 모듈 PASS이며 `.local-reports/pvt2/web-dashboard-build.log`에 기록했다. 기존 전용 runner venv는 CPython 3.12.10 및 고정 의존성 확인 PASS다. 앞선 전역 Python 3.12의 annotated-doc 부재는 전용 환경 빌드 불가의 근거가 아니다.

실행 환경은 Windows, 저장소 `.venv`, Node/npm이며 임시 시험 경로는 `C:\Users\grayc\work\bsp-rq60-tmp\v2`다. 다음 명령과 로그의 결과는 로컬 모의 범위다.

| 실행 명령 | 로그와 결과 |
|---|---|
| `.venv/Scripts/python.exe -m pytest <12 backend/gui_test/tests/test_plugin_integration_*.py> backend/gui_test/tests/test_flashing.py -q -p no:cacheprovider --basetemp="C:\Users\grayc\work\bsp-rq60-tmp\v2"` | `focused.log`: 169 PASS. 꺾쇠는 실제 지정한 12개 시험 파일의 축약 표기다. |
| `.venv/Scripts/python.exe -m pytest backend/gui_test/tests -q -p no:cacheprovider --basetemp="C:\Users\grayc\work\bsp-rq60-tmp\v2"` | `backend-suite-status.log`: 494 PASS, 경고 28 |
| `.venv/Scripts/python.exe -m pytest tests/test_windows_runner_bundle.py tests/test_setup_runtime.py tests/test_setup_commands.py -q -p no:cacheprovider --basetemp="C:\Users\grayc\work\bsp-rq60-tmp\v2"` | `runner-setup.log`: 정책 오류 5 FAIL, 131 PASS, 7 SKIP. 같은 명령을 해당 프로세스의 `$env:PSExecutionPolicyPreference='Bypass'`로 재실행해 `runner-setup-bypass.log` 136 PASS, 7 SKIP |
| `npm.cmd run build --prefix apps/gui-test` | `gui-test-ui-build.log`: PASS |
| `npm.cmd run build:gui-test --prefix apps/web` | `web-host-build.log`: PASS |
| `npm.cmd run build --prefix apps/web` | `web-dashboard-build.log`: PASS, 1612개 모듈 |

위 로그는 모두 `.local-reports/pvt2`에 있다.

최종 패키지는 고정 커밋의 깨끗한 `C:/Temp/bsp-rq60-build`에서 생성했으며 검증된 `apps/gui-test/static`만 복사했다. Runner smoke는 원본 저장소 작업 디렉터리에서 clean worktree의 ZIP을 대상으로 실행했다. 인터프리터는 원본 저장소에서 사용했다. 아래 `<repo>`는 원본 저장소, `<stage>`는 `<repo>/.local-reports/pvt2/clean-wheelstage`, `<delivery>`는 `<repo>/dist/bsp-upgrade-integration-20261107`, `<zip>`은 `C:/Temp/bsp-rq60-build/dist/windows-runner/BSP-Windows-Runner.zip`이다.

| 실행 명령 | 로그와 결과 |
|---|---|
| `<repo>/apps/gui-test/.build/runner-venv/Scripts/python.exe scripts/build_windows_runner.py --log-dir <repo>/.local-reports/pvt2/portable-build` | 종료 0; 고정 revision과 scoped_dirty=false |
| `<repo>/.venv/Scripts/python.exe apps/gui-test/package.py --integration --include-ui --output <delivery>/bsp-gui-test-integration.zip` | `clean-package-integration.log`: 종료 0, 130개 파일 |
| `<repo>/.venv/Scripts/python.exe apps/gui-test/package.py --stage-headless-wheel <stage>` | `clean-stage-wheel.log`: 종료 0 |
| `<repo>/.venv/Scripts/python.exe -m pip wheel <stage> --no-deps --no-build-isolation -w <delivery>` | `clean-wheel-build.log`: 종료 0 |
| `<repo>/.venv/Scripts/python.exe -m pip install --no-deps --target <repo>/.local-reports/pvt2/clean-wheel-install <wheel>` | `clean-wheel-install.log`: 종료 0; `clean-wheel-smoke.log`에서 integration·plugin_client import와 entrypoint 확인 |
| `$env:BSP_RUNNER_EXE=<zip>; <repo>/.venv/Scripts/python.exe -m pytest tests/portable_runner_smoke.py -q -p no:cacheprovider --basetemp=C:/Temp/bsp-rq60-smoke2` | 원본 저장소 cwd; `portable-runner-smoke.log`: 10 PASS, 종료 0 |

고정 커밋의 깨끗한 worktree에서 Windows 패키지를 빌드하고 원본 저장소에서 해당 패키지의 portable Runner smoke 10 PASS를 확인했다. 빌드 manifest는 `scoped_dirty=false`와 고정 `source_revision`을 기록한다. 깨끗한 source ZIP·headless wheel도 재생성하고 격리 설치·import를 확인했다. 근거는 `.local-reports/pvt2/clean-*.log`와 `portable-runner-smoke.log`다. 기존 pvt2 source ZIP에는 사용자의 기존 `device-test.example.json`이 포함되어 최종 전달본으로 사용하지 않는다.

최종 산출물 `dist/bsp-upgrade-integration-20261107`의 SHA-256: source ZIP `d0ecdadd76afaba7a73d85a50916e399ea77cfa8984adc97b8761b1611e2ff10`, wheel `576e349cbbd54d67838e97c55d0ad2e293cc8fad778696cdcf853c60de2bd847`, Runner ZIP `e66fc3b20d379f2cb3f2463a9d23b66a447956ac2de03e621c11de23d253ca4c`. T-208의 실제 Linux 설치·복원은 여전히 NOT_RUN이다.

| 시험 | 로컬 모의 근거 |
|---|---|
| T-200 | `backend/gui_test/tests/test_plugin_integration_service.py` |
| T-201 | `test_plugin_integration_http.py`, `test_plugin_integration_transport.py` |
| T-202 | `test_plugin_integration_selection.py` |
| T-203 | `test_plugin_integration_snapshots.py`, `test_source_snapshots.py` |
| T-204 | `test_plugin_integration_batches.py`, `test_plugin_integration_pipeline.py` |
| T-205 | `test_plugin_integration_observer.py`, `test_plugin_integration_pipeline.py`, `test_plugin_integration_remote.py` |
| T-206 | `test_plugin_integration_batches.py`, `test_plugin_integration_pipeline.py` |
| T-207 | `test_plugin_integration_recovery.py`, `test_plugin_integration_remote.py` |
| T-208 | `test_plugin_integration_package.py`와 Windows 로컬 ZIP·wheel 근거만 확보. 실제 Linux 설치·복원 인수 미실행으로 NOT_RUN |
| T-209 | 실제 회사 환경 인수 NOT_RUN |

추가 연결 진단은 callback, 회전되는 `connections.jsonl`, 백엔드 부재 시 클라이언트 로그를 제공한다. 세부 확인은 `test_plugin_integration_diagnostics.py`와 로컬 실행 로그를 따른다.

초기 실패 이력: `.local-reports/pr3/output.log`는 최종 capture drain의 panic·gap 2 FAIL / 14 PASS, `pr4/output.log`는 원격 console 판정 전달 2 FAIL / 13 PASS로 모두 실제 코드 결함이었다. `pr5/output.log`는 강화된 RELEASED 증거와 고정 시계에 맞지 않는 fixture의 5 FAIL / 9 PASS로 별도 제품 결함이 아니다. fixture 보정 후 작성자 점검 pr6 47 PASS, pr7 169 PASS이며 독립 전체 시험과 합산하지 않는다. runner-setup PowerShell 정책 실패도 위 기록대로 보존한다.
