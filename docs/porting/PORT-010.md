# PORT-010 · Sonnet 기본과 사용량·시간

RQ-12/72·D-78. [관측 계약](../design/MODEL_USAGE_TIMING.md), [실행 증거](../testing/runs/20261117-sonnet-telemetry.md)를 함께 전달한다. 회사 필수 정책·COMPANY_MAP/APPLIED를 먼저 확인하고 회사 기능을 보존한다. 이 문서는 실제 회사 인수를 완료했다는 뜻이 아니다.

## 기준과 적용 위치

선행 원본은 `12a82a6b6018a9d271eb2750bbcb58764c8c24ba`이다. 코드·시험 고정 커밋은 `75751f385d1e386b3c09a377a0871f0ce03b5df4`다. 이 커밋의 41개 변경 파일과 검증 tree를 원격 main에 해시 대조해 반영했다. 기존 main 정책 D-76(별도 Claude 리뷰), native/v1/v2 어댑터·영속 attempt·TC usage 저장이 선행 조건이다. 새 JS 라이브러리나 DB 테이블은 추가하지 않는다. Python/Node 의존성은 기존 lock을 재사용한다.

- 공통 코드: `backend/domain/telemetry.py`의 정규화/집계, `policy.py`의 모델/구현 선택. 회사의 gate/수동시험/최종 검토는 그대로 연결한다.
- 호스트 연결: `backend/settings.py`, `backend/adapters/{native,bridge,capabilities}.py`, `backend/domain/{engine,orchestration}.py`, `backend/worker/main.py`, `backend/api/main.py`. 모델 결과 wire schema와 과금 메타데이터를 분리하고 worker journal 전에 저장한다.
- BSP UI: `apps/web/src/{Telemetry.tsx,main.tsx,style.css}`. API는 회사 인증·최신성 보호를 재사용한다. 같은 version의 사용량 변경도 반영한다.
- 공용 TC UI: `packages/gui-test-ui/src/{TestPage.tsx,test.css}`의 AttemptTiming 및 Run/TC/attempt 표시 부분만 적용한다. 다른 세션 timeout/Mock WIP를 이 기능의 필수 변경으로 가져오지 않는다.
- 시험: `tests/test_telemetry.py`, `tests/e2e/telemetry.spec.ts`; OpenCode 경로를 의도하는 기존 `test_engine.py`/`test_native.py`는 명시 선택을 사용한다.

## 보존·전달 절차

기존 runtime DB/설정을 백업하고 새 코드를 staged 경로에 준비한다. JSON 선택 필드만 추가하므로 과거 기록은 그대로 읽는다. 새 설정은 Claude/Sonnet 기본이며 기존 명시 모델을 보존한다. **기존 고정 job은 재저장하거나 새 profile로 덮어쓰지 않는다.** 새 설정만 저장하고 새 job에서 확인한다. 구버전으로 되돌릴 때는 코드/UI를 함께 복원하며 DB/기록을 reset하지 않는다. 관측 필드는 구버전이 실행 상태로 해석하면 안 된다.

플러그인은 새 profile의 implementation_tool/models를 손실 없이 전달한다. Bridge wrapper는 model_policy를 지원 모델로 대응하고 orchestration wrapper의 별도 모델 설정도 Sonnet으로 확인한다. 실제 사용량 미보고를 0으로 변환하지 않는다. Agent Monitor는 API·Worker·빌드 UI를 같은 코드로 갱신하고 기존 서비스는 `bash run.sh restart`로 갱신한다. Windows 커넥터 실행/SSH/UART 동작을 이 변경을 이유로 바꾸지 않는다.

검증 명령은 `.venv/bin/python -m pytest tests/test_telemetry.py tests/test_engine.py tests/test_settings.py tests/test_api.py`, `bash scripts/build-ui.sh all`, 격리 runtime의 `scripts/test_dashboard_browser.py telemetry.spec.ts dashboard.spec.ts orchestration.spec.ts`다. 실제 CLI 모델/과금 대조·회사 Linux/BSP/장비는 T-277이며 별도로 수행하고 APPLIED에 증거를 남긴다.
