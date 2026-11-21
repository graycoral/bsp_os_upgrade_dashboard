# 회사 복사본 스모크 시험

| 필드 | 내용 |
|---|---|
| source_repo/source_commit | graycoral/bsp_os_upgrade_dashboard · 전달본의 `agent-monitor/AGENT_MONITOR_SOURCE.json` `source_head` |
| target_repo/target_commit | 회사 담당자가 현행 Git SHA와 사전 부분 적용 상태를 기록 |
| scope | 폴더 복사, 기존 단일 서비스 설정, 독립/통합 UI, Windows 커넥터 사전 검사 |
| changes | 회사 접점 목록은 아래 표 참조. 공통 실행 DB schema 변경 없음 |
| package_release | `PLUGIN_PACKAGE.json`과 `AGENT_MONITOR_SOURCE.json`의 동일 release |
| evidence | 회사 시험 NOT_RUN. 적용 담당자가 각 행의 명령, 결과, 로그 위치, SHA와 release를 현지 기록 |
| open_questions | 회사 wheel 공급원과 서비스 소유자, 회사 API 인증·포트, Windows 실제 실행 환경 |
| next_task | 04 회사 구조·적용 현황 대조 후 승인 범위의 05 스모크 |

## 1. 설치 없이 확인

1. 승인 경로로 전달 폴더 전체를 복사한다. 전달자가 별도 채널로 제공한 두 manifest의 SHA-256을 실제 파일과 비교한다. Linux에서는 `sha256sum PLUGIN_PACKAGE.json agent-monitor/AGENT_MONITOR_SOURCE.json`, Windows에서는 `Get-FileHash -Algorithm SHA256`을 사용한다. inner의 `source_dirty=false`, 원본 SHA, `include_ui=true`, 양쪽 release, outer Windows descriptor의 release를 확인한다. 추가 파일을 담는 회사 문서·환경·런타임은 전달 폴더 밖에 둔다.
2. `python3 -I "$PACKAGE/plugin.py" help`와 `python3 -I "$PACKAGE/plugin.py" verify "$PACKAGE" --pristine`를 실행한다. 예상 결과는 도움말과 같은 release의 `VERIFIED`다. 이 두 명령에는 Python 표준 라이브러리만 필요하다. Python 3.11~3.13, 가상환경 생성, SQLite, 승인된 Linux wheel 공급 경로를 확인한다. 새 복제 환경에 `PIP_NO_INDEX=1 PIP_FIND_LINKS="$WHEELHOUSE" python -m pip install -r "$PACKAGE/agent-monitor/requirements.lock"` 및 `python -m pip check`를 실행한다. 대상 아키텍처 및 Python ABI별 wheel 준비가 필요하다. 일반 재검증은 동봉한 Python 파일에 대응하는 표준 bytecode 캐시를 허용한다. 인수 시 `--pristine`은 그 캐시도 검사 대상에 넣는다. 사전 빌드 UI만 제공할 때 수신자 환경의 Node/npm 설치를 생략한다.
3. 아래 네 값과 서비스 실제 리스너를 확인한다. `ss -ltnp`와 Windows `Get-NetTCPConnection -State Listen`으로 해당 포트의 소유자를 확인한다. Linux Worker와 Windows Manager/Host는 각각 기존 한 소유자로 유지한다. 테스트에 독립 home/runtime/connector state와 독립 포트를 배정한다.

| 옵션 | 확인할 위치와 예상 결과 |
|---|---|
| `--home` | Linux 설치본과 current/service receipt, 플러그인 상태의 지속 경로 |
| `--runtime` | 설정·실행 DB 경로의 절대 경로. 기존 home에 연결된 `runtime-location.json`과 일치 |
| `--port` / `--monitor-port` | Linux Agent Monitor HTTP. 회사 운영 예시 8765, 제품 예시 8766. 현지 설정을 우선 |
| `--connector-port` | Linux에서 접근하는 별도의 direct connector 포트. 제품 예시 8771. Windows SSH-R의 `remote_runner_port`와 일치 |
| `--project` / `--state-dir` | 회사 프로젝트 식별자와 기존 플러그인 상태 경로. 같은 논리 프로젝트에 새 상태 저장소를 임의로 추가하지 않음 |

## 2. 서비스·API·UI

