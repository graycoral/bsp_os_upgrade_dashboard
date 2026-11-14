# 보드 커넥터 간략 화면 검증

2026-11-14 · RQ-63/T-258. 기준 `b685ab9ada779bc60bbeb2500fb1adbfb7d63607`과 로컬 preview 수정 위의 후속 UI 변경이다.

- 내 보드 → 보드 리스트, 작은 한 줄 목록과 COM 표시. 전체/보드/Windows·SSH·서버·왕복 상태는 신호등과 tooltip/접근 가능한 이름을 제공한다. stale 정상 단계는 UNKNOWN으로 바꾸며 제어 차단을 유지한다.
- 멀티플렉서·PuTTY/콘솔 설명은 기본 접힌 연결 상세에 배치한다. 로그는 기본 180px, 세로 크기 조절과 접기/열기를 제공하며 갱신 시 접기 상태를 유지한다.
- TC 실행 로그 탭을 TC 로그로 바꾸고 TC stdout/stderr와 보드 UART 수신 출력을 구분한다. PuTTY·수동 제어권·실행 정책과 DB/API는 변경하지 않았다.

## 검증

- `.venv/bin/python scripts/test_connector_browser.py`: Chromium **14 PASS**, 21.3초. 새 간략 화면 시험과 기존 연결·편집·로그·충돌·stale·설정·좁은 화면/키보드 회귀를 포함한다. 로그 `.local-reports/20261114-connector-compact-ui/browser-1.log`.
- `.venv/bin/python -m pytest backend/gui_test/tests/test_connector_web.py -q`: **36 PASS**, 1.70초. 로그 같은 폴더의 `api.log`.
- `docs/testing/validate_docs.py` 및 `git diff --check`: PASS.
- `node --check packages/gui-test-ui/src/connector_web/view.mjs`: PASS.
- 실행 중인 Mac CLI preview의 native Chrome을 새로고침하여 보드 리스트·상태등·접힌 연결 안내·작은 로그·TC 로그 명칭을 확인했다. 보드2대와 COM7/8은 모의 데이터다.
- 정확한 코드/시험 해시는 같은 로컬 폴더 `source-manifest.json`에 보존한다. 브라우저 원본 결과/스크린샷은 `.local-reports/20261114-connector-web-review/browser-1794651356039247000/`에 있다.

회사 Windows·실제 UART/USB·SSH·PuTTY·장비 인수는 NOT_RUN이다. 이전 Astra 승인을 이번 UI 후속의 독립 승인으로 재사용하지 않는다. 이번 변경은 구현자 검증이며 아직 미커밋이다.

## 게시 전 현재 파일 재검증

기존 검증 이후 연결 시작/종료를 단일 전원 버튼으로 합친 변경과 연결 단계 tooltip 조정이 추가되어 현재 파일을 다시 검증했다. 전원 버튼은 연결 시작/종료만 요청하며 TC 시작 버튼이 아니다. 진행·예약·UNKNOWN·stale 또는 요청 처리 중에는 종료/중복 요청을 차단한다. 기존 서버 측 제어 검사는 유지한다.

- `.venv/bin/python -m pytest backend/gui_test/tests/test_connector_web.py -q`: 36 PASS, exit 0.
- 고정 Node/Chromium 경로의 `.venv/bin/python scripts/test_connector_browser.py`: 14 PASS, exit 0. 시작→종료 전환과 시험 중 종료 차단, tooltip hover/focus/Escape·polling 보존을 포함한다.
- 로그와 최종 source/test manifest: `.local-reports/20261114-connector-publish-check/`. 이전 manifest를 이번 코드의 근거로 재사용하지 않는다.
- 문서/공백 검사를 통과한 변경을 사용자 지시로 게시한다. 실제 회사 인수와 별도 독립 코드 리뷰는 수행하지 않았다.

현재 소스 SHA256 `f2dd970143c267677a993d821ba0b884067422edf2f31de6ce7ed7609f9bdbbb`, 시험 SHA256 `78a6abe73cad1ac301fc5c9ceebfa08a0901d36e8d100974c91403159c77bd16`.

문서 검사 첫 실행은 TEST_RESULTS.csv의 T-258 중복 행으로 실패했다. 이 파일은 현재 결과 한 행을 유지하는 형식이므로 최신 기준으로 교체하고 이전 시험 근거는 위 실행 이력에 보존했다. 수정 후 재검사했다.
