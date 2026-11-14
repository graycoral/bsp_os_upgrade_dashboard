# PuTTY 입력 통합과 간략 화면

2026-11-14 · RQ-63/66·D-74·T-265/266. RQ-69 공통 연결 작업을 보존하면서 이 후속의 제어/UI 변경을 검증했다. 실제 회사 장비와 PuTTY 실행은 하지 않았다.

PuTTY 열기에서 Host의 기존 실행 게이트 아래 배타 입력 grant를 받은 뒤 창을 연다. Raw 연결 종료와 별도의 프로세스 종료 감시가 입력을 반환한다. 실행 실패·소켓 연결 전 창 종료도 정리하며 이전 창은 자신의 grant만 반환한다. legacy 수동 API를 보존하고 기본 웹/Qt 화면의 별도 수동 버튼을 제거했다.

메시지는 연결 단계 옆에 표시하고 길면 아래로 넘긴다. 연결된 Linux 서버는 보드 리스트 아래 작게 표시하며 stale에서는 숨긴다. 중복 한글 제목/일반 소개·로그 제목을 제거하고 로그 탭을 상단과 같은 스타일로 맞추며 폴더 열기를 옆에 둔다. 로그 → 소스/실행 경로 → 연결 상세 순서와 로그 상시 표시를 유지한다.

## 실행 근거

원본 로그는 `.local-reports/20261114-connector-putty/`에 보존한다.

- `python-1.log`: 88 PASS / 1 FAIL. 제어 차단은 정상이나 바뀐 오류 문구와 기존 시험의 문자열 matcher가 달랐다. 오류 코드 SERIAL_BUSY를 검증하도록 시험을 수정했다.
- `python-2.log`: 89 PASS. 실제 loopback Raw TCP, 모의 UART·PuTTY 프로세스로 입력/수신/반환/경합을 확인했다.
- `python-3.log`: transport payload 시험 추가 후 90 PASS.
- `python-final.log`: 다른 보드의 입력 독립성·동일 창 중복 방지 후 **91 PASS**, 8.83초.
- `browser-1.log`: 15 PASS, 24.2초. 최종 로그 탭 스타일 적용 전의 중간 검증.
- `browser-2.log`: 최종 UI **15 PASS**, 23.9초. 연결/제어 차단·편집·stale·다중 탭/CSRF·좁은 화면/키보드·알림/연결 서버·로그 탭/폴더 버튼을 확인했다.

명령: `.venv/bin/python -m pytest backend/gui_test/tests/test_putty_control.py backend/gui_test/tests/test_serial_multiplexer.py backend/gui_test/tests/test_connector_web.py backend/gui_test/tests/test_board_connector.py -q`, `.venv/bin/python scripts/test_connector_browser.py`(고정 Node/Chromium). 정확한 코드/시험 SHA는 로컬 `source-manifest.json`에 보존한다. API/프로세스/브라우저 mock 시험을 실제 Windows·UART/USB·SSH·PuTTY·회사 TC 인수로 확대하지 않는다. 새 DB 이전/패키지 의존성은 없으며 안전 복원은 연결·TC 종료 후 같은 이전 코드 묶음으로 수행하고 runtime/설정/기록은 보존한다.

독립 리뷰 범위와 후속 게시 기준은 아래를 따른다.

기준 부모 커밋은 `0180fea8ad15d4f072ac77cb572c7a4f6d91d95f`이며 RQ-69 게시 변경을 보존했다. 현재 제품 SHA256 `0077aea54d351a4fe50cb4d3e3f026862fb964463aa6b5f49fec3194d69633ce`, 시험 SHA256 `44d43010124b8c18cff2769c30b031980da636b79bb690f88635ac180c06ee2c`.

최종 서버 표시 보완: 설정 화면에 남은 과거 주소를 사용하지 않고 실제 probe/status의 제한된 connection_server 정보를 표시한다. 다른 탭에서 서버가 바뀌어도 오래된 주소를 표시하지 않는다. 이 보완 후 `python-final-2.log` **91 PASS**(9.32초), `browser-final.log` **15 PASS**(25.0초)를 재확인했다.

