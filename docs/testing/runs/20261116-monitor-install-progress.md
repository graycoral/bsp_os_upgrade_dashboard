# Agent Monitor 설치 대기 표시

RQ-68 / T-254 / REG-0096. 기준 `8ae756bc23b5f262233f59549f650c913bb43266`에 관리자의 설치 진행 안내와 회귀 시험을 적용했다.

## 보고·원인

사용자가 `run.sh --port 8765` 실행 중 화면 무출력과 Ctrl+C 후 manage.py 121행의 subprocess.run 대기를 보고했다. 해당 호출은 requirements.lock의 pip install이며 stdout/stderr를 install.log로만 보내고 있었다. 회사 상세 로그는 외부 공유가 제한된다. 네트워크·사내 패키지 저장소의 실제 대기 원인은 미확정이다.

## 수정과 적용

소스·기존 환경 확인을 알리고 가상환경 준비와 Python 패키지 설치를 단계별로 표시한다. 두 설치 명령은 시작·로그 경로·10초 간격 경과 시간·완료·실패 종료 코드·중단을 stderr로 알린다. 상세 출력은 설치 home의 install.log에 저장한다. 명령 결과는 stdout JSON으로 반환한다.

Agent Monitor 담당자는 `apps/agent-monitor/manage.py`, `tests/test_agent_monitor_manager.py`를 적용한다. 플러그인 담당자는 복사형 배포본에 해당 관리자를 포함하고 stderr를 설치 진행 화면에 연결한다. 회사 설치 로그는 현지에서 확인한다. DB 변경은 없다. `--port`는 일반 하이픈 두 개로 입력한다. 단계 안내까지 도달했다면 옵션 파싱은 통과한 상태다.

## 검증

전체 로그는 `.local-reports/20261116-monitor-install-progress/`의 로컬 전용 자료다.

| 실행 | 결과 | 로그 |
|---|---|---|
| 기존 main에서 `test_t254_preparation_reports_stages_and_keeps_stdout_clean` | 예상 1 FAIL | `before-fix.log` |
| manager/lifecycle/recovery/delivery 최초 회귀 | 81 PASS | `tests.log` |
| 격리 checkout에서 manager/lifecycle/recovery/delivery/setup_runtime 회귀 | 129 PASS / 8 플랫폼 SKIP | `final-tests.log` |

최종 명령은 `python -m pytest tests/test_agent_monitor_manager.py tests/test_agent_monitor_lifecycle.py tests/test_agent_monitor_recovery.py tests/test_agent_monitor_delivery.py tests/test_setup_runtime.py -q`다. 조용한 10초 자식 프로세스로 대기 안내를 확인했다. 실패 출력의 로컬 보관·화면 비노출, 실제 SIGINT 전달 후 자식 종료와 설치 잠금 해제, 기존 release/runtime 데이터 보존을 확인했다. 원본 main 격리 checkout에 이번 코드·시험만 복사해 검증했다.

코드 SHA-256 `766a85abfa28820d0762d9829c41c383d767d062ee3b4f95d6bcf88d251e0cc6`. 시험 SHA-256 `9c1c63f205e3e765b0a510696d9b82b5396f7467be1fa9fa463c600cc2dc87ac`. 회사 Linux의 실제 패키지 다운로드·설치 완료와 Windows 전용 경로는 NOT_RUN이다.

수정 코드·시험 커밋은 `0824070078b77f5d8eba9e4a556dce5238b55f2f`다. 문서 검사 1691개 링크 PASS, `git diff --check` PASS를 확인했다.
