# 2026-10-12 작업 폴더 기반 내장 CLI 연결 검증

- run_id: 20261012-native-cli
- recorded_at: 2026-10-12T13:09:24.139105+09:00
- executor: Codex
- requirements/tests: D-42 / ADR-09 / RQ-37 / T-96~102, 기존 T-61~70·T-86~95 회귀
- code_revision / test_revision / dirty_diff_hash: `sha256:b4c196864c5c3a109575fb2381aa0ad50fc80458c8a2643bce8d1ff7872b44b2`
- [코드 파일별 manifest와 변경 목록](20261012-native-cli-evidence/source-manifest.json)
- 환경: macOS, Python 3.11.7, Node 22.23.2, Vite 7.3.7, Chromium headless shell. 테스트의 vendor CLI는 임시 Python 모의 실행 파일이다.

| 검증 | 결과 | 근거 |
|---|---|---|
| Python 전체 | 217 PASS, 기존 Starlette/httpx 경고 1 | [출력](20261012-native-cli-evidence/backend.txt), [JUnit](20261012-native-cli-evidence/pytest.xml) |
| TypeScript/Vite 빌드 | PASS | [출력](20261012-native-cli-evidence/build.txt) |
| 브라우저 전체 | 5 PASS | [출력](20261012-native-cli-evidence/browser.txt), [결과](20261012-native-cli-evidence/browser-results.json) |
| 개별 자동 시험 | 222 PASS | [CSV](20261012-native-cli-evidence/automated-results.csv) |
| 내장 설정 화면 시각 확인 | PASS | [화면](20261012-native-cli-evidence/settings.png), 입력/고급 모드/재접속 |
| 8765 기존 화면 적용 | PASS | [API·worker·기존 job 해시 보존](20261012-native-cli-evidence/local-preview.json) |
| 문서 링크·요구사항·시험 CSV | PASS | [검사](20261012-native-cli-evidence/doc-validation.json) |
| 실제 Linux/모델/BSP/Jira/장비 T-102 | NOT_RUN | 사용자가 직접 인수 예정. 실제 작업/모델 호출 없음 |
| 독립 Claude 검토 | NOT_REVIEWED | 모델 검토 미수행 |

## 구현과 확인한 범위

기본 native 연결은 계정 PATH에서 도구를 찾고 버전/필수 옵션·로컬 로그인 설정을 점검한다. CLI_READY와 실제 모델 접속 성공을 구분한다. 사용자 역할 파일은 읽어 job에 고정한다. 내장 CLI는 결과 schema/JSON 이벤트를 정규화하며 실행 토큰과 내부 owner는 프롬프트에서 제외한다. 모델 응답으로 worker 게이트/DB 상태를 변경하지 않는다.

코드의 실제 내용 해시·별도 리뷰 세션, 사용자 등록 Bash 빌드/검증/통합 명령, 출력 파일 갱신·허용 경로·해시를 검사했다. 수정/빌드/내장 검증은 같은 잠금을 사용한다. 환경 오류를 FIX 실패 횟수에 넣지 않고, 종료 불명은 UNKNOWN·잠금 보존 및 재시도 차단으로 처리한다. 기존 브리지·job snapshot·실패 이력·소스 자동 기준·수동 시험·데모 게이트는 유지한다.

시험 프로그램으로 worker의 연결→병렬 허용 분석→최초 계획→선행 코드/교차 리뷰/빌드/검증을 확인했다. 실제 LLM 추론/변경 품질·실제 BSP/보드·전체 운영 E2E를 검증한 결과는 아니다. 등록된 명령의 시험 범위/종료 코드 신뢰성은 프로젝트 인수에서 확인해야 한다. 기존 자동 조정 O1~O5, 보고 v2, 세션 프로세스 재접속, OS snapshot 격리는 여전히 후속 범위다.

## 최초 실패와 수정 이력

- 최초 Python: [205 PASS](20261012-native-cli-evidence/backend-initial.txt). 연결 흐름/리뷰/잠금 시험 추가 후 [208 PASS](20261012-native-cli-evidence/backend-intermediate.txt).
- 첫 UI: [3 PASS/2 FAIL](20261012-native-cli-evidence/browser-initial.txt), 새 선택 필드의 label 탐색 문제. [구조화 기록](20261012-native-cli-evidence/browser-initial-results.json).
- 두 번째 UI: [3 PASS/2 FAIL](20261012-native-cli-evidence/browser-second.txt), 추천 응답과 작업 폴더 편집 경합 및 textarea 재접속 label 문제. [구조화 기록](20261012-native-cli-evidence/browser-second-results.json).
- Python 추가 회귀: [213 PASS/1 FAIL](20261012-native-cli-evidence/backend-process-failed.txt). 종료한 프로세스의 PGID에 신호를 보내는 경계에서 PermissionError. 정상 종료 후 신호 생략, 실제 종료 권한 실패는 UNKNOWN/lease 유지로 수정하고 세 가지 방지 시험을 추가했다.
- 최종 Python 217 PASS, UI 5 PASS. REG-0006~0008은 [회귀 기록](../REGRESSION_LEDGER.md)에 연결한다. 최초 실패 파일은 삭제/덮어쓰기하지 않는다.

## 적용과 호환

현재 폴더에는 .git이 없어 Git 커밋 대신 파일별 내용 해시로 시험 기준을 기록했다. GitHub push/merge는 수행하지 않았다. DB schema_version=1 유지. 기존 8765 API를 재시작하고 worker를 실행했으며 기존 데모 job 하나의 전체 snapshot 해시가 그대로임을 확인했다. 설정은 demo이며 새 외부 작업/티켓/장비 적용 없음.

내장 모드가 없는 과거 job은 기존 브리지 의미로 실행한다. 설정의 정확한 자동 placeholder 네 개가 모두 미설치인 경우만 native로 정규화한다. 설치/사용자 브리지 배열은 보존한다. 브리지 기본 경로 채우기는 고급 모드에만 남겼다.

## 재현 명령

```bash
.venv/bin/python -m pytest -q
npm run build --prefix apps/web
BSP_E2E_PORT=8767 BSP_BROWSER_EXECUTABLE=<installed-chromium> .venv/bin/python scripts/test_e2e.py
.venv/bin/python docs/testing/validate_docs.py
```

[사용 안내](../../agents/ENVIRONMENT_AND_BRIDGES.md), [보고 계약](../../design/AGENT_STATUS_CONTRACT.md), [진행 기록](../../implementation/WORK_STATUS.md)을 함께 갱신했다.
