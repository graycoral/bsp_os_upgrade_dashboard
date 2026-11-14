# 보드 커넥터 상태 설명·전원 버튼·패널 정렬

2026-11-14 · RQ-63/T-259. 기준 b685ab9와 미커밋 preview/간략 UI 수정 위의 후속이다.

- Windows/SSH/서버/왕복 이름·상태등에 작은 hover/focus 설명 상자를 제공한다. 역할과 현재 상태, stale 확인 필요를 표시한다. Esc로 닫고 주기 갱신 시 focus/hover를 유지한다.
- 연결 시작/종료를 전원 아이콘 버튼 하나로 합쳤다. Windows 실행부·SSH·서버 연결이며 TC 실행은 아니다. 연결/종료 중·pending·stale에서 중복 조작을 차단하고 RUNNING/RESERVED/UNKNOWN 작업이 있으면 종료를 비활성화한다. 서버의 기존 종료 안전 검사는 유지한다.
- 작은 보드 항목을 유지하며 데스크톱의 목록 외곽을 상세 패널 높이에 맞춘다. 로그는 접기를 없애고 항상 표시한다. 연결 상세/콘솔 안내와 소스/실행 경로만 접을 수 있다.

## 검증

`python scripts/test_connector_browser.py`를 현재 최종 UI에서 실행했다. Chromium **14 PASS**, 24.8초. 기존 14개 브라우저 회귀에 설명 상자/갱신 중 focus·Esc·stale 설명, 동일 버튼 시작/종료·작업 중 차단, 패널 정렬·로그 상시 표시 검증을 포함한다.

로컬 근거는 `.local-reports/20261114-connector-status-help/browser-1.log`, `browser-2.log`, `source-manifest.json`이다. browser-1은 로그 접기 제거 전의 중간 14 PASS이며 browser-2가 최종 코드 근거다. native Chrome의 실제 Mac preview를 새로고침하여 단일 전원 버튼과 접기 없는 로그 보기를 확인했다. 실제 Windows·UART·SSH·PuTTY·장비 인수는 NOT_RUN이다. DB/API·새 의존성·실행 코어 변경은 없으며 새 독립 리뷰/커밋/푸시는 하지 않았다.