| 항목 | 절차와 예상 결과 |
|---|---|
| 사전 상태 | 기존 소유가 확인된 home에서 `python3 -I "$PACKAGE/plugin.py" --home "$MONITOR_HOME" --runtime "$MONITOR_RUNTIME" monitor status`. 이 조회는 서비스를 시작하지 않는다. 구버전이 실행 중이면 `state=READY`와 `deployment.state=UPDATE_REQUIRED`가 함께 나타날 수 있다. `UNVERIFIED`이면 current/receipt와 API 소스를 확인한다. `NOT_INSTALLED`이면 회사의 기존 별도 서비스 소유 여부를 확인한다. |
| 버전 전환 | 소유자 승인 전 [롤백 절차](ROLLBACK.md)의 백업·게이트를 확인한다. 회사 서비스 관리자가 지정된 절차를 적용한 뒤 위 조회의 `deployment.state=MATCHED`를 확인한다. package/installed/running release가 같고 `installed_path=running_path`여야 한다. `service.json`의 owner/API/Worker PID와 시작 식별자를 실제 프로세스 명령 및 작업 디렉터리와 대조한다. |
| API | 사용할 인증/프로필로 GET `/api/v1/health`, `/api/v1/config/modules`, `/api/v1/gui-test/live/integration/settings`를 조회한다. health의 `managed_release`, `managed_runtime`, `managed_source`와 현재 설치가 일치한다. 모듈 목록과 설정 revision은 기존 DB에서 읽힌다. 회사 Auth/SSO·scope·same-origin·prefix와 로그인되지 않은 접근 거부를 두 역할로 검증한다. 설정 값과 토큰 전문은 시험 증거에 남기지 않는다. |
| 설정 | 독립 runtime에서 `settings export --file NEW_FILE`을 실행하고 `expected_revision`을 기록한다. 승인된 fixture 항목 하나를 편집하여 `settings import --file PATH`를 실행한다. UI 새로고침 후 새 revision과 변경 값이 나타난다. 동일 파일 재가져오기는 `SETTINGS_CHANGED`이며 편집 파일 바이트와 기존 DB가 유지된다. `settings file sync/push`는 직결에서 거부된다. 현재 회사 hook이 기존 파일 bridge를 사용하면 HTTP 세션의 별도 CAS 계약으로 시험한다. |
| UI | 대시보드와 GUI Test의 `index.html`과 JS/CSS를 요청해 HTTP 200·manifest byte hash를 확인한다. GUI Test 독립 검사는 복사본 소스를 실행 경로로 두고 `python -B -m backend.gui_test.standalone.server --runtime "$SMOKE_RUNTIME" --port "$SMOKE_PORT" --static-dir "$PACKAGE/agent-monitor/apps/gui-test/static"`을 사용한다. 브라우저에서 OS 업그레이드 대시보드, Test 현황 및 보드 커넥터 탭, 독립 GUI Test 화면의 렌더링과 설정/목록 조회를 확인한다. company 운영 runtime에서 fixture 작업을 생성하지 않는다. |
| 단일 소유·격리 | 관리 중인 홈·포트·runtime이 디스크의 receipt 및 프로세스와 동일한지 확인한다. 별도 시험 home의 상태를 조회해 기존 서비스에 종료 요청이나 DB 변경이 없음을 확인한다. 저장된 일시정지·예약·UNKNOWN에는 기존 복구 절차를 적용한다. |

## 3. Windows

- `agent-monitor/` 복사본의 `board-connector.bat`, `board-connector.cmd`, `scripts/board_connector.py`, 두 Windows lock, `connector/web_assets/index.html`·`host.mjs`, 공용 `view.mjs`·`style.css`와 TC 상태 모듈을 검증한다. Bootstrap 디렉터리는 해당 descriptor와 `start-board-connector.bat`를 사용하며 생성하는 연결 정보가 회사 로컬에만 있도록 확인한다.
- Windows Python 3.11~3.13 x64, 선택 UI별 lock/wheel, OpenSSH, COM, PuTTY, fastboot 가용성 및 release별 실행 경로를 점검한다. 실제 연결 전 기존 Manager/Host의 시작 PID, 인자, 데이터 home, 진행 중 작업과 예약/UNKNOWN을 확인한다.
- 승인된 Windows 스모크에서 올바른 번호와 runner identity, `Test 현황` 목록, 기존 설정과 RX 기록의 보존을 관찰한다. SSH-R, COM/PuTTY/fastboot 실물 확인 및 T-305는 실험실 권한을 따로 기록한다.

## 회사 Host Adapter 위치

| 회사가 조정할 접점 | 공통 코드 진입점 |
|---|---|
| slash 등록·활성화/알림, 프로젝트·home·runtime·포트, 단일 서비스 소유자 | `plugin.py` direct CLI 또는 기존 `PluginSession.start_watch()`/HTTP adapter, `manage.py status` |
| 모듈 목록 게시자·정책 및 version 연결 | `backend/gui_test/standalone/bsp_plugin_client.py`의 모듈 게시와 expected version. 회사 영속 목록의 키·그룹·권한에 매핑 |
| 회사 호스트 페이지에서 탭·API prefix·권한·CSS | `packages/gui-test-ui/src/host.ts`의 GuiTestHost, 기존 회사 인증/Origin·scope 계약 |
| Windows 배치 경로·SSH-R·카탈로그/보드·도구 매핑 | `board-connector.bat` / bootstrap launcher, 초기 site 설정. 현지 SSH 키/토큰은 보호된 경로에서 사용 |
