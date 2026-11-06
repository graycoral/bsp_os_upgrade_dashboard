# RQ-57 병합 코드 게시 전 로컬 검증 · 2026-11-06

코드·시험 기준: `16882f497bce09b767ba71f0df1f7b92cfb53e95`. 별도 Sol High 독립 검토는 이 커밋에 대해 지적 사항 없이 APPROVED다. 이전 작업 트리의 시험과 실패 이력은 [기존 실행 기록](20261106-portability.md)에 보존한다. 아래 로그는 로컬 `.local-reports/publication-merge-tests-20261106-142902/`에 있다.

- 두 npm UI 빌드: 각각 종료 코드 0.
- 별도 Luna 실행의 Python 명령: `.venv/Scripts/python.exe -m pytest backend/gui_test/tests tests/test_gui_test_layout.py tests/test_engine.py tests/test_hardware_pipeline.py tests/test_gui_dashboard.py tests/test_gui_source_portability.py -q --basetemp <short C:/Temp>`. 최초 긴 작업 공간 임시 경로에서는 Windows 긴 경로 문제로 410 PASS, 18 FAIL, 4 SKIP, 12 ERROR였다 (`pytest.log`). 짧은 임시 경로 재실행은 439 PASS, 1 FAIL, 4 SKIP이었다 (`pytest-short-temp.log`). 실패한 `test_windows_runner.py::test_real_python_single_dual_and_idempotency`는 시간 초과였고, 해당 사례만 재실행해 1 PASS, 종료 코드 0이었다 (`pytest-windows-runner-isolated.log`). 코드나 시험을 변경하거나 약화하지 않았다. 여러 실행을 합쳐 440개 사례가 PASS했으며 단일 실행의 440 PASS는 아니다. 4 SKIP은 Windows에서 symlink 등을 사용할 수 없는 조건이다.
- 설정·소스 Mock 브라우저: 16 PASS. 혼합 브라우저 최초 실행 22건 중 dashboard 6건은 API harness가 없어 실패했다. 별도 dashboard 실행은 Windows의 `ModuleNotFoundError: fcntl`로 BLOCKED였다 (`dashboard-isolated.log`). 이 6건은 로컬 검증 범위 밖이며 Linux PR CI에서 별도로 확인한다.
- workflow 브라우저 최초 실행은 `BSP_BROWSER_EXECUTABLE` 부재로 21 PASS, 53 FAIL이었다. 설치된 Chrome 경로를 환경 변수로 지정한 동일 코드 재실행은 74 PASS, 종료 코드 0이었다 (`workflow-chrome.log`).

기존 사용자 서버 8766은 건드리지 않았으며 시험이 소유한 API는 종료했다. 실제 회사 인수 T-190, 실제 모델·인증·장비 및 외부 연결은 NOT_RUN이고 운영 baseline은 NONE이다. 로컬 Mock 결과는 실제 회사 인수 결과가 아니다.

Documentation validation: .venv/Scripts/python.exe -X utf8 docs/testing/validate_docs.py exited 0 (959 links, 57 requirements, 190 test cases, 70 NOT_RUN, 0 errors); git diff --check exited 0. Log: .local-reports/publication-merge-tests-20261106-142902/docs-validator-final.log.
