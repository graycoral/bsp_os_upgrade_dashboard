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
