# PORT-013 · 직결 보드 커넥터 · 자율 실행 묶음 · 양방향 진단 · 직접 프록시

- **대상 결정·요구사항:** `D-83`, `RQ-77`~`RQ-81` (`T-291`~`T-305`)
- **원본 기준선:** `14e640247a9e17567bc03a8171bbee437b1060ed`
- **대상 코드 커밋:** `b71653b` (직결·자율 실행·양방향 진단 본체) + `85f7f05` (리뷰 `F-01`~`F-08` 수정·`run.sh` `--home` 분리·폴더 복사 전달·`watch_connection`; 후속 대시보드 작업 삭제/재실행·`Test 현황` 전체 TC 토글·회사 `8765` 격리는 [PORT-014](PORT-014.md) 참조)
- **상태:** `LOCAL_IMPLEMENTED_AND_REVIEWED` (Node 22+ `npm run build` 및 실장비 `T-305` 별도)
- **선행 조건:** [PORT-009](PORT-009.md), [PORT-011](PORT-011.md), [PORT-012](PORT-012.md)

## 2026-11-27 · 8771 응답과 Manager 연결 상태 일치

- 원본 기준 `03e4ac39d44657554c0eb966984542477b6dd9d5`, identity 수정 `a39b008`, 60초 타임아웃 제품 커밋 `57979a1be32ea3676f8e26613f6f8b1bceecdc5c`, 회사 증상 재현 시험 커밋 `67c5a79e5762043545c8aa2b2b2a4fff7e4b3ed9`. 선행 기능은 PORT-013의 direct-connector-v1 Host, 실행 기록, Linux 직결 진단이다.
- 제품 변경은 [ssh_tunnel.py](../../backend/gui_test/connector/ssh_tunnel.py) 한 파일이다. 회사 플러그인의 소스 전달 경로는 `<플러그인 전달 폴더>/agent-monitor/backend/gui_test/connector/ssh_tunnel.py`, Windows 실행 소스에서는 `<board-connector.cmd 폴더>/backend/gui_test/connector/ssh_tunnel.py`다. 회사 변경분을 대조해 적용하고 서명된 폴더는 기존 릴리스 절차로 다시 생성한다. 현재 배포본 `7691c0e` 이후의 별도 소스 수정이다.
- Linux SSH 서버에서 해당 계정으로 비대화식 `curl`을 실행하면 설정 포트의 identity를 직접 검증한다. 원격 명령이 제한되면 같은 서버의 플러그인 연결 진단이 보낸 새 `peer/hello`를 활용한다. 이 경우 Windows에서 설정한 서버와 Linux가 보고한 호스트의 이름 또는 해석 주소가 일치해야 한다. 양쪽 증거가 없으면 주 터널을 유지하고 확인 대기를 표시한다.
- 회사 확인은 같은 home·포트·계정으로 Manager를 다시 시작한 뒤 Linux identity의 `runner_id`와 Windows 연결 진단을 대조한다. identity 확인용 단발 SSH 명령의 기본 타임아웃은 60초이며, 정상 응답을 받으면 즉시 판정을 진행한다. 최소 65초 동안 주 SSH PID와 `connected_since`가 유지되고 보드 목록이 조회되는지 기록한다. 적용 전부터 같은 identity가 응답하면 이전 터널 소유자를 먼저 확인한다.
- DB 이전은 없다. 복구는 설치 경로의 이전 소스 또는 서명 릴리스를 복원하고 동일 home의 Manager를 다시 시작한다. 재현·시험 명령과 다른 경로에서 발견한 결함은 [검증 기록](../testing/runs/20261127-ssh-identity-probe.md)에 있다. 회사 Windows OpenSSH 인수 T-305는 NOT_RUN이다.

## 퓨징 설정 수동 입력과 플러그인 기본값

후속 RQ-83의 복사 경로·회사 플러그인 매핑·검증·복구는 [PORT-016](PORT-016.md)을 따른다.

## 1. 이식 범위 및 핵심 변경 위치

