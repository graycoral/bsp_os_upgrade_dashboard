# 2026-11-06 · 실행·진단 명령 검증

RQ-59/D-63/REG-0072. 기준 `037b98f`; 검증한 소스·시험은 이후 커밋 `792d862645a7113f86f2932b112c5222b7c4a64f`로 고정했다. coordinator가 커밋 전 manifest 22개 항목의 불일치 0건을 확인했다. 커밋 후 재시험을 뜻하지 않는다. T-195~198 로컬 PASS, T-199 회사 인수 NOT_RUN. 시험 결과·실패 이력과 로컬 전용 증거는 아래에 기록한다. 회사 SSH·공유 폴더·장비 인수 T-199는 별도다. 과거 ZIP 시험과 실제 회사 인수를 재사용하지 않는다.

독립 Sol High 정적 리뷰는 네 지적을 수정한 뒤 APPROVED다. 리뷰는 시험 실행 PASS를 의미하지 않는다. 검토 당시 `scripts/setup_runtime.py` SHA-256 `7ba89ab28871795f03f2e91b89d036ae2760844f27b4a6a89efbe3c28a834ef3`. 별도 실행의 최초 Python 시험은 297 collected, 287 PASS/7 SKIP/3 FAIL이며 기존 fixture가 새 typed exception과 어긋난 사례다. 수정 후 재시험 이력과 최종 결과는 아래와 같다. 최초 로그·JUnit은 로컬 전용 `.local-reports/20261106-setup-commands/59acff8c4fca4685a830410eca1457d5/`에 보존하며 Git에 포함하지 않는다.

최종 소스·시험 독립 Sol High 정적 리뷰 APPROVED. 최초 287 PASS/7 SKIP/3 FAIL 후 첫 재시험은 294 PASS/7 SKIP/2 FAIL이었다. 기존 typed exception assertion을 수정하면서 cleanup 검증을 유지했고 최종 303 collected, 296 PASS/7 SKIP/0 FAIL, 26 warnings, exit 0이다. 7 SKIP은 Windows symlink 권한 1건과 Linux/POSIX/Bash 전용 6건이며 PASS가 아니다. 최초·재시험 로그와 XML은 같은 로컬 증거 폴더에 보존한다.

Windows Python 3.13.5에서 자식 프로세스에만 `PSExecutionPolicyPreference=Bypass`를 설정하고 `.venv/Scripts/python.exe -X utf8 -m pytest -p no:cacheprovider --basetemp=<외부 고유 임시 경로> ... --junitxml=<증거 경로>/pytest-final2.xml`을 실행했다. 대상: `tests/test_setup_commands.py`, `tests/test_setup_runtime.py`, `tests/test_runner_ports.py`, `tests/test_catalog_timeout.py`, `tests/test_windows_runner_bundle.py`, `tests/test_build_entrypoint.py`, `backend/gui_test/tests/test_catalog_settings.py`, `backend/gui_test/tests/test_source_snapshots.py`, `backend/gui_test/tests/test_source_transport.py`, `backend/gui_test/tests/test_flashing.py`, `backend/gui_test/tests/test_windows_runner.py`. 최종 로컬 `final-source-manifest.txt` SHA-256 `182099ca10c5af24f7895afd80d628c83fd71370ef2d1a4acd070102f768545a` (공백 제외). 패키지 시험은 아래와 같다.

## 새 ZIP 빌드·검증

커밋 `792d862645a7113f86f2932b112c5222b7c4a64f`에서 Python 3.12.10과 PyInstaller 6.22.3으로 추가 설치 없이 빌드했다. build-info scoped_dirty=false, 소스 해시 98개다. `dist/windows-runner/BSP-Windows-Runner.zip`: 27,889,244 bytes, SHA-256 `4809e0cee8de08bff0d1d0211f9b59385af8905a01348e0f5f4ef06784f65f0c`. ZIP 111개 항목, SHA256SUMS 110개 항목이 모두 일치하며 `GUIDE.md`, `launch-run.cmd`, `diagnose.cmd`를 포함한다.

실제 압축 해제 ZIP smoke 10 PASS, exit 0. PATH를 System32로 제한해 Python/pip 미설치 조건을 구성하고 PYTHONPATH/PYTHONHOME을 제거했으며 profile·명령·읽기 중심 doctor·로컬 인증과 실제 frozen host의 `source_snapshot_v1` 및 합성 등록 source PUT을 확인했다. 실제 TC·SSH·장비는 실행하지 않았다. 로컬 전용 증거는 `.local-reports/20261106-setup-commands/59acff8c4fca4685a830410eca1457d5/package/`의 build/verify/smoke stdout·stderr, `verify-package.py`, smoke XML과 build 출력에 지정된 중첩 빌드 로그다. T-199 회사 인수와 운영 baseline NONE은 유지한다.

빌드 및 smoke 재현 명령 (`<evidence>`는 위 로컬 증거 디렉터리의 절대 경로, `<unique>`는 별도 고유 임시 경로):

```powershell
apps/gui-test/.build/runner-venv/Scripts/python.exe -X utf8 scripts/build_windows_runner.py --log-dir <evidence>/package
$env:BSP_RUNNER_EXE = '<절대 ZIP 경로>'
.venv/Scripts/python.exe -X utf8 -m pytest -p no:cacheprovider --basetemp=<unique> tests/portable_runner_smoke.py --junitxml=<evidence>/package/smoke.xml
```

문서 검증 최초 FAIL: 요구사항 표의 RQ-59 누락으로 coverage mismatch (58 requirements, 199 tests, 1008 links, 72 NOT_RUN). 표 형식 수정 후 별도 재검증 PASS, exit 0: 1008 links, 59 requirements, 199 test cases, 72 NOT_RUN, 오류 0. `git diff --check`도 exit 0이며 출력이 없다. 최초 로그는 `package/docs-validate.stdout.log`, 최종 로그는 `package/docs-validate-final.*`와 `package/diff-check-final.*`에 로컬 보존한다.
