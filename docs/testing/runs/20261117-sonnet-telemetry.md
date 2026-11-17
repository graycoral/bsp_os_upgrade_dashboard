# 2026-11-17 · Sonnet 기본·사용량/시간

RQ-12/72·D-78·T-274~277·REG-0105. 사용자 구현 지시와 상세 답변, 완료 후 커밋·main 병합 지시를 적용했다. 시작 main은 `1da1da2173c84689662de669d6a95fb8775c7037`이고 최종 분리 대상은 동시 게시된 자동 serial 기능을 보존한 `12a82a6b6018a9d271eb2750bbcb58764c8c24ba`다. 다른 세션의 보드 커넥터 정리/force-stop/timeout WIP는 제외한다.

## 구현과 발견

새 설정/작업에서 Claude Sonnet을 분석·설계·구현·독립 리뷰·조정·질의 기본으로 명시하고 OpenCode는 구현 도구로 선택한다. 명시 모델·기존 고정 job·Opus 난항 전환·별도 Claude 리뷰·승인/배타/수동시험 게이트를 유지한다. CLI 공식 sonnet 별칭을 사용하며 특정 최신 버전이나 단가를 하드코딩하지 않는다. 등록 빌드·검증·통합은 기존 명령이다.

BSP 전체 과금은 기존에 공통 수집/표시가 없었다. TC 사용량은 Run 선택 후 접힌 상세에 존재했다. '삭제됨'이라고 단정하지 않고 전체→모듈→단계→ROUND의 관측/표시를 추가했다. CLI 외곽 정보와 서버 시간만 사용하고 실패·재시도·별도 리뷰·조정/질의를 집계한다. 실제0/일부/미보고, 캐시 읽기/쓰기, 병렬 경과/ROUND 누적을 구분한다. 기존 JSON 선택 필드로 저장하고 DB 테이블은 추가하지 않는다.

사용량 audit는 상태 CAS를 갱신하지 않으므로 기존 UI의 같은 version snapshot 생략을 제거했다(REG-0105). 메타데이터는 모델 입력/조정 snapshot/결과 journal hash에서 분리한다. ROUND는 별도 pagination으로 전체 영속 이력을 읽는다. TC는 기존 사용량 코어를 유지하고 Run/TC/시도 시간을 함께 표시한다. 회사 전달은 [PORT-010](../../porting/PORT-010.md), 필드/계산 경계는 [계약](../../design/MODEL_USAGE_TIMING.md)에서 관리한다.

## 검증 대상과 결과

코드 내용 기준 `workingtree:sha256:cf008542c402f19424c5369e9764346780eb361d5670eeada549a33aca78766b`, 시험 내용 기준 `workingtree:sha256:69f5a0284b3c4bb6620a1a1c9140e0599fdc09157830b8c62f2ba3d46c57e838`. 파일명+NUL+최종 bytes+NUL을 정렬 순서로 SHA256한 값이며 파일 목록은 로컬 evidence-manifest.json에 보존했다. raw 로그는 `.local-reports/20261117-sonnet-telemetry/`에만 보관한다. 환경 macOS/Python3.11, 고정 Node22.23.2/npm10.9.8, Chromium1243. 공급자 CLI는 fake argv/ProcessResult이고 실제 추론·과금 서비스·BSP/보드는 호출하지 않았다.

| 검증 | 결과 | 근거 |
|---|---|---|
| 새 정책/집계 unit·API·native argv·실패/별도 리뷰·조정·예외 보존 | PASS | test_telemetry.py 18개; candidate-regression-publish.log |
| engine/settings/API·v2 계약·조정 core | PASS | 추가 hardening 전 새 시험17개 포함 386 PASS; candidate-core-final.log |
| 지원 가능한 native/process/worker 회귀 | PASS | 90 PASS/1 SKIP; 기존 플랫폼9개 별도 비교; candidate-supported-process.log |
| 최종 통합 Python | PASS · 477 PASS/1 SKIP/기존 플랫폼9개 제외 | candidate-regression-publish.log |
| BSP/단독 TC UI typecheck·Vite build | PASS | candidate-build-final.log; 기존 lock 재사용 |
| BSP workflow·조정·Sonnet 선택·작은 전체/모듈/단계/ROUND·TC 사용량/시간 | PASS | candidate-browser-pass.log 15 PASS; TC 독립 GUI-UI-17도1 PASS |
| 문서 연결·요구사항/시험/CSV 일치·diff 공백 | PASS | candidate-docs.log; git diff --check |
| 실제 공급자 모델/과금 대조·회사 Linux/BSP/장비 | NOT_RUN | T-277 |
| 별도 Claude/Astra 제품 변경 코드 리뷰 | NOT_REVIEWED | 이 변경의 독립 모델 리뷰를 실행하지 않음 |

## 실패 이력과 한계

초기 build 명령 경로가 오래된 scripts/build.sh여서 실패했고 현재 scripts/build-ui.sh로 바로잡았다. apps/web/node_modules가 비어 있어 lock 기반 npm ci 후 재실행했다. 첫 TS 검사에서 불필요 React import/optional value 타입 오류를 수정한 뒤 두 UI가 통과했다. 새 v2 조정 시험은 fixture에 UUID/session과 schema_version이 빠져 process 진입 전 거부됐고 유효한 계약으로 수정했다. 계약 검사를 약화하지 않았다.

최초 관련 Python 넓은 실행은 472 PASS/1 SKIP/9 FAIL이었다. 실패9개는 test_native의 native pipeline1, test_orchestration_worker의 Linux boot/proc identity3·receipt launch1·legacy control receipt4다. 변경 전 `1da1da2`에서 같은9개 FAIL을 재현했다(baseline-platform.log). macOS에는 /proc boot identity와 Linux receipt가 없어 실제 연결 READY/launch 증거를 확정할 수 없다. 이9개는 제품 PASS에 포함하지 않고 최종 지원 범위 실행에서 명시적으로 제외했다. 초기 단독 timeout/output-bound 시험의 UNKNOWN도 보존하며 이후 회귀 실행에서 PASS였다.

넓은 브라우저 실행에서는 GUI-UI-02 복구 실패 이후 예약/제어 상태 때문에 후속03~05가 실패해 중단했다(candidate-browser.log). 별도 실행의 GUI-UI-07은 COMPLETED FAIL 대신 PAUSED INCOMPLETE여서 실패하고 뒤17도 실행이 막혔다(candidate-browser-final.log). 변경 전 `12a82a6`의 깨끗한 runtime에서02와07의 같은 실패를 각각 재현했다(baseline-browser.log, baseline-tc-retry-browser.log). 기존 fail-stop/종료 확인 흐름과 시험 기대의 차이는 이번 기본 모델/관측 변경으로 해결했다고 주장하지 않는다. 이력을 지우거나 기존 시험을 완화하지 않았고 관련 새 표시 시험17은 독립 runtime에서 통과했다.

기존 wrapper의 공급자 사용량은 미집계다. 실제0과 다르며 기존 과거 기록을 backfill하지 않는다. 프로세스 종료~저장 사이 강제 종료로 잃은 미수집 사용량을 추정하지 않는다. CLI 보고 비용은 구독/실제 청구서와 다를 수 있다. 로컬 모의 PASS는 Linux/회사 인수나 전체 제품 배포 가능 판정이 아니다.
