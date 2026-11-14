# 플러그인 중심 구현 독립 코드 리뷰 · 2026-11-14

## 기준과 판정

- `review_id`: `20261114-plugin-centric-code-01`
- 기준: `main` / `e4f53ca1ec288feb3eb1b9ccff8335a398ad321c` 위 미커밋 구현. 최종 커밋은 아직 없다.
- 검토자: 별도 Codex 세션 `/root/plugin_code_review`. 부모가 `fork_turns=none`, `model=gpt-6-astra`, `reasoning_effort=xhigh`로 호출했고 도구가 수락했다. 로컬 설정의 `high`보다 한 단계 높은 요청이며, 도구가 실제 런타임 모델/effort를 별도로 반환한 것은 아니다. 부모 런타임 override를 확인했다고 주장하지 않는다. **Claude 검토가 아니다.**
- 최초 판정: **CHANGES_REQUESTED**. 아래 PC-C01~06을 구현 담당자에게 전달했다. 수정 후 관련 코드와 회귀를 재검토한 최종 판정: **APPROVED — 이 문서의 명시한 코드 범위에 한함**.
- 추적: RQ-67 / D-71 / T-240~245 / REG-0085. 기준 계약은 [요구사항 리뷰](20261114-plugin-centric-review.md)와 [설계의 최종 기술 기준](../../design/PLUGIN_CENTRIC_INTERFACE_PLAN.md)이다.
- 실제 회사 ACON/분석 모델/조치 검증 adapter, Linux 회사 설치, Windows 장비·플래싱·TC 및 T-246은 **NOT_RUN**이다. 로컬 모의 PASS나 코드 승인을 회사 배포 승인으로 해석하지 않는다. 커밋·푸시·실제 장비 실행은 수행하지 않았다.

`AGENTS.md`, `CLAUDE.md`, `portable-feature` 스킬, 문서 지도/현재 상태, 관련 계약·PORT와 개발 로그 처리 규칙을 읽었다. 제품 코드는 변경하지 않았고 이 리뷰 문서만 작성했다. 재현·시험은 임시 runtime과 모의 adapter를 사용했다.

## 읽은 코드 범위

- `core/failure_analysis.py`, `api/failure_analysis.py`, `standalone/analysis_worker.py` 및 Manager/IntegrationService/Worker/reporting/session deletion/timeout/discovery 연결.
- `core/shared_settings.py`, `api/shared_control.py`, runtime, standalone integration/PluginClient, 전체 host `backend/api/main.py`의 bootstrap·인증·권한 경계.
- connector shared control/supervisor/Qt 공통 설정 UI, Windows Host의 실제 설정 fingerprint, 공통 `SharedControl.tsx`/TestPage/browser host.
- `apps/agent-monitor/manage.py`/`delivery.py`의 설치·활성화·서비스 소유, 종료 admission barrier, API 재시작과 Worker 보존, 소스 manifest와 복사 전달 시험.
- 제거/명명 변경된 스크립트의 현재 호출부·CI·패키징 접점. 과거 EXE artifact의 provenance 검사에 남은 옛 경로는 당시 artifact 계약이며 현재 실행 호출로 보지 않았다.

동시에 작성된 새 **브라우저형 보드 커넥터 전체 기능**은 이 리뷰에 포함하지 않는다. `connector/web.py`, `web_actions.py`, `native_picker.py`, `connector_web/*`의 별도 사용자 흐름이나 Windows 동작을 승인하지 않았다. 해당 자산의 패키지 allowlist 추가만 확인했다.

## 발견과 수정 재검토

### PC-C01 · P1 · 종료 불명 상태의 영구 복구 차단 — 해결

- 최초 근거: `manager.py`의 latch 상태 `recover` 일괄 거부와 `failure_analysis.py:_verified`의 UNKNOWN 거부가 결합되어, 실제 프로세스가 종료되어도 새 분석이 실행 조건을 만족할 수 없었다. startup recovery도 RUNNING Attempt만 조사했다. integration의 pre-TC READY 응답은 latch를 보존하면서 UNKNOWN까지 그대로 유지했다.
- 재현 조건/영향: 새 Run TC가 UNKNOWN으로 저장된 뒤 실제 probe가 STOPPED가 됨. 일반 복구·분석·재개가 모두 막혀 예약을 유지한 채 작업을 계속할 수 없다.
- 수정 확인: `Manager.reconcile_unknown()`이 실제 probe와 상태 버전 CAS로 종료 근거만 갱신한다. latch와 `environment_ready=False`를 보존하고 이전 분석 lease/revision을 대체한다. 일반 recover와 Worker 경로가 연결되었다. integration pre-TC READY는 PAUSED로 정리하되 분석/정상 재준비를 요구하며, READY 자체를 TC 종료 근거로 사용하지 않는다.
- 검증: UNKNOWN/RUNNING probe 유지, STOPPED 후 이전 응답 거부·latch 유지·검증 후 원래 slot retry, integration READY 재전달 회귀. T-241.

