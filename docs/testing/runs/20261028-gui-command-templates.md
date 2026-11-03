# TC 명령 템플릿 검증

기준: Windows 빌드 변경 b72d2c0. RQ-41/T-115~117. 구현 후 검증 결과를 기록한다. 실제 TC/RBM/장비는 NOT_RUN이다.

## 로컬 검증

- 전체 Python 회귀: 315 PASS (기존289 + 명령 관련26).
- 명령 관련 시험: TC 이름/파일/경로·COM 치환, 잘못된 변수/인자 거부, 저장/조회/버전 불일치, Run 중 프로파일 변경·관리자 재시작·오류 복구 후 snapshot 유지, 기존 Run 호환 및 hardware 차단.
- 표준 Playwright Chromium 다운로드가 잘린 ZIP으로 실패했다. 제품 코드/의존성을 변경하지 않고 무시되는 로컬 도구 폴더의 Chromium153으로 브라우저를 검증하며, CI는 표준 Playwright 브라우저를 사용한다.
- 백엔드 초안의 import 오타로 최초 수집 오류가 있었고 수정 후 명령 시험26개 및 전체315개를 통과했다.
- 실제 Python TC/RBM/장비 호출은 수행하지 않았다.

## 최종 화면 검증

구현 커밋: `5af89797bd64b95675862947ca36bc108b08416e`.

- 단독 및 Dashboard TypeScript/Vite 빌드 PASS.
- 단독 브라우저 6 PASS, Dashboard 브라우저 11 PASS(기존 Dashboard 5 + 공통 GUI6).
- 신규 GUI-UI-06: 저장·선택 복원, Single/Dual argv 미리보기 및 Run 미생성, Mock 실행 argv, 완료 Run snapshot 불변, 수정 후 Preflight 해제, 사라진 프로파일 자동 대체 금지 확인.
- 로컬 680px 화면 레이아웃 넘침 없음. 해당 Chromium에 한글 폰트가 없어 글리프 확인은 제한되며 기존 화면도 같은 환경 제약을 보인다.
- 문서 링크/추적성 검사 PASS. Windows 신규 빌드에도 명령 계약 시험을 포함했다.

CI: [Windows 전용 빌드](https://github.com/graycoral/bsp_os_upgrade_dashboard/actions/runs/40621464890), [기존 Linux/Windows 회귀](https://github.com/graycoral/bsp_os_upgrade_dashboard/actions/runs/40621464940). 결과는 해당 구현 커밋의 실행으로 확인한다.
