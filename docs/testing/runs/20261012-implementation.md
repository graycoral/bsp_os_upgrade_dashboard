# 2026-10-12 로컬 구현 검증

- run_id: 20261012-local-implementation
- executed_at: 2026-10-11T17:20:43.676352+00:00
- executor: Codex
- scope: unit / contract / integration / ui-e2e; 외부 연동은 fixture
- code_revision / test_revision / dirty_diff_hash: `sha256:e7c55a77ed22ec95593cabe01be06ba749c2c65186be0d1b45a33067ebe339b4`
- 파일별 내용 기준: [source-manifest.json](20261012-evidence/source-manifest.json)
- 환경: macOS, Python 3.11, Node.js 22.23.2, Vite 7.3.7, 설치된 Chromium headless shell. 의존성은 requirements.lock과 package-lock.json 기준.

| 실행 | 결과 | 근거 |
|---|---|---|
| Python 도메인/API/저장/브리지/Jira 시험 | 78 PASS, 경고 1 | [출력](20261012-evidence/backend.txt), [시험별 결과](20261012-evidence/automated-results.csv) |
| TypeScript/Vite 프로덕션 빌드 | PASS | [출력](20261012-evidence/build.txt) |
| 브라우저 설정·재접속·작은 화면 | PASS | [출력](20261012-evidence/browser.txt) |
| 브라우저 최소 수동 FAIL → 재시도 → PASS | PASS | 같은 출력; 추가 정보 없이 결과 등록, 미선택 제출 차단 |
| 브라우저 데모 선행 완료 | PASS | 같은 출력; 계획 확인 전 비활성, 선행 전체 완료 후 해제, 새로고침 유지 |
| 실제 Linux/SSH/에이전트/BSP/장비/Jira | NOT_RUN | 환경별 브리지와 실행 증거 없음 |
| Claude 독립 검토 | NOT_REVIEWED | 수행하지 않음 |

실행 명령: `.venv/bin/python -m pytest -q`, `npm run build --prefix apps/web`, `BSP_E2E_PORT=18766 BSP_BROWSER_EXECUTABLE=<installed-chromium> .venv/bin/python scripts/test_e2e.py`.

T-61~67은 해당 명세를 모두 확인해 요약 CSV에 PASS를 기록했다. 기존 T-01~60의 부분 검증은 자동 시험명으로 추적하지만 전체 인수 조건을 모두 충족한 것으로 승격하지 않았다. 예를 들어 백업 복원 시험 통과는 전체 DB migration 인수 통과와 같지 않고, demo 전체 흐름 시험은 실제 도구·장비 인수가 아니다. 시험 건수와 목표 목록의 수는 서로 다른 기준이다.

## 실패와 재시험

- 최초 UI 빌드 타입 오류: [FAIL](20261012-evidence/initial-build-failed.txt). null 보호 수정 후 현재 빌드 PASS. REG-0001.
- 수동 결과 label 탐색 충돌: [FAIL](20261012-evidence/initial-browser-01-failed.txt). 명시적 aria-label 후 해결. REG-0002.
- 독립 상태 갱신 중 명령 version 충돌: [FAIL](20261012-evidence/initial-browser-02-failed.txt). 제한적 재접수와 서버 게이트 유지. [이전 재시험 PASS](20261012-evidence/initial-browser-passed.txt), 현재 브라우저 PASS. REG-0003.
- 이번 최초 브라우저 실행은 샌드박스의 로컬 포트 제한으로 BLOCKED: [출력](20261012-evidence/browser-blocked.txt). 제품 실패로 분류하지 않는다.
- 다음 실행은 기존 8766 서버로 잘못 연결되어 로그인 대기 3개 FAIL: [출력](20261012-evidence/browser-failed.txt). 시험 러너가 포트 충돌을 즉시 거부하고 매번 별도 runtime/키를 사용하도록 수정했다. 별도 18766과 검증된 Chromium으로 재시험 3개 PASS. REG-0004.

이전 실패 출력은 보존했다. 인증 키·운영 DB·브라우저 세션/trace·개인 환경 설정은 게시 대상에서 제외했다. 코드 내용 해시 기준 결과이며 실제 운영 baseline은 아직 등록하지 않는다.
