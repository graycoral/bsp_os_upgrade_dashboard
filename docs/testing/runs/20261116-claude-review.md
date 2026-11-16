# 실행 도구 정리와 Claude 별도 세션 리뷰

RQ-13·RQ-37 / D-76. 코드·시험 기준은 `9f30b2b0294e413fc8364d790d5c8b1f59adcff1`, 비교 기준은 `e37a75d01bd4741e3b6d7a787543b36315d913aa`다. macOS / Python 3.11.7 / Node 22.23.4 / npm 10.9.9 / Chrome 157에서 로컬 모의 CLI·임시 DB로 수행했다. 개발 실행자는 Codex이며 실제 Claude 리뷰 세션이나 회사 모델을 호출하지 않았다.

## 변경

- 제품의 Codex 탐지·인증 확인·명령 생성·결과 변환과 설정 화면·기본값·예제 설정을 제거했다.
- OpenCode와 Claude 구현 모두 Claude의 새 세션으로 리뷰한다. v2 역할·계약 버전·배정 근거를 확인하고 v1/v2 결과 접수에서 구현 세션 재사용을 거부한다.
- 이전 설정의 폐기된 도구 항목은 조회·저장 시 정리한다. 다른 설정과 CAS 버전 검사를 유지한다. 과거 작업 snapshot에서 폐기된 도구를 직접 호출해도 실행을 거부한다.
- 과거 실행·시험·개발 작성자 기록과 수동 검토 패키지의 과거 attempt 읽기를 보존했다. 소스 해시의 기존 도구 메타데이터 제외 규칙도 유지한다.
- 요구사항·계약·역할 안내·현재 구성도와 플러그인/Agent Monitor 전달 지침을 갱신했다. DB 스키마 변경은 없다.

## 검증

기존 GUI Test 제한시간/Mock 관련 7개 WIP 파일은 제외하고 HEAD에서 만든 별도 checkout에 이번 변경만 복사했다. 개발 로그는 `.local-reports/20261116-claude-review/`에 보관하며 Git에 포함하지 않는다.

| 실행 | 결과 | 로컬 근거 |
|---|---|---|
| 설정·정책·API·계약·조정·수동 검토 패키지와 새 별도 리뷰 회귀 | 446 PASS, exit 0 | `focused-contracts.log` |
| 영향 Python 8개 파일 전체 | 524 PASS / 10 FAIL / 1 SKIP, exit 1 | `final-tests-v2.log` |
| 출력 크기/timeout 시험 재시도 | 1 PASS, exit 0 | `timeout-retry.log` |
| 수정 전 native·worker 비교 | 84 PASS / 9 FAIL / 1 SKIP, exit 1 | `baseline-tests.log` |
| Agent Monitor UI TypeScript·Vite 빌드 | PASS, exit 0 | `ui-build-retry.log` |
| 예제 설정 Profile 로드 | PASS | Claude/OpenCode 항목 확인 |
| 문서 링크·RQ/T 정합성 | PASS, 1775 links / 70 RQ / 269 T | `docs-check.log` |
| 브라우저 25개 회귀 | 14 FAIL / 1 중단 / 10 NOT_RUN, exit 130 | `browser-tests.log` |
| 설정 화면 T-95·T-101 재시도 | 2 FAIL, exit 1 | `focused-browser.log`, `focused-no-trace.log` |
| 수정 전 브라우저 T-39·T-59·T-95·T-101 | 4 FAIL, exit 1 | `baseline-browser.log` |

Python의 지속 실패 9개는 Linux `/proc` 기반 프로세스 식별·receipt와 그 결과를 사용하는 worker 시험이며 수정 전 기준에서도 재현됐다. 추가 출력 크기 시험 1개는 일시적으로 프로세스 그룹 종료 불명 판정이 나왔고 같은 코드의 단독 재시도에서 통과했다. 실제 Linux 프로세스 인수는 NOT_RUN이다.

브라우저에서는 초기 화면의 ‘작업 상태를 확인하고 있습니다’ 대기와 다운로드·단계 진행 대기가 발생했다. T-95·T-101의 초기 화면 대기는 수정 전 기준에서도 재현됐다. 같은 대기가 반복되어 확장 시험을 중단했고 미수행 건은 NOT_RUN으로 기록했다. 전체 UI 인수 완료 판정을 내리지 않았다. 실서비스나 사용자 runtime은 변경하지 않았다.

초기 시험에서 새 설정 회귀의 Settings import 누락과 이전 ‘작성 도구와 리뷰 도구가 달라야 한다’는 시험 조건을 수정했다. 실패 로그 `first-tests.log`, `isolated-tests.log`, `final-tests.log`를 보존했다. 첫 UI 빌드는 npm PATH 누락으로 exit 127이었고 설치된 Node 경로로 재시도해 통과했다.

### 실행 명령

```bash
PATH="/usr/bin:/bin:$PATH" .venv/bin/python -m pytest -q tests/test_settings.py tests/test_engine.py tests/test_api.py tests/test_native.py tests/test_orchestration_contracts.py tests/test_orchestration_runtime.py tests/test_orchestration_worker.py tests/test_claude_orchestrator.py
bash scripts/build-ui.sh dashboard
.venv/bin/python scripts/test_dashboard_browser.py dashboard.spec.ts settings-sync.spec.ts orchestration.spec.ts
.venv/bin/python docs/testing/validate_docs.py
```

## 전달

플러그인은 [최신 전달 요청서](../../agents/BSP_UPGRADE_PLUGIN_REQUEST.md)의 이번 절을 사용한다. Agent Monitor는 [PORT-007](../../porting/PORT-007.md#2026-11-16--claude-별도-세션-리뷰)의 파일·변경 위치·데이터 처리·빌드 절차를 따른다. 회사 Linux의 Claude/OpenCode 인증·추론, 실제 BSP·보드·Jira 인수는 NOT_RUN이다.
