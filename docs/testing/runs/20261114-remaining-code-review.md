# 잔여 구현 독립 코드 리뷰 · 2026-11-14

## 범위와 현재 판정

- `review_id`: `20261114-remaining-code-01`
- 기준: `main` / `e4f53ca1ec288feb3eb1b9ccff8335a398ad321c` 위 미커밋 변경. 최종 커밋·회사 배포 승인은 아니다.
- 검토자: 별도 Codex 세션 `/root/plugin_code_review`. 사용자 요청에 따라 부모가 `gpt-6-astra` / `xhigh`로 호출했고 도구가 수락했다. 실제 런타임 모델/effort를 별도로 반환받았다는 의미는 아니다. **Claude 검토가 아니다.**
- 최초 판정: **CHANGES_REQUESTED**. RC-C01~07의 발견·수정 이력을 보존한다. 수정 및 최종 재시험 후 판정: **APPROVED — 아래 명시한 코드·hash 범위의 로컬 구현 승인**.
- 기존 [플러그인 중심 코드 리뷰](20261114-plugin-centric-code-review.md)의 승인 범위를 확장하는 별도 리뷰다. 당시 제외했던 브라우저 보드 커넥터와 신규 분석 자동화·모듈 재시도·캐시 보관·설치 복구를 포함한다. 과거의 범위 제외와 실패 기록을 소급 변경하지 않는다.
- 추적 범위: 기존 브라우저 연결기 RQ-63/65/66, T-247~250 및 잔여 구현 **RQ-68/D-72/T-251~256/REG-0089**.

AGENTS.md, CLAUDE.md, portable-feature 스킬, 관련 설계·계약·로그 처리 규칙을 적용했다. 제품 코드는 수정하지 않았다. 실제 회사 Linux/Windows 설치, 회사 ACON/모델·조치 검증 프로그램, SSH/보드/플래싱/회사 TC/Jira는 **NOT_RUN**이다. 시험은 임시 디렉터리·모의 어댑터·로컬 TC/프로세스 fixture를 사용한다.

## 검토 대상

- `connector/web.py`, `web_actions.py`, `native_picker.py`, `web_assets/host.mjs`, `connector_web/view.mjs`·CSS·패키징, 브라우저 기본 진입점과 CMD/소스 launcher.
- `standalone/analysis_runtime.py`, 기존 Worker/앱 factory/API 연결, 해시 고정 명령 분석기·독립 검증기·기본 HOLD.
- `core/failure_analysis.py`, `core/ports.py`, `services/module_test_selection.py`의 모듈 Run 재시도 및 기존 BSP 선택/게이트 재확인.
- `core/retention.py`, `execution/retention.py`, `api/storage.py`, 생산자/참조 수락 잠금과 Linux/Windows 유지보수, 공통 설정·Qt·브라우저 저장 공간 UI.
- `apps/agent-monitor/manage.py`, `recovery.py`, `prerequisites.py`, OS 준비 스크립트의 기존 runtime 채택·백업·롤백·release 정리·검증된 공급물 설치.

## 발견 이력

### RC-C01 · P2 · 확인된 탭 UI 요구사항 회귀 — 해결

초기 `connector_web/view.mjs`는 로그 종류를 select로 제공하고 모든 보드 설정 fieldset을 한 화면에 쌓았다. 사용자 확정 요구사항인 로그 종류 탭과 보드 설정 하위 탭을 충족하지 않았다. 탭·키보드 이동·초안 보존·숨겨진 보드 필수값 이동을 재검토했다. 중복 invalid handler도 제거했으며 3개 보드 중 2·3번 COM이 모두 비었을 때 첫 오류인 2번 탭과 입력란으로 이동하는 브라우저 회귀가 통과했다.

### RC-C02 · P2 · 읽기 전용 CMD 진단이 설치로 진입 — 해결

새 `board-connector.cmd`는 Python 후보를 찾지 못하면 `--diagnose` 여부와 무관하게 BC-29 PowerShell/winget 준비를 실행했다. 읽기 전용 진단 약속과 충돌한다. 진단에서는 준비를 건너뛰고 후보/설치 부재를 보고해야 한다. Python 스크립트 내부의 diagnose 분기만으로는 Python 자체가 없는 CMD 경로를 막지 못한다.