### PC-C02 · P2 · 사용자 일시중지 후 분석 재개 불가 — 해결

- 최초 근거: `analysis_manual_hold`를 설정하는 경로만 있고 해제 경로가 없어 requeue 후에도 `_verified`가 계속 HOLD했다.
- 수정 확인: controller의 명시적 requeue 또는 일반 Run `reanalyze`만 수동 hold를 해제한다. latch와 조치 검증은 유지한다. 수정 도중 ordinary Run의 서비스 분석자가 다른 사용자의 hold를 해제할 수 있는 부분도 지적했고, 최종 구현은 실제 controller를 확인한다. TestPage에 해당 명시 동작을 연결했다.
- 검증: 비소유자 requeue/reanalyze 거부, 소유자 재분석 후 즉시 claim 금지, 신뢰된 검증 뒤 재실행. T-241/243.

### PC-C03 · P1 · 빈 초기 설정이 등록 커넥터를 선택하지 못함 — 해결

- 최초 근거: `IntegrationValues.runner_id`의 기본 `''`가 저장된 뒤 `IntegrationService.frozen_config()`의 `setdefault()`는 등록된 runner identity를 채우지 않았다.
- 재현 조건/영향: 무설정 bootstrap → connector 등록 → 나머지 필수 기본값 저장. 실제 등록이 있어도 `INTEGRATION_NOT_CONFIGURED`로 Run 수락이 막힌다.
- 수정 확인: 명시 runner pin은 보존하고 빈 값에만 등록 identity를 적용한다. 중앙 설정을 조회할 때 임의로 저장값을 바꾸지 않으며, 수락 Run에 고정한다.
- 검증: SharedSettings가 실제 기본값을 생성한 상태에서 registered identity로 수락하는 회귀. T-242.

### PC-C04 · P1 · 중단된 서비스의 미해결 작업을 무시한 버전 활성화 — 해결

- 최초 근거: `manage.prepare()`는 service lock의 현재 점유 여부만 검사했다. supervisor가 종료되었어도 DB에 UNKNOWN/PAUSED/예약/BSP 작업이 남은 경우 새 release를 활성화할 수 있었고, 활성 여부 검사와 pointer 쓰기가 원자적이지 않았다.
- 수정 확인: `activate()`가 supervisor와 같은 `service.lock` 안에서 persisted work를 확인하고 `current.json`을 쓴다. 미해결 작업이면 UPDATE_PENDING으로 남기며 start는 기존 current release를 사용한다. start-to-serve 사이 release 변경도 고정 인자로 검사한다. API를 먼저 닫아 새 수락을 차단한 뒤 DB를 확인하는 종료 순서와 Worker 보존도 대조했다.
- 검증: stopped+UNKNOWN 활성화 유예, 동일 release 재사용, 잠금 경합, 변경된 release 기동 거부, UPDATE_PENDING의 기존 release 기동, API 장애/종료 요청 중 Worker 단일 소유. T-244.

### PC-C05 · P1 · 미지원 정책 Run의 플래싱 진입 — 해결

- 최초 근거: 미지원 saved policy 검사가 `Manager.claim()`에만 있어 `IntegrationService.prepare_run()`은 소스 준비와 `begin_integration()`을 먼저 실행할 수 있었다.
- 모의 재현: 미지원 정책을 저장한 QUEUED/PREPARING Run에서 `SOURCE_PREPARATIONS=1`, `HARDWARE_BEGINS=['begin_integration']`, `TC_CLAIM=None`. 실제 하드웨어는 호출하지 않았다.
- 수정 확인: prepare_run 진입 및 준비 결과를 수락하는 DB 트랜잭션 안에서 supported policy와 latch를 다시 검사한다.
- 검증: 미지원 integration 정책에서 preparer와 begin_integration 모두 0회, claim 없음. T-241. 최초 재현 로그는 아래 경로에 보존한다.

### PC-C06 · P2 · TC 사이의 일시적 연결 실패 후 계속 HOLD — 해결

