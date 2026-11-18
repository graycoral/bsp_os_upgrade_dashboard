# 2026-11-19 `.omo` CLI 메타데이터 제외 처리

RQ-13/37 · T-92/98/100 · REG-0116. 회사 테스트 중 코드 구현(`code`) 단계에서 구현은 성공했으나 작업 폴더의 `.omo` 때문에 단계 검증/리뷰에서 실패한다는 보고를 확인했다.

## 원인과 변경

- `backend/adapters/native.py`의 `workspace_revision`(v1)과 `_file_observations`(v2)는 `.gitignore`를 읽지 않고 하드코딩된 제외 목록(`.git`, `.repo`, `.claude`, `.codex`, `.opencode`, `.bsp-dashboard`)만 사용해 워크스페이스 바이트를 해싱·관찰했다. `.omo`(Oh My OpenCode 등의 상태/세션 폴더·파일)가 제외 목록에 없어, 구현 직후 별도 Claude 리뷰 도중 `.omo`가 갱신되거나 변경 파일로 감지되면 실패 처리됐다.
- `backend/adapters/native.py`: `IGNORED_WORKSPACE_DIRS`에 `.omo`를 추가하고 디렉터리뿐 아니라 동일 이름의 파일·심볼릭 링크도 해시/관찰에서 제외했다. v1/v2 프롬프트에도 CLI/VCS 메타데이터를 소스 변경이나 리뷰 결함으로 취급하지 않도록 명시했다.
- `backend/adapters/inventory.py`: 3-tree 인벤토리 제외 집합(`VCS`)에 `.claude`, `.codex`, `.opencode`, `.omo`, `.bsp-dashboard`를 추가했다.
- `backend/settings.py`: `resolve_source_revision`에서 `new_base`의 `git status --porcelain -z --untracked-files=normal`을 검사할 때 미추적 CLI 메타데이터(`.claude`, `.codex`, `.opencode`, `.omo`, `.bsp-dashboard`)는 미커밋 소스 변경에서 제외했다. 실제 수정 파일이나 일반 미추적 파일은 기존대로 거부한다.
- `apps/agent-monitor/delivery.py`, `.gitignore`: 소스 내보내기 제외 목록과 저장소 `.gitignore`에 `.omo`를 추가했다.

## 검증

원본 로그는 `.local-reports/20261119-omo-ignore/` 아래 로컬 전용으로 보관한다.

| 검증 | 결과 | 명령·근거 |
|---|---|---|
| `.omo` 제외·회귀 시험 (`test_native`, `test_orchestration_contracts`, `test_settings`, `test_new_job_tool_policy`) | PASS · 232개 · 종료1(Mac sandbox `killpg` 1건) | `.venv/bin/python -m pytest -q tests/test_native.py -k "not test_t100_worker_native_pipeline_retains_gates_and_cross_review" tests/test_orchestration_contracts.py tests/test_settings.py tests/test_new_job_tool_policy.py`; `pytest-3.log` |
| `main` 통합 회귀 시험 (`module_catalog`, `bsp_plugin_client`, `api`, `settings`, `orchestration_contracts`, `connector_test_status`, `connector_mirror_http`, `plugin_runtime`, `core`, `execution_timeouts`) | PASS · 330개 · 종료0 | `PATH=/usr/bin:/bin:/usr/sbin:/sbin .venv/bin/python -m pytest -q ...`; `pytest-combined-2.log` |
| 문서·링크/ID·공백 검사 | PASS | `docs/testing/validate_docs.py`, `git diff --check` |
| 실제 회사 Linux/OpenCode 실행 | NOT_RUN | 현지 환경에서 별도 확인 |
