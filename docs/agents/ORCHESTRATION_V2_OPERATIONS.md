# 자동 조정·모듈 v2의 로컬 구현과 도입 절차

2026-11-06 현재 **O1~O4 로컬 구현·모의 검증 완료**이다. [이번 실행 기록](../testing/runs/20261106-orchestration-v2.md)의 시험/리뷰 상태를 먼저 확인한다. 검증된 제품 소스는 `1899e034120447559fd8d87129b220936f797895`이며 [PR #14](https://github.com/graycoral/bsp_os_upgrade_dashboard/pull/14)와 [최종 CI](https://github.com/graycoral/bsp_os_upgrade_dashboard/actions/runs/42072357947)에 연결한다. 이 안내는 운영 배포나 실제 모델 인증·BSP·장비/Jira 인수 완료를 뜻하지 않는다.

| 경로 | 구현·사용 조건 | 검증 경계 |
|---|---|---|
| 모듈 보고 v1 | 기존 기본값. 저장된 과거 job 유지 | 기존 wire/게이트를 보존 |
| 모듈 보고 v2 | 새 job에서 명시 선택, capability snapshot 고정 | 엄격한 역할별 schema·실제 파일/소스/근거 검사. 독립 코드 검토 APPROVED, 로컬·모의 시험/CI 통과 |
| 자동 조정 v1 | v2와 `orchestration.enabled=true`를 함께 설정 | 별도 영속 큐·호출·제안 경로. 모듈 배정자는 기존 worker 하나 |
| 수동 Claude 패키지 | 사용자가 직접 호출하는 오프라인 도구 | 자동 worker 경로를 활성화하지 않음. 실제 T-91 별도 |
| 실제 Linux·모델·장비·Jira | 대상 환경의 별도 증거 필요 | O5/실환경 인수는 미완료 |

## 설정과 capability

`backend/settings.py`의 `Profile`이 현재 설정 기준이다. `module_report_version` 기본1, `orchestration.enabled` 기본false다. 조정 기본값은 `timeout_seconds=120`, `max_calls=20`, `max_stale_replans=2`, `auto_retry_limit=0`이다. 이 숫자는 D-58의 구현 선택이며 사용자가 각각 확정한 운영 정책으로 해석하지 않는다. 변경은 새 job에만 적용하고 기존 job snapshot은 변환하지 않는다.

`command_result_path` 기본은 `.bsp-dashboard/results/{job_id}/{attempt_id}/{stage}.json`이다. `bridge_capabilities`는 도구별 명시 capability document 또는 argv command를 받는다. command는5초·64KiB로 제한하고 문서에 없는 probe flag를 추측하지 않는다. 정확한 capability/명령 결과 필드는 [보고 계약](../design/AGENT_STATUS_CONTRACT.md)과 [capability schema](../../contracts/adapter-capabilities-v1.schema.json), [명령 결과 schema](../../contracts/command-result-v1.schema.json)를 따른다.

기본 runner=native는 별도 wrapper 작성을 요구하지 않는다. 설치된 CLI의 help/version 점검과 native 변환기 지원을 기록해도 `CLI_READY`는 실제 인증·추론 성공이 아니다. capability의 authentication/inference는 UNVERIFIED로 남는다. demo의 capability는 모의 지원이며 모델 호출이 없다. 기존 bridge/v1은 유지하고 v2/조정 미지원은 조용히 v1으로 낮추지 않는다.

frozen 역할/버전과 작성자별 독립 리뷰 정책은 설정 확인·선택·배정·호출·결과 접수에서 다시 검사한다. 적격 구현/리뷰 쌍이 없으면 프로세스 실행 전에 거부한다. 정확한 배정/보고 계약은 [보고 계약11절](../design/AGENT_STATUS_CONTRACT.md#11-오케스트레이터-연동용-모듈-보고-v2)을 따른다.

등록한 native 빌드/검증/통합 명령에는 `BSP_REQUEST_PATH`, `BSP_RESULT_PATH`, `BSP_RESULT_SCHEMA_PATH`가 전달된다. 명령은 요청 대상에 맞는 구조화 결과 파일과 실제 사례별 근거를 작성해야 한다. exit0·다운로드·퓨징 완료만으로 필수 사례 PASS를 만들지 않는다. 일반 stdout이나 모델 문장에서 시험 결과를 추정하지 않는다.

## 상태와 근거 확인

분석은 고정된 세 소스 tree inventory를 읽고 공유 workspace의 다른 모듈 변경 때문에 분석 자체를 막지 않는다. v2의 원본 Git 기준과 실제 실행 소스 해시는 [보고 계약11절](../design/AGENT_STATUS_CONTRACT.md#11-오케스트레이터-연동용-모듈-보고-v2)에서 구분한다. 코드 성공은 실제 변경과 일치하는 canonical `bsp-workspace-diff-v1` 근거와 별도 리뷰가 필요하다. 등록 산출물은 해시와 대상 소스 attestation을 검사한다. 근거 경로·세부 wire 필드를 다른 문서에서 재정의하지 않는다.

조정은 결과 수집과 독립 큐로 실행하며 조정 장애가 독립 모듈을 막지 않도록 한다. 제안 접수/APPLIED는 실제 agent 성공과 다르다. 후보·영향 보류·제안 이유·과거 기준·보고 상세를 화면에서 구분한다. 새 판단만 기존 Decision/Jira 경로로 연결하며 일반 실패를 자동 발송하지 않는다. 기본 수동 장비 시험과 최종 사람 검토는 유지한다.

프로세스 receipt와 결과 envelope는 재시작 검토용 영속 근거다. 종료를 입증하지 못하면 UNKNOWN을 유지하고 writer/조정 lane을 새 프로세스에 재배정하지 않는다. Windows 자손 프로세스 종료의 미확인 상태를 timeout이나 lease 만료만으로 해제하지 않는다. 이 기능을 실제 Linux 프로세스 재접속 완료로 표현하지 않는다.

## BSP schema1 백업과 별도 복원

BSP DB는 schema1→2 추가 migration을 사용한다. GUI Test 별도 DB는 schema1을 유지한다. **새 `Store(live_db)`를 먼저 생성하면 migration이 실행되므로, 이전 전 백업은 DB 경로를 helper에 직접 전달한다.** 라이브 서비스 설정/재시작은 이 안내만으로 실행하지 않는다. 실행 중 쓰기/산출물 변경을 정지한 승인된 유지보수 범위에서 DB와 참조 파일을 일관되게 확보한다.

저장소 루트의 Python 환경에서 아래 API를 사용한다. 예제 경로는 실제 BSP DB·artifact root·비어 있는 별도 목적지로 바꾼다. `backup_runtime`에 문자열/Path DB 경로를 전달하면 sqlite read-only 연결과 SQLite backup API를 사용하고 원본을 migrate하지 않는다.

```python
from pathlib import Path
from backend.storage.recovery import backup_runtime, verify_backup, restore_runtime

manifest = backup_runtime(
    Path('/srv/bsp-runtime/dashboard.db'),
    Path('/srv/bsp-runtime/artifacts'),
    Path('/srv/bsp-backups/before-v2-unique'),
)
verified = verify_backup(Path('/srv/bsp-backups/before-v2-unique'))
restored = restore_runtime(
    Path('/srv/bsp-backups/before-v2-unique'),
    Path('/srv/bsp-restore/verification-unique'),
)
```

목적지는 원본/runtime/artifact와 겹치지 않는 새 빈 경로여야 한다. bundle은 `dashboard.db`, 참조된 `artifacts/{job}/{id}`, `manifest.json`으로 구성한다. 검사는 DB integrity/foreign-key·DB bytes/해시·참조 산출물/보고 근거의 누락/해시/크기를 확인한다. 원본 실패나 변조를 수정해 통과시키지 않고 새 실행으로 남긴다.

복원은 별도 빈 목적지에만 수행한다. 서비스 자동 시작·UNKNOWN/lease 자동 해제·역 migration은 없다. 복원 후 소스·설정·도구·현재 프로세스와 누락 근거를 별도 대조하고, schema2로 연 DB를 구버전 worker로 재개하지 않는다. 현재 실제 복구 연습은 schema1 DB와 산출물0개였으므로 전체 운영 복구·산출물 변조 인수까지 완료된 것은 아니다. 운영 baseline NONE을 유지한다.
