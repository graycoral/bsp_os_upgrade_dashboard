# PORT-015 · Windows 실행 폴더의 Linux SSH 설정

RQ-82는 플러그인이 저장한 Linux SSH 접속 프로필을 Windows 실행 폴더에 채운다. PORT-011 전달 구조와 PORT-013 직결을 선행 적용한다. 원본 기준은 `83dffb6532edc119a55f09bc57f7fa47d38f9bcd`다. 이번 개발·리뷰 범위는 로컬 작업 트리이며 회사 전달용 대상 커밋은 아직 고정하지 않았다.

## 플러그인 접점

```sh
python3 plugin.py --home "$PLUGIN_HOME" --runtime "$PLUGIN_RUNTIME" --project PROJECT connect profile --server HOST --account USER
python3 plugin.py --home "$PLUGIN_HOME" --runtime "$PLUGIN_RUNTIME" --project PROJECT connect export --output "$WINDOWS_PACKAGE"
```

회사 플러그인에서 이미 접속 정보를 알고 있으면 최초 설정 또는 접속 대상 변경 시 첫 명령에 전달한다. 서버는 Windows에서 접근할 수 있는 호스트명 또는 IP, 계정은 Windows가 SSH로 접속할 Linux 계정이다. 두 명령과 호스트의 `connect --watch`에 같은 플러그인 런타임 및 커넥터 포트를 사용한다. Windows에서는 생성된 폴더의 `start-board-connector.bat`를 실행한다.

저장된 대상의 SSH 포트를 한 번만 바꾸려면 내보내기에 `--ssh-port`를 지정한다. 다른 대상은 `--server`와 `--account`를 함께 지정한다. 이 경우 SSH 포트를 생략하면 기존 명시 내보내기와 같이 22를 사용한다. 역방향 포트는 플러그인의 커넥터 포트를 기본으로 사용한다. 명시 내보내기에서 변경한 값은 해당 폴더에만 적용한다. SSH 개인 키와 비밀번호는 전달물에 포함하지 않는다.

## 원본 파일과 데이터

- [명령 어댑터](../../backend/gui_test/standalone/plugin_commands.py)의 `execute_direct`가 프로필 저장과 내보내기 인자 결정을 처리한다. CLI 진입점은 [plugin.py](../../apps/agent-monitor/plugin.py)다.
- [기존 bootstrap 계약](../../backend/gui_test/core/connector_bootstrap.py)의 SSH 검증을 저장에도 재사용한다. Windows 실행기는 기존 bootstrap-v2를 읽는다.
- [공유 설정 저장소](../../backend/gui_test/core/shared_settings_store.py)는 `shared-settings.db`의 `meta`에 별도 키로 보관한다. 기존 DB는 프로필 없이 시작하며, 스키마 이전과 신규 의존성이 필요 없다. 기존 preferences 행은 그대로여서 이전 코드로 돌아가면 새 메타데이터를 읽지 않고 기존 명시 내보내기를 사용할 수 있다. 프로필을 포함해 복원하려면 해당 런타임의 `shared-settings.db`를 기존 백업 절차로 복원한다.

## 검증과 인수

로컬 T-306 및 회사 T-307은 [시험 기록](../testing/runs/20261122-connector-ssh-profile.md)을 따른다. 회사에서는 실제 Windows 첫 실행으로 SSH 연결을 확인하고, 플러그인 활성화 훅이 늦은 연결을 감지하는지 확인해 `APPLIED.md`에 남긴다.
