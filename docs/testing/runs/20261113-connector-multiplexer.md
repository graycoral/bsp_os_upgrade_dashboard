# 포트 멀티플렉서·GUI · 2026-11-13

RQ-66/D-70/T-236~239/REG-0084. 기준 `77708ad40c4b869b084121597643948cb923ad70`. 단일 UART owner/loopback RPC·PuTTY Raw, 공통 TC Serial 어댑터, Host/flash 게이트·관찰 구독, 작은 GUI와 변경분 렌더링을 구현한다. 새 의존성·DB 이전·EXE/배포 ZIP은 없다.

| 실행 | 결과 | 범위 |
|---|---|---|
| core-1.log | 6 PASS | 가짜 UART + 실제 TCP/Serial 클라이언트 |
| integration-1.log | 69 PASS | connector·기존 flashing 회귀 |
| integration-2.log | 79 PASS | batch 통합 포함 |
| core-2.log | 1 FAIL / 8 PASS | 실제 TC 자식에서 venv 링크 resolve로 base Python이 선택되어 pySerial 부재 |
| core-3.log | 9 PASS | 실행 경로 보존 후 동일 시험. 실제 TC common.py가 자동 제공된 Serial 어댑터로 UART fake 왕복 |
| regression-1.log | 28 FAIL / 1432 PASS / 21 SKIP | Mac 전체 회귀: 기존 Linux /proc 기반 프로세스 identity·receipt 의존 시험 실패. 시험 완화 없이 원본 로그 보존, Linux CI에서 확인 |
| final-local.log | 643 PASS / 12 SKIP | 전체 GUI Test backend, launcher, setup-runtime, layout 회귀. UART·TCP·실제 TC 자식·Qt 모의 검증 |

```bash
QT_QPA_PLATFORM=offscreen PATH=/usr/bin:/bin:/usr/sbin:/sbin .venv/bin/python -m pytest -q backend/gui_test/tests/test_serial_multiplexer.py backend/gui_test/tests/test_board_connector.py backend/gui_test/tests/test_flashing.py backend/gui_test/tests/test_plugin_integration_batches.py
```

Mac Python 3.11.7/Qt 6.8.3 offscreen 모의 GUI: 760×520, 로그 영역 80px, 첫 프레임 338.3ms, 동일 상태 500회 평균 0.143ms, 프로세스 최대 RSS 약 73.9MiB. 설치/관리자/SSH를 포함한 Windows 시작 시간이나 실보드 처리량 측정은 아니다. gui-metrics.json 및 화면 PNG를 로컬에 보관했다.

원본 로그·이미지·manifest는 `.local-reports/connector-multiplexer-20261113/`에만 보관하며 Git에 넣지 않는다. 회사 Windows 11/실물 T-239 NOT_RUN, 독립 리뷰 NOT_REVIEWED. Windows CI와 제품 SHA는 게시 후 추가한다. 실제 회사 공통 모듈 소스가 없어 적용 방법과 참조 common.py 검증까지만 완료한다. ADB USB 서버 프록시는 별도이며 이번 UART 구현에 포함하지 않는다.

최종 소스 보완(종료 직전 수신 오류 재확인·동시 상태 조회 잠금) 후 `final-local-2.log`: 1 FAIL / 642 PASS / 12 SKIP. 기존 native Manager 반복 시험에서 Mac os.killpg가 PermissionError를 반환해 worker thread가 종료되었다. 원본 로그를 보존하며 동일 시험과 Windows/Linux CI를 재확인한다. T-236~238은 이 로컬 모의/프로세스 결과로 PASS, T-239는 NOT_RUN이다.

코드 sha256:d9879a27152554b4add8ae3a414955397f4da25493b73a1c8d09ecf03251cbd5; 시험 sha256:09b6d9b567e6707d726a4e6c107ed1900d17c353afacacce6cb22dfb50c7a7e8.

동일 실패 시험을 포함한 `test_windows_runner.py`와 신규 `test_serial_multiplexer.py` 재시험 `final-retry.log`: 38 PASS. 코드·시험·시간 제한을 변경하지 않았으며 앞선 PermissionError 실패 기록은 유지한다. Linux/Windows 전체 CI에서 플랫폼별 결과를 추가 확인한다.
