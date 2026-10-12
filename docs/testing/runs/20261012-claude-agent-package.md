# 2026-10-12 Claude 수동 오케스트레이터 패키지 검증

- run_id: 20261012-claude-agent-package
- executor: Codex
- recorded_at: 2026-10-12T03:34:06.799167+09:00
- scope: offline agent package / unit / contract / integration / UI regression / documentation
- code_revision / test_revision / dirty_diff_hash: `sha256:4059f100169fe5d68d4dfaea90c00f810f19ef7da4c35d95adadaccb2029ba21`
- [코드·시험·패키지 원본 manifest](20261012-claude-agent-evidence/source-manifest.json)
- 환경: macOS, Python 3.11.7, Node 22.23.2, Vite 7.3.7, 기존 설치 Chromium headless shell. Claude CLI는 이 환경에 없으며 모델 호출을 수행하지 않았다.

## 결과

| 검증 | 결과 | 증거 |
|---|---|---|
| 새 수동 패키지 시험 | 66 PASS | [전체 출력](20261012-claude-agent-evidence/backend.txt), [개별 결과](20261012-claude-agent-evidence/automated-results.csv), [JUnit](20261012-claude-agent-evidence/pytest.xml) |
| 기존 백엔드 회귀 | 87 PASS | 같은 출력. 전체 153 PASS, 기존 Starlette/httpx deprecation 경고 1개 |
| TypeScript/Vite 화면 빌드 | PASS | [빌드 출력](20261012-claude-agent-evidence/build.txt) |
| 격리된 데모 브라우저 회귀 | 3 PASS | [출력](20261012-claude-agent-evidence/browser.txt), [결과 JSON](20261012-claude-agent-evidence/browser-results.json) |
| 문서·요구사항·시험표 일치 | PASS | [문서 검사](20261012-claude-agent-evidence/doc-validation.json) |
| 패키지 내보내기·독립 실행 | PASS | 위 66개에 포함. [최종 배포 검사](20261012-claude-agent-evidence/package-check.json) |
| 실제 Claude 검색·호출·판단 품질 | NOT_RUN | T-91. 사용자가 직접 수행하기로 한 범위 |
| 대시보드 자동 조정/모듈 v2 | NOT_IMPLEMENTED / NOT_RUN | O1~O5, T-71~85 유지 |
| 실제 Linux/SSH/BSP/장비/Jira | NOT_RUN | 외부 연동 시험 없음 |
| Claude 독립 코드/문서 검토 | NOT_REVIEWED | 모델 검토를 실행하지 않음 |

## 변경과 시험 범위

실제 `.claude/agents/bsp-upgrade-orchestrator.md`를 추가했다. Read/Glob/Grep allowlist, model inherit, 입력 읽기→근거 대조→구조화 제안 반환 순서를 정의한다. Python 표준 라이브러리 도구는 입력/출력 검사, 파일 해시/경로 확인, 제안별 수동 검토 미리보기, 새 폴더로만 내보내기를 제공한다. JSON의 성공과 실제 작업 성공을 구분하고 모든 결과에 execution_performed=false를 표시한다.

주요 거부 시험: 다른 작업/세션/트리거/기준/모듈/시도/원인, 중복 키·ID, 변조/누락/경로 이탈/외부 심볼릭 링크 근거, 임의 명령·approved/percent, 미지원 자동 재시도, 잘못된 전환 근거. 정상 다섯 제안 종류와 계획 add/update/deactivate를 검사했다. UNKNOWN/종료 미확인/중지/계획 미확인/선행 미완료/판단 보류는 BLOCKED, 새 상태와 다른 기준은 STALE, 나머지는 WAITING_USER다. 분석의 선행 예외를 유지한다. 이 미리보기는 서버 gate 구현의 인수가 아니다.

패키지를 원본과 다른 임시 폴더에 내보내고 별도 Python 프로세스로 check-agent/validate를 실행했다. manifest 바이트 해시를 확인하고 같은 경로 재내보내기를 거부했다. 전역 설치/기존 CLAUDE.md 덮어쓰기/DB 복사/외부 실행은 없다. Read 도구의 실제 Claude 동작·OS sandbox·자료의 진실성·판단 품질은 이 검사로 증명하지 않는다.

기존 코드/설정/시험 32개는 이전 manifest와 바이트가 같으며 이번 환경에서 다시 실행했다. DB 스키마/API/worker/UI 동작은 변경하지 않았다. 브라우저는 포트 18766의 새 임시 runtime으로 실행하여 사용자 runtime을 초기화하지 않았다. 키 없는 진입·설정 유지·JSON export·좁은 화면, 수동 FAIL→재시도→PASS, 데모 선행 완료→나머지 모듈 진행을 확인했다.

## 실행과 이력

```bash
.venv/bin/python -m pytest -q --junitxml=docs/testing/runs/20261012-claude-agent-evidence/pytest.xml
npm run build --prefix apps/web
BSP_E2E_PORT=18766 BSP_BROWSER_EXECUTABLE=<installed-chromium> .venv/bin/python scripts/test_e2e.py
.venv/bin/python docs/testing/validate_docs.py
```

첫 패키지 시험은 [58 PASS](20261012-claude-agent-evidence/package-initial.txt)였고, 계획 추가/해제 및 중복·대상 검사를 8개 보강한 후 최종 66개와 기존 87개를 함께 실행했다. 이번 시험에서 FAIL은 없었다. 이전 REG-0001~0005 및 당시 FAIL/PASS 근거는 삭제하지 않았다.

T-86~90은 이 범위에서 PASS, 실제 사용자 Claude 인수 T-91은 NOT_RUN이다. T-61~70은 기존 기능 재검증의 최신 실행으로 갱신했다. T-01~60의 전체 인수 미확인과 T-71~85의 미구현 상태는 유지한다. 이전 85개 결과는 과거 실행 기록에서 확인 가능하며 운영 정상 기준은 계속 NONE이다. 파일 패키지와 수동 프로필은 자동 연동 O1 JSON Schema·영속 제안 접수·Jira 자동화의 대체 구현이 아니다.
