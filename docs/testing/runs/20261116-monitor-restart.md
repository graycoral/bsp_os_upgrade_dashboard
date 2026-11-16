# 갱신 후 이전 API 재사용과 명시적 restart

RQ-68 / T-254 / REG-0101. 코드·시험 기준은 `0c98758e96315e376115b5ea58a8ca4ac6eae79c`, 이전 기준은 `a35bcdc078b8e2c64f269b86001c23b0ef792362`다.

## 확인과 변경

사용자는 환경 점검에서 Codex 로그인 안내가 새로 나온다고 확인했다. 현재 native 어댑터에는 해당 안내·Codex 실행 경로가 없다. start는 서비스가 실행 중이면 prepare 전에 기존 상태를 반환한다. 소스 갱신 후에도 기존 설치본을 재사용하는 경로를 시험으로 확인했다. 회사의 실제 프로세스·설치 버전은 직접 확인하지 않았다.

`run.sh restart`와 `manage.py restart`를 추가했다. Git 소스는 지정 source의 UI를 먼저 빌드하고, 배포 manifest가 있는 복사본은 포함된 UI를 사용한다. 새 환경 준비를 마친 뒤 기존 supervisor에 종료를 요청하고 종료 확인 후 준비한 release를 활성화·시작한다. 일반 start는 기존 설치본 재사용과 갱신 명령을 stderr로 안내한다.

포트 생략 시 저장된 서비스 포트를 사용한다. 설정·시험 기록은 기존 runtime을 사용한다. UI/설치 실패는 기존 서비스를 유지한다. 종료 보류는 RESTART_BLOCKED, 45초 내 종료 미확인은 RESTART_PENDING이다. 새 release 활성화가 보류되면 오류를 반환한다. 기존 작업·예약·프로세스 종료 판정을 유지한다.

## 검증

별도 checkout에 이번 코드·시험 4개 파일만 복사했다. GUI Test 제한시간/Mock 관련 7개 WIP 파일을 제외했다. macOS / Python 3.11.7에서 설치·재시작 호출은 모의 프로세스로 검사했고 기존 reset의 로컬 HTTP 시험도 함께 실행했다.

```bash
PATH="/usr/bin:/bin:$PATH" .venv/bin/python -m pytest -q tests/test_agent_monitor_manager.py tests/test_agent_monitor_lifecycle.py tests/test_agent_monitor_recovery.py tests/test_agent_monitor_reset_live.py tests/test_agent_monitor_delivery.py tests/test_build_entrypoint.py
bash -n run.sh
./run.sh restart --help
.venv/bin/python docs/testing/validate_docs.py
```

- Python 회귀는 201 PASS / 5 SKIP, exit 0이다.
- 셸 구문과 CLI help는 PASS, exit 0이다.
- 설치 전 UI 빌드 순서, 다른 source 경로, 복사본 UI 재사용, 준비 실패 시 기존 서비스 보존, 종료 거부/시간 초과, 후보 release 적용 보류, 포트 유지와 root launcher 인자 전달을 확인했다.
- 첫 확장 명령은 없는 시험 파일을 지정해 수집 단계에서 종료했다. 다음 실행의 4개 실패는 새 restart 시험에서 임시 source를 지정하지 않아 발생했다. 시험 입력을 수정하고 전체를 다시 실행했다. 원본 로그는 보존했다.

전체 로그는 `.local-reports/20261116-monitor-restart/`의 `tests-first.log`, `tests-isolated.log`, `tests-isolated-v2.log`, `tests-final.log`, `launcher-help.log`, `docs-check.log`에 로컬 보관한다. Git에는 요약만 포함한다. 실제 회사 Linux 서비스 갱신과 Claude/OpenCode 모델 호출·장비 시험은 NOT_RUN이다.

## 회사 전달

Agent Monitor는 [PORT-007](../../porting/PORT-007.md#2026-11-16--설치본-갱신과-재시작)의 파일·절차를 적용한다. 플러그인은 [최신 요청서](../../agents/BSP_UPGRADE_PLUGIN_REQUEST.md)의 이번 절에 따라 복사본 관리자와 갱신 호출을 반영한다. 사용자 실행 명령은 [스크립트 안내](../../../scripts/README.md#갱신-후-재시작)에 있다.
