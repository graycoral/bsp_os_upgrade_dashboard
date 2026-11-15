# 2026-11-15 · 추가 반영 확인·main 정리

기준 main: `a582144c8b8a4693b1a497383d3b823916c16e0f`. 사용자 요청은 추가 반영 확인·커밋·푸시 및 반영된 브랜치 삭제다.

## 게시 범위

미게시 `TEST_TIMEOUT_SYNC_PLAN.md`, 문서 지도·현재 상태·진행 기록·플러그인 전달 구분을 갱신한다. 설계 APPROVED와 제품 부분 WIP/CHANGES_REQUESTED를 구분한다. 기본120초·Mock 제거·단일 설정 controller는 이번에 구현하지 않았다. 로컬 제품 수정 7개와 기존 runtime은 변경 없이 보존한다. 실행 중 Agent Monitor도 재시작하거나 소스를 교체하지 않는다.

검증: `python docs/testing/validate_docs.py`, `git diff --cached --check`. 제품 코드 변경이 없으므로 새 제품시험은 NOT_RUN이다. 과거 미러 구현 Python924/브라우저27 PASS를 이번 설계의 시험으로 재사용하지 않는다. 원본 로그는 `.local-reports/20261115-main-cleanup/`의 로컬 전용 자료다.

## 브랜치 확인

| 로컬 백업 | main 반영 근거 |
|---|---|
| `backup/20261114-local-putty-handoff` | `b120932`와 tree 동일 |
| `backup/20261114-local-putty-publication` | `916676d`와 tree 동일 |
| `backup/20261114-pre-api-publication` | `b685ab9`와 tree 동일 |
| `backup/20261114-pre-putty-return-retry` | `916676d`의 PuTTY 반환 재시도·오류 표시·회귀 시험이 이 초기 구현을 대체함을 diff로 확인 |
| `backup/20261115-local-connector-handoff` | `6866b41`와 tree 동일 |
| `backup/20261115-local-connector-ui` | `bb803c3`와 tree 동일 |

위 로컬 브랜치 6개는 `.local-reports/20261115-main-cleanup/published-backups.bundle`에 복구 자료를 보관·검증한 뒤 예상 SHA를 확인해 삭제했다. bundle은 미커밋이다. detached 검증 worktree와 실행 중인 미러 worktree는 보존한다.

원격 `feature/connector-multiplexer`의 `dc2f855`는 main의 조상으로 확인했다. 원격 삭제는 BLOCKED로 남았다. Git HTTPS 자격 증명이 없고 GitHub 연결 도구에는 branch delete 기능이 없다. 브라우저 호스트는 unavailable, native computer-use는 onboarding 미완료로 접근하지 못했다. SSH 접속도 기존 known_hosts와 호스트 키가 달라 거부됐다. 인증·SSH 신뢰 검사를 우회하지 않는다.

문서 검사 PASS(상대 링크1,666개), staged diff 검사 PASS. 제품 코드 추가 게시 없음. 로컬 main 외 브랜치는 정리했으며 원격 기능 브랜치1개 삭제는 위 접근 수단 복구 후 필요하다.
