# 2026-10-12 키 없는 진입과 외부 에이전트 계약 정리

- run_id: 20261012-local-entry-agent-contract
- executor: Codex
- backend executed_at: 2026-10-12T02:40:13.324687+09:00
- scope: unit / contract / integration / ui-e2e / documentation; 외부 서비스는 fixture
- code_revision / test_revision / dirty_diff_hash: `sha256:086fa9b0dc2478a3a843eac9e4480a5e26fb597801a86c5aa818430a791dbef9`
- 코드·시험 파일 내용: [source-manifest.json](20261012-entry-agent-evidence/source-manifest.json)
- 환경: macOS, Python 3.11.7, Node.js 22.23.2, Vite 7.3.7, 설치된 Chromium headless shell. requirements.lock/package-lock.json 기준.
- 정책 변경: D-38, RQ-25/29, T-68~70. 기존 수동 결과·데모 정책 T-61~67도 같은 코드에서 재검증.

| 검증 | 결과 | 근거 |
|---|---|---|
| Python 도메인/API/저장/브리지/Jira fixture | 87 PASS, 경고 1 | [출력](20261012-entry-agent-evidence/backend.txt), [실행별 결과](20261012-entry-agent-evidence/automated-results.csv) |
| TypeScript/Vite 프로덕션 빌드 | PASS | [출력](20261012-entry-agent-evidence/build.txt) |
| UI 키 없는 진입·설정 유지·JSON export·작은 화면 | PASS | [브라우저 출력](20261012-entry-agent-evidence/browser.txt) |
| UI 수동 FAIL → 재시도 → PASS | PASS | 같은 출력, 기존 필수 결과만 입력하는 흐름 유지 |
| UI 데모 선행 수동 완료·전체 게이트 | PASS | 같은 출력, 브라우저 총 3 PASS |
| 현재 8765 화면 새로고침 | PASS | 실제 로컬 화면에 로그인 없이 기존 작업/모듈 표시. 작업 기록 유지 |
| 새 에이전트 계약 JSON 예시 6개·필드/해시 형식 | PASS | [문서 예시 검사](20261012-entry-agent-evidence/agent-document-check.json) |
| 실제 Linux/SSH/CLI wrapper/장비/사내 Jira | NOT_RUN | 현재 요청은 계약 문서화, 환경별 wrapper 연결·실제 인수는 별도 |
| Claude 독립 검토 | NOT_REVIEWED | 수행하지 않음 |

실행 명령: `.venv/bin/python -m pytest -q`, `npm run build --prefix apps/web`, `BSP_E2E_PORT=18766 BSP_BROWSER_EXECUTABLE=<installed-chromium> .venv/bin/python scripts/test_e2e.py`.

키·로그인 쿠키를 새로 만들거나 읽지 않는다. 실제 peer의 loopback 여부, Host/Origin/Fetch-Site, 변경 요청의 비밀이 아닌 UI 헤더로 로컬 경계를 유지한다. 시험 러너는 키 파일 대신 매번 다른 instance_id로 자신의 API를 확인한다. 이전 runtime의 키 파일은 사용하지 않으며 기존 작업 DB를 초기화하지 않았다.

T-61~70은 해당 명세의 로컬 조건을 확인하여 최신 CSV를 PASS로 갱신했다. T-01~60은 전체 인수 조건 확인과 부분 자동 검증을 구분하기 위해 기존 NOT_RUN을 유지했다. 이전 구현 실행 기록/manifest는 보존한다. 현재 manifest는 최종 재시험 코드와 시험을 식별하며 아래 최초 실패 당시 시험 파일과 같다고 주장하지 않는다.

## 최초 실패와 재시험

최초 API 시험은 **86 PASS, 1 FAIL**이었다. 삭제한 로그인 경로를 404로만 예상했으나, 빌드된 화면이 정적 경로를 제공하는 환경에서는 POST가 405였다. 로그인/키가 없어졌는지는 정상이며 시험 기대값을 정적 UI 유무에 따른 404/405와 로그인 쿠키 미발급으로 수정했다. 그 외 접근 차단 검증은 유지했다. [최초 실패](20261012-entry-agent-evidence/backend-initial-failed.txt)를 보존했고, 새 실행에서 87 PASS를 확인했다. 제품 기능 실패가 아닌 시험의 라우팅 기대값 오류로 분류한다.

## 문서 정리와 실제 지원 한계

[AGENT_STATUS_CONTRACT.md](../../design/AGENT_STATUS_CONTRACT.md)를 외부 에이전트에 전달하는 단일 계약으로 작성했다. 기존 AGENT_ORCHESTRATION/RUNTIME_ROLES의 중복·미구현 필드 목록은 삭제하고 링크로 대체했다. README/문서 지도/AGENTS/CLAUDE/API/논리 데이터 모델에서 새 계약을 참조한다.

bridge/worker/engine/policy/settings 코드를 대조했다. 현재는 단계 종료 JSON만 수신하며 실행 중 세부 퍼센트·heartbeat·agent HTTP push·판단 결과의 자동 Jira 생성·변경별 분석 분류 자동 반영은 구현하지 않았다. 문서 예시의 형식 확인은 실제 agent가 올바른 BSP 결과를 만든다는 증거가 아니다. 제품 코드 및 UI 시험 후 변경한 것은 문서와 시험 기록이며 에이전트 프로토콜 동작을 새로 구현한 변경은 없다.
