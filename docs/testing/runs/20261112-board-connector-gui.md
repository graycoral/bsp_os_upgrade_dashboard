# 2026-11-12 · 보드 커넥터 GUI/공통 등록·콘솔

기준 HEAD `6734c843c46e986ce5c35a0851c38ac009661b98` + 승인된 기존 timeout/영구 삭제 WIP. 사용자 지시로 Astra 설계 CHANGES_REQUESTED F1~F7을 반영한 Sol 구현이다. 최신 표시명은 보드 커넥터. 제품 변경은 미커밋이며 commit/push/새 EXE·전달 ZIP/회사 SSH·보드·TC·BSP·모델·Jira 실행은 하지 않았다. 독립 코드 리뷰 결과는 실제 후속 기록과 구분하고 Claude 리뷰 완료라고 표시하지 않는다.

RQ-63/D-67/T-222~228/REG-0079. [규범 계약](../../design/BOARD_CONNECTOR_CONTRACT.md), [안내](../../gui_test/TEST_BOARD_CONNECTOR_GUI.md), [PORT-009](../../porting/PORT-009.md).

## 변경 범위

공통 영속 registry/안정된 adapter facade, loopback 인증·역방향 identity 왕복, transport와 semantic revision 분리, source-less Host/TC 실행 bootstrap, 기존 demo/live DB별 단일 Worker 소유, full-host plugin auth/health 접점을 구현했다. 기존 Run identity/source/policy·snapshot/preparation·수동 시험/최종 검토 게이트를 보존한다.

독립 manager·인증 IPC·기존 CLI Host/SSH helper와 동일 Qt real/mock view를 추가했다. 환경설정은 보드 수 1~32/보드별 nested 탭, 연결은 작은 LED/요약, 접힌 로그는 보드 콘솔/TC 실행/연결/플러그인 오류 탭이다. native 파일 선택·COM 읽기 전용 열거·원자 설정/백업·변경 취소·close detach를 제공한다. 저장 공간은 주기 제한·일부 집계가 명시된 읽기 전용이다.

보드 RX 콘솔은 코어 hub가 소유하고 batch에는 해당 보드만 handoff한다. GUI/API는 읽기 구독이며 control COM을 열지 않는다. producer durable 오류/epoch+record seq·retention·한도와 중앙 SQLite 오류 재조회, reference PluginClient를 추가했다. 기존 TC stdout/stderr와 보드 원문은 구분한다. Dashboard는 opt-in 공통 컴포넌트가 열린 화면에서 inventory만 별도 갱신한다.

## 증거와 실패 보존

전체 stdout/stderr·상세 결과·이미지는 `.local-reports/`의 로컬 전용 파일이며 Git에 포함하지 않는다. 주 실행 경로는 `.local-reports/connector-gui-implementation-20261112/`다.

| 실행 | 결과 | 증거/설명 |
|---|---|---|
| 초기 connector 단위/Qt 14건 | PASS | connector-1/2/3.log; 해당 중간 코드만 유효 |
| 기존 timeout/삭제/WindowsRemote/plugin HTTP 집중 67건 | PASS | focused-1.log; 해당 중간 코드만 유효 |
| GUI 전체 1차 | 505 PASS / 24 FAIL | gui-full-1.log; 구버전 `/usr/local/bin/git` PATH, legacy facade의 테스트 주입 호환, 기존 timeout WIP의 새 catalog 메타 기대 누락을 분리 |
| GUI 전체 2차 | 524 PASS / 5 FAIL | gui-full-2.log; `/usr/bin` PATH/legacy 호환 수정 후; catalog 메타 2건과 Mac killpg EPERM 3건 |
| GUI 전체 3차 허용환경 | 533 PASS / 2 FAIL | gui-full-3.log; Mac killpg EPERM→실행 스레드 예외→대기 제한 초과. 보안 assert 실패가 아님 |
| 위 두 TC fixture 재실행 허용환경 | 2 PASS | runner-retry-1.log; 프로세스 종료 규칙/killpg 코드는 약화하지 않음 |
| connector + timeout/영구 삭제 중간 집중 | 50 PASS | connector-8.log; Astra 잔여 4건의 방지 회귀 포함 |
| 호스트/포터블 광역 중간 | 138 PASS / 13 FAIL / 2 SKIP | host-focused-1.log; Linux /proc·process receipt 8건, Mac process_identity 미지원 1건, sandbox loopback EPERM 1건, builder fixture의 기존 build.lock 경계 3건. 고정 hash 불일치라고 해석하지 않음. 관련 없는 Linux 지원을 Mac으로 확대/테스트 약화하지 않음 |
| 두 UI 중간 build | PASS | ui-build-1.log; Dashboard/standalone TypeScript+Vite |
| 브라우저 첫 명령 | NOT_RUN | browser-connector-1.log; 파일 경로 regex로 No tests found |
| 브라우저 두 번째 명령 | 환경 BLOCKED | browser-connector-2.log; listen EPERM. 같은 fixture를 공식 허용환경으로 재실행 |

