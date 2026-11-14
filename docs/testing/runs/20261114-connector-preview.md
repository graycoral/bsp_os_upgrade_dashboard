# 보드 커넥터 실제 로컬 미리보기 기동

2026-11-14 · RQ-63/T-257/REG-0090. 기준 `b685ab9ada779bc60bbeb2500fb1adbfb7d63607` 위 로컬 수정이다. 사용자 요청으로 실제 Mac에서 `python -m backend.gui_test.connector --preview`를 실행했다.

첫 실행은 exit 2 / `Invalid receipt port`였다. `run_preview()`가 `bind_loopback(0)`을 호출하지만 공통 receipt binder는 입력 포트 0을 의도적으로 거부한다. 기존 모의 브라우저 fixture는 다른 소켓 준비 경로를 사용해 이 CLI 진입 결함을 잡지 못했다.

유효한 preview 포트 8774와 기존 `allow_fallback=True`를 사용하도록 수정했다. 점유 시 ephemeral 할당은 기존 binder 내부에서 처리하며 공통 포트 검증을 완화하지 않았다. 서버 종료 후 listener도 명시적으로 닫는다.

- 신규 진입 회귀: 수정 전 1 FAIL, 수정 후 새 web 시험 포함 **36 PASS**, exit 0. 실제 loopback listener에 대해 origin/포트·브라우저 일회 티켓·인증된 페이지/모의 status·소켓 닫힘을 확인했다. 브라우저 opener와 서버 루프만 모의 처리하며 실제 장비를 사용하지 않는다.
- 실제 CLI: 수정 후 서버가 유지되고 Chrome의 `보드 커넥터` 탭이 열렸다. native UI에서 `모의 미리보기` 표시·보드 2대·COM7/COM8과 로그를 확인했다. `연결 시작` 클릭 후 `연결됨` 및 모든 모의 연결 단계 `정상`을 확인했다. 실제 COM·SSH 접속을 뜻하지 않는다.
- 로컬 근거: `.local-reports/20261114-connector-preview/before.log`, `after.log`, `source-manifest.json`. 원본 로그/manifest는 Git에 포함하지 않는다.

프로세스는 사용자가 화면을 살펴볼 수 있도록 유지한다. 임시 모의 프로파일만 사용하며 실제 Windows 설정을 읽지 않는다. 이전 Astra 승인은 이전 코드 범위이며 이 후속 수정은 구현자 회귀·실제 기동 확인이다. 새 커밋/푸시는 수행하지 않았다.
