# 실행 중 일시정지 세션의 초기화

RQ-68 / T-254 / REG-0099. 기준 `625c6ce81d7cf7062de9c18a8ac81f65f6f36865`.

## 재현과 원인

회사에서 `bash run.sh reset`을 실행하면 진행·대기·일시정지·종료 불명 작업이 남았다는 오류가 발생했다. 기존 reset은 일반 stop을 먼저 요청했다. 일반 stop의 has_work는 PAUSED 예약을 미완료 작업으로 판단했다. 기존 257 PASS는 해당 보류를 수용하는 시험을 포함했고, 실행 중 서비스에서 초기화가 완료되는 경로를 확인하지 않았다.

기존 코드에 새 회귀 시험을 적용해 같은 RuntimeError를 재현했다. 시험은 실제 loopback HTTP API·실제 SQLite 기록·기존 supervisor 루프를 사용하며 API/Worker 자식 프로세스와 보드 실행은 시험용 객체로 대체한다. 회사 서비스나 장비에는 연결하지 않는다.

## 수정

실행 중 reset은 저장된 서비스 instance/release/runtime을 health와 비교한다. 종료 근거가 확인된 세션을 대상으로 취소 전 백업을 만들고 기존 live/legacy API에 CAS 취소를 요청한다. 취소와 이미지 설치 예약 해제를 확인한 뒤 기존 stop으로 API/Worker를 종료한다. 종료 후 Worker 잠금과 runtime 상태를 다시 확인하고 DB를 비운다.

live/legacy 경로가 같은 DB를 공유할 수 있으므로 live 경로를 먼저 처리하고 취소한 Run을 중복 처리하지 않는다. 기존 기본 화면이 생성하는 demo-dashboard.db도 지원한다. 완료된 취소의 cancel_requested/pending_terminal_state 기록은 검증된 종료·예약 해제 근거와 함께 해석한다. 초기 이관의 PAUSED 전용 예약 조건은 기존 범위로 유지하고, reset은 소유권과 종료 근거가 확인된 QUEUED 예약도 처리한다.

RESET_DRAINING은 취소·종료 대기, RESET_PENDING은 DB 초기화 단계다. 원래 백업은 두 단계와 재시도 전체에서 유지된다. 취소 API 응답 유실, 백업 변경, 소유 서비스 불일치, 검사 후 세션 실행 시작을 별도로 검증한다. DB schema 변경은 없다. 실행 중 백업은 DB별 확정 시점을 기준으로 생성한다.

## 시험 결과

원본 로그와 manifest는 `.local-reports/20261116-reset-live/`에 로컬 전용으로 보관한다. 최종 시험은 main 기준 격리 checkout에 변경 코드·시험 4개만 적용했다. 별도 GUI Test WIP 7개는 검증/게시 범위에서 제외했다.

| 실행 | 결과 | 근거 |
|---|---|---|
| 기존 main과 PAUSED HTTP 회귀 | 예상 1 FAIL | before-fix-retest.log, 회사 오류 문장 재현 |
| 첫 HTTP 연결 시험 | 3 FAIL | live-initial.log, 기본 생성 demo-dashboard.db 누락 확인 |
| DB 지원 후 HTTP 재시험 | 1 PASS / 2 FAIL | live-retest.log, QUEUED 예약과 취소 완료 metadata 확인 |
| 관리 코드와 HTTP 회귀 | 118 PASS | combined-tests.log |
| 이미지 설치 예약 최종화 포함 | 4 PASS | live-batch-tests.log |
| 공유 DB 라우터 포함 | 7 PASS / 1 FAIL | configured-live-tests.log, 같은 Run의 최종화 중 중복 취소 검사 발견 |
| 초기 확장 회귀 | 264 PASS / 8 SKIP | final-tests.log |
| 중복 처리 보완 후 최종 격리 회귀 | 268 PASS / 8 SKIP | final-retest.log, 24.09초 |

최초 baseline 실행의 시험 API 재시작 socket 정리 warning은 before-fix.log에 보존했다. 시험 socket 재사용을 수정한 before-fix-retest.log에서 warning 없이 같은 제품 오류를 재현했다.

최종 명령은 아래와 같다.

```bash
python -m pytest tests/test_agent_monitor_reset_live.py tests/test_agent_monitor_manager.py tests/test_agent_monitor_recovery.py tests/test_agent_monitor_lifecycle.py tests/test_agent_monitor_delivery.py tests/test_setup_runtime.py backend/gui_test/tests/test_core.py backend/gui_test/tests/test_plugin_integration_recovery.py backend/gui_test/tests/test_session_deletion.py -q -rs
```

HTTP 완료 경로 8개는 PAUSED 일반 TC, QUEUED TC, 통합 TC, 이미지 설치 예약의 네 상태와 기본/공유 DB 구성을 조합했다. 각 시험은 백업 원본의 PAUSED/QUEUED와 예약 2개, 현재 DB의 초기화, supervisor 종료 및 단일 백업을 확인한다. 이미지 설치 예약은 실제 최종화 함수를 사용하고 Windows 해제 응답을 모의한다.

SKIP 8개는 UI 빌드 자산을 요구하는 복사 인수 1개와 Windows DPAPI/PowerShell/CMD 7개다. 최종 Starlette TestClient httpx deprecation warning 1건이 있었다.

코드 manifest SHA-256 `c2e7fc4e22c3b0f53d1604a2971e11668c60e945de4fa2f8356333607c1fb601`. 시험 manifest SHA-256 `f7289ae9aae0c6dd639e23480165d51fafc8ad4c35139dfa27579f905682a0f6`.

## 회사 전달

[플러그인 요청문](../../agents/BSP_UPGRADE_PLUGIN_REQUEST.md), [PORT-007](../../porting/PORT-007.md), [현재 초기화 절차](../../agents/PLUGIN_CONTROL_API.md#설정을-유지하는-일괄-초기화)를 함께 전달한다. 회사에서는 최신 코드를 받은 후 같은 reset 명령을 사용한다. 기존 실행 중 관리자에는 이미 제공된 API/stop 계약으로 연결한다. 새 전용 endpoint 배포가 선행 조건인 구조는 도입하지 않았다.

실제 회사 Linux·Windows 커넥터·보드 인수는 NOT_RUN이다. 실행 중 TC/분석, 종료 불명, 소유권 불일치와 별도 미완료 BSP 작업은 기존 실행 근거와 종료 절차에 따라 처리한다.

수정 코드·시험 고정 커밋은 `17c6c6a2b1895a7f006a1ff7c2caf52b838e9bcf`다. 문서 상대 링크 1746개 검사와 git diff --check는 PASS다.

후속 회사 보고에서 같은 종료 오류가 이어졌다. 정상 생성한 미완료 BSP 작업을 함께 두면 직전 게시 코드에서 재현된다. REG-0099 시험은 TC/예약 완료 경로를 다뤘고 이 조합을 포함하지 않았다. [REG-0100 보완](20261116-reset-bsp.md)을 따른다.