최종 CMD는 설치 분기 전에 전체 인자에서 `--diagnose`를 확인한다. 정적 경계·Python diagnose 회귀를 확인했으며 native CMD 실행 회귀는 현재 macOS에서 SKIP이다. 실제 Windows 확인을 수행했다고 표시하지 않는다.

### RC-C03 · P2 · Linux SSH 준비가 불필요한 Python 3.13 설치를 요구 — 해결

초기 `bootstrap-prerequisites.sh`는 지원 Python이 이미 있고 SSH만 없어도 배포판 기본 Python 대신 `python3.13` 패키지를 무조건 요청했다. 지원되는 기존 Python을 재사용하고 누락된 SSH만 준비하는 경로와, Python 자체가 없을 때의 배포판 패키지 설치 후 지원 버전 검사가 필요하다.

최종 apt/dnf 분기는 지원 Python이 있으면 SSH만 준비하고, 없으면 배포판 기본 Python/venv 패키지를 준비한 뒤 지원 범위를 확인한다. shell mock에서 두 경로의 고정 argv를 확인했다. 실제 OS package manager는 실행하지 않았다.

### RC-C04 · P2 · 공급 TC 환경의 손상을 receipt만으로 재사용 — 해결

초기 `prerequisites.install_supplied()`는 signed manifest receipt revision이 같으면 `REUSED`를 반환했다. 이전 설치 후 `supplied-tc-environment`의 interpreter를 삭제하거나 고정 패키지가 손상돼도 재사용이 성공으로 표시된다. 앞에서 환경 재생성 명령을 준비해도 receipt 분기가 실행을 건너뛴다. 설치된 환경을 다시 검증한 후 재사용하도록 요청했다.

최종 구현은 interpreter, 고정 distribution 버전, RECORD에 기록된 파일 hash를 확인한다. 검사는 `-I -S`와 명시 site-packages 경로를 사용하여 회사 TC import 및 `.pth` 시작 hook을 실행하지 않는다. 후속 검토에서 동일 버전 손상은 일반 pip install이 건너뛰는 점도 지적했고, 최종 설치는 `--force-reinstall`과 기존 offline/hash 제한을 함께 사용한다. 삭제된 환경·같은 버전 손상 회귀를 확인했다.

### RC-C05 · P1 · 캐시 전체 순회·삭제 동안 실행 기록 쓰기 잠금 유지 — 해결

초기 `core/retention.collect()`는 `BEGIN IMMEDIATE`를 전체 `_measure()`/`shutil.rmtree()` 동안 유지했다. 큰 캐시에서 15초 SQLite busy timeout을 넘으면 정상 `Manager.emit()`/`finish()`가 실패하고 DashboardWorkers가 해당 Worker의 스케줄링을 중단할 수 있다. Windows collector도 전체 작업 동안 `host.lock`을 유지하여 제어·상태·종료 처리를 지연시킨다. 별도 executor만으로 공유 잠금 문제는 해결되지 않는다.

임시 DB에서 `collect_trees`를 느린 파일시스템 대기로 바꾼 뒤 별도 연결의 `BEGIN IMMEDIATE`가 `database is locked`로 실패함을 재현했다. 생산자/참조 보호를 유지하면서 긴 파일 작업을 DB/실행 제어 잠금 밖으로 옮기는 수정과 동시성 회귀를 요청했다.

최종 구현은 scan과 격리 후 삭제를 DB/control 잠금 밖에서 수행한다. 생산자 잠금과 짧은 writer transaction 안에서는 현재 참조와 후보 inode/mtime를 재확인하고 atomic rename으로 격리한다. Windows 업로드 publication도 별도 cache 잠금을 사용하며 Host.start/FlashService.start_prepare와 잠금 순서를 공유한다. 신선한 격리 디렉터리는 다른 collector가 건드리지 않으며 종료 시 in-flight 정리를 기다려 process ownership을 유지한다. 느린 Linux scan/delete, Windows scan/delete/publication 중 writer/control 잠금 획득과 scan 뒤 생성된 참조 보존을 시험한다.