초기 connector-5의 observer 로컬 변수 누락, connector-7의 durable 오류 acknowledgement 중복을 실패 원본과 함께 보존하고 수정했다. 최종 코드 결과는 아래 최종 검증 절에 기록한다.

## Astra 후속 지적의 방지 회귀

- 전역 control COM/다른 보드 normal RX 충돌: `test_flash_prepare_rejects_all_control_and_other_board_rx_conflicts`와 subset batch B 관찰 유지 시험.
- durable error stream의 empty ACK 후 current snapshot 재합성 중복: `test_durable_error_ack_repoll_no_duplicate_and_stale_history`.
- 오래된 console projection: verified_at 기반 fresh/received_at/stale, 같은 시험 및 `test_monitor_display_stale_preserves_last_known_execution_and_readonly_storage`.
- safe-stop 우회: Host TC, batch reserve, legacy flash, batch prepare 모두 같은 stopping fence. `test_atomic_safe_stop_fence_rejects_new_tc_and_batch`, `test_stop_fence_covers_legacy_flash_and_batch_preparation`.

## 실제 Qt 화면과 미실행 경계

Mac `.venv` Python 3.11.7 x86_64, PySide6-Essentials/shiboken6 6.8.3를 사용했다. 공식 PyPI·Qt 설치 문서와 wheel의 QtWidgets 포함을 확인했다. 설치는 한 번 수행했으며 초기 sandbox DNS 실패와 허용환경 설치 로그는 root의 `.local-reports/connector-qt-install-*/`에 보존한다. 새 EXE/배포 ZIP은 만들지 않았다.

사용자가 Mac 실제 창을 보고 보드 수/보드별 탭/로그 탭을 피드백했다. root가 현재 소스의 별도 격리 Qt widget 렌더링과 QTabBar class/4개 로그 탭·780×560 확인을 수행했다: `.local-reports/board-connector-current-ui-996dc1e0/`의 summary.json/run.log/두 PNG. 이전 combo 캡처는 후속 화면 증거로 재사용하지 않는다. 네이티브 앱 클릭 자동화는 도구의 앱 사용 승인 거절로 BLOCKED이며 offscreen 검사와 구분한다.

실제 Windows Qt/DPAPI/OpenSSH·회사 8765 양방향·실제 control/RX splitter·fastboot/TC·회사 plugin의 실제 오류 수신은 **T-228 NOT_RUN**이다. 보드 콘솔 mock/TC Python fixture/브라우저 route는 실장비 인수가 아니다. 직접 Z:/UNC 공유 원본 실행, 새 자동 GC, Windows Qt wheel을 포함한 새 editable 배포 조립도 미구현/미실행으로 남긴다.

## 최종 검증

최종 결과:

| 명령/범위 | 결과 | 로컬 증거 |
|---|---|---|
| `PATH=/usr/bin:/bin:/usr/sbin:/sbin QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q backend/gui_test/tests tests/test_api.py tests/test_gui_dashboard.py tests/test_gui_test_layout.py tests/test_gui_source_portability.py tests/test_catalog_timeout.py` | **605 PASS / 1 FAIL** | final-python-2.log; 단일 잔여는 `test_contained_process_termination_and_host_reservation[cancel]`의 간헐적 Mac killpg EPERM→대기 실패 |
| 새 connector·기존 timeout/영구 삭제 + 위 cancel fixture 재실행 | **53 PASS** | final-focused-2.log; 종료 확인 코드를 약화하지 않았고 전체 최초 실패는 보존 |
| Dashboard/API/패키징/소스/목록 제한시간 집중 | **111 PASS** | final-focused-1.log; 이후 TC Python bootstrap 보강은 위 최종 회귀에 포함 |
| `bash scripts/build.sh all --skip-install`(Node22 PATH) | **PASS** | ui-build-final-2.log; Dashboard/standalone TypeScript·Vite |
| `npx playwright test settings-sync --reporter=line`(apps/web, 허용 Chrome/loopback 환경) | **13 PASS** | browser-final-2.log 및 browser-final-2-artifacts/; 실제 빌드 화면에서 등록 전→등록→분리→stale 표시, catalog 반복 복사 없음 포함 |

브라우저 browser-connector-3의 unexpected 요청은 기존 timeout WIP의 `/execution-timeouts` 응답을 fixture에 반영하지 않은 것이었고, browser-final의 12 PASS/1 FAIL은 추가된 `TC 실행 제한시간` 카테고리가 기존 정확 옵션 기대에서 누락된 것이었다. 실제 계약에 맞춰 fixture/정확 기대를 갱신한 뒤 같은 13건을 재실행했다. Python final-python-1의 604 PASS/1 FAIL 역시 wheel entrypoint 정확 기대에 기존 integration과 새 connector script가 누락된 시험 유지보수 문제였고 최종 회귀에서 수정 검증했다. 실패 로그는 지우지 않았다.