- 최초 근거: ordinary Run의 claim preflight 실패는 `attempt_id=None`으로 분석을 생성한다. `_verified`는 모든 no-attempt RETRY를 거부하고, `_prepare_child`는 이전 PASS Attempt가 있으면 동일 입력 child를 거부했다.
- 모의 재현: TC0 PASS → TC1 배정 전 보드 단절 → 연결 복구/신뢰된 조치 근거. RETRY와 동일 입력 REPREPARE 모두 HOLD, index1/기존 PASS Attempt만 남았다.
- 수정 확인: ordinary/no-attempt/PREFLIGHT이며 현재 slot이 PENDING인 경우에만 동일 Run retry를 허용한다. 원래 Run+lease의 모든 예약, 보드·BSP 게이트·정지 근거를 확인한다. integration의 준비/플래싱 실패는 이 예외를 사용할 수 없다. 다음 claim에서도 기존 검사를 다시 수행한다.
- 검증: slot0/1 복구, 이전 PASS 이력 유지, 누락/다른 token/다른 소유자 예약 HOLD, 재단절 시 새 Attempt 없이 다시 latch, integration 준비 RETRY 차단. T-241.

## 독립 실행 근거

원본 로그와 JSON hash 목록은 `.local-reports/` 아래 로컬 전용이며 Git에 포함하지 않는다.

| 실행 | 결과 | 근거 |
|---|---|---|
| 중간 집중 pytest: failure_analysis/shared_control/shared_connector_control/agent_monitor_manager | 92 PASS. 이후 수정 전 중간 근거이며 최종 근거로 재사용하지 않음 | `.local-reports/20261114-plugin-code-review-02/pytest.log` |
| 미지원 정책 플래싱 진입 모의 재현 | 결함 재현, exit 0 | `.local-reports/20261114-plugin-code-review-01/unsupported-policy.log` |
| TC 사이 preflight 복구 모의 재현 | 결함 재현, exit 0 | `.local-reports/20261114-plugin-code-review-01/preflight-recovery.log` |
| 최종 6파일 집중 pytest | **134 PASS, exit 0**, FastAPI/Starlette 의존성 deprecation warning 1건 | `.local-reports/20261114-plugin-code-review-final/pytest.log`, `exit-code.txt` |
| lifecycle 시험의 POSIX 범위 표기 추가 후 해당 파일 재시험 | **18 PASS, exit 0** | `.local-reports/20261114-plugin-code-review-final/lifecycle-posix-marker.log` |
| `git diff --check` | PASS | 최종 정적 확인 |

최종 시험 명령:

```sh
.venv/bin/python -m pytest \
  backend/gui_test/tests/test_failure_analysis.py \
  backend/gui_test/tests/test_shared_control.py \
  backend/gui_test/tests/test_shared_connector_control.py \
  tests/test_agent_monitor_manager.py \
  tests/test_agent_monitor_lifecycle.py \
  tests/test_agent_monitor_delivery.py -q
```

시험 전후 변경 소스 hash를 `source-before.json`/`source-after.json`으로 비교했다. 검토한 core/shared/Qt/lifecycle 구현과 해당 시험은 실행 중 동일했다. 별도 브라우저 커넥터 자산을 포함하는 `apps/gui-test/package.py`, `scripts/build_connector_bundle.py`와 `tests/e2e/shared-control.spec.ts`는 동시에 변경되어 그 최종 변경을 위 134 PASS의 검증 대상으로 주장하지 않는다. 최종 승인 대상 45개 파일 hash는 `reviewed-source.json`에 별도 보존한다. 해당 manifest SHA256은 `089bab32ddb2c2a801b2155a087a11908e7398727cb420e878cc78e0b4ed3cd8`이다. 이후 파일 변경은 이 승인 범위의 재검토가 필요하다.

수정 후 검토 범위에서 남은 P1/P2 발견 사항은 없다. 신뢰된 verifier가 없는 환경에서 HOLD하는 동작은 의도된 제한이다. 전체 UI 빌드·브라우저 회귀·독립 복사 환경의 추가 설치 검증과 회사 인수 상태는 [통합 구현 기록](20261114-plugin-centric-implementation.md)의 실제 실행 근거를 따르며 이 리뷰가 대신하지 않는다.

## 후속 코드 재검토 · Linux 진입점과 기존 runtime 보존

부모 구현 세션이 최초 승인 뒤 발견한 추가 범위를 같은 독립 리뷰 세션에서 재검토했다. 기존 `Wizard.linux_start()`가 별도의 API/Worker를 직접 소유하고, 변경된 `run.sh`가 기존 저장소 `.runtime` 대신 관리 홈의 새 runtime을 사용할 수 있었던 문제다. 이 후속 검토는 RQ-67/D-71/T-244~245/REG-0085 범위이며 별도 브라우저 커넥터 WIP는 계속 제외한다.

