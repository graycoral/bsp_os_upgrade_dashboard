# 새 작업 직접 생성의 구현 기본값 누락

RQ-12/72·D-78·T-274·REG-0110 후속. 회사에서 새 작업의 코드 구현 단계가 OpenCode로 표시된다는 보고를 받았다. 로컬에서 같은 표시를 만드는 직접 생성 경로를 재현했지만 회사의 실제 생성 경로·실행 버전·고정 profile은 확인하지 못했다.

## 재현과 수정

일반 대시보드 API는 Settings.get의 Profile 검증을 거쳐 Claude/Sonnet 기본값을 받는다. Engine.create에 과거 형식의 dict를 직접 전달하는 플러그인 경로는 prepare_job_profile이 구현 도구 필드를 채우지 않았다. 새 job에도 필드가 빠진 채 저장되어 기존 job 호환 정책인 OpenCode 우선이 적용됐다.

prepare_job_profile에서 두 정책 필드를 먼저 정규화한다. 구현 도구가 없으면 Claude, Claude 모델이 없거나 비어 있으면 Sonnet이다. 명시 도구/모델·입력 dict는 보존한다. 정규화 이후 환경 확인·capability·fingerprint를 고정한다. 기존 job과 동일 요청 재전달은 이 경로를 다시 실행하지 않는다. 회사가 자체 생성 함수를 쓰면 같은 연결을 적용해야 한다.

## 검증과 제약

코드·시험 고정 커밋은 `b7735ac8f84fb04c537311c8eaed42c531f5a4e7`다. 최초 재현 기준 f0fd97c에서 누락/빈 모델/명시 모델 세 경우 모두 새 코드 claim이 OpenCode여서 실패했고 수정 후 Claude/Sonnet 또는 명시 모델로 배정됐다. 일반 API 경로는 수정 전에도 정상이다. 중간 시험의 Store.save fixture event 인자 누락은 고쳐 재실행했으며 실패 로그를 보존했다.

```bash
python -m pytest -q tests/test_new_job_tool_policy.py tests/test_settings.py tests/test_engine.py tests/test_orchestration_runtime.py tests/test_orchestration_contracts.py tests/test_api.py tests/test_telemetry.py
python docs/testing/validate_docs.py
```

추가 시험은 명시 OpenCode/모델 보존, 기존 snapshot·멱등 재전달 불변, v2 capability 고정 전 정규화를 확인한다. 모의 BSP 결과와 실제 Engine claim을 사용하고 CLI 모델·실보드·회사 서버를 호출하지 않았다. macOS Python3.11에서 수행했다.

- 최종 회귀394 PASS, exit0. 게시 후보에서도 같은394 PASS를 확인했다. `.local-reports/20261117-new-job-tool/final.log`; 게시 후보 worktree의 `.local-reports/publish/final.log`.
- 관련 native 포함 범위는 185 PASS/2 DESELECTED. 프로세스 종료 확인 관련 worker 시험은 이전 기준에서도 실패했다. 출력 제한 시험은 최초 실행에서 종료 미확인으로 실패했지만 이전 기준과 수정본의 개별 재실행은 PASS였다. 이 두 항목의 실패를 숨기거나 제품 PASS로 확대하지 않는다.
- 원본 로그: `before.log`, `baseline-tests.log`, `after-1.log`, `after-2.log`, `timeout-recheck.log`, `focused.log`. 모두 로컬 `.local-reports/20261117-new-job-tool/` 아래에 보존한다.
- Astra/xhigh 독립 리뷰 APPROVED. 관련 회귀353 PASS, 최종 신규 시험7 PASS, diff 검사 PASS. 독립 로그는 `.local-reports/20261117-independent-new-job-policy-review/targeted-1.log`, `final-new-policy.log`다. Claude 리뷰로 표시하지 않는다.

UI·DB 스키마·보드 커넥터 변경은 없다. 회사 실제 BSP/모델 실행은 NOT_RUN이다. 명시 `implementation_tool=opencode`는 계속 OpenCode이므로 이번 수정으로 모든 회사 상황이 해결됐다고 단정하지 않는다. [플러그인·Agent Monitor 적용](../../porting/PORT-010.md#새-작업-직접-생성-기본값-보완), [전달 요청](../../agents/BSP_UPGRADE_PLUGIN_REQUEST.md#2026-11-17--새-작업-구현-기본값-적용)을 따른다.