최종 증분에서는 한 번에 최대 32개만 격리하고 `batch_limited`를 표시한다. READY installer 캐시 재사용도 1시간의 참조 수락 유예를 갱신하며, async 업로드에서 cache 잠금이 필요한 status 조회는 threadpool로 넘겨 event loop를 막지 않는다. 이 증분을 별도로 재시험했다.

### RC-C06 · P2 · Windows 정리 결과의 응답 wrapper를 UI가 그대로 표시 — 해결

`connector_cleanup`은 `{state: 'CHECKED', runner_id, report: {...}}`를 반환하지만 초기 React StorageControl과 브라우저 cleanup 렌더러는 wrapper만 읽었다. 따라서 Windows는 항상 `CHECKED`만 보이고 실제 예정/삭제 용량, 보호 파일로 인한 한도 초과, 일부 집계 여부가 사라진다. 성공 시 내부 report를 표시하고 실패 상태는 유지하도록 요청했다.

두 UI가 내부 report를 풀어 표시하도록 수정했다. 실제 CHECKED/report 구조를 사용한 Windows 2 MiB 및 보호 파일 한도 초과 표시 회귀를 확인했다.

### RC-C07 · P2 · 오프라인 이관 검사가 일반 Run의 미래 실행 정책을 누락 — 해결

초기 `recovery.inspect()`는 일반 Run의 `retry_policy`를 읽었지만 실제 저장 필드는 `execution_policy`다. 임시 PAUSED Run에 `execution_policy='future-policy'`를 넣으면 `compatible=true`, `adoptable=true`로 판정하는 결함을 재현했다. 기존 Worker는 미래 정책을 거부하므로 이 결함이 하드웨어 배정 우회는 아니지만, 호환 이관 판정이 틀렸다.

최종 검사는 top-level execution_policy와 integration.retry_policy를 각각 확인하고 미래 값·서로 다른 정책을 거부한다. 미래 일반 정책, 미래 integration 정책, 서로 다른 알려진 정책 회귀를 확인했다.

## 추가 변경 확인

구현 담당자가 broad 회귀에서 발견한 `ProcessTree.stopped()/stop()`의 POSIX EPERM/EACCES 예외도 검토했다. 접근할 수 없는 process group을 종료됨으로 취급하지 않고 False를 반환하여 기존 실행부가 UNKNOWN을 기록하도록 한다. ProcessLookupError의 기존 종료 증거 조건은 유지한다. 해당 모의 errno 회귀는 실제 프로세스에 신호를 보내지 않는다.

health registry 응답에 기존 `instance_id`가 누락된 변경은 field를 보존하는 수정과 실제 앱 factory/TestClient 회귀를 대조했다. 초기 health 회귀의 403은 TestClient peer 설정 오류이며 제품 인증을 약화하여 통과시키지 않았다.

## 독립 실행 근거

전체 로그는 `.local-reports/20261114-remaining-code-review/` 아래 로컬 전용이며 Git에 포함하지 않는다.

| 실행 | 결과 | 로그 |
|---|---|---|
| connector_web / analysis_runtime / module_analysis_retry / module_selection / failure_analysis 집중 pytest | 185 PASS, exit 0; 이후 변경 전 중간 근거 | `core-web-01.log`, `core-web-01.exit` |
| GC 공유 잠금 재현 첫 시도 | fixture 오류, exit 1: macOS `/var` symlink 경로를 LaunchLock이 거부. 제품 실패로 계산하지 않음 | `retention-lock-repro.log`, `retention-lock-repro.exit` |
| 같은 fixture 경로를 resolve한 GC 재현 | 결함 재현, exit 0: `WRITE_DURING_SCAN=BLOCKED database is locked` | `retention-lock-repro-02.log`, `retention-lock-repro-02.exit` |
| installer/lifecycle/launcher/setup 집중 pytest | 137 PASS / 19 SKIP, exit 0; 후속 공급물·정책 수정 전 중간 근거 | `installer-01.log`, `installer-01.exit` |
| 브라우저 첫 독립 실행 | 환경 실패, exit 1: shell PATH에 npx 없음. 임시 fixture 종료됨 | `browser-01.log`, `browser-01.exit` |
| 고정 로컬 Node/browser 경로로 브라우저 재시험 | **12 PASS, exit 0** | `browser-02.log`, `browser-02.exit` |
| 미래 일반 정책 adoption 검사 모의 재현 | 결함 재현, exit 0: compatible/adoptable true | `adoption-policy-repro.log`, `adoption-policy-repro.exit` |
| 최종 집중 Python 17개 파일 | **432 PASS / 19 SKIP, exit 0**, 의존성 deprecation warning 24건 | `final-python-01.log`, `final-python-01.exit` |
| 마지막 GC 제한·유예 및 UI 연결 증분 Python | **78 PASS, exit 0**; 앞 시험과 겹치므로 건수 합산하지 않음 | `final-delta-02.log`, `final-delta-02.exit` |
| 최종 브라우저 연결기 | **13 PASS, exit 0** | `browser-final-03.log`, `browser-final-03.exit` |
| `git diff --check` | PASS | 최종 정적 확인 |