**후속 판정: APPROVED.** 다음 경계를 확인했다.

- Linux 설정 마법사는 기존 `self.runtime`과 선택 포트를 공통 관리자 `start`에 전달한다. 자체 API/Worker 생성과 종료 처리를 제거했으며 메뉴 Ctrl+C가 상주 서비스의 종료 지시가 되지 않는다. 등록형 connector 설정과 개발용 `.venv`가 없는 관리자 bootstrap을 지원한다.
- `run.sh`는 호출 CWD와 무관하게 저장소 `.runtime`을 명시하고, 사용자가 설정한 `BSP_RUNTIME`은 명시 runtime으로 전달한다.
- `runtime_path()`/`bind_runtime()`은 설치 홈에 최초 runtime 경로를 저장한다. 기존 설정·기존 기본 runtime·활성 서비스가 있으면 다른 경로로 재지정하지 않으며, 버전 활성화와 서비스 실행도 이 고정 경로를 사용한다. runtime 데이터를 복사하거나 초기화하지 않는다.
- 초기 변경에 섞인 `Wizard.manifest()`의 Linux Python 사전 검사 제거를 지적했다. 실제 실행은 여전히 개발용 Python 경로를 사용하므로 기존 검사를 복원했고, 질문/파일 처리 전에 거부하는 시험으로 확인했다.

### 최초 관리형 이관의 명시적 제한

기존 runtime에 미완료·PAUSED·UNKNOWN 작업이 있고 관리형 `current.json`이 없으면 기존 실행 코드와 새 후보의 호환성을 증명할 수 없다. 이 경우 **`INITIAL_RUNTIME_ADOPTION_BLOCKED`로 보류**하고 runtime과 후보를 보존하며, API/Worker를 새로 시작하지 않는다. 이는 완료된 이관으로 표시하지 않는 의도된 안전 경계다.

최초에는 UPDATE_PENDING 뒤 존재하지 않는 current를 읽어 일반 설치 오류로 끝나므로 이 상황을 별도 지적했다. 최종 구현은 runtime 경로를 포함한 명시 오류를 반환한다. [공개 안내의 최초 연결 예외](../../agents/PLUGIN_CONTROL_API.md)는 운영자가 원래 실행한 소스/가상환경 또는 검증된 호환 버전을 먼저 확인하고 그 버전의 복구 절차를 사용하도록 명시한다. 호환성을 확인할 수 없으면 보류한다. 활성화를 거부한 새 후보의 API/Worker 직접 실행이나 이력 삭제로 검사를 우회하도록 안내하지 않는다. 이미 관리된 같은 release의 재시작/복구는 지원한다.

### 후속 독립 시험과 기준

명령: `.venv/bin/python -m pytest tests/test_setup_runtime.py tests/test_agent_monitor_manager.py tests/test_agent_monitor_lifecycle.py tests/test_build_entrypoint.py -q`.

| 실행 | 결과 | 로컬 전용 근거 |
|---|---|---|
| 최초 추가 범위 시험 | 88 PASS / 11 SKIP, exit 0 | `.local-reports/20261114-plugin-code-review-runtime-01/pytest.log` |
| 최초 이관 오류 추가 뒤 시험 | 1 FAIL / 88 PASS / 11 SKIP. 기존 release 재사용 fixture가 current 함수만 모의하고 실제 current.json은 만들지 않았음 | 같은 폴더 `pytest-final.log` |
| fixture에 기존 current pointer를 명시한 동일 시험 재실행 | **89 PASS / 11 SKIP, exit 0**. 제품의 최초 이관 차단은 유지 | 같은 폴더 `pytest-retest.log`, `retest-exit-code.txt` |
| 등록형 무개발 venv 시작·manifest 사전 검사 집중 확인 | **2 PASS**, exit 0 | 같은 폴더 `late-guards.log` |
| `git diff --check` | PASS | 최종 정적 확인 |

11 SKIP은 플랫폼 전용 시험이며 실제 Windows/Linux 회사 인수가 아니다. 후속 대상 8개 파일의 hash는 `.local-reports/20261114-plugin-code-review-runtime-01/reviewed-source.json`에 보존했다. manifest SHA256은 `e1b3676f37cd68e4f4c41ac5f2dd63080b66e99848f0d22fbf4e1b4b9586abaf`다. 이 목록은 동일 파일의 앞선 승인 hash를 대체하며, 나머지 앞선 승인 범위는 유지한다. 이후 대상 파일이 바뀌면 해당 변경을 다시 검토한다.
