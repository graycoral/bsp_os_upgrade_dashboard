# Windows 보드 커넥터 단일 실행기 · 2026-11-13

RQ-65/D-69/T-232~234/REG-0082. 기준 `683447734f3d47feb85ddf472b051663706f862e`. 사용자 요청으로 최초 환경 준비·의존성 설치·GUI 실행을 `board-connector.cmd` 하나로 묶었다. 기존 GUI/Host/단순 SSH 진입점 3개를 제거하고 CLI 자동화·Linux·별도 웹 서비스·빌드는 유지한다. [스크립트 정리 목록](../../../scripts/README.md#windows-실행-스크립트-정리--2026-11-13).

실행 코드 `scripts/board_connector.py`는 고정 패키지 버전·GUI import를 확인하고 정상 환경을 네트워크 없이 재사용한다. 기존 저장소 .venv가 완전하면 읽기 전용으로 재사용한다. 의존성 변경/손상 시 사용자 home 아래 새 환경에 준비하고 검증 후 환경 선택 기록을 원자 교체한다. 설치 잠금과 실패한 신규 디렉터리만 정리하는 규칙으로 기존 환경·설정·TC Python을 보존한다. TC/이미지/소스를 복사하거나 실제 장비를 실행하지 않는다. DB·새 패키지 의존성 변경은 없다.

| 실행 | 결과 | 범위 |
|---|---|---|
| focused-1.log | 14 PASS / 2 SKIP | 최초 설치·재사용·버전 변경·손상·실패·설정 보존·잠금·잘못된 pin/캐시·진단. Windows CMD 미실행 |
| regression-1.log | 220 PASS / 10 SKIP | 준비·GUI·CLI/설정·포트·레이아웃·토큰 없는 연결 회귀 |
| regression-2.log | 220 PASS / 12 SKIP | 주석 변경은 재설치하지 않는 fingerprint, 최종 코드 회귀. CMD LF/CRLF 사례 추가 |

재실행 명령:

```bash
QT_QPA_PLATFORM=offscreen PATH=/usr/bin:/bin:/usr/sbin:/sbin .venv/bin/python -m pytest -q -rs tests/test_board_connector_launcher.py backend/gui_test/tests/test_board_connector.py tests/test_setup_runtime.py tests/test_setup_commands.py tests/test_runner_ports.py tests/test_gui_test_layout.py backend/gui_test/tests/test_tokenless_connections.py
```

12 SKIP은 실제 Windows CMD 4건과 기존 DPAPI/Windows wrapper/endpoint 8건이다. Windows CI에 새 CMD 시험 및 실제 `--install-only` 첫 설치·PIP_NO_INDEX 재사용을 추가했다. 로컬에서는 Windows 실행 T-233 NOT_RUN, 회사 GUI·SSH·장비 인수 T-234 NOT_RUN이며 독립 리뷰 NOT_REVIEWED다. CI 결과는 확인 후 아래에 추가한다. 원본 로그와 manifest는 `.local-reports/connector-launcher-20261113/`에만 보관한다.

## CI와 병합

제품·시험 고정 커밋 `46a0cb9328f3cb351078b2d2b8e48faf0aaa2fc5`, [PR #20](https://github.com/graycoral/bsp_os_upgrade_dashboard/pull/20), main 병합 `ad16eaac5c6837b85e73aea52864ce9b101170f1`.

- [Linux/Windows 회귀 CI](https://github.com/graycoral/bsp_os_upgrade_dashboard/actions/runs/43361815564): 전체 SUCCESS. Linux Python 1444 PASS / 20 SKIP, 대시보드 브라우저 60 PASS, 단독 GUI 브라우저 18 PASS. Windows Python 636 PASS / 4 SKIP, 패키지·설치형 서비스 smoke PASS.
- Windows job 131676852932의 실제 CMD LF/CRLF·공백/기호 경로·인자/종료 코드 시험 PASS. 신규 가상환경 첫 설치와 `PIP_NO_INDEX=1` 재실행 모두 PASS(T-233). 첫 설치는 2026-11-13 03:55:47~03:56:10 UTC 단계 내 완료했고 재실행에서는 설치 단계를 다시 수행하지 않았다.
- [독립 Windows 빌드](https://github.com/graycoral/bsp_os_upgrade_dashboard/actions/runs/43361815065): Windows PowerShell/pwsh 모두 SUCCESS.

원본 CI 로그는 로컬 windows-ci.log/linux-ci.log로 보관했다. 문서 검사 1,279 링크·65 요구사항·234 시험·오류 0과 git diff --check를 통과했다. 실제 회사 GUI·SSH·장비 T-234 NOT_RUN과 독립 리뷰 NOT_REVIEWED는 유지한다. CI 패키지는 검증용이며 새 EXE 배포물을 만들지 않았다.