집중 시험 명령:

```sh
.venv/bin/python -m pytest -q \
  backend/gui_test/tests/test_connector_web.py \
  backend/gui_test/tests/test_analysis_runtime.py \
  backend/gui_test/tests/test_module_analysis_retry.py \
  backend/gui_test/tests/test_module_selection.py \
  backend/gui_test/tests/test_failure_analysis.py
```

최종 Python 실행은 위 5개 파일에 `test_retention.py`, `test_process_uncertainty.py`, `test_windows_runner.py`, `test_tokenless_connections.py`, `test_source_snapshots.py`, `test_plugin_integration_batches.py`와 `tests/test_agent_monitor_{recovery,lifecycle,manager,delivery}.py`, `tests/test_board_connector_launcher.py`, `tests/test_setup_runtime.py`를 더했다. 마지막 증분은 `test_retention.py`, `test_plugin_integration_pipeline.py`, `test_plugin_integration_snapshots.py`, `test_connector_web.py`를 재실행했다.

브라우저는 `scripts/test_connector_browser.py`로 매번 새 임시 mock server를 실행했다. 초기 npx 부재 후 저장소의 고정 Node v22.23.4 및 로컬 Playwright browser 경로를 사용했다. 실제 보드나 기존 실행 서비스에 연결하지 않았다. macOS에서 건너뛴 Windows CMD/OS 전용 회귀는 실제 Windows PASS로 계산하지 않는다.

부모 구현 세션의 별도 통합 근거도 로그 끝을 확인했다: `.local-reports/20261114-remaining-implementation/broad-python-04.log` **1009 PASS / 24 SKIP**, `monitor-browser-04.log` **6 PASS**. 두 UI 빌드 결과와 복사 전달 검증은 [통합 구현 기록](20261114-plugin-centric-implementation.md) 및 잔여 구현 기록의 실제 실행을 따른다. 부모 실행을 검토자가 독립 실행한 것처럼 표시하지 않는다.

## 최종 판정과 고정 범위

검토 범위에서 미해결 P1/P2 발견 사항은 없다. 기본 분석기는 HOLD만 생성하며 회사 조치 검증 adapter가 없는 상태에서 자동 재실행하지 않는다. UNKNOWN·실행 중·예약을 오프라인 이관이나 캐시 정리로 지우지 않으며, Run/DB/로그와 실패 snapshot 근거를 보존한다. 보관 한도는 보호 대상과 32개 처리 제한 때문에 일시적으로 초과할 수 있고 화면이 이를 표시한다.

최종 소스·시험 **71개 파일**의 SHA256을 `.local-reports/20261114-remaining-code-review/reviewed-source.json`에 고정했다. manifest SHA256은 **`e45926f045046da7530935fa810b8b79a6bb8991575c52ffa9e501e14910f116`**이다. 마지막 Python 증분·브라우저 재시험 전후 대상 파일의 변경은 없었다. 앞선 432 PASS 실행 뒤 변경된 7개 파일은 별도 증분 재검토·재시험 대상으로 기록했으며, 이전 PASS만으로 최종 변경을 승인하지 않았다.

이 승인은 해당 미커밋 로컬 구현의 코드 리뷰다. 실제 회사 설치·서명된 회사 공급물·Windows picker/CMD/OS package manager·회사 분석/검증 프로그램·ACON·보드 인수는 **NOT_RUN**으로 남는다. 커밋·푸시·회사 배포·장비 실행을 수행하지 않았다.
