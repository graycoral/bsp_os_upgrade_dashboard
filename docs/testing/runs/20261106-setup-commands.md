# 2026-11-06 · 실행·진단 명령 검증

RQ-59/D-63/REG-0072. 기준 `037b98f`; 대상 코드 커밋은 구현·검증 후 고정한다. T-195~197 로컬 PASS, T-198 패키지 및 T-199 회사 인수 NOT_RUN. 실제 시험 결과·명령·실패 및 재시험과 로컬 전용 증거 경로는 실행 후 추가한다. 회사 SSH·공유 폴더·장비 인수 T-199는 별도다. 과거 ZIP 시험과 실제 회사 인수를 재사용하지 않는다.

독립 Sol High 정적 리뷰는 네 지적을 수정한 뒤 APPROVED다. 리뷰는 시험 실행 PASS를 의미하지 않는다. 검토 당시 `scripts/setup_runtime.py` SHA-256 `7ba89ab28871795f03f2e91b89d036ae2760844f27b4a6a89efbe3c28a834ef3`. 별도 실행의 최초 Python 시험은 297 collected, 287 PASS/7 SKIP/3 FAIL이며 기존 fixture가 새 typed exception과 어긋난 사례다. 수정 후 재시험은 대기 중이다. 최초 로그·JUnit은 로컬 전용 `.local-reports/20261106-setup-commands/59acff8c4fca4685a830410eca1457d5/`에 보존하며 Git에 포함하지 않는다.

최종 소스·시험 독립 Sol High 정적 리뷰 APPROVED. 최초 287 PASS/7 SKIP/3 FAIL 후 첫 재시험은 294 PASS/7 SKIP/2 FAIL이었다. 기존 typed exception assertion을 수정하면서 cleanup 검증을 유지했고 최종 303 collected, 296 PASS/7 SKIP/0 FAIL, 26 warnings, exit 0이다. 7 SKIP은 Windows symlink 권한 1건과 Linux/POSIX/Bash 전용 6건이며 PASS가 아니다. 최초·재시험 로그와 XML은 같은 로컬 증거 폴더에 보존한다.

Windows Python 3.13.5에서 자식 프로세스에만 `PSExecutionPolicyPreference=Bypass`를 설정하고 `.venv/Scripts/python.exe -X utf8 -m pytest -p no:cacheprovider --basetemp=<외부 고유 임시 경로> ... --junitxml=<증거 경로>/pytest-final2.xml`을 실행했다. 대상: `tests/test_setup_commands.py`, `tests/test_setup_runtime.py`, `tests/test_runner_ports.py`, `tests/test_catalog_timeout.py`, `tests/test_windows_runner_bundle.py`, `tests/test_build_entrypoint.py`, `backend/gui_test/tests/test_catalog_settings.py`, `backend/gui_test/tests/test_source_snapshots.py`, `backend/gui_test/tests/test_source_transport.py`, `backend/gui_test/tests/test_flashing.py`, `backend/gui_test/tests/test_windows_runner.py`. 최종 로컬 `final-source-manifest.txt` SHA-256 `182099ca10c5af24f7895afd80d628c83fd71370ef2d1a4acd070102f768545a` (공백 제외). 패키지 시험은 별도다.