| 영역 | 주요 파일 | 회사 적용 시 조정/확인 포인트 |
|---|---|---|
| **공통 설정 분리 · 복구 호환** | `backend/gui_test/core/shared_settings_store.py`, `timeouts.py`, `shared_settings.py`, `core/retention.py`, `api/storage.py`, `runtime.py`, `apps/agent-monitor/recovery.py` | 회사 runtime의 `runs.db`/`gui-test-settings.json`에서 1회 자동 이관 확인; **`recovery.py` `RESET_TABLES['connector-registry.db']`에 `'direct_cache'`와 `'shared-settings.db'`를 반드시 함께 반영** (기존 4개 테이블만 고정 시 `reset`이 `RESET_BLOCKED`로 실패) |
| **양방향 진단 · bootstrap-v2** | `backend/gui_test/core/connector_diagnostics.py`, `core/connector_bootstrap.py`, `connector/bootstrap.py`, `connector/shared_control.py`, `apps/agent-monitor/plugin_delivery.py` | Linux `/proc/net/tcp{,6}`·`uid=0` `sshd` 구분 및 `bootstrap-v2` 적용 |
| **Windows SSH -R 수명 분리 · 브리지** | `backend/gui_test/connector/ssh_tunnel.py`, `connector/supervisor.py`, `connector/emergency.py`, `execution/launch.py`, `scripts/setup_runtime.py` | Linux 설정 포트 identity·`icacls` 키 ACL·DPAPI `manager-bridge` 동작 확인 |
| **자율 실행 묶음 · 실패 분석 래치** | `backend/gui_test/execution/connector_runs.py`, `execution/host.py`, `execution/batches.py`, `execution/retention.py`, `execution/session_deletion.py`, `connector/console.py` | `executions.db` v2 스키마 자동 마이그레이션, `D-48` `/v1/flash-tests`와 `Host.lock` 배타 유지 확인 |
| **플러그인 독립 클라이언트 · 전달** | `backend/gui_test/standalone/direct_connector_client.py` (`watch_connection` 포함), `standalone/plugin_commands.py` (`connect --watch`), `apps/agent-monitor/plugin.py`, `apps/agent-monitor/plugin_delivery.py` (`windows_directory`, ZIP 제거), `apps/agent-monitor/manage.py` (`prepare-env`), `run.sh` (`--home` 체크아웃별 분리) | 회사 플러그인 Git의 `/bsp-upgrade` 진입점과 `--connector-port` vs `--port` 옵션 연결; `connect --watch`로 `127.0.0.1:8771` 주기 감시; 보드 커넥터는 `<플러그인-전달>/agent-monitor/` 폴더 전체 복사(ZIP 미사용); 회사 대시보드 `run.sh`도 `--home` 분리 정렬 |
| **Agent Monitor 직접 프록시 · UI** | `backend/gui_test/connector/direct_proxy.py`, `connector/registry.py`, `connector/api.py`, `backend/api/main.py`, `standalone/integration.py`, `scripts/serve_monitor.py`, `packages/gui-test-ui/src/ConnectorMirror.tsx`, `SharedControl.tsx`, `apps/web/src/main.tsx`, `packages/gui-test-ui/src/connector_web/view.mjs`, `style.css`, `connector/web_actions.py`, `connector/preview.py`, `connector/gui.py` | 원본 전달 담당자는 두 UI를 빌드하고 자산을 검증한다. 회사가 UI 소스를 수정하거나 자체 빌드하면 Node 22+ 환경에서 `bash scripts/build-ui.sh`로 다시 빌드한다. 배포 시 [PORT-011의 폴더 절차](PORT-011.md#현재-유효-기준)를 따른다. |

## 2. 보존해야 하는 정책

- `D-48` `/v1/flash-tests` 수동 기본 원칙·자동 프로파일 파이프라인·사람 최종 검토.
- `D-77` `--force-stop`, `D-78` 모델 단계 정책, `D-81` 웹 커넥터 좌우 분할, `D-82` 모듈 콤보박스·시작 내부 검사.
- `FLASHING` 중 `taskkill /T /F` 금지, 원격 `-R` 포트 임의 폴백 금지, `StrictHostKeyChecking=no` 금지, 분석 래치 활성 중 수동 `resume` 차단(`409 ANALYSIS_LATCH_ACTIVE`).

## 3. 회사 검증 및 미완료 항목

- 직결 본체의 당시 로컬 Python 루프백/모의 427 + 212 PASS (`tests/test_direct_connector_unit*.py` 포함). 해당 실행의 Hydrogen 독립 검토는 NOT_REVIEWED이며, 위 상태는 후속 `85f7f05`의 F-01~F-08 검토 반영을 포함한다. [본체 실행 기록](../testing/runs/20261119-direct-connector-implementation.md).
- **회사 전달 전 필수:** (1) Node 22+ 환경에서 공급자 UI 빌드(`npm run build`) 및 전달본 자산 검증, (2) 별도 독립 리뷰 세션 완료, (3) `T-305`(`DCA-15`) 실물 Windows OpenSSH·COM·PuTTY·`fastboot`·Linux `sshd` 인수.
