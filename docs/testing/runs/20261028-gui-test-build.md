# Windows GUI Test 빌드 검증

기준 main: `2e2d24b74d8464d432e118fd4a80646d6d7a6c9a`. RQ-40/T-112~114.

## 범위

GUI 전용 npm/TypeScript/Vite 설정, Windows PowerShell/CMD 빌드, wheel/독립 ZIP, 설치 가이드 및 CI. 기존 UI와 실행 Core/API/DB 변경 없음. 기존 Dashboard 빌드와 `package.py --base` 호환성 보존.

## 실행 상태

- 독립 웹 빌드: Linux Node 24.22.1에서 PASS. 지원 Windows 빌드 버전인 Node 22는 CI에서 별도 검증한다.
- Windows PowerShell 5.1/7 및 오프라인 설치: PASS. 아래 Windows CI 증거 참조.
- 실제 COM/TC/RBM 및 회사 Windows 인수: NOT_RUN. Mock 시험을 실장비 검증으로 해석하지 않는다.

## 로컬 추가 검증

- Python 3.12.14 전체 회귀: **289 PASS** (기존 284 + 패키지 경계 5).
- 독립 폴더(공백 경로, backend/apps/.git 없음) Core/API/패키징: **58 PASS, 2 deselected**. 두 제외 사례는 Git 탐색과 Dashboard 통합이며 전체 회귀에서 별도 실행했다.
- 기존 Dashboard 및 GUI Test 독립 TypeScript/Vite 빌드: PASS.
- Python wheel 및 standalone ZIP 생성, ZIP 전체 SHA256 manifest 대조·Dashboard 파일/patch 제외: PASS.
- 단독 Mock E2E 5개 시나리오: PASS.
- 문서 링크/추적성 검사: PASS.

위 시험의 구현 커밋은 `c0cb130265ae8014f1b2db5463b295bfedf7b050`이다. 최종 문서 결과 기록은 별도 커밋으로 추가한다.

## Windows CI 증거

[Windows 전용 빌드 실행 40620443558](https://github.com/graycoral/bsp_os_upgrade_dashboard/actions/runs/40620443558), 구현 커밋 `c0cb130265ae8014f1b2db5463b295bfedf7b050`.

| 환경 | 독립 GUI 빌드 | ZIP 오프라인 설치·CLI·정적 JS·Mock E2E | 결과 |
|---|---|---|---|
| Windows / PowerShell 5.1 / CPython 3.12 x64 / Node 22 | PASS | PASS | success |
| Windows / PowerShell 7 / CPython 3.12 x64 / Node 22 | PASS | PASS | success |

- 소스는 `gui_test/`만 공백 포함 임시 경로에 복사했다. Dashboard와 Git 메타데이터는 없다.
- fresh venv 설치는 `--no-index`로 수행했다. 저장소 밖에서 start/status/restart/stop 및 health/UI JS 응답, 5개 Mock 시나리오를 검증했다.
- artifact: `GUI-Test-Standalone-Windows-powershell`, `GUI-Test-Standalone-Windows-pwsh`. 내부 `gui-test-windows-py312.zip`이 배포 ZIP이다.
- Windows 전용 스크립트 변경은 위 CI로 검증했고, 기존 Windows 패키지 job도 성공했다. 기존 Linux 전체 회귀 결과는 [동일 커밋 회귀 실행](https://github.com/graycoral/bsp_os_upgrade_dashboard/actions/runs/40620443420)에서 확인한다.
- 실제 Windows 10/11 사용자 PC, 사내 정책/미러 및 실장비 인수는 별도다. GitHub의 Windows hosted runner 결과를 모든 회사 환경 검증으로 확대하지 않는다.
