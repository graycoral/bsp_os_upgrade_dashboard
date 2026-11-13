# 보드 커넥터 연결 토큰 제거 · 2026-11-13

RQ-64 / D-68 / T-230~231 / REG-0081. 기준 `48a34237939dd31f62c8b3b83ef13d55324009e2`, 대상은 미커밋 작업 트리다. 독립 리뷰 NOT_REVIEWED, 실제 Windows·Linux SSH·보드·회사 플러그인 인수 T-231 NOT_RUN이다.

Runner HTTP·커넥터 등록·플러그인 연결에서 공유 토큰 검사를 제거했다. 등록·모니터·종료·TC/이미지 전송·플래싱 설정에서 토큰을 읽거나 전송하지 않는다. SSH/loopback·비브라우저 제한, identity 고정, controller/Run 소유권, 멱등 키, 배치 예약은 유지한다. GUI 관리자 IPC 자격·prepared_token·lease·자동 읽기 전용 브라우저 세션은 연결 설정과 별개이므로 유지한다. DB 이전·새 의존성·새 EXE/배포 ZIP은 없다. 대시보드 자동 설치는 계속 보류한다.

| 실행 | 결과 | 원인·후속 |
|---|---|---|
| initial.log | 179 PASS / 11 FAIL / 8 SKIP | 이전 토큰 기대 8건과 Mac의 CLI fixture 플랫폼 3건. 토큰 없는 계약과 명시적 플랫폼 fixture로 수정 |
| focused-2.log | 195 PASS / 8 SKIP | 등록·플러그인·설정·Dashboard 집중 시험 |
| broad.log | 690 PASS / 25 FAIL / 10 SKIP | 구형 번들 fixture의 토큰 기대 6건, Mac /proc process identity 불가 18건, Mac killpg EPERM 1건. 실패 원본 보존 |
| broad-2.log | 722 PASS / 6 FAIL / 10 SKIP | 전체 GUI Test·설정·번들·API 범위. Mac /proc 의존 파일 제외. 앞 killpg 실패는 통과. 번들 readiness의 남은 토큰 기대 6건 수정 |
| hardware.log | 21 PASS | 기존 BSP 하드웨어 파이프라인을 fake Host로 확인 |
| final.log | 186 PASS / 10 SKIP | 토큰 없는 연결·API·설정·번들·하드웨어 집중 재시험 |
| final-2.log | 208 PASS / 51 FAIL / 10 SKIP | setup_commands 추가 시 기존 CLI fixture가 Mac을 미지원하여 조기 종료. 해당 fixture를 명시적 플랫폼으로 수정하고 토큰 없는 HTTP/파일 미조회 기대 갱신 |
| final-3.log | 259 PASS / 10 SKIP | 최종 코드의 집중·진단·CLI 회귀 통과 |

최종 명령:

```bash
PATH=/usr/bin:/bin:/usr/sbin:/sbin QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q -rs backend/gui_test/tests/test_tokenless_connections.py backend/gui_test/tests/test_plugin_integration_http.py backend/gui_test/tests/test_plugin_integration_diagnostics.py tests/test_api.py tests/test_setup_runtime.py tests/test_runner_ports.py tests/test_windows_runner_bundle.py tests/test_hardware_pipeline.py tests/test_setup_commands.py
```

새 회귀는 토큰 환경변수 없이 Host/등록/플러그인 Run/모니터/종료, 구형 token 인자 미전송, 설정 토큰 파일 미조회, 브라우저·원격 주소 거부, 서비스 경로 제한과 중복 Run 방지를 확인한다. 기존 플래싱·배치·소스 전송 시험은 broad-2.log에 포함된다. 모든 실행은 임시 mock/TC fixture이며 실제 장비 실행은 없다.

10 SKIP은 Windows DPAPI·CMD/PowerShell·로컬 endpoint·DLL/Job Object 전용 시험이다. `test_setup_active_endpoints.py`의 Mac /proc 의존 18건은 환경 제약으로 남아 Linux/Windows 재시험이 필요하다. 프로세스 소유권 검사를 약화하거나 실패 이력을 삭제하지 않았다. 광역 전체 PASS나 회사 인수 완료로 표현하지 않는다.

로그·SHA256 manifest는 `.local-reports/service-tokenless-20261113/`에 보관한다. 시험 코드 revision은 CSV와 manifest에 고정한다. 회사 적용 범위·동시 갱신·복원은 [PORT-009](../../porting/PORT-009.md), 사용자 절차는 [보드 커넥터 가이드](../../gui_test/TEST_BOARD_CONNECTOR_GUI.md)를 따른다.

문서 검사 PASS: 상대 링크 1,266개·요구사항 64개·시험 231개·오류 0개. CSV 줄바꿈 정리 후 `git diff --check` PASS.

2026-11-13 게시 후속: 사용자 병합·푸시·브랜치 정리 지시로 제품·시험 변경을 `929158f672a5a155d00b89ca679cf775ea3744b3`로 main에 게시했다. 로컬과 원격 tree `674de51c3edc8c854f4b1895b64871d76212fc3e` 일치를 확인했다. 위 미커밋 표현은 최초 검증 시점 기록이다.
