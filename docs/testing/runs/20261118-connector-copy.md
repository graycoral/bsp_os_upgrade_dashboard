# 2026-11-18 보드 커넥터 탭 설명 정리

RQ-70 / T-268 화면 문구 후속. 사용자 요청에 따라 `ConnectorMirror.tsx`에서 탭 소개·PuTTY 동작·경로 출처·명령 결과 구분·자동 COM 공유 설명과 TC 목록의 조회 전용 부연을 제거했다. 미연결 조치는 한 문장으로 줄였다. `SharedControl.tsx`는 공유 구조 설명을 제거하고 실제 장비 적용 상태를 유지한다. 공통 컴포넌트의 같은 문구가 표시되는 다른 화면에도 적용된다.

설정 이름·버튼·빈 상태·오래된 정보·오류·로그 누락·설정 충돌·UNKNOWN 복구 안내를 유지한다. DB·API·의존성 변경 없음. 기존 미커밋 TC 목록·제한시간 변경을 보존했으며 커밋·게시·실제 장비 실행은 하지 않았다.

원본 로그와 브라우저 자료는 `.local-reports/20261118-connector-copy/` 아래 로컬 전용이며 Git에 포함하지 않는다.

| 검증 | 결과 | 근거 |
|---|---|---|
| Dashboard TypeScript/Vite | PASS · 종료0 | `bash scripts/build-ui.sh dashboard --skip-install`; `build-1.log` |
| T-268 기존 브라우저 회귀 | PASS · 16개 · 종료0 | `node node_modules/@playwright/test/cli.js test connector-mirror.spec.ts --reporter=line`; `browser-2.log` |
| 문서 검사·diff 공백 | PASS · 종료0 | `python3 docs/testing/validate_docs.py`, `git diff --check`; `docs-2.log`, `diff-check-2.log` |
| 실제 회사·Windows·장비 인수 | NOT_RUN | 문구 수정과 로컬 모의 검증 범위 |

최초 브라우저 시도는 샌드박스의 `listen EPERM 127.0.0.1`로 모의 서버 시작 실패(1 FAIL·15 NOT_RUN)했다. `browser-1.log`를 보존하고 같은 시험을 로컬 포트와 브라우저 실행이 허용된 환경에서 재실행해 16개 PASS를 확인했다. 새 시험은 추가하지 않았다.

현재 로컬 웹 서버는 이 저장소의 `apps/web/dist`를 제공하므로 화면 새로고침으로 반영된다. API·Worker는 재시작하지 않았다. 독립 리뷰와 실제 회사 인수는 수행하지 않았다.

시험 결과 표는 ID당 한 행인 기존 계약을 유지해 T-268을 이번 검증으로 갱신했다. 이전 근거는 `20261115-connector-mirror`/`c4d7664653a2ae884736e9b9824908f899b771b0`의 [당시 기록](20261115-connector-mirror.md)에 보존한다. 최초 문서 검사에서 중복 결과 행과 CSV 줄바꿈을 발견해 해당 행만 수정했다. 최초 검사 로그도 보존한다.
