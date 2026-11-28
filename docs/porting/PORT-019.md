# PORT-019 · TC 경로 실행, 보드 ADB 전송, 실패 로그 전달

회사 플러그인이 TC 루트를 넘기면 Windows 보드 커넥터가 실행할 파일과 보드를 결정한다. 실패하면 플러그인은 같은 실행·시도 ID로 TC 로그와 보드별 커널 로그를 받는다. 이 기능의 이식 단위는 Linux 참조 CLI, Windows 커넥터, 두 프로그램 사이의 계약이다.

## 적용 기준

| 항목 | 기준 |
|---|---|
| 원본 비교 범위 | `ba31de7aff550a220d890b1725a56645c9e47b97` → `161680977a2e7d7a581550d7acb5c6bcbb6a84ed`. [고정 변경 내역](https://github.com/graycoral/bsp_os_upgrade_dashboard/commit/161680977a2e7d7a581550d7acb5c6bcbb6a84ed) |
| 선행 기능 | [PORT-011](PORT-011.md)의 복사형 CLI와 [PORT-013](PORT-013.md)의 SSH 직결 Host·소스 스냅샷·실패 분석. 회사에서 prepare/send를 사용하면 [PORT-017](PORT-017.md)의 멱등 재접수도 보존한다. |
| 요구사항·검증 | RQ-78/79/81, T-321/322, REG-0139/0140. 원본 코드 게시와 로컬 검증 완료. 회사 적용 상태 UNKNOWN, 실장비 인수 NOT_RUN. |
| 전달 기준 | 이번 기능의 고정본은 위 Git 커밋이다. 기존 회사 전달 폴더 `deliveries/company-handoff-7691c0e/`는 이전 릴리스다. |

## 어디에 적용하는가

아래 경로는 원본 저장소 루트 기준이다. 복사형 Linux 플러그인에서는 각 경로 앞에 `agent-monitor/`를 붙인다. Windows 소스형 커넥터에서는 `board-connector.cmd`가 있는 디렉터리를 루트로 사용한다. 새 복사본이 필요하면 고정 커밋을 체크아웃해 두 UI를 빌드한 뒤 PORT-011 절차로 새 폴더에 export하고 `verify --pristine`을 실행한다. [내보내기 및 복사 절차](PORT-011.md#폴더-전달과-검증)

| 적용 위치 | 원본 경로 | 변경 내용 |
|---|---|---|
| Linux 참조 CLI | `backend/gui_test/standalone/{direct_connector_client,plugin_commands,plugin_parser}.py`, `backend/gui_test/core/discovery.py` | TC 루트·스냅샷으로 실행을 요청하고 실패한 시도의 증거를 조회한다. 명시적인 TC 선택과 기존 실행 조회도 지원한다. |
| Windows 실행기 | `backend/gui_test/execution/{path_runs,connector_runs,host,source_snapshots,failure_evidence}.py`, `backend/gui_test/core/discovery.py` | TC 분류·순서 결정, ADB 준비 확인·전송·실행, 실패 상태 저장과 보드별 로그 수집을 맡는다. |
| Windows 상태 화면 | `backend/gui_test/connector/gui.py`, `packages/gui-test-ui/src/connector_web/view.mjs` | 표시용 목록이 없어도 Host가 수락한 실행 단계와 결과를 보여 준다. |
| 공통 계약 | `contracts/{connector-path-run-v1.schema,connector-run-request-v1.schema,plugin-cli-v1,plugin-behavior-changes}.json` | 같은 고정본으로 경로 요청, CLI 옵션과 기능 지원 여부를 맞춘다. |

회사 플러그인 담당자는 프로젝트의 TC 루트를 넘기고 반환된 Run ID를 해당 빌드·모듈에 연결한다. 실패 시 `test status`의 `active_analysis.attempt_id`를 사용한다. 명령 예시에서 `$TC_ROOT`는 세 폴더의 상위 경로다.

```sh
python3 plugin.py test run --tc-root "$TC_ROOT" --no-follow
python3 plugin.py test status "$RUN_ID"
python3 plugin.py test logs "$RUN_ID" --failure-attempt "$ATTEMPT_ID"
```

## 설정·데이터·복원

1. Windows의 `windows-runner.json`에서 `path_run`의 보드와 고유 ADB 시리얼을 매핑한다. `python3/`와 `dual_board/`는 Windows에서 실행하고, `linux/`의 TC는 보드 셸 응답을 확인한 뒤 개별 파일을 `adb push`한다. 상대 경로의 보조 파일이 필요한 TC는 별도 배치가 필요하다. UART의 후보 명령 `adb`는 현장 재확인 대상이다. [설정 예시·수정 가능한 확인표](../gui_test/BOARD_CONNECTOR_EXECUTION.md#tc-루트-실행과-adb)
2. 유휴 Host를 중지하고 기존 설치본·프로필·SQLite DB를 백업한다. Linux CLI와 Windows Host에 같은 고정본을 적용한 뒤 Host를 시작하면 DB v4가 `connector_failure_evidence` 테이블과 nullable `connector_runs.evidence_serials_json` 열을 추가한다. 이전 시도의 커널 로그는 소급 수집하지 않는다.
3. 롤백할 때는 Host를 중지하고 현재 DB를 별도로 보관한 뒤 이전 설치본·프로필·업그레이드 전 DB를 복원한다. 백업 이후 실행한 TC 기록은 별도 보관한 DB에 남는다.

## 검증과 회사 인수

- **원본 검증** — 게시한 코드와 동일한 트리에서 Python·Qt 88건과 Chrome 1건이 통과했다. 실패 증거 시험은 Dual 보드 부분 수집, 재접속, 마스킹, 재시작·삭제, 복사형 CLI 조회와 기본 분석기의 HOLD를 검증했다. [T-321 실행 기록](../testing/runs/20261128-connector-path-run.md) · [T-322 실행 기록](../testing/runs/20261128-failure-evidence.md)
- **회사 실행 확인** — 대상 보드의 UART 진입 절차와 ADB 시리얼을 확인하고 세 폴더에서 대표 TC를 실행한다. PASS이면 다음 TC로 진행하는지, 실패하면 즉시 멈추는지 확인한다. 실패한 Single과 Dual에서 TC 출력 끝부분과 보드별 `dmesg` 최근 50줄을 조회한다. 한 보드의 권한 오류와 재접속 후 동일 시도 재조회도 확인한다. [플러그인 조회와 부분 수집 처리](../agents/BOARD_CONNECTOR_PLUGIN_WORKFLOW.md#실패한-시도의-로그-받기)
- **회사 적용 이력** — 실제 회사 파일 위치는 `COMPANY_MAP.md`에 대응시키고, `APPLIED.md`에 PORT-019, 원본·회사 커밋, 적용한 범위, 장비 및 플러그인 수신 결과를 기록한다. 실제 보드의 수집 권한과 전송 지연은 현장에서 측정한다.
