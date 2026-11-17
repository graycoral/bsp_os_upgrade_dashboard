# 모델 기본·사용량·시간 계약 · D-78

RQ-12/72. 새 설정/작업은 `implementation_tool=claude`, `models.claude=sonnet`이다. Claude의 분석·설계·구현·별도 리뷰·조정·질의 호출에 모델을 명시한다. OpenCode는 명시 선택한 구현에만 사용한다. 명시 모델은 보존하고 Claude 빈 값은 Sonnet으로 정규화한다. 새 설정 기본과 과거 job의 동결 profile을 구분한다. 동결 profile에 구현 도구 필드가 없으면 기존 OpenCode 우선·configured 모델 정책을 유지한다. 빌드/검증/통합 등록 명령·수동 장비시험·확인/판단/선행/배타 게이트는 그대로다. OpenCode의 기존 난항 Opus 전환은 유지한다.

`sonnet`은 Claude CLI의 공식 [모델 별칭](https://code.claude.com/docs/en/model-config)이다. 실제 모델 ID는 CLI가 보고한 경우에만 표시한다. 요청 별칭으로 실제 모델을 추정하지 않는다. 기존 JSON wrapper는 전달받은 model_policy를 실제 실행 모델에 적용해야 한다. orchestration v1의 별도 wire schema는 바꾸지 않으므로 기존 wrapper의 조정 모델은 현지 설정으로 Sonnet을 적용하고 확인한다.

## 관측·저장 경계

`backend/domain/telemetry.py`가 공개 조회 집계를 소유한다. Native는 실제 프로세스의 서버 시작/종료와 monotonic 시간을 관측하고 Claude 외곽 JSON `modelUsage`/`usage`·`total_cost_usd`, OpenCode JSON `step_finish`의 `tokens`/`cost`를 읽는다. OpenCode step ID 재전송은 중복 집계하지 않는다. 모델이 작성하는 structured_output/report/터미널 문장에서는 비용을 읽지 않는다. 성공/실패/계약 거부/UNKNOWN 호출도 보고된 관측값을 남긴다. 공급자 envelope가 없거나 파싱할 수 없으면 미집계다. 가격표를 적용하거나 청구서를 추정하지 않는다. CLI 보고 비용은 실제 결제/구독 청구액과 동일하다고 보증하지 않는다.

실행 attempt의 기존 JSON에 `telemetry_calls`, job에 `control_telemetry`를 선택 필드로 저장한다. DB 테이블 추가/과거 backfill은 없다. call 레코드는 서버 발급 id, tool, role, requested_model, 서버 started_at/ended_at, duration_seconds, models, cost_usd만 보존한다. 모델 행은 provider/model, input_tokens/output_tokens, cache_read_tokens/cache_write_tokens, cost_usd다. 제한된 길이·유한 비음수 숫자로 정규화하고 원문/자격정보/임의 키를 저장하지 않는다. call ID는 불변이며 replay/늦은 완료가 비용을 두 번 더하지 않는다. 조정/질의는 전체에 한 번, 모듈 지정 질의는 해당 모듈에도 포함한다.

Bridge.execute는 구현과 별도 리뷰의 call을 함께 모으고 Worker가 결과 journal 이전에 분리 저장한다. 메타데이터는 agent 결과 wire/내용 hash에 포함하지 않는다. audit 저장은 상태 CAS version/updated_at을 바꾸지 않는다. 늦은 관측 기록은 해당 attempt에 추가하되 결과 완료를 승인하지 않는다. 모델 입력/조정 snapshot에서는 관측 필드를 제외한다. 프로세스 종료와 저장 사이의 강제 종료로 수집하지 못한 사용량은 과거 출력에서 추정 복원하지 않는다. 기존 wrapper의 공급자 사용량은 수집하지 않으며 서버 호출 시간만 기록한다.

## 조회와 작은 표시

job/module/stage의 `telemetry` projection은 models, cost_usd, reported_cost_usd, status, round_count/call_count, total_seconds, elapsed_seconds, timing_partial, tokens_partial을 제공한다. 비용 status는 `reported`/`partial`/`unavailable`/`not_applicable`이다. 미보고 토큰·비용은 null이고 실제 보고된 0은 0이다. partial이면 알려진 비용 소계와 일부 미집계를 함께 표시한다. 같은 모델의 일부 호출이 미보고이면 그 필드 전체가 미집계다. 다른 호출의 모델 자체가 미보고이면 알려진 모델 합계는 전체가 아니며 tokens_partial로 표시한다. demo·등록 명령만 실행한 단계에 유료 모델 비용을 만들지 않는다.

ROUND는 서버 attempt 하나이고 구현 ROUND 시간에는 별도 리뷰가 포함된다. 단계 누적은 실패/재시도를 포함한 ROUND 서버 시간 합이다. 모듈 경과는 첫 관측 시작부터 마지막 종료까지이며 병렬 수행·대기 때문에 누적과 다를 수 있다. 전체 경과는 작업 생성부터 최종 검토까지이며 완료 전에는 현재 시각까지다. 실행/UNKNOWN/수동 입력 대기 ROUND는 현재까지 경과를 보여준다. 오래된 시작/종료 누락은 시간 미집계/일부 미집계로 남긴다. call duration은 monotonic 프로세스 시간이고 ROUND는 서버 배정~완료 wall time이므로 값이 같을 필요가 없다.

`GET /api/v1/jobs/{job_id}/telemetry?module_id=...&stage=...&offset=0&limit=25`는 최신 시작부터 ROUND 목록을 반환한다. items/total/offset/next_offset 구조, limit 1~200, offset>=0이다. 모듈/단계 필터를 지원하고 상태 변경 권한을 부여하지 않는다. 공개 항목은 ROUND 식별·순번·상태·tool/model·서버 시간·집계·정규화 call만이며 token/owner/process receipt/raw output은 제외한다. snapshot의 attempt 최신10개 제한과 별개로 전체 영속 이력을 읽는다.

BSP 전체/모듈/단계에 11px 요약을 두고 모델별/ROUND 상세는 접어 둔다. 전체 모델 행은 작게 노출하며 단계·모듈의 모델별 내역과 ROUND는 펼쳐 본다. 상세는 열 때만 읽고 25개씩 더 조회한다. 기존 snapshot 최신성 검사를 통과한 같은 version도 반영하여 audit/경과가 보이게 한다. TC Run/TC/attempt는 기존 usage contract를 재사용하고 서버 시도 시간 요약을 추가한다. TC 입력·출력·비용 미집계 규칙은 기존 GUI Test 코어가 소유한다.

검증: [실행 기록](../testing/runs/20261117-sonnet-telemetry.md), 이식: [PORT-010](../porting/PORT-010.md). 실제 모델/회사 인수는 T-277 NOT_RUN이다.
