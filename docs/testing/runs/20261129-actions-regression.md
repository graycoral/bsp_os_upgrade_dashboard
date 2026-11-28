# GitHub Actions 회귀 시험 · 2026-11-29

기준 커밋 `d471ce7`의 [실패 실행](https://github.com/graycoral/bsp_os_upgrade_dashboard/actions/runs/46159827359)에서 Ubuntu pytest 3건과 Windows pytest 9건이 실패했다. RQ-66/67 및 REG-0141에 해당한다.

| 시험 | 원인과 수정 |
|---|---|
| 포트 대체·실패 후 정리 3건 | 시작 시 구형 프로필이 proxy로 자동 이전되어 파일 비교가 실패했다. 현재 프로필에서 시작해 SSH 실패·명시 포트 충돌·identity 불일치 후 설정 파일의 바이트와 자식 프로세스 정리를 검사한다. |
| 시리얼 프록시 4건 | 실제 Windows 자식 Python은 CRLF를 출력한다. 전체 stdout을 OS 줄바꿈과 비교하고 시리얼 바이트는 기존대로 정확히 비교한다. |
| 프로필·서버 파일 탐색 3건 | Windows 경로를 Linux 서버 설정에 전달했다. 모의 실행은 Linux 서비스 경로를 사용하고 파일 탐색은 실제 임시 폴더와 심볼릭 링크를 사용한다. |
| 종료 불명 2건 | POSIX 프로세스 그룹을 모의하면서 Windows에 없는 SIGKILL을 참조했다. 신호와 시스템 호출을 함께 모의하고 권한 거부 시 종료 미확인을 검사한다. |

macOS Python 3.11에서 변경과 관련된 GUI Test 시험 파일 다섯 개를 실행해 55 PASS, Windows 시리얼 백엔드 1 SKIP를 확인했다. 포트 대체 3건은 macOS에 Linux 프로세스 생성 시각을 제공하는 `/proc`가 없어 해당 환경에서 검증할 수 없다. Linux·Windows 결과는 수정 커밋에 연결된 GitHub Actions 실행을 확인한다.

로컬 원본 로그는 작업 폴더의 `.local-reports/actions-20261129/`에 보존한다.

## Python 회귀 다음 단계에서 드러난 실패

수정 `921a57f`의 [회귀 실행](https://github.com/graycoral/bsp_os_upgrade_dashboard/actions/runs/46160650758)에서 Ubuntu와 Windows pytest가 통과했다. Windows 첫 설치는 성공했고, 같은 터미널에서 다시 시작한 설치 확인은 BC-56으로 실패했다. PowerShell 프로세스가 상속한 PATH에 등록된 시스템·사용자 PATH를 합친 뒤 필수 도구를 확인한다. 등록된 경로는 패키지 설치 직후에도 다시 읽는다.

대시보드·standalone 브라우저에서 실패 분석 대기 중인 Run을 즉시 재개하려 하면 서버가 거부하고 해당 Run이 보드를 계속 예약했다. GUI-UI-02/04/07은 분석 대기·재개 거부·취소를 확인한 후 다음 시나리오를 시작한다. GUI-UI-10은 통과 시나리오에서 반복 실행 순서와 횟수를 검사한다. 공통 설정 시험은 커넥터와 Test 현황에 각각 있는 패널 중 해당 summary를 소유한 패널을 조회한다.

로컬 재시험은 Playwright 고정 Chromium으로 변경된 실행 시나리오와 제어권 시험 5 PASS, 공통 설정 6 PASS였다. 런처·복구 Python 시험은 119 PASS, 플랫폼 전용 등 27 SKIP였다. 개발 로그는 같은 로컬 증거 폴더에 보존한다.
