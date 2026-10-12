# 2026-10-12 소스 자동 기준·브리지 기본값 검증

- run_id: 20261012-settings-defaults
- recorded_at: 2026-10-12T10:12:54.219043+09:00
- executor: Codex
- requirements/tests: RQ-36 / T-92~95; 기존 회귀 T-61~70, 수동 패키지 T-86~90
- code_revision / test_revision / dirty_diff_hash: `sha256:6091277a4e1d575ff541ce401cf63ed9a856e617a37ae959a7e206f2e5550b94`
- [파일별 manifest](20261012-settings-defaults-evidence/source-manifest.json)
- 환경: macOS, Python 3.11.7, Node 22.23.2, Vite 7.3.7, 기존 Chromium headless shell. Git은 시험용 임시 저장소 사용.

| 검증 | 결과 | 근거 |
|---|---|---|
| Python 전체 | 173 PASS, 기존 deprecation 경고 1 | [출력](20261012-settings-defaults-evidence/backend.txt), [개별 결과](20261012-settings-defaults-evidence/automated-results.csv), [JUnit](20261012-settings-defaults-evidence/pytest.xml) |
| TypeScript/Vite 빌드 | PASS | [출력](20261012-settings-defaults-evidence/build.txt) |
| 브라우저 | 4 PASS | [출력](20261012-settings-defaults-evidence/browser.txt), [구조화 결과](20261012-settings-defaults-evidence/browser-results.json) |
| 설정 화면 시각 확인 | PASS | [시험 화면](20261012-settings-defaults-evidence/settings.png). 기본값·빈 기준·누락 파일 안내 확인 |
| 기존 로컬 화면 적용 | PASS | [상태 확인](20261012-settings-defaults-evidence/local-preview.json). 빈 설정 기본값 반영, API만 재시작, 기존 job 유지 |
| 문서/요구사항/시험 목록 일치 | PASS | [검사](20261012-settings-defaults-evidence/doc-validation.json) |
| 실제 Linux/CLI 에이전트/BSP 빌드/Jira/장비 | NOT_RUN | 연결 프로그램 기본 경로만 제공. 실제 wrapper 실행 없음 |
| Claude 독립 검토 | NOT_REVIEWED | 수행하지 않음 |

## 구현 범위

source_revision 기본값을 빈 문자열로 바꿨다. demo는 시연용 기준을 자동 사용하고, bridge는 신규 OS 원본 Git HEAD를 깨끗한 상태에서 읽어 job/profile에 고정한다. 상태와 HEAD를 재확인하며 Git 관련 상속 환경과 repository fsmonitor 호출을 제외한다. 자동 커밋/checkout/파일 삭제를 하지 않는다. 직접 40/64자리 해시 지정은 형식 확인 후 유지한다.

같은 시작 명령 재전송은 원래 결과를 반환하여 바뀐 HEAD로 다른 작업을 만들지 않는다. 다른 새 작업만 새 HEAD를 읽는다. 설정 자체의 자동 기록 의도는 빈칸으로 유지한다. 이는 세 입력 소스 전체 snapshot이나 실행 중 파일의 불변성 보장이 아니다.

새 Profile의 브리지는 workspace/.bsp-dashboard/bridges/claude, opencode, codex, build를 기본으로 사용한다. 명시된 배열과 선택 도구의 []는 보존한다. 추천 API는 저장/실행하지 않고, UI는 빈 항목만 채우며 작업 폴더 변경 시 기본 경로만 재계산한다. 점검은 실행 파일 없음/권한 없음/파일 준비를 구분하고 build도 포함한다. FILE_READY는 실제 계약/도구 인증 성공이 아니다.

## 시험 상세

- 임시 Git의 깨끗한 HEAD, job 고정/중복 시작, 새로운 HEAD의 새 job, Git 없는 데모.
- 수정/미추적 파일, Git 없음/빈 저장소, 잘못된 직접 해시: 작업 미생성. 유효한 직접 해시와 Git 환경 오염 분리.
- Git fsmonitor 실행 스크립트를 설정한 임시 저장소에서도 소스 기준 조회가 외부 hook을 실행하지 않는지 확인.
- 기본 경로, 직접 명령/빈 배열 보존, 실행 파일/권한, 선택 Codex 미설치와 해제, 추천 API의 무저장·무실행.
- 설정 UI에서 workspace 변경→기본 경로 갱신→Claude 사용자 경로 유지→빈 OpenCode만 채움→저장/재접속→파일 미설치 표시.
- 기존 키 없는 진입/설정, 수동 FAIL→재시도→PASS, 데모 선행 전체 게이트 및 수동 오케스트레이터 패키지 회귀.

최초 Python 실행은 [172 PASS](20261012-settings-defaults-evidence/backend-initial.txt)였다. 자체 검토에서 Git fsmonitor 비실행 확인을 추가한 후 최종 173 PASS를 기록했다. 이번 변경의 시험 FAIL은 없으며 이전 실패 기록은 보존한다. 최종 변경은 소스 자동 조회의 실행 억제와 시험 하나이며 브라우저/빌드 대상 프런트엔드는 그대로다.

기존 8765 runtime의 설정 v1에서 빈 agent/build 경로를 채우고 알려진 데모 기준을 자동 기록으로 바꿔 설정 v2를 저장했다. 변경 전후 기존 job 전체 snapshot이 같음을 확인했다. API만 최종 코드로 재시작했고 worker·기존 작업·DB schema_version=1을 유지했다. 새 외부 작업이나 원격 연결은 수행하지 않았다.

## 재현 명령

```bash
.venv/bin/python -m pytest -q
npm run build --prefix apps/web
BSP_E2E_PORT=18766 BSP_BROWSER_EXECUTABLE=<installed-chromium> .venv/bin/python scripts/test_e2e.py
.venv/bin/python docs/testing/validate_docs.py
```

사용 방법은 [설정·브리지 안내](../../agents/ENVIRONMENT_AND_BRIDGES.md)에 정리했다. 기본 경로는 실제 연결 프로그램 설치를 대신하지 않는다. GitHub 반영 및 운영 인수 기준 승격은 수행하지 않았다.
