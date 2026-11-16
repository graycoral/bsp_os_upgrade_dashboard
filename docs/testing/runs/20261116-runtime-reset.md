# 설정 유지 일괄 초기화

RQ-68 / T-254. 기준 `cc19559f204dfdee0547c20b34d5701191c28669`에 사용자 요청한 일괄 초기화를 추가했다. 사용자는 환경·연결 설정을 유지하고 세션·시험 기록·예약을 초기화하며 실행 전 자동 백업을 남기는 범위를 선택했다.

## 변경

`bash run.sh reset`이 기존 관리자의 reset_runtime을 호출한다. 설치/시작·서비스·Worker/GUI Test 잠금과 실행 종료 근거를 확인하고, SQLite WAL을 포함한 runtime 백업을 생성한 뒤 실행 DB 기록을 비운다. 환경·연결 설정, 저장된 TC 선택/명령/시간 설정, TC 소스와 runtime 파일은 유지한다. 세부 테이블 범위는 [사용 안내](../../agents/PLUGIN_CONTROL_API.md#설정을-유지하는-일괄-초기화)를 따른다.

서비스 실행 중에는 기존 안전 stop을 요청한다. 작업으로 서비스 종료가 보류되면 해당 사유를 반환한다. 종료된 서비스의 검증된 PAUSED 예약을 처리하며 UNKNOWN·실행 중/종료 불명 시도·분석 lease·미해제 플래싱 batch·미지원 DB를 거부한다.

DB별 transaction과 runtime-reset.json을 사용한다. 중간 실패는 RESET_PENDING이며 start/install/serve에서 재시도를 안내한다. 같은 명령을 다시 실행하면 원래 백업의 해시를 확인하고 남은 처리를 완료한다. 설정 보존과 반복 실행은 동일 경로에서 검증한다. 초기화가 서비스 시작을 수행하지 않으므로 실행은 기존 run.sh 명령을 사용한다.

## 검증

원본 로그와 파일별 manifest는 `.local-reports/20261116-runtime-reset/`에 로컬 전용으로 보관한다. main 기준의 격리 checkout에 이번 코드/시험 5개만 적용했다. 별도 GUI Test 작업 파일 7개는 포함하지 않았다.

| 시험 | 결과 | 로그 |
|---|---|---|
| 초기 manager/recovery/lifecycle | 113 PASS | initial-tests.log |
| 확장 회귀 | 257 PASS / 8 SKIP | final-tests.log |
| 안내 문구 반영 후 관리 진입점 재시험 | 115 PASS | entrypoint-retest.log |
| 게시 코드 전체 재시험 | 257 PASS / 8 SKIP | published-source-tests.log, 18.78초 |
| root Bash 구문·diff 공백 검사 | PASS | bash -n / git diff --check, exit 0 |

확장 명령은 아래와 같다.

```bash
python -m pytest tests/test_agent_monitor_manager.py tests/test_agent_monitor_recovery.py tests/test_agent_monitor_lifecycle.py tests/test_agent_monitor_delivery.py tests/test_setup_runtime.py backend/gui_test/tests/test_core.py backend/gui_test/tests/test_plugin_integration_recovery.py backend/gui_test/tests/test_session_deletion.py -q -rs
```

대상에는 실제 root reset 진입의 임시 DB 시험, 설정·등록 보존, paused 예약 2개 제거와 원본 백업, 백업/다중 DB/완료 receipt 실패 후 재시도, 초기화 중 start/serve 거부, 백업 변경 거부, Worker 잠금·종료 불명·분석·미해제 플래싱 거부가 포함된다. subprocess는 임시 runtime을 사용하고 실제 회사 서비스·TC·보드에 연결하지 않았다.

SKIP 8개는 UI 빌드 자산을 요구하는 복사 인수 1개와 Windows DPAPI/PowerShell/CMD 7개다. Starlette TestClient의 httpx deprecation warning 1건이 있었다.

코드 manifest SHA-256 `a2af5103833d4dd503815366172cabea80e8f38cb79dd4aa7acb92643cc2dc8e`. 시험 manifest SHA-256 `db763a697303fb81aeef6dd35690a0ef043d24c09dce1d7c3d3936aa34aba7b2`.

## 적용과 남은 검증

[플러그인 요청문](../../agents/BSP_UPGRADE_PLUGIN_REQUEST.md)과 [PORT-007](../../porting/PORT-007.md)에 복사 대상·CLI 결과·백업/재시도 조건을 기재했다. DB schema 변경은 없다. 회사 Linux 실제 데이터 초기화·서비스 종료 및 Windows 연동은 NOT_RUN이다. Windows 커넥터 DB와 외부 TC/이미지 저장소의 초기화는 이번 Linux runtime 명령의 대상에 포함하지 않았다.

코드·시험 고정 커밋은 `226c3f2db3d67e374d5b303b168b4248a1177ea1`다. 문서 상대 링크 1732개 검사 PASS를 확인했다.
