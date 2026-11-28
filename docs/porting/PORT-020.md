# PORT-020 · 플러그인 활성화와 Windows 보드 커넥터의 대시보드 열기

## 적용 대상과 복사 위치

고정 소스는 `bf1f7d289b64baefd03bea98f3799838cea73123`이다. [회사 복사본과 검증값](../../deliveries/company-handoff-bf1f7d2/00_START_HERE.md)을 확인한다.

RQ-86 · T-323 · REG-0142. 선행 전달본은 `190e350`이다. 현재 패키지의 고정 소스 커밋은 `agent-monitor/AGENT_MONITOR_SOURCE.json`의 `source_head`에 있으며 전달 안내서 `00_START_HERE.md`에 검증값을 함께 제공한다. 복사 절차는 [PORT-011](PORT-011.md#폴더-전달과-검증), 직결 구조는 [PORT-013](PORT-013.md), 제한망 운영은 [PORT-018](PORT-018.md)을 따른다.

| 담당 | 위치와 작업 |
|---|---|
| 원본 Linux 패키지 | `apps/agent-monitor/plugin.py`와 `manage.py`가 서비스 준비·재사용을 처리한다. `backend/gui_test/standalone/plugin_commands.py`가 Windows 연결 프로필을 생성한다. 회사 플러그인 저장소에는 새 전달 폴더 전체를 복사해 루트의 `plugin.py`, `PLUGIN_PACKAGE.json`, `agent-monitor/`를 함께 둔다. |
| Windows 커넥터 | 같은 버전의 커넥터에서 SSH 포워딩과 현재 Agent Monitor 응답을 확인하고 웹·Qt의 열기 버튼에 Windows 로컬 주소를 전달한다. 프로필 포함 배포는 `connect export`로 만든 폴더 전체를 장비 PC에 복사해 `start-board-connector.bat`로 적용한다. |
| 회사 플러그인 | 사내 활성화 훅에서 패키지 루트의 CLI를 호출한다. 같은 설치의 home·runtime·포트를 넘기고 결과를 표시한다. 실제 사내 훅 위치와 적용 커밋은 회사 `COMPANY_MAP.md`와 `APPLIED.md`에 기록한다. [담당자 요청문](../agents/BSP_UPGRADE_PLUGIN_REQUEST.md#회사-플러그인-활성화-시-agent-monitor-준비) |

## 활성화와 연결

1. **플러그인 활성화** 시 보드 연결을 기다리지 않고 다음 단발 명령을 비동기로 실행한다. 회사 제한망에서는 UI와 Python 의존성을 갖춘 같은 릴리스를 먼저 설치한다. 설치를 허용하는 환경에서는 `--no-provision`을 생략할 수 있다.

   ```sh
   python3 "$PACKAGE/plugin.py" --home "$MONITOR_HOME" --runtime "$MONITOR_RUNTIME" \
     --monitor-port "$MONITOR_PORT" monitor ensure --no-provision
   ```

2. 성공하면 종료 코드 0과 stdout의 JSON에서 `state=READY`, `reused`, `port`, `url`, `release`를 읽는다. 반환된 URL은 Linux 로컬 주소다. 준비된 설치가 없는 제한망에서는 종료 코드 6과 stderr의 `NOT_PROVISIONED`를 설치 담당자에게 알린다. 포트 충돌이나 설치 버전 불일치가 발생하면 대시보드의 오류만 알리고 직결 기능은 계속 제공한다. 설치 전환이 필요하면 기존 운영자의 안전 갱신 절차를 사용한다. 여러 창이 같은 서비스를 사용하므로 창 닫기에서 서버를 종료하지 않는다. 커넥터 감시가 필요하면 기존 소유자의 `connect --watch`를 유지한다.

3. **Windows 연결 폴더 생성** 시 회사에 저장한 SSH 프로필을 사용하고 Linux의 실제 모니터 포트를 명시할 수 있다. 아래 `WINDOWS_PACKAGE`는 새 출력 디렉터리다. 포트를 지정하지 않은 구형 직결 프로필에는 저장된 모니터 포트가 없을 수 있다. 그런 설치는 기존 설정을 대조한 뒤 같은 서버·계정으로 생성한 새 연결 프로필을 적용한다. 기존 COM·키·실행 기록은 해당 장비의 설치에 보관한다.

   ```sh
   python3 "$PACKAGE/plugin.py" --home "$MONITOR_HOME" --runtime "$MONITOR_RUNTIME" \
     --monitor-port "$MONITOR_PORT" connect export --output "$WINDOWS_PACKAGE"
   ```

4. **Windows에서 열기**를 누르면 브라우저는 커넥터가 바인딩한 `http://127.0.0.1:<Windows 로컬 포트>`로 접속한다. 이 포트에서 SSH가 Linux의 모니터 포트로 전달한다. 플러그인과 Windows Host 사이의 기본 역방향 포트 `8771`은 보드 직결용이다. 화면은 사용자가 버튼을 누를 때 열리고 기존 서비스의 로그인 설정을 따른다.

   Windows 로컬 포트가 일시적으로 점유됐거나 대시보드용 SSH 프로세스만 종료되면 해당 포워딩을 다시 시도한다. 보드 직결이 살아 있으면 같은 SSH 역방향 연결을 계속 쓴다. 포트를 열고 현재 서비스와 HTML 응답까지 확인한 뒤 버튼을 다시 표시한다.

커넥터 전용 폴더를 생성할 때에는 `connect export --without-monitor`를 사용할 수 있다. 이전 프로필에 모니터 포트가 없고 설정에서도 지정하지 않은 독립 직결 설치는 역방향 터널만 사용한다.

## 회사 인수와 복구

원본에서 `bash scripts/test_monitor_activation.sh python package browser-monitor`를 실행하면 Python 회귀, 복사형 패키지·임시 서비스, 대시보드 버튼의 브라우저 시험을 수행한다. 인자를 생략하면 보드 커넥터의 전체 브라우저 회귀까지 실행한다. 공개 실행 요약은 전달 폴더 안의 `agent-monitor/docs/testing/runs/20261129-monitor-activation.md`에 들어간다.

| 현지 시험 | 기대 결과 |
|---|---|
| Windows가 꺼진 상태에서 플러그인을 활성화하고 두 번째 창을 연다. | 같은 home·runtime에서 같은 API와 Worker를 재사용한다. 창을 닫고 다시 열어도 같은 서비스에 접속한다. |
| 대시보드 준비 전 Windows를 먼저 연결한 뒤 플러그인을 활성화한다. | 보드 직결을 유지한다. 대시보드가 응답하면 Windows 웹·Qt에서 열 수 있다. |
| 회사 지정 Linux 포트와 다른 Windows 로컬 포트를 사용한다. SSH를 끊었다 다시 연결한다. | 실제 Windows 포트로 접속하고 단절 시 이전 링크가 사라진다. 재접속한 서버의 링크만 열린다. |
| 준비되지 않은 제한망 설치 또는 충돌하는 모니터 포트로 시작한다. | 기동 실패가 표시된다. 제한망에서 다운로드가 발생하지 않고 보드 직결을 계속 사용할 수 있다. |

준비에 성공한 모니터 포트는 설치 home의 `monitor-port.json`에 설치 경로·릴리스·runtime과 함께 기록한다. DB 스키마 이전은 없다. 복구 시 새 회사 활성화 호출을 해제하고, 기존 소유자 절차로 서비스·커넥터를 안전하게 중지한 뒤 이전 패키지와 보관한 연결 프로필을 같은 home·runtime으로 복원한다. 기존 DB와 장비 설정은 유지한다. 원본 스크립트 시험과 실제 회사 훅·Windows SSH 인수는 [실행 기록](../testing/runs/20261129-monitor-activation.md)을 참조한다.