추가 F2: 잘못되거나 미설정인 외부 TC Python은 GUI/Host 상태 bootstrap을 막지 않는다. 별도 `tc_python_configured_v1`/execution_ready와 서버 Preflight/integration/legacy 실행 게이트가 실제 TC를 차단한다. GUI Python으로 자동 대체하지 않는다(기존 source-root 개발 CLI의 호환 기본은 유지).

source·시험 후보 고정은 로컬 `source-manifest.json`의 경로별 SHA256과 source_digest를 따른다. 이 manifest는 게시 커밋이 아니며 로컬 전용이다. [Astra 재검토](20261112-board-connector-code-review.md)는 위 4건 코드 읽기 승인으로 한정한다. 전체 단일 실행을 모두 PASS라고 표현하지 않는다. 간헐적 Mac process group 시험과 별도 광역 호스트의 Linux/lock 제약은 남은 환경 검증 사항이며 Windows/회사 인수를 대체하지 않는다.

최종 문서 검사 `python docs/testing/validate_docs.py` PASS: 상대 링크 1,232·요구사항63·시험228·오류0(`docs-final-2.log`). `git diff --check` PASS. source-manifest 경로별41개 SHA256 재계산 mismatch0(`final-verification.json`); 후보 source_digest `891f1cacb2a9a0d697703622badee0ea698557b4e583d6a12f610e99cd014067`. 최초 보존 대상 WIP17개 중7개는 바이트 동일,10개는 연결/실행 준비·콘솔/삭제 연계를 위해 의도적으로 통합했고 삭제/전체 덮어쓰기를 하지 않았다. docs CSV의 신규7행 CRLF 공백 경고도 LF로 수정한 후 검사했다.

root 인계 확인에서도 문서 검사·공백 검사 PASS와 제품/시험 41개 파일 SHA256 mismatch0을 독립 확인했다(`.local-reports/board-connector-root-final-83a8ab9d/`). root의 별도 브라우저 실행은 초기 heading 대기 실패로 보존했다(`.local-reports/board-connector-root-browser-21044b77/`); 이후 Sol의 순차 13건 통과와 구분하며 root가 브라우저를 통과했다고 표시하지 않는다. 모든 로컬 원본은 Git에 포함하지 않는다.

## 게시 전 재검증 · 사용자 후속 승인

사용자가 자동검증 재시도와 커밋·푸시를 명시 승인했다. 앞 절의 미게시 표현은 최초 구현 시점의 기록이다. 원본 로그는 `.local-reports/board-connector-publish-a2732952/`에만 보존한다.

- 동일 광역 Python 명령 재실행: **606 PASS**, 종료 코드 0 (`python.log`). 과거 Mac 취소 시험 실패는 삭제하지 않으며 이번 실행에서 해당 사례도 통과했다.
- 동일 settings-sync Chrome 회귀: **13 PASS**, 종료 코드 0 (`browser.log`, `browser-artifacts/`).
- `bash scripts/build.sh all --skip-install`: 두 UI build **PASS**, 종료 코드 0 (`build.log`).
- 최신 공통 Qt 위젯 offscreen 렌더링 **PASS** (`qt-render.log`, `summary.json`): 제목 보드 커넥터, 780×560, 실제 `QTabBar`와 보드 콘솔/TC 실행/연결/플러그인 오류 4탭 확인. 제품·시험 41개 파일은 앞선 source manifest와 SHA256 mismatch 0이다.
- 사용자 승인 후 네이티브 앱 접근을 재요청했지만 도구가 `Computer Use was not approved to use Python`을 반환했다. 네이티브 창 클릭 자동화는 계속 **BLOCKED**이며 Qt 위젯 검사와 구분한다.

게시 범위는 보드 커넥터와 함께 검증한 TC 제한시간·세션 영구 삭제 및 관련 문서다. 기존 별도 전체 대시보드 자동설치 설계 초안은 로컬에 보존하고 게시에서 제외한다. 실제 Windows/회사 T-228은 NOT_RUN이며 새 EXE·ZIP은 생성하지 않는다. 제품 고정 커밋은 후속 PORT-009 기록을 따른다.

게시할 index를 별도 디렉터리로 추출한 문서 검사 PASS: 상대 링크 1,224·요구사항63·시험228·오류0 (`staged-docs.log`). 신규 파일까지 포함한 공백 검사에서 timeout 시험 파일의 EOF 여분 빈 줄 1개를 제거했다(시험 로직 변경 없음). 이 공백 정리 이전 41개 hash 비교와 구분하며 최종 게시 내용은 Git commit으로 고정한다.
