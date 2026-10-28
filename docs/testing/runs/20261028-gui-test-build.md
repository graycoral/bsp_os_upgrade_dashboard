# Windows GUI Test 빌드 검증

기준 main: `2e2d24b74d8464d432e118fd4a80646d6d7a6c9a`. RQ-40/T-112~114.

## 범위

GUI 전용 npm/TypeScript/Vite 설정, Windows PowerShell/CMD 빌드, wheel/독립 ZIP, 설치 가이드 및 CI. 기존 UI와 실행 Core/API/DB 변경 없음. 기존 Dashboard 빌드와 `package.py --base` 호환성 보존.

## 실행 상태

- 독립 웹 빌드: Linux Node 24.22.1에서 PASS. 지원 Windows 빌드 버전인 Node 22는 CI에서 별도 검증한다.
- Windows PowerShell 5.1/7 및 오프라인 설치: CI 대기. 결과 확인 후 이 기록과 T-112~114를 갱신한다.
- 실제 COM/TC/RBM 및 회사 Windows 인수: NOT_RUN. Mock 시험을 실장비 검증으로 해석하지 않는다.
