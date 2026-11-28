# 2026-11-22 · 웹 보드 커넥터 찾아보기와 TC 경로 재현

기준 커밋 `557b7d070a195c44f17bf2eb05e0d8fd0dd7c73d`. 제품 코드와 DB 스키마는 수정하지 않았다. macOS arm64에서 Python 3.11.7, Node 22.23.5, Chrome 157.0.8103.79 및 임시 루프백 환경을 사용했다.

## T-308 · 찾아보기 안내 누락

| 조건 | 기대 | 관찰 |
|---|---|---|
| 미리보기 → 환경설정 → TC Python, SSH 개인 키, PuTTY의 `찾아보기` | 선택할 수 없는 이유와 전체 경로 직접 입력 안내 | 3 FAIL. `/api/pick`은 모두 HTTP 200. 미리보기 API는 빈 경로를 반환했고 화면 안내는 비어 있었다. 입력 초안과 버튼은 유지됐다. |
| TC Python `찾아보기` → Windows 선택 API를 모의로 지연 → `PICKER_UNAVAILABLE` 반환 | 응답 대기 표시. 실패 응답 후 직접 입력 안내, 초안 유지, 버튼 재활성화 | 1 FAIL. 요청이 전송되고 버튼이 잠겼지만 응답 대기 표시는 없었다. 409 응답 뒤 직접 입력 안내, 초안 유지, 버튼 재활성화는 확인했다. |

- `.venv/bin/python scripts/test_connector_browser.py`의 모의 fixture를 그대로 사용하고 Playwright에 `--grep 'T-308|TC source replacement|server settings retain overrides'`를 추가했다. **신규 T-308 4 FAIL, 기존 경로 관련 시험 2 PASS**, 종료 1. `browser-focused.log` 및 `browser-1795326715876065000/artifacts/`에 화면·trace가 있다. 시험 지문은 [결과 CSV](../TEST_RESULTS.csv)의 시험 diff SHA-256이다.
- `.venv/bin/python -m pytest -q backend/gui_test/tests/test_connector_web.py -k 'native_picker or preview'`는 4 PASS, 종료 0. `picker-api.log`에 선택·취소 모의와 미리보기 API 확인을 보존했다.
- 초기 전체 웹 브라우저 실행은 관련 시험에 집중하기 위해 중단했다. 6 PASS, 기존 콘솔 오류 표시 시험 1 FAIL, 1 중단, 15 미실행, 종료 130. `browser.log` 및 `browser-1795326639958959000/artifacts/`에 보존했다.
- REG-0117 미수정. 실제 Windows 공통 대화상자의 미표시 원인과 회사 인수 T-250은 확인 전이다.

### 저장소에서 다시 재현하기

T-308은 결함 재현 시험이다. 기본 커넥터 회귀 실행에서는 건너뛴다. Playwright와 Chromium이 준비된 원본 체크아웃에서 아래 명령을 실행한다. 안내가 누락된 버전에서는 4건이 실패한다.

```sh
BSP_REPRO_T308=1 python scripts/test_connector_browser.py --grep T-308
```

실제 Windows 확인 절차는 [회사 전달 안내](../../porting/PORT-009.md#브라우저-파일-선택과-tc-경로-확인)를 따른다.

## 공통 TC 경로 추가 확인

모의 Windows Host와, 같은 임시 Linux runtime을 읽는 Monitor API 및 플러그인 클라이언트로 REG-0118을 확인했다. 온라인 시험의 연결 영수증은 격리 Monitor 루프백 주소로 대체했다. SSH와 실제 Windows는 실행하지 않았다.

1. Linux 공통 설정에 첫 TC 폴더를 저장하고 플러그인이 Windows Host에 목록을 보냈다. Windows `ManagerActions.shared`에서 이 경로를 읽고 두 번째 유효한 경로를 저장하면 플러그인이 같은 `shared-settings.db`에서 두 번째 경로를 읽었다.
2. 직후 Host `/v1/test-status`는 여전히 첫 경로·첫 스크립트를 반환했고 `projection_stale`은 `false`였다. 플러그인이 목록을 다시 보내면 두 번째 경로·스크립트를 반환했다. [직결 설계](../../design/DIRECT_CONNECTOR_ARCHITECTURE.md#73-tc-카탈로그-투영-put-v1tc-catalog-projection--agent-monitor-없는-windows-tc-표시)는 Monitor 스캔도 갱신 경로로 명시한다. 현행 `push_tc_projection()` 호출은 플러그인 경로에서 확인했다.
3. 공통 설정 연결 영수증이 없는 직결 상태를 별도로 확인했다. TC 경로와 제한시간을 함께 제출하면 제한시간만 로컬에 저장되어 동기화 대기 항목에 남고 응답은 성공이었다. Windows 웹 폼은 이 상태에서도 TC 경로를 편집할 수 있다. Linux 공통 경로는 그대로였다.

온라인 결과는 `tc-path-check.log`에 보존했다. 첫 오프라인 시도는 macOS 임시 경로의 심볼릭 링크로 중단됐다. 실제 경로로 다시 실행한 오프라인 확인은 `tc-path-offline.log`에 보존했다.

명령 로그는 로컬 전용 `.local-reports/20261122-connector-file-picker.GOoEL6/`, 브라우저 fixture 산출물은 로컬 전용 `.local-reports/20261114-connector-web-review/` 아래 위 실행 폴더에 있으며 저장소에 포함하지 않는다.

## 2026-11-29 · 게시 및 회사 전달 문서 확인

- `921a57f21af130daa28d649c445f3177b0a27d9f` 기준 격리 체크아웃에서도 모의 브라우저 재현 시험 4건이 같은 안내 누락으로 실패했다. 기본 실행에 `--grep T-308`만 지정하면 4건을 건너뛴다. 로그 `browser-repro.log`, `browser-default.log`.
- [보드 커넥터 사용 가이드](../../gui_test/TEST_BOARD_CONNECTOR_GUI.md), [PORT-009](../../porting/PORT-009.md), [PORT-013](../../porting/PORT-013.md)에 사용 방법과 현지 확인 범위를 기록했다. `export --without-ui`로 새 전달 폴더를 생성해 `verify --pristine`과 위 세 문서의 원본 바이트 및 manifest 해시 일치를 확인했다.
- [현재 회사 전달본의 시작 안내](../../../deliveries/company-handoff-7691c0e/00_START_HERE.md)에서 추가 인수 절차를 연결했다. 고정 패키지 `7691c0e`의 `verify --pristine` 및 `verify-evidence`가 통과했다. 게시 변경은 원본 재현 시험과 안내 문서에 해당한다. 실환경 인수 상태는 미실행이다.

이번 확인의 원본 출력은 로컬 전용 `.local-reports/20261129-t308-publish.cbXlUd/`에 있다.
