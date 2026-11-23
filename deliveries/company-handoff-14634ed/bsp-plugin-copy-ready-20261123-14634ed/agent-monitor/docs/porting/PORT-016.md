# PORT-016 · 보드 커넥터 웹의 퓨징 설정 이식

**RQ-83 · T-309 · REG-0119.** 플러그인이 이번 빌드의 퓨징 BAT나 보드 프로파일을 지정하지 않았을 때 사용자가 웹에서 저장한 값을 직결 CLI가 사용한다. 선행 기능은 [PORT-011 폴더 전달](PORT-011.md#현재-유효-기준)과 [PORT-013 직결 커넥터](PORT-013.md)다. 개발·회귀 비교 기준은 `557b7d070a195c44f17bf2eb05e0d8fd0dd7c73d`이며, 기능·시험의 고정 커밋은 `ac79a5643dd77c45b7f2c035c716970c6564a2d1`다. 복사할 패키지의 소스 커밋과 release는 전달 폴더 바깥의 인수 기록과 패키지 manifest에서 대조한다.

## 전달 폴더에서 바뀌는 위치

아래 경로는 **회사 플러그인에 복사하는 패키지 루트** 기준이다. 이 루트에서 `plugin.py`, `PLUGIN_PACKAGE.json`, `agent-monitor/`가 함께 보인다. 기존 배포 폴더 `deliveries/company-handoff-8abe926/bsp-plugin-copy-ready-20261122-8abe926/`는 이전 버전이다. 아래 표는 PORT-016의 변경 범위이며 이전 배포 이후의 다른 기능까지 포함한 전체 파일 차이는 두 패키지의 manifest에서 비교한다.

| 실행 위치 | 새 패키지 안의 파일 | 적용 내용 |
|---|---|---|
| 회사 플러그인 진입점 | `plugin.py`, `agent-monitor/apps/agent-monitor/plugin.py` | 같은 진입점이 두 위치에 복사된다. 도움말에 직결 퓨징 옵션을 표시한다. |
| Linux 명령 처리 | `agent-monitor/backend/gui_test/standalone/plugin_commands.py`, `agent-monitor/backend/gui_test/standalone/direct_connector_client.py` | `settings save`의 프로파일 게시, `test preview/run --flash`의 명시값 우선·누락값 보완, 프로파일 이름 검증 |
| 대시보드 소스 | `agent-monitor/apps/web/src/main.tsx`, `agent-monitor/packages/gui-test-ui/src/ConnectorMirror.tsx`, `agent-monitor/packages/gui-test-ui/src/SharedControl.tsx` | 보드 커넥터 탭 상단에 퓨징 설정을 펼치고 기존 Linux 공통 설정에 저장 |
| Windows 웹 커넥터 | `agent-monitor/packages/gui-test-ui/src/connector_web/view.mjs`, `agent-monitor/backend/gui_test/connector/web_actions.py` | 환경설정에서 BAT·프로파일·이미지 허용 폴더 입력, Linux 공통 서버에 저장할 수 없는 퓨징 값의 오프라인 저장 거부 |
| 사전 빌드 UI | `agent-monitor/apps/web/dist/index.html` 및 `assets/`, `agent-monitor/apps/gui-test/static/index.html` 및 `assets/` | 각 index와 그 index가 가리키는 JS·CSS를 함께 전달한다. 실제 해시 파일명은 해당 패키지 manifest에 기록된다. Windows 커넥터의 웹 뷰는 위 행의 별도 MJS를 사용한다. |
| 동봉 안내·회귀 시험 | `agent-monitor/docs/agents/{BSP_UPGRADE_PLUGIN_REQUEST,PLUGIN_CONTROL_API}.md`, `agent-monitor/docs/gui_test/TEST_BOARD_CONNECTOR_GUI.md`, `agent-monitor/tests/test_direct_connector_unit4.py`, `agent-monitor/tests/e2e/{connector-mirror,connector-web}.spec.ts` | 회사 콜백 매핑과 수동 설정 절차, API·브라우저 회귀 시험 |
| 전달·무결성 | `README.md`, `agent-monitor/docs/porting/PORT-016.md`, `agent-monitor/AGENT_MONITOR_SOURCE.json`, `PLUGIN_PACKAGE.json` | 생성된 루트 README에서 이 문서를 찾을 수 있다. 내부 manifest는 소스·빌드 파일을, 외부 manifest는 루트 파일과 내부 패키지를 검증한다. |

원본 트리의 경로는 위 표에서 `agent-monitor/` 접두사를 제거하면 된다. 루트 `plugin.py`의 원본은 `apps/agent-monitor/plugin.py`다. 루트 README 변경은 패키지 내부 `agent-monitor/apps/agent-monitor/plugin_delivery.py`에도 들어가므로 재내보내기에서도 안내가 유지된다. README와 manifest 생성 로직은 [plugin_delivery.py](../../apps/agent-monitor/plugin_delivery.py)와 [delivery.py](../../apps/agent-monitor/delivery.py)다. Windows에 기본 폴더를 전달하면 `agent-monitor/` 자체가 Windows 실행 루트가 된다. `connect export --output`으로 만든 Windows 폴더도 내부 소스 기준 상대경로를 유지하며, 연결 정보를 넣은 경우 `start-board-connector.bat`와 `connector-connection.json`이 추가된다.

## 원본에서 생성하고 회사에서 적용하기

1. 원본 담당자가 전달 대상 커밋을 고정한 깨끗한 체크아웃에서 두 UI를 빌드한다. 아래 명령의 `NEW_PACKAGE`는 소스 트리 밖에 새로 만들 폴더의 절대 경로다.
2. 생성된 패키지의 release, `source_head`, `source_dirty`, 두 manifest의 SHA-256을 인수 기록에 남긴다. 기존 패키지를 보관하고, 회사 플러그인 저장소에 검증한 새 폴더 전체를 배치한다. 실행 중인 Linux Monitor는 `plugin.py monitor status`에서 설치·실행 release를 대조하고 기존 관리자의 업데이트 절차를 따른다. Windows도 같은 release의 실행 폴더를 사용한다.
3. 회사 담당자가 빌드 완료 훅에서 이미지 출력 폴더와 BAT 상대 경로를 확인하고 활성 보드 프로파일을 매핑한다. 회사 YAML 키와 훅 위치는 회사 `COMPANY_MAP.md`에 기록한다. 플러그인 값이 빠진 경우 대시보드의 **보드 커넥터 → 이미지 퓨징 설정** 또는 Windows 웹의 **환경설정 → 이미지 퓨징 · 서버 공통 설정**에서 보완한다. Windows에서 저장하려면 Linux 공통 서버에 연결되어야 한다. [빌드별 입력 계약](../agents/PLUGIN_CONTROL_API.md#빌드별-퓨징-입력)

```sh
bash scripts/build-ui.sh all
python3 -B apps/agent-monitor/plugin.py export --output "$NEW_PACKAGE"
python3 -IB "$NEW_PACKAGE/plugin.py" verify "$NEW_PACKAGE" --pristine
```

## 인수와 복구

- 회사에서 같은 home/runtime으로 `test preview --flash`를 실행해 플러그인 명시값, 부분 수동 보완, 전체 수동 보완을 확인한다. BAT가 이번 빌드에 속하는지 대조하고, 필수값 누락 시 안내되는지 확인한다. 옵션 없는 `test preview`는 TC 단독이어야 한다. 실제 장비 퓨징은 회사에서 승인한 인수 시점에 수행한다.
- DB 스키마 이전은 없다. 기존 `shared-settings.db`의 `installer_roots`, `installer_path`, `flash_profile`을 사용한다. 복구 시 이전 패키지·매칭 Windows 폴더와 기존 home/runtime을 사용한다. 이전 CLI에서는 회사 훅도 이전 명시 인자 방식으로 되돌린다. 회사 커밋·release·시험 결과는 회사 `APPLIED.md`에 남긴다.
- 원본 로컬 시험은 Python 53 PASS, 대시보드 브라우저 16 PASS, Windows 웹 모의 시험 19 PASS·기준 버전에서도 재현된 5 FAIL이다. 회사 YAML, 실제 Windows·USB 인수는 NOT_RUN이다. 상세 증거는 원본 저장소의 `docs/testing/runs/20261123-fusing-settings.md`에서 확인한다.
