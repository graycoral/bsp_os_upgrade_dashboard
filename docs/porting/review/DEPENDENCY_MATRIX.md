# 복사형 전달 의존성 및 폐쇄망 사전 검사

| 필드 | 내용 |
|---|---|
| source_repo/source_commit | graycoral/bsp_os_upgrade_dashboard · `457587d3b4b5ecb2526db39b3c420803d85d8874` |
| source_commit | `457587d3b4b5ecb2526db39b3c420803d85d8874` · `git rev-parse HEAD origin/main` 결과 일치, 최초 `git status --short --branch`는 깨끗한 `porting/copy-ready-20261122` |
| target_repo/target_commit | N/A |
| scope | Linux·Windows·UI·CLI·API·DB별 공급 및 수신 조건 |
| changes | 이 감사 문서 신규 작성. 제품·DB 변경 NONE |
| package_release | 제품 전달용 NONE. UI 제외 시험용 `ce29893244d4a68c90d6f47efb734ce08dd447938290b759042bcb20b2e04ae5` |
| evidence / execution_evidence | 2026-11-22 Darwin arm64 · Python 3.11.7 · pytest 9.1.1. 선정 시험 18 PASS, 1 SKIPPED. 원본 문서 검사 2,122링크·81요구·304시험·90 NOT_RUN, 오류 0. 명령·로그는 [실행 근거](IMPLEMENTATION_HANDOFF.md#실행-근거) 참조 |
| open_questions / unknowns | 회사 적용 기준·서비스 소유자·인증·wheel 공급원·Windows 장비는 TARGET_UNKNOWN. 회사 적용 담당자가 04에서 확인. 실장비 T-305 NOT_RUN |
| next_task | 02는 PORT-011/013의 빌드·실행 조건 안내를 정렬하고 03은 양 UI 빌드 및 Node 없는 수신 smoke를 수행 |

검사 명령은 실제 수신 경로·OS에서 수행할 항목이다. 네트워크 공급 가능성이나 사내 설치 정책을 원본 검사로 판정하지 않았다.

| 환경·기능 | 필요한 버전·계약 및 원본 위치 | 동봉/사전 준비 | 폐쇄망 검사 명령과 확인값 | 미확인 범위 |
|---|---|---|---|---|
| Linux 플러그인 CLI | Python ≥3.11 (`pyproject.toml:4`), stdlib 진입 `apps/agent-monitor/plugin.py:8` | 전체 폴더와 두 manifest 동봉. Python 별도 | `python3 -V`, `python3 -I plugin.py help`, `python3 -I plugin.py verify .`. help는 무결성 검사와 별도로 실행 | 대상 interpreter/파일 권한 |
| Linux Manager·Worker/API | `requirements.lock` 전체. FastAPI 0.143.0, Uvicorn 0.54.0, Pydantic 2.14.0, httpx 0.28.1. `manage.py:160` venv 생성·pip install | requirements가 동봉된다. wheel/venv·인터프리터 별도. 플랫폼/ABI별 Linux wheels 필요 | 폐쇄망 시험용 새 venv에서 `PIP_NO_INDEX=1 PIP_FIND_LINKS="$WHEELHOUSE" python -m pip install -r requirements.lock` 후 `python -m pip check` 및 `python -c "import fastapi,uvicorn,pydantic,httpx"`. 설치 서비스도 승인된 pip 공급 설정을 상속해야 함 | 회사 Linux 배포판, libc/아키텍처, pip/venv, 미러/프록시 |
| Linux 공개 도구·서명된 추가 패키지 | `apps/agent-monitor/prerequisites.py:111` gpgv, 승인 keyring 및 서명, 선택 wheelhouse | 선택 공급 절차. Manager 기본 pip install 및 Windows GUI와 구분 | `command -v gpgv`, 조직이 승인한 manifest/signature/키·wheel hash 대조. 설정 값·자격증명 출력 금지 | 회사의 서명·도구 배포 정책 |
| UI 생산자 | Node 22.12+와 npm을 권장하는 빌드 스크립트, Vite lock engines는 ^20.19.0 또는 ≥22.12.0. `scripts/build-ui.sh:18`, `apps/web/package-lock.json:1275` | 두 앱 package-lock과 공용 TSX는 동봉. node_modules와 registry 캐시 별도 | `node --version`, `npm --version`, 양 lock에 맞는 사전 npm 캐시/내부 registry로 `bash scripts/build-ui.sh all`. 결과 `apps/web/dist/index.html`, `apps/gui-test/static/index.html`와 JS/CSS 확인 | 생산자의 Node·npm 공급, 01 빌드 NOT_RUN |
| UI 수신자 | Dashboard `backend/api/main.py:348` StaticFiles, standalone `backend/gui_test/standalone/server.py:149` static_dir. Windows 브라우저 `scripts/board_connector.py:44` | 사전 빌드 두 트리, MS용 HTML/MJS/CSS. 직접 수정·재빌드 때만 JS 도구 필요 | 새 폴더의 PATH에서 node/npm 부재를 확인하고 Python만으로 help/verify, dashboard 및 standalone 지정 static_dir의 index/참조 자산을 로컬 GET. standalone 소스 실행 시 실제 `apps/gui-test/static` 지정 | 실제 수신본 두 UI HTTP smoke 03 수행. 브라우저 현지 정책 |
| Windows GUI | x64 CPython 3.11~3.13, 3.13 우선. `board-connector.cmd:35`, `scripts/board_connector.py:40`. 기본 browser는 `apps/gui-test/requirements.lock`과 pyserial 3.5, 선택 Qt는 `apps/board-connector/requirements.lock`의 PySide6-Essentials/shiboken6 6.8.3 | BAT/CMD·소스·lock 동봉. Python·ABI별 wheels·사용자 쓰기 가능한 캐시 별도. embedded CLI의 win_amd64 cp312 lock으로 3.13 충족 여부를 보장할 수 없음 | `py -0p`, `py -3.13 -c "import struct,sys;print(sys.version,struct.calcsize('P')*8)"`. 새 Windows venv에 같은 lock 오프라인 설치 및 pip check, 선택 Qt까지 import | Windows 네이티브 실행·GUI·기존 캐시 설치 NOT_RUN |
| Windows 장비·터널 | `scripts/board_connector.py:197`, `backend/gui_test/connector/ssh_tunnel.py:20`, PORT-013. OpenSSH/PowerShell, fastboot, 선택 PuTTY·COM/드라이버. 도구 최소 버전은 코드에서 고정하지 않음 | 도구 실행 파일/드라이버·SSH 계정·신뢰된 호스트키·ACL·허용 포워딩은 현지 준비. 소스 패키지에 비밀/키 미포함 | `Get-Command ssh,fastboot,putty -ErrorAction SilentlyContinue`, `ssh -V`, `fastboot --version`, `[System.IO.Ports.SerialPort]::GetPortNames()`. Linux에서 `ss -ltn`, Windows에서 `Get-NetTCPConnection -State Listen`로 예정 포트 사전 조사 | Windows SSH-R·PuTTY·serial/fastboot 실물, T-305 NOT_RUN |
| API·CLI host | `plugin.py:55` monitor `--port/--monitor-port`와 `--connector-port` 분리, `direct_connector_client.py:88` 기본 8771, `main.py:89` local peer/same-origin/identity. 회사 dashboard 예시 8765, Monitor 8766 | 서버·SDK 동봉, 회사 slash 매핑·계정/권한·URL 경로 현지 | 배포 전 기존 service.json과 `manage.py status --home "$MONITOR_HOME"` 대조. 단일 owner, explicit project 및 동일 서비스의 runtime 확인. 회사 proxy/scope는 기존 인증 시험으로 판정 | 실제 값, 회사 모듈 게시·부분 이식·접근 권한 TARGET_UNKNOWN |
| Linux DB | SQLite (별도 최소 버전 미명시), `core/shared_settings_store.py:96` shared-settings v1 DELETE+flock+CAS. `core/store.py:17` runs v1·reservations, `recovery.py:334` dashboard 1/2 호환 확인 | 빈 DB도 생성 가능. 기존 runtime은 전달 폴더 밖. SQLite backup/manifest는 현지에만 보관 | `python3 -c "import sqlite3; print(sqlite3.sqlite_version)"`. 복제 DB에서 read-only integrity_check, schema_version, run/예약·revision 전후 일치. `manage.py inspect-runtime --home "$MONITOR_HOME"`은 설치된 home 기준 | 사내 데이터량·filesystems 잠금·이전·복원 |
| Windows DB | `execution/host.py:89`·`execution/connector_runs.py:37` executions.db runner_meta connector_schema_version 2. Linux runs.db와 별개 | 현지 Windows runtime 별도 백업. release 폴더 밖에 유지 | 소유자 정지 확인 후 일관된 복제본에서 `SELECT value FROM runner_meta WHERE key='connector_schema_version'`, 무결성·보류 작업·attempt/분석·예약과 이전 버전 읽기 여부 대조 | 실제 구버전 호환/복원 NOT_RUN |
| 모델·Jira | 실제 BSP/실패 분석은 별도 기능. `backend/gui_test/standalone/analysis_runtime.py:1`에서 등록 adapter 사용 | 사내 Claude Code + Bedrock 권한·모델은 별도 현지 선택. OpenCode는 이 복사/검사의 필수품 아님 | help/verify/import/정적 자산 확인까지 모델 호출 불필요. 승인 목록은 사내 담당자가 직접 확인 | Bedrock, Jira, 모델 추론 NOT_RUN |

동일 논리 서비스를 재사용할 때는 기존 설정 DB와 home/runtime binding을 함께 식별한다. 독립 비교 환경은 두 포트와 home/runtime·connector state·SSH-R 바인드를 독립 지정한다. 실서버의 관리자 권한·패키지 설치·장비 제어를 preflight 대신 실행하지 않는다.
