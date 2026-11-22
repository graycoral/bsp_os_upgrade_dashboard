# 2026-11-22 · Windows 커넥터 SSH 프로필

- 요구사항 RQ-82, 로컬 T-306, 회사 및 Windows T-307, [PORT-015](../../porting/PORT-015.md)
- 기준 커밋 `83dffb6532edc119a55f09bc57f7fa47d38f9bcd`의 로컬 작업 트리
- T-307 `NOT_RUN`. 회사 Linux 시작 훅, 실제 SSH 접속 및 Windows 최초 bootstrap 실행은 회사 환경에서 확인한다.

## 로컬 시험

- T-306 PASS. macOS Python 3.11.7에서 `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q -rs tests/test_direct_connector_unit1.py tests/test_direct_connector_unit4.py tests/test_plugin_delivery.py`로 28건 PASS, 종료 0. 원본 로그는 `.local-reports/20261122-connector-ssh-profile/root-regression-loopback.log`다.
- 최초 개발 세션 실행은 25 PASS, 루프백 바인딩이 금지된 세 시험이 `PermissionError`로 실패했다. 같은 시험을 루프백 허용 환경에서 다시 실행해 모두 통과했다. 최초 로그 `.local-reports/20261122-connector-bootstrap-profile-dev/pytest-1.log`를 보존한다.
- 플러그인 런타임 및 복구 회귀 `.venv/bin/python -m pytest -q -rs tests/test_plugin_runtime.py tests/test_agent_monitor_recovery.py tests/test_recovery_bundle.py` 105 PASS. 첫 실행은 104 PASS와 T-254의 루프백 바인딩 실패 1건이었다. 해당 묶음을 루프백 허용 환경에서 다시 실행했다. 로그는 `.local-reports/20261122-connector-bootstrap-profile-dev/pytest-2.log`와 `pytest-4.log`다.
- 결과 CSV에 기록한 SHA-256은 기준 커밋 대비 제품 소스 다섯 파일 및 시험 파일의 `git diff --no-ext-diff` 출력 지문이다. 위 로그는 로컬 전용이다.
- `.venv/bin/python docs/testing/validate_docs.py` PASS, `git diff --check` PASS.

## 독립 리뷰

개발과 분리된 Codex 세션이 코드 및 T-306을 리뷰했다. 저장된 SSH 포트 2222가 다른 서버와 계정을 명시한 기존 내보내기에 적용될 수 있음을 지적했다. 수정본은 명시 서버와 계정을 함께 요구하고 SSH 포트 생략 시 22를 사용하며, 저장된 대상에는 저장 포트를 적용한다. 수정본 재검토 결과 APPROVED였다.

별도 CLI 시험 2건과 기존 DB 복구·bootstrap v1/v2·Windows 실행기 전달 시험 3건이 통과했다. 로컬 원본 로그는 `.local-reports/20261122-connector-ssh-profile-review/`의 `cli.log`, `compatibility.log`다. Claude 실행기는 현재 환경에서 실행할 수 없어 Claude 리뷰는 미실행이다.