문서 검사와 git diff --check PASS. 1360px 브라우저 결과 이미지를 확인해 단일 제목·같은 로그 탭 스타일/폴더 버튼·패널 정렬·접힌 두 상세 영역을 확인했다. native Chrome 재조작 도구는 이번 후속에서 pipe 시작 오류로 사용할 수 없어 현재 열린 탭의 갱신은 확인하지 못했다. 브라우저 fixture 결과와 실제 열린 Mac 탭 확인을 구분한다.

## REG-0092 · 독립 리뷰와 반환 재시도

Astra/xhigh 첫 코드 리뷰는 CHANGES_REQUESTED였다. 일반 실행 실패/종료 반환과 lease CAS 보호는 확인했지만, 반환 통신까지 실패하면 소유권이 남고 수동 반환 버튼도 없어지는 P2를 지적했다. 서버 caption·다른 보드 게이트 등 최종 전체 범위는 NOT_REVIEWED이며 독립 시험은 sandbox 제약으로 수행하지 못했다.

게시 전 로컬 커밋 289a1a0의 실제 Manager 코드를 별도 모듈로 읽어 프로세스 생성 실패+반환 요청 실패를 주입했다. 한 번만 반환을 시도하고 manual 소유가 남음을 `reg0092-before.log`에 재현했다. 기존 작업 파일을 되돌리지 않았다.

동일 grant를 1/2/4초부터 최대30초 간격으로 재시도하고 상태·시도 횟수·원인만 노출한다. 키는 상태/로그/DB에 넣지 않는다. 웹/Qt에서 반환 중을 표시하고 해당 보드의 새 열기를 막는다. 실행 실패/Raw 전 창 종료 × 기존/새 grant의 네 조합에서 첫 반환 실패→통신 회복과 새 grant 보호를 재시험했다.

최종 `python-review-fix.log` **95 PASS**(13.79초), `browser-review-fix.log` **15 PASS**(26.4초). Astra/xhigh는 이 P2 수정 범위에 한해 APPROVED, 추가 P1/P2 없음을 보고했고 위 실행 로그를 확인했다. 독립 재실행·이전 미검토 범위·실제 회사 인수는 별도다. 전체 최신 UI/통합에 대한 독립 승인을 뜻하지 않는다.

최종 리뷰 반영 제품 SHA256 `d4e7d69f28ab06659329a29c957da3d6b27a6d9021c8bd127f5bc1b54263006b`, 시험 SHA256 `56b3a6fc5febefeb5bc1b43d82ea1752ca8e98962343039299ec58e5e6351749`. 앞선 91/15 실행과 해시는 수정 전 단계의 이력이다.

## 게시·회사 전달 기준

제품·시험 고정 커밋: `916676d5f46df9050be2c149f0798b273466bd39`. 부모 `0180fea`의 RQ-69 보완을 포함한다. Git HTTPS push 인증이 없어 연결된 GitHub Git API로 28개 파일 blob SHA와 전체 tree `2f5c6f1165ddf97c45f64f160af4b664ebd0da5d`의 일치를 확인한 뒤 expected HEAD로 main을 갱신했다. 원격 commit을 fetch하여 같은 tree와 로컬 clean을 확인했다. runtime·사용자 설정·로그·EXE/ZIP은 게시하지 않았다.

전달은 [요청문](../../agents/BSP_UPGRADE_PLUGIN_REQUEST.md)의 최신 D-74 코드 블록과 PORT-007/009, 공개 API 안내를 같은 기준으로 공유한다. 회사 저장소 적용·실제 Windows/PuTTY·장비 검증은 수행하지 않았다. REG-0092의 게시 전 로컬289a1a0은 실패 재현 기준이며 공개 제품 기준이 아니다.
