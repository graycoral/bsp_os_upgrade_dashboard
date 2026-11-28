# PORT-013 · 직결 보드 커넥터 · 자율 실행 묶음 · 양방향 진단 · 직접 프록시

## 2026-11-28 · 경로 위임과 ADB TC

2026-11-29 원본 저장소의 `main`에 게시한 적용 기준은 [`1616809`](https://github.com/graycoral/bsp_os_upgrade_dashboard/commit/161680977a2e7d7a581550d7acb5c6bcbb6a84ed)이다. 회사 Windows·보드 적용과 인수는 대기 중이다.

기존 SSH 직결과 소스 스냅샷이 선행 조건이다. Windows 소스형 커넥터에는 `backend/gui_test/execution/{path_runs,connector_runs,host,source_snapshots}.py`, `backend/gui_test/core/discovery.py`, 웹·Qt Run 단계 표시를 함께 적용한다. Linux 전달 패키지의 `agent-monitor/backend/gui_test/standalone/{direct_connector_client,plugin_commands,plugin_parser}.py`와 공용 backend, `contracts/{plugin-cli-v1,connector-run-request-v1.schema,connector-path-run-v1.schema}.json`을 같은 버전으로 배포한다. Windows 프로필에 보드와 ADB 시리얼을 매핑한다. Windows 커넥터가 전송 전 ADB 연결과 셸 응답을 확인한다. UART로 ADB 모드를 켜는 명령은 운영 안내의 현장 재확인 표에서 관리한다. 후속 실패 증거 기능은 Windows 공용 backend에 `execution/failure_evidence.py`를 추가하고 Host와 Linux 참조 CLI를 함께 갱신한다. 유휴 Host를 중지해 SQLite를 백업한다. 시작할 때 DB v4가 `connector_failure_evidence`와 nullable `connector_runs.evidence_serials_json`을 자동 추가한다. 이전 TC에 커널 로그를 소급 수집하지 않는다. DB 복구 시 Host를 중지하고 보관한 이전 DB 복사본을 사용한다. [증거 조회와 검증](../testing/runs/20261128-failure-evidence.md) 이전 release와 프로필 백업으로 복구한다. 진행 중인 ADB Run은 해당 버전에서 종료 상태를 확인한 후 교체한다. [운영 절차](../gui_test/BOARD_CONNECTOR_EXECUTION.md#tc-루트-실행과-adb) · [모의 검증과 미실행 범위](../testing/runs/20261128-connector-path-run.md)

- **대상 결정·요구사항:** `D-83`, `RQ-77`~`RQ-81` (`T-291`~`T-305`)
- **원본 기준선:** `14e640247a9e17567bc03a8171bbee437b1060ed`
- **대상 코드 커밋:** `b71653b` (직결·자율 실행·양방향 진단 본체) + `85f7f05` (리뷰 `F-01`~`F-08` 수정·`run.sh` `--home` 분리·폴더 복사 전달·`watch_connection`; 후속 대시보드 작업 삭제/재실행·`Test 현황` 전체 TC 토글·회사 `8765` 격리는 [PORT-014](PORT-014.md) 참조)
- **상태:** `LOCAL_IMPLEMENTED_AND_REVIEWED` (Node 22+ `npm run build` 및 실장비 `T-305` 별도)
- **선행 조건:** [PORT-009](PORT-009.md), [PORT-011](PORT-011.md), [PORT-012](PORT-012.md)

## 2026-11-27 · Linux 공통 설정 출처와 빈 TC 경로 표시

선행 공통 설정 조회 `efe8847`, 적용 코드·시험 `72c4c2f37577ee53cfbede9b28faec237d6263d1`. Windows `board-connector.cmd` 기준 `backend/gui_test/connector/{linux_settings_probe,ssh_tunnel,shared_control,supervisor,shared_settings_ui}.py`, `backend/gui_test/connector/web_assets/host.mjs`, `packages/gui-test-ui/src/connector_web/view.mjs`를 함께 적용해 Manager를 다시 시작한다. Linux 직결 명령의 DB 경로와 설정 상태 출력은 플러그인 전달 폴더의 `agent-monitor/backend/gui_test/standalone/plugin_commands.py`를 갱신한다. 패키지 실행본은 재빌드한다. 기존 설정 DB와 프로필은 보존하고 이전 소스로 롤백할 수 있다. [REG-0137 재현 및 시험](../testing/runs/20261127-connector-restart-and-settings-source.md)

## 2026-11-27 · Agent Monitor 미실행 시 SSH 계정의 Linux 공통 설정 읽기

RQ-81 · T-302 · REG-0133. 선행 직결 수동 조회 `ce006b8f3016baa339e36dfa1fdbfe63846b4caf`, 고정 수정·시험 커밋 `efe8847a42a7fac35117826a860b6ba3c0864702`. Windows 소스형 커넥터의 `backend/gui_test/connector/`에 `linux_settings_probe.py`를 추가하고 `ssh_tunnel.py`와 `supervisor.py`를 교체한 뒤 해당 프로필의 Manager를 다시 시작한다. 회사 패키지 설치본은 같은 코드로 다시 패키징한다. Linux 런타임·DB 이전은 없다. 선행 Linux 플러그인의 설정 저장 형식(v1), SSH 원격 명령과 Linux의 curl·Python 3 표준 sqlite3를 사용한다. 기존 설치 home과 runtime을 보존한 채 이전 Windows 소스로 롤백할 수 있다. [회귀시험과 현지 확인 절차](../testing/runs/20261127-connector-recovery-and-offline-settings.md)

## 2026-11-27 · 연결한 Linux 서버의 TC 경로 자동 표시

기준 커밋 `48987bf2388157262e396a5b0e80f196bc886791`, 코드·시험 커밋 `a46947859a52a9cb1eaccf0779ea9a0458ca4603`. 선행 기능은 직결 Host, Linux 공통 설정 저장소, 8771 identity 확인이다.

| 적용 대상 | 적용할 상대 경로 |
|---|---|
| Windows 소스형 커넥터 | `backend/gui_test/connector/`의 `supervisor.py`, `ssh_tunnel.py`, `shared_control.py`, `web_actions.py`, `shared_settings_ui.py`, `gui.py`, `web_assets/host.mjs` 및 `backend/gui_test/core/connector_diagnostics.py` |
| Windows 웹 화면 | `packages/gui-test-ui/src/connector_web/view.mjs` |
| Linux 플러그인·Agent Monitor | `backend/gui_test/standalone/direct_connector_client.py`, `backend/gui_test/connector/direct_proxy.py`, `backend/gui_test/core/connector_diagnostics.py` |

Windows는 `board-connector.cmd`가 있는 폴더, Linux 플러그인 전달본은 `<플러그인 전달 폴더>/agent-monitor/`를 기준으로 위 상대 경로를 대조해 적용한다. 패키지 설치본은 기존 릴리스 절차로 재생성하고 양쪽 프로세스를 재시작한다. DB 이전은 없다. 복구 시 기존 설치본과 같은 데이터 디렉터리로 재시작한다. [회귀시험과 회사 확인 절차](../testing/runs/20261127-connector-linux-settings.md)

### ‘서버 공통 설정 불러오기’ 후속 수정

기준 `7f21176`, 수정 `cc671797ce1fb11b7c5bc1e1825f194a9ebf6370`. 위 Windows 소스 중 `backend/gui_test/connector/shared_control.py`, `supervisor.py`, `web_actions.py`를 함께 적용한 뒤 Manager를 다시 시작한다. 실행 중인 기존 Manager에 브라우저만 다시 접속하면 이전 코드가 계속 동작한다. Linux 측은 위 자동 표시 기능과 동일한 버전을 사용한다. DB 이전은 없다. [버튼 동작·재현·복구 확인](../testing/runs/20261127-connector-linux-settings.md#수동-불러오기)

## 주 SSH 시작 전 현재 Host의 identity가 이미 응답한 경우

프로필의 이전 주 SSH와 수동 터널을 구분하는 안내, 강제 종료 후 서버 포트 확인은 [PORT-009 후속](PORT-009.md#2026-11-27--재시작-전-ssh-소유권과-강제-종료-후-포트-확인) 네 파일을 함께 적용한다. [운영 절차](../gui_test/FORCE_STOP.md)

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
