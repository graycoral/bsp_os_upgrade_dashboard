# 원본 이식성 감사

| 필드 | 내용 |
|---|---|
| source_repo/source_commit | graycoral/bsp_os_upgrade_dashboard · `457587d3b4b5ecb2526db39b3c420803d85d8874` |
| source_commit | `457587d3b4b5ecb2526db39b3c420803d85d8874` · `git rev-parse HEAD origin/main` 결과 일치, 최초 `git status --short --branch`는 깨끗한 `porting/copy-ready-20261122` |
| target_repo/target_commit | N/A |
| scope | 00 원본 계획 검토와 01 소스·문서 감사. PORT-007/009/011~014와 정상 전달 진입점 |
| changes | 이 감사 문서 신규 작성. 제품·DB 변경 NONE |
| package_release | 제품 전달용 NONE. UI 제외 시험용 `ce29893244d4a68c90d6f47efb734ce08dd447938290b759042bcb20b2e04ae5` |
| evidence / execution_evidence | 2026-11-22 Darwin arm64 · Python 3.11.7 · pytest 9.1.1. 선정 시험 18 PASS, 1 SKIPPED. 원본 문서 검사 2,122링크·81요구·304시험·90 NOT_RUN, 오류 0. 명령·로그는 [실행 근거](IMPLEMENTATION_HANDOFF.md#실행-근거) 참조 |
| open_questions / unknowns | 회사 적용 기준·서비스 소유자·인증·wheel 공급원·Windows 장비는 TARGET_UNKNOWN. 회사 적용 담당자가 04에서 확인. 실장비 T-305 NOT_RUN |
| next_task | 02는 문서 정리 계획을, 03은 아래 A01~05와 인수인계 시험을 적용 |

## 판정

**01 원본 감사 PASS.** 복사 단위는 `plugin.py`, `agent-monitor/`, 외부 manifest를 포함한 전달 폴더 전체다. 원본 소스·헤드리스 복사본에서 확인한 내용과 미검증 의존성을 분류했다. 사전 빌드 두 UI가 포함된 실제 전달본 및 설치·실행 release 대조는 03 게이트다. P0 근거는 발견되지 않았다. P1은 잘못된 배포·기록·설정 갱신을 일으킬 조건이다. 실제 회사 장애 원인은 미확정이다.

| ID | Severity | Component | evidence(file:line) | classification | failure condition | recommendation | test |
|---|---|---|---|---|---|---|---|
| A01 | P1 | 두 UI 및 기본 export | `apps/agent-monitor/delivery.py:52`, `backend/api/main.py:348`, `backend/gui_test/standalone/server.py:149` | REFACTOR_REQUIRED | 파일 수집기가 Dashboard index만 요구한다. 임시 fixture에 index 하나와 없는 JS 참조를 두었을 때 해당 index만 반환했다. 독립 UI가 비어도 수집을 통과한다 | 기존 full export/verify에서 양쪽 index·실제 로컬 참조 자산을 확인. headless 선택은 유지 | 03 두 UI 빌드 후 각각 index/참조 누락 회귀, 복사본 static GET |
| A02 | P1 | 출처 pin | `apps/agent-monitor/delivery.py:32`, `apps/agent-monitor/delivery.py:87`, `tests/test_plugin_delivery.py:42` | REFACTOR_REQUIRED | Git 밖에서 재-export한 시험본은 파일 492개와 release가 동일했지만 source_head가 pin에서 null로 바뀌었다. 다른 Git에 복사하면 그 Git의 HEAD를 읽을 수 있다 | 기존 manifest로부터 source_head를 계승. 공급자 첫 export는 고정 소스 및 작업 트리를 기록 | 초기 export와 Git 외부 및 별도 Git의 재-export SHA 비교 |
| A03 | P1 | 설치본, 실행본 버전 | `apps/agent-monitor/manage.py:218`, `apps/agent-monitor/manage.py:230`, `apps/agent-monitor/plugin.py:113` | REFACTOR_REQUIRED | start가 활성 설치본을 재사용하고 health는 receipt와 일치해도 새로 복사한 release 여부를 알리지 않는다 | 외부 manifest → current.json 설치 경로 → service.json/health managed_release를 비교해 구버전 사용을 명시. 업그레이드와 종료는 해당 소유자의 절차 | 구 서비스와 새 전달본 fixture. 상태 조회로 프로세스·작업 유지 검증 |
| A04 | P1 | 플러그인 설정 파일 동기화 | `apps/agent-monitor/plugin.py:21`, `backend/gui_test/standalone/plugin_commands.py:264`, `backend/gui_test/standalone/plugin_settings_file.py:76` | REFACTOR_REQUIRED | direct 경로는 settings file의 detail을 판별하지 않고 주어진 파일을 읽어 저장한다. 문서의 sync/push로 호출하면 기존 파일 bridge의 방향·충돌 처리와 달라진다 | 해당 기능을 회사 요구로 채택하려면 기존 bridge 계약을 복원하고 충돌 시험. 그 전에는 direct에서 지원을 검증한 export/import만 안내하고 미지원 명령의 자동 실행을 차단 | direct 경로에서 파일 부재·변경 충돌·기존 revision·회전 백업. 01은 코드 대조 |
| A05 | P1 | package verify의 범위 | `apps/agent-monitor/plugin_delivery.py:15`, `apps/agent-monitor/plugin_delivery.py:109`, `apps/agent-monitor/plugin_delivery.py:125` | REFACTOR_REQUIRED | 등록된 파일 hash를 검사하지만 outer entrypoint/Windows descriptor와 release의 대응, 추가 파일·필수 자산 집합은 완전 대조하지 않는다 | 전달 직전 전용 새 폴더에서 양쪽 목록과 실제 일반 파일·진입점·자산을 대조. 파일별 SHA와 별개 채널의 신뢰 가능한 전달 checksum을 기록 | manifest 누락/불일치 시 실패, 생성 후 검증 및 안전한 extra 파일 정책 |
| A06 | P1 | 서비스·Worker·runtime 소유권 | `run.sh:20`, `run.sh:39`, `apps/agent-monitor/manage.py:63`, `apps/agent-monitor/manage.py:392`, `backend/worker/main.py:382` | ADAPTER_REQUIRED | 별도 home에서 동일 서비스를 다시 배정하거나 동일 업무의 서로 다른 runtime이 생기면 예약/상태가 갈라진다 | 동일 논리 서비스는 기존 home/runtime/worker 한 소유자. 병행 비교는 포트와 데이터 경로를 모두 분리. 회사 기존 process 및 DB 대응표 확보 | 중복 Worker lock, 기존 paused 예약 유지, 두 home 간 stop/status 격리 |
| A07 | P1 | Linux 및 Windows 저장소 | `backend/gui_test/core/shared_settings_store.py:96`, `backend/gui_test/core/store.py:17`, `backend/gui_test/execution/host.py:89`, `backend/gui_test/execution/connector_runs.py:550`, `apps/agent-monitor/recovery.py:410` | COPY_AS_IS | Linux shared-settings v1/GUI runs v1과 Windows executions의 connector schema 2가 서로 다른 소유자. Linux 백업만으로 Windows 이력을 복원할 수 없다 | 사본에서 양측 개별 백업·검증. 예약·UNKNOWN·revision·시도/분석 이력을 보존하고 구 코드의 schema 호환성 확인 | 01 Linux migration/CAS·WAL backup·rollback PASS. Windows 이전/복원 NOT_RUN |
| A08 | P1 | HTTP 권한·회사 경로 | `backend/api/main.py:89`, `backend/api/main.py:112`, `backend/api/main.py:140`, `scripts/serve_monitor.py:20` | ADAPTER_REQUIRED | 회사 proxy/prefix·로그인·다중 사용자를 loopback 단일 사용자와 같게 취급하면 요청 거부 또는 권한 경계 변경 | 회사 adapter에서 권한·경로·origin 및 service identity를 명시. 기존 same-origin·method/path scope 유지 | 회사 기존 로그인·권한 및 회귀, 테스트 클라이언트 허용/거부 매핑 |
| A09 | P2 | CLI 및 Python import | `apps/agent-monitor/plugin.py:8`, `apps/agent-monitor/plugin.py:83`, `tests/test_plugin_delivery.py:48` | COPY_AS_IS | plugin.py만 이동하면 상대 소스 탐색과 backend imports가 끊긴다 | 폴더 구조 보존, Python 실행기/공통 의존성 지정. direct는 Connector, monitor만 Monitor 기동 | 복사본 -I help/verify/import/TC preview 모의 PASS |
| A10 | P2 | Windows GUI·SSH 터널 | `apps/agent-monitor/plugin_delivery.py:39`, `scripts/board_connector.py:40`, `scripts/board_connector.py:138`, `backend/gui_test/connector/ssh_tunnel.py:20`, `docs/porting/PORT-014.md:22` | COPY_AS_IS | folder 일부 복사, x86 Python, 오프라인 wheel 부족, SSH-R 점유 시 시작 실패 | 기본 agent-monitor/board-connector.bat, bootstrap 생성 폴더는 start-board-connector.bat. 같은 호스트의 listener와 remote_runner_port 대조 | 헤드리스 산출물 파일·모듈 PASS. 원격 바인드·COM·PuTTY·fastboot T-305 NOT_RUN |
| A11 | P2 | React 코어·회사 페이지 | `apps/web/src/main.tsx:12`, `apps/gui-test/src/main.tsx:2`, `packages/gui-test-ui/src/host.ts:4` | ADAPTER_REQUIRED | 재빌드 때 상대 소스가 빠지거나 회사 host의 API prefix·탭 등록이 다르면 화면을 연결할 수 없다 | 공통 UI COPY_AS_IS. 자체 페이지로 통합할 때 GuiTestHost 구현·tab/route·권한만 매핑. 공급된 독립 UI는 정적 파일 제공 | 두 앱 빌드, 회사 UI의 TC 목록·설정 revision·탭 전환 |
| A12 | P2 | 외부 plugin slash/모듈 callback | `backend/gui_test/standalone/bsp_plugin_client.py:29`, `docs/porting/PORT-012.md:11` | ADAPTER_REQUIRED | 실제 회사 기존 모듈 키/선행 그룹과 구현 범위 TARGET_UNKNOWN | 기존 영속 목록과 publish_modules/expected_version 연결. 회사 imports·부분 적용 여부는 04에서 기록 | 회사 T-290 NOT_RUN |
| A13 | P2 | 폐쇄망 설치 | `apps/agent-monitor/manage.py:160`, `scripts/board_connector.py:197`, `apps/agent-monitor/prerequisites.py:111` | BLOCKED | 현지 wheel 공급원·Windows tools·ABI 확인 전 독립 신규 설치 판정 불가 | 의존성 표에 따라 양측 공급물을 준비해 폐쇄망 preflight | 사내 오프라인 설치 NOT_RUN |
| A14 | P3 | 과거 embedded CLI ZIP, Node 수신 설치, 모델/SDK | `apps/agent-monitor/plugin_delivery.py:65`, `apps/agent-monitor/manage.py:243`, `pyproject.toml:4` | NOT_REQUIRED | 다른 배포 계약·빌드 전용 도구·실제 모델을 기본 복사 전제로 두면 오프라인 설치 범위 증가 | ZIP/CLI는 별도 선택. 사전 빌드 전달, help/verify와 실제 모델 인증·호출을 분리 | 03 Node 없는 PATH smoke, 모델 인수 NOT_RUN |
