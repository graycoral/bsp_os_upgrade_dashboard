# Agent Monitor 전달 기준 · 2026-11-14

사용자의 커밋·푸시 지시에 따라 로컬 완료 변경을 고정했다.

- 이전 기준: `e4f53ca1ec288feb3eb1b9ccff8335a398ad321c`
- 제품·시험·문서 커밋: `475e285cc35765b29470348b581194aa03c47677`
- 대상: `graycoral/bsp_os_upgrade_dashboard`의 `main`
- 범위: 플러그인 중심 Agent Monitor, 보드 커넥터 웹 화면, 실패 분석/재실행, 공통 설정, 자동 캐시 정리, 의존성/설치/복구, 스크립트 정리와 문서

코드·시험은 [최종 실행 기록](20261114-remaining-implementation.md)의 source/test manifest와 커밋 후에도 일치했다. Python1009 PASS/24 SKIP, 브라우저13+6 PASS, 두 UI 빌드 PASS를 재사용하며 동일 코드에서 시험을 다시 수행한 것으로 표시하지 않는다. [별도 Astra 리뷰](20261114-remaining-code-review.md)는 APPROVED다. 게시 전 원격 main과 기준 커밋의 차이는 없었고 whitespace 검사를 통과했다. 실행 데이터·로그·새 EXE·배포 ZIP은 커밋에 포함하지 않았다.

회사 담당자는 [PORT-007](../../porting/PORT-007.md)·[PORT-009](../../porting/PORT-009.md)와 [공개 설치/API 안내](../../agents/PLUGIN_CONTROL_API.md)를 사용한다. 위 커밋에 문서 고정 변경을 추가한 main을 받는다. 회사 분석기·검증기·ACON 매핑과 실제 Windows/Linux 설치·SSH·장비 인수는 NOT_RUN이다. 기본 분석은 조치 근거 없이 HOLD를 해제하지 않는다.

전송 경로: 로컬 HTTPS 인증 부재와 SSH host key 불일치 때문에 SSH 설정을 바꾸지 않고 인증된 GitHub 연결 도구로 게시했다. 원격 제품 tree `da4f38f988099da7322fb2f448452830459cb027`는 로컬 검증 커밋의 tree와 일치한다. API 생성으로 커밋 ID가 달라져 이 문서와 PORT의 고정 기준을 원격 제품 커밋으로 갱신했다. 기존 로컬 커밋은 복구용 로컬 태그로 보존한다.
