# 2026-11-06 · O1~O4·모듈 보고 v2·복구 검증

최종 상태: **O1~O4 로컬 구현·모의 검증 완료 / 독립 코드 검토 APPROVED / Linux·Windows CI SUCCESS / O5·실환경 인수 NOT_RUN / 운영 baseline NONE**. 제품 소스/시험 기준은 `1899e034120447559fd8d87129b220936f797895`이며 [PR #14](https://github.com/graycoral/bsp_os_upgrade_dashboard/pull/14)로 전달한다. 시작 커밋 `2c6bf29` 이후의 실패·검토·재시험과 당시 대기 상태는 아래에 순서대로 보존하고 최종 판정은 마지막 CI 절을 따른다. RQ-30~34/D-58, 기존 T-71~85를 사용한다. 과거 D-39 문서 전용·D-40 수동 패키지·D-42 내장 v1 연결의 검증 범위를 소급 변경하지 않는다.

## 범위와 역할

사용자는 남은 자동 조정 O1~O4와 복구의 구현·로컬 검증을 승인했다. 기본 모듈 보고 v1·조정 OFF·새 작업에만 설정 적용·단일 실행 관리자·기본 수동 장비 시험·최종 사람 검토를 유지한다. 실제 모델/BSP/보드/Jira 실행과 운영 배포는 이번 구현 검증에 포함하지 않는다.

| 역할 | 실제 배정 |
|---|---|
| 요구 분석·구조 설계 | Astra XHigh |
| 상세 설계 | Astra High |
| 백엔드 계약·소스/전송, 백엔드 런타임/저장, UI 구현 | 각각 Sol High |
| 별도 시험 작성 | Sol Medium |
| 새 독립 코드 리뷰 | Sol High |
| 별도 시험 실행·보고 | Luna Low |

계약/fixture, v2 보고/후보/보류, 영속 조정 큐/제안, API/UI, BSP DB의 추가 migration과 오프라인 백업/복원을 구현 중이다. 필드 권위는 [보고 계약](../../design/AGENT_STATUS_CONTRACT.md), [조정 명세](../../design/ORCHESTRATOR_SPEC.md)와 `contracts/*.schema.json`이다. GUI Test 별도 DB의 schema1과 BSP schema2를 혼동하지 않는다.

## 최초 증거와 실패 이력

원본 stdout/stderr·JSON/XML·manifest는 `.local-reports/orchestration-20261106/` 및 `.local-reports/recovery-drill-20261106/`에만 보존한다. 이 경로는 로컬 전용이며 Git에 포함하지 않는다.

| 실행 | 현재 결과·제한 |
|---|---|
| 최초 신규 Python 시험 | 99개 중 97 PASS / 1 FAIL / 1 Linux 전용 SKIP. 복구 fixture 파일명 실패의 시험 수정 후 별도 재실행 대기. 최초 결과 보존 |
| 기존 7개 파일 Windows 비교 | 기능 트리와 깨끗한 `2c6bf29` 모두 158 PASS / 41 FAIL / 37 ERROR. 235개 정확한 JUnit node ID/결과 비교 차이0. 기존 Windows 환경 결과이며 Linux/POSIX 통과 근거가 아님 |
| UI production build | `ui-build-03` PASS. UI 실행 시험은 아직 미수행 |
| 소스 담당 smoke | import/구문 검사만 수행. 제품 시험의 대체가 아님 |
| 확장 시험 최초 실행 | 160개 중151 PASS / 6 FAIL / 3 Windows 제한 SKIP / 0 ERROR. 후보 metadata4건·bridge private observation fixture1건·실제 worker의 demo helper simulation 근거1건을 수정 중. guard를 약화하지 않고 fixture/구현을 바로잡은 뒤 별도 Luna 재실행 대기 |
| 새 독립 리뷰 | `.local-reports/orchestration-20261106/review/findings.md`: 6개 P1/P2, CHANGES_REQUESTED. 수정 및 해당 소스 재검토 전 APPROVED가 아님 |

리뷰의 실제 발견은 미해결 `needs_decision`의 계획 확인 우회, 리뷰 보고의 blocking 후보 누락, 비코드 역할의 오래된 소스 허용, v1 조정/질문 receipt 누락, 실제 변경과 무관한 diff 허용, polling의 전체 보고 반복 전송이다. [REG-0050~0055](../REGRESSION_LEDGER.md)에 원인·재현·방지 시험을 기록했다. 담당별 수정·방지 시험을 진행 중이며 최종 수정 커밋·재실행 ID는 확정 후 추가한다. 환경 제약을 제품 결함으로 기록하지 않는다.

## 실제 읽기 전용 복구 연습

`recovery-drill-20261106/source-01`에서 기존 BSP schema1 DB의 일관된 백업·별도 경로 복원을 수행했다. 원본 해시 불변, 복원 DB 해시 일치, integrity/foreign-key 검사 통과. meta1/jobs1/commands3/events3/leases0/config1을 확인했다. 실제 artifact와 작업 결과는0개였으므로 실제 산출물의 누락/변조 음성 검증은 수행하지 못했다. 별도 populated fixture 시험이 필요하며 전체 운영 복구 성공으로 확대하지 않는다. GUI DB4개는 읽기 전용 목록 조사만 했고 백업하지 않았다.

복구 helper는 DB와 참조 산출물/보고 근거를 새 목적지에 복사하고 해시·참조를 검사한다. 복원은 서비스 시작·lease/UNKNOWN 해제·migration·운영 승격을 자동 수행하지 않는다. [복구 절차](../../agents/ORCHESTRATION_V2_OPERATIONS.md)를 따른다.

## 실제 연동 준비 상태

설정된 SSH에 strict BatchMode 제한 시간 점검은 exit255였으며 Linux CLI/인증을 검증하지 못했다. 로컬 API8766 health HTTP200은 Linux 연결 증거가 아니다. 현재 프로필은 demo/native이고 세 소스 root·빌드 명령·Jira URL/프로젝트/인증이 준비되지 않았다. TC root가 상위 작업 폴더까지 넓어 범위를 확정해야 하며 이미지/flash manifest/fastboot 대상도 미확인이다. Linux 작업/세 소스 root·Jira 설정 위치와 TC/이미지/manifest 위치에 대한 사용자 응답을 기다린다. 비공개 호스트·계정·토큰은 이 문서에 기록하지 않는다.

T-85/T-91/T-102/T-108/T-130/T-136/T-141/T-160의 실제 환경 인수는 증거 전 NOT_RUN이다. 필요한 연결·입력 미준비는 BLOCKED 준비 조건으로 구분하며 로컬 시험으로 PASS를 만들지 않는다. 실제 BSP 수정/빌드·모델 추론·장비 퓨징·Jira 발송·실서비스 변경은 수행하지 않았다.

## 후속 실행과 독립 재검토 — RR4 수정 전 기준

아래는 최초 실패를 대체하여 삭제하는 기록이 아니라 별도 후속 실행이다. 실행자는 별도 Luna Low이며, 문서 담당자는 제품 시험을 실행하지 않았다. RR4 수정 및 신규56개 시험 이후의 최종 결과는 아직 없다.

| 실행 ID / 로컬 근거 경로 | 명령·결과 | 판정 범위 |
|---|---|---|
| `tests-expanded-20261106-001` | 신규4개 Python 파일 최초 확장: 160개 중151 PASS / 6 FAIL / 3 SKIP, exit1 | 후보 metadata4건, bridge private observation fixture1건, demo helper simulation 근거1건의 실패 보존. guard를 완화하지 않고 fixture/구현 보완 |
| `tests-rereview-final-20261106-001` | `python -m pytest tests/test_orchestration_contracts.py tests/test_orchestration_runtime.py tests/test_orchestration_worker.py tests/test_recovery_bundle.py -q` 및 고유 basetemp/JUnit 옵션: 235개 중232 PASS / 3 플랫폼 SKIP, exit0 | RR4 수정 전 신규 시험. Windows에서 실제 POSIX 그룹 종료 검증으로 확대하지 않음 |
| `windows-suitable-existing-20261106-001` | Windows 적합 기존 회귀 선택: 422개 중416 PASS / 6 SKIP, exit0 | 기존 Windows 동작 회귀. POSIX 의존7개 파일의 전체 통과를 뜻하지 않음 |
| `browser-expanded-20261106-001` → `browser-final-20261106-001` | `npx playwright test tests/e2e/orchestration.spec.ts`: 최초4 PASS / 2 TIMEOUT → 보완 후6 PASS, 최종 exit0 | T-73/79/82/83/84 합성 API fixture UI. 최초 timeout·trace 보존, 실제 외부 연결 없음 |
| `ui-build-04` | `npm --prefix apps/web run build`, exit0 | TypeScript/production build. 실제 CLI·장비 인수와 별도 |

각 경로의 기준은 `.local-reports/orchestration-20261106/<실행 ID>/`이며 stdout/stderr·JUnit·trace는 Git 제외다. 위 명령의 정확한 추가 인자·환경·시각·소스 manifest는 별도 실행자의 최종 보고로 확정할 예정이다. 과거 결과를 현재 RR4 수정 소스의 검증으로 재사용하지 않는다.

기존 POSIX 의존7개 파일의 Windows 비교 수치 정정: pytest 단계별 원본 요약은 기능 트리/깨끗한 `2c6bf29` 모두 **158 PASS / 41 FAIL / 37 ERROR**다. 반면 **235개 정확한 JUnit node ID**를 각각 하나의 결과로 비교하면 양쪽 모두 **158 PASS / 41 FAIL / 36 ERROR**, 기능 트리만의 결과 차이0이다. 이는 단계별 ERROR와 고유 node 집계의 차이며 어느 쪽도 Linux PASS가 아니다. 최초 표의 단일 집계 해석은 이 정정으로 보완하며 원본 실패는 보존한다. Linux CI는 현재 대기다.

독립 Sol High의 `rereview-1.md`는 초기6건 수정 확인 후 RR1(v1 job의 명시 v2 수락), RR2(부모 결과 없는 review 실행 중 lease 해제), RR3(해결된 동일 후보의 보류 재생성)를 추가했다. `rereview-2.md`는 초기6건과 RR1~3의 해당 수정에 남은 결함이 없음을 확인했고, reviewer가 선택89개를 직접 실행해 **89 PASS / 139 deselected**, 실패/skip0을 기록했다. 이는 reviewer의 제한된 재현·시험이며 별도 전체 실행을 대신하지 않는다.

동일 재검토의 **RR4/P2**는 frozen tool의 역할 capability를 구현/리뷰 선택과 호출 직전에 적용하지 않은 결함이다. OpenCode가 reviewer 전용으로 광고돼도 implementer로 선택될 수 있었다. REG-0059에 수정·역할 행렬 시험을 추적했다. 이 재검토 당시 상태는 **CHANGES_REQUESTED**이며 뒤의 최종 코드 승인과 실행 결과를 구분한다.

최종 독립 Sol High의 `review/final-review.md`는 `final-manifest.json`에 고정된 소스에서 초기6건+RR1~4 총10건을 다시 확인해 **APPROVED**했다. reviewer의 최종 소스 개별5건 확인은 역할 부적합 OpenCode의 Claude/Codex 선택, 부적합 wrapper/native 호출 거부, 역할 쌍 부재 거부, v1 선택 보존이며 모두 통과했다. 이전89개 실행은 이전 manifest에만 해당한다. 최종 전체 시험/브라우저/Linux CI나 T-71~84의 모든 세부 조건 통과를 reviewer가 주장하지 않았으며 별도 실행·목록 대조를 기다린다.

## RR4 이후 별도 실행 — 실패 보존

별도 Luna Low의 `rr4-targeted-20261106-001`은 신규56개 **56 PASS, exit0**이다. `tests-final-20261106-001`은 신규4개 파일 총291개 중 **286 PASS / 2 FAIL / 3 플랫폼 SKIP, exit1**이다. T-80 bridge fixture가 execution만 bridge로 바꾸고 명시 frozen capability를 갖추지 않은 실패와 T-81 worker pending assertion 실패를 확인했다. 후자는 같은 원인인지 추가 확인 중이다. fixture/세부 인수 조건 시험 담당자가 수정·보강 중이며 이 결과를 최종 PASS로 바꾸지 않는다. 소스의 독립 코드 APPROVED와 fixture 실행 결과를 구분한다. 로그/JUnit은 같은 로컬 실행 ID 경로에 보존한다.

## T-71~84 인수 조건과 시험 연결

아래는 인수 조건별 실제 시험 연결이다. `C`=`tests/test_orchestration_contracts.py`, `R`=`tests/test_orchestration_runtime.py`, `W`=`tests/test_orchestration_worker.py`, `B`=`tests/test_recovery_bundle.py`, `E`=`tests/e2e/orchestration.spec.ts`다. `test_` 이후의 이름으로 각 실제 함수를 찾을 수 있다. 오른쪽 열은 확인할 조건을 보존한 목록이며 그 실행·플랫폼 대조와 최종 PASS 범위는 마지막 CI 절에 연결한다. T-73/74/81의 부족했던 정확한 조건은 아래 신규17개로, create replay는 REG-0060의9개 및 기존 T-100으로 보완했다.

| ID | 목록의 인수 조건 → 현재 방지 시험 | 최종 판정에 필요한 근거 |
|---|---|---|
| T-71 | 임의 kind/셸/변조 일괄 거부: C `t71_entire_actionable_batch_is_rejected_for_unsafe_proposals`; 계획·선행·수동·최종/별도 리뷰 경계: W `t71_t78_full_demo_v2_worker_preserves_confirmation_boot_manual_and_final_gates` | 전체 worker/정책 회귀 및 단일 배정·공유 lock 회귀 |
| T-72 | 중복/늦은 이벤트·job active1: R `t72_queue_dedup_active_run_and_late_trigger_survive_independently`, `t72_concurrent_coordinator_claim_has_one_winner`; 결과 선접수·일반 성공/조회 무호출·동일 세션 질문 직렬화: W `t72_*` | 영속 event/질문/worker 선택 전체 결과 |
| T-73 | 실패 포함 correlation/근거 hash: C `t73_*`; 자기 감사 불변·원래 root 한도: R `t73_response_audit_does_not_stale_its_own_proposal`, `t73_stale_replanning_budget_remains_on_original_root_across_new_run_ids`; E stale/409 | plan/source/state/evidence별 STALE/CONTRACT와 미변경 근거 |
| T-74 | 보고 ID replay/conflict: R `t74_report_replay_and_conflict_keep_first_full_report`; 명령 idempotency/다른 제안 stale: R `t74_human_retry_is_idempotent_and_first_effective_proposal_stales_rest`; 결과 crash/replay: R/W `t82_*terminal*` | 같은 proposal_key의 동일/다른 내용 및 명령 commit 전후 재시작 조건 확인 |
| T-75 | before/순환/의존/중복/UNKNOWN 차단·rename/add/deactivate의 ID/이력 보존·새 범위 사람 확인: R `t75_*`; 미해결 판단 계획 차단: R `r1_needs_decision_without_candidate_never_approves_scope` | 최초 분석 누락·계획 확인/그룹/필수시험 제외 경계 전체 결과 |
| T-76 | FIX 같은 원인2회/난항·환경 오류·최신 attempt/cause/lease·auto limit: R `t76_*`; frozen 역할/작성자별 독립 리뷰: C/R/W `rr4_*` | RR4 이후 새56개 결과·기존 v1 선택 회귀·기본 자동 재시도0 |
| T-77 | 성공/실패 모든 frozen ID/input hash·JSON 중복/크기/깊이·충돌: C `t77_*`; stale 이력: R `t77_t79_stale_analysis_preserves_history_without_current_holds`; 실제 diff: C `r5_*` | 최신 보고·보류에 stale/conflict 효과 없음 |
| T-78 | 역할별 필수 보고·null+이유·필수 사례 실제 PASS/소스·근거/경로·정확한 별도 리뷰: C `t78_*`, R `t78_*`; 분류/판단·실제 source/diff: R `r1_*`, C `r3_*`/`r5_*`; W 전체 demo | fake command/파일·빌드·integration·read-only source 및 symlink 플랫폼별 근거 |
| T-79 | blocking/nonblocking·stale·claim 경쟁·transaction rollback: R `t79_*`; code/review 원자 후보: R `r2_*`; 동일 해결 후보 반복/실질 변경 재개: R `rr3_*`; E 후보 분류 | RR3 포함 hold/trigger/report 원자성 전체 결과 |
| T-80 | 소유 근거/전체 영향·동일 candidate/Decision 재사용·Jira Done과 적용 분리: R `t80_*`, `rr3_*`; coordinator/Jira 격리: W `t81_*` | 기존 Jira 응답 유실·일반 오류 비발송·독립 범위 회귀(모의) |
| T-81 | coordinator 실패 중 모듈 접수·한도/UNKNOWN 큐: R `t81_*`; 실제 worker의 coordinator/Jira 병행 지연: W `t81_actual_worker_drains_modules_while_coordinator_and_jira_block`; malformed wire: C `t77_*`/`t73_*` | timeout/잘못된 JSON/도구 오류·한도별 모듈 결과 보존 |
| T-82 | 영속 receipt/UNKNOWN/lease·terminal 불변/crash/replay: R/W `t82_*`; v1 coordinate/question 실제 무해한 자식: W `r4_*`; 부모 결과 없는 nested review: W `rr2_*`; migration/backup/tamper/restore: B `t82_*`; E UNKNOWN | Linux 실제 session/group 종료 시험 별도, Windows 자손 불명은 UNKNOWN 유지; 운영 baseline NONE |
| T-83 | strict schema/미지원 capability·새 job snapshot: C `t83_*`, R `t83_saved_settings_change_only_new_job_frozen_contract`; v1로 명시 v2 역방향 수락 차단: C/R `rr1_*`; 역할 capability: C/R/W `rr4_*`; E 새 설정 | RR4 이후 최종 결과, genuine unversioned v1·integer1 호환 및 조용한 downgrade 없음 |
| T-84 | 제안 접수/실제 성공·STALE/409·UNKNOWN·후보 이유·새 job 설정·job 전환·escape: E6개; bounded page/지연 상세: R `r6_report_polling_returns_bounded_metadata_and_detail_is_explicit` | 최종6개 브라우저 결과와 list bytes/page bound, 닫힌 상세 무요청 |

### 세부 인수 조건 보강 — 신규17개, 최종 로컬 실행 통과

별도 Sol Medium 담당자가 T-80/T-81 fixture의 실제 bridge 실행 설정에 맞는 명시 frozen capability를 보완하고 다음17개 사례를 추가했다. 제품 정책/guard는 완화하지 않았다. 별도 Luna Low의 아래 최종 실행에서17개 모두 통과했다.

| ID | 정확한 추가 함수 / 사례 | 검증 조건 |
|---|---|---|
| T-73 | R `test_t73_changed_snapshot_basis_stales_proposals_without_execution_effects` — response_intake/proposal_application × state_version/plan_version/source_fingerprint | STALE, 기존 modules/version 불변, 원래 replan trigger 하나 |
| T-73 | R `test_t73_evidence_basis_is_revalidated_without_mutating_execution` — substituted_response_hash/evidence_unavailable_at_apply | 응답 hash 변경은 FAILED/CONTRACT·제안 없음, 적용 시 근거 부재는 REJECTED·실행 효과 없음 |
| T-74 | R `test_t74_same_proposal_key_replays_identical_response_and_rejects_changed_content_after_restart` | 재시작 후 동일 응답 replay, 다른 내용 IDEMPOTENCY_CONFLICT·기존 제안 하나 보존 |
| T-74 | R `test_t74_proposal_command_restart_replays_one_effect_across_commit_boundary` — before_commit/after_commit_before_response | rollback 또는 commit 뒤 재구성 Engine의 replay, retry 효과/이벤트 중복 없음; 기존 human_retry 시험은 first APPLIED/나머지 STALE 확인 |
| T-81 | W `test_t81_real_control_adapter_failure_preserves_pass_and_independent_module_intake` — malformed_json/tool_unavailable/timeout/tool_exit | 실제 Bridge adapter와 process stub에서 정확한 실패, 기존 PASS/독립 모듈 결과 보존, 제안 없음·lane 해제 |
| T-81 | R `test_t81_coordinator_budget_exhaustion_preserves_pass_and_independent_intake` — max_calls/max_stale_replans | 추가 호출 차단·root 대기 유지, 이전 PASS와 독립 접수 보존 |

## 최종 로컬 Python 실행 —305 PASS / 3 플랫폼 SKIP

별도 Luna Low가 fixture2건 보완 및 신규17개 인수 조건 시험을 포함한 신규4개 파일 전체를 `tests-acceptance-final-20261106-001`로 실행했다. **총308개 중305 PASS / 3 플랫폼 SKIP / 0 FAIL / 0 ERROR, exit0, 21.96초**다. 앞선291개 실행의2 FAIL은 그대로 보존하며 이 별도 재실행으로 후속 확인했다.

```text
python -m pytest tests/test_orchestration_contracts.py tests/test_orchestration_runtime.py tests/test_orchestration_worker.py tests/test_recovery_bundle.py -q --junitxml .local-reports/orchestration-20261106/tests-acceptance-final-20261106-001/junit.xml --basetemp C:/Temp/bsp-o6acc-20261106-001
```

stdout/stderr와 JUnit은 `.local-reports/orchestration-20261106/tests-acceptance-final-20261106-001/`에 로컬 보존하며 Git에 올리지 않는다. 플랫폼 skip은 Windows에서 수행하지 못한 환경별 사례이며 이 실행만으로 Linux 동작을 PASS 처리하지 않는다. Linux CI와 최종 인수 조건/소스 근거 대조는 대기다.

T-85/T-91/T-102/T-108/T-130/T-136/T-141/T-160의 실제 환경 인수는 계속 **NOT_RUN**이다. Linux CI와 세부 인수 조건 확인 전 T-71~84의 CSV도 기존 NOT_RUN을 유지한다. 위 시험 연결표와 최종 로컬 실행의 범위를 구분하며 남은 작업은 Linux CI, 최종 증거/인수 조건 대조와 결과 확정이다. 운영 baseline은 NONE이다.

## 최초 CI — Linux 회귀 실패와 REG-0060

PR #14의 최초 CI 실행은 [GitHub Actions 42071298278](https://github.com/graycoral/bsp_os_upgrade_dashboard/actions/runs/42071298278)이며 head는 `247d08080dee0f47f667afd6f487ab4ff603e445`다. 구현 소스 커밋은 `4c060bc7cfc1c6f0402a49cbaf82ca3076bfbe2d`이며 이후 head의 시험 변경은 공백 정리다. 아래 결과는 별도 Luna Low의 CI 실행 보고이며 문서 담당자가 시험을 실행한 것이 아니다.

| job | 실제 결과 | 범위·제한 |
|---|---|---|
| Linux regression | **FAIL: 1 FAIL / 949 PASS / 15 SKIP / 1 warning, 43.86초** | 유일 실패는 기존 `tests/test_native.py::test_t100_new_job_freezes_resolved_paths`. 이후 demo/browser/package 단계는 SKIPPED이며 성공으로 해석하지 않음 |
| Windows package | **SUCCESS: 343 PASS / 3 SKIP / 1 warning, 78.82초** | wheel 172,464 bytes, SHA256 `5c66626f84c0e735280b47ca6c2c72ea7acb9b255fc4e75b0063fa6272ac02c`. 설치 후 health/static HTTP200·모의 demo5 PASS. 실제 모델/장비 인수 없음 |

원본 CI 로그는 `.local-reports/orchestration-20261106/ci-first-20261106-001/`에 로컬 보존한다. 이 최초 실패를 후속 성공으로 덮어쓰지 않는다.

REG-0060의 원인은 `Engine.create`가 저장된 동일 명령의 replay를 찾기 전에 `prepare_job_profile`의 도구 준비/capability probe를 다시 수행한 것이다. 새 job 때 고정한 도구 경로를 보존해야 하는데 PATH에서 도구를 제거한 뒤 같은 create 명령을 재요청하면 재탐색이 실패해 저장 응답을 돌려주지 못했다. 구현 담당자는 공통 command digest/replay 판별을 사용한 읽기 전용 선조회, payload deepcopy, DB transaction 밖 도구 probe, 최종 transaction의 원자적 재확인으로 수정했다. 같은 키의 다른 내용은 계속 충돌이며 concurrent create는 job 하나만 생성해야 한다.

별도 시험 담당자가 runtime의 `test_t100_create_*` 및 `test_t100_concurrent_duplicate_create_persists_one_job_command_and_initial_trigger` 신규9개(재시작 후 cache replay1·collision4·invalid key3·concurrent one-job1)를 보강했다. 이전10건의 코드 승인을 이 새 수정에 자동 적용하지 않는다.

## REG-0060 수정 후 로컬 재실행 —314 PASS / 3 SKIP

별도 Luna Low의 `tests-create-final-20261106-001`은 신규4개 Python 파일 전체 **총317개 중314 PASS / 3 플랫폼 SKIP / 0 FAIL / 0 ERROR, exit0, 23.09초**다. 신규 create9개 모두 PASS이며 이전305 PASS 실행과 최초 CI의1 FAIL을 별도 이력으로 보존한다.

```text
python -m pytest tests/test_orchestration_contracts.py tests/test_orchestration_runtime.py tests/test_orchestration_worker.py tests/test_recovery_bundle.py -q --junitxml .local-reports/orchestration-20261106/tests-create-final-20261106-001/junit.xml --basetemp C:/Temp/bsp-o6create-20261106-001
```

로그/JUnit은 `.local-reports/orchestration-20261106/tests-create-final-20261106-001/`에 Git 제외 보존한다. 추가 독립 Sol High의 `review/cache-first-review.md`는 `cache-first-manifest.json`에 고정한 수정 소스를 **APPROVED**했고 reviewer가 신규9개를 직접 실행해9 PASS를 확인했다. 최초 실패한 기존 POSIX T-100과 전체 Linux CI 재실행은 아직 대기다. T-71~84 CSV 승격은 전체 CI와 인수 대조 전까지 보류하며 실제 인수 NOT_RUN·운영 baseline NONE을 유지한다.

## 최종 제품 소스 CI — 로컬·모의 범위 완료

별도 Luna Low가 [CI 42072357947](https://github.com/graycoral/bsp_os_upgrade_dashboard/actions/runs/42072357947)의 **전체 SUCCESS**를 확인했다. 실행 소스와 시험은 모두 `1899e034120447559fd8d87129b220936f797895`다. REG-0050~0059 수정은 `4c060bc7cfc1c6f0402a49cbaf82ca3076bfbe2d`, REG-0060 수정은 최종 `1899e034120447559fd8d87129b220936f797895`에 포함된다. 원래 구현의 독립 승인과 cache-first 추가 독립 승인 모두 실제 검토 manifest에 연결돼 있다. 이후 문서 정리 커밋을 제품 시험 소스 커밋과 혼동하지 않는다.

| 검증 | 명령/실제 결과 | 범위 |
|---|---|---|
| Linux 전체 Python | `python -m pytest -q --junitxml=.local-reports/pytest.xml` — **959 PASS / 15 SKIP / 1 warning, 56.91초** | 신규4개 Python 파일과 최초 실패 기존 T-100 포함. 결과 summary 시각 `2026-11-05T17:14:11.9875513Z` |
| Dashboard 브라우저 | `python scripts/test_e2e.py` — **31 PASS**, 1.7분 | 신규 E6개·기존 Dashboard 회귀. summary 시각 `2026-11-05T17:17:09.0926949Z` |
| 단독 GUI 브라우저 | `python -m backend.gui_test.demo.browser_e2e` — **18 PASS**, 49.9초 | 기존 공통 UI 회귀. summary 시각 `2026-11-05T17:18:00.3301282Z` |
| Dashboard demo | `python -m backend.gui_test.demo.e2e --dashboard --output .local-reports/demo-e2e.json` — **7개 simulation PASS** | pass/fail/disconnect/timeout/unknown/sync-failure/sync-lost-response. 실제 장비 실행 아님 |
| Windows package | 지정 Windows 회귀 **343 PASS / 3 SKIP / 1 warning, 78.82초** | wheel stage/build/install·health/static HTTP200·설치 demo5 SUCCESS |
| 빌드·배포 산출물 검사 | Linux/Windows의 지정 build, packaging, wheelhouse 및 모든 upload 단계 SUCCESS | 승인된 로컬 패키징/모의 설치 범위. 운영 배포 아님 |

CI 환경은 workflow의 Linux/Windows runner, Python3.12·Node22와 설치된 잠금 의존성이다. 원본 CI 로그는 `.local-reports/orchestration-20261106/ci-create-fixed-20261106-001/linux-regression-job.log`와 `windows-package-job.log`에 보존하며 Git에 올리지 않는다. artifact ZIP은 위치 참조만 확보했으므로 개별 JUnit의 신규317개 분해 결과나15개 skip 사유를 새로 만들어 주장하지 않는다.

플랫폼 대조: Windows 로컬 신규4개 파일의314 PASS/3 SKIP과 Linux 전체 성공을 함께 사용한다. Windows에서 건너뛴 T-78 파일/디렉터리 symlink2개와 T-82 Linux process-group1개는 `skipif os.name != 'posix'` 조건으로 Linux CI에서 활성화된다. Linux에서 제외되는 Windows 전용 T-82 guard는 로컬 Windows 실행에서 확인했다. 따라서 “317개 모두 Linux PASS”로 기록하지 않고 조건별 양쪽 실행 근거를 연결한다.

위 인수 조건표·추가17개·REG-0060의9개·기존 회귀·브라우저 및 독립 승인을 대조해 **T-71~84와 T-100을 현재 로컬·모의 범위 PASS**로 갱신한다. 일반 오류를 Jira로 전송하거나 실행/최종 검토를 조정 제안으로 대체하지 않는 정책과 v1 기본·조정 OFF·새 job snapshot을 보존했다. 다른 기존 POSIX 관련 T-ID를 aggregate만으로 일괄 승격하지 않는다.

이 최종 결과는 [PR #14](https://github.com/graycoral/bsp_os_upgrade_dashboard/pull/14)의 제품 소스 CI 기준이다. 이전 문서 검사 `docs-validator-final-20261106-001`은891 links/54 requirements/168 tests/83 NOT_RUN PASS였으며 현재 결과 갱신 전 문서의 검사 이력이다. 최종 문서 검사는 담당 실행자가 별도로 기록한다. 최초 실패와 앞선 모든 실행을 보존하며 T-85/T-91/T-102/T-108/T-130/T-136/T-141/T-160은 실제 환경 증거 전 NOT_RUN이다. 실제 Linux CLI 인증/추론·BSP 수정/빌드·보드 퓨징·Jira 발송·서비스 운영 변경을 수행하지 않았고 운영 baseline은 NONE이다.


### Preserved T-100 summary history

The prior INVALIDATED canonical row (preserved at product source commit `1899e034120447559fd8d87129b220936f797895`) and original PASS row from `20261101-local-update-evidence/upstream-test-results.csv` are retained verbatim. The original native CLI run remains the authority for its older environment. The new PASS applies only to the current source and evidence above.

```csv
test_id,status,run_id,code_revision,test_revision,environment,executed_at,executor,evidence,defect_id,notes
T-100,INVALIDATED,20261012-native-cli,sha256:b4c196864c5c3a109575fb2381aa0ad50fc80458c8a2643bce8d1ff7872b44b2,sha256:b4c196864c5c3a109575fb2381aa0ad50fc80458c8a2643bce8d1ff7872b44b2,macOS; Python 3.11.7; local CLI simulators; Chromium; no live models,2026-10-12T13:09:24.139105+09:00,Codex,runs/20261012-native-cli.md,,현재 로컬 환경 전체 항목 미재검증; 이전 PASS는 원 실행 이력 및 upstream-test-results.csv에 보존. Python 217 / browser 5 / UI build PASS; 실제 Linux CLI 모델 호출 및 BSP 인수 미실행
T-100,PASS,20261012-native-cli,sha256:b4c196864c5c3a109575fb2381aa0ad50fc80458c8a2643bce8d1ff7872b44b2,sha256:b4c196864c5c3a109575fb2381aa0ad50fc80458c8a2643bce8d1ff7872b44b2,macOS; Python 3.11.7; local CLI simulators; Chromium; no live models,2026-10-12T13:09:24.139105+09:00,Codex,runs/20261012-native-cli.md,,Python 217 / browser 5 / UI build PASS; 실제 Linux CLI 모델 호출 및 BSP 인수 미실행
```
