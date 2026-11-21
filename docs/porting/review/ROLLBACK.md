# 회사 도입 전 백업 및 롤백

| 필드 | 내용 |
|---|---|
| source_repo/source_commit | graycoral/bsp_os_upgrade_dashboard · 전달본 source manifest의 `source_head` |
| target_repo/target_commit | 회사 담당자가 이전 및 새 코드 SHA와 배포 경로를 기록 |
| scope | Linux Monitor 및 Windows Connector의 별도 코드/DB 복원 검사 |
| changes | Source release 포인터·receipt 검증 사용. 공통 DB schema 변경 없음 |
| package_release | 현재와 후보의 manifest release, 실제 로드 경로, 향후 롤백 대상의 SHA를 각각 기록 |
| evidence | 회사 정지·DB 복구 NOT_RUN. 로컬 회귀는 단계 03 결과 참조 |
| open_questions | 회사 기존 Manager/Worker의 관리 명령, 기존 DB 호환성, Windows ACL과 백업 보관 정책 |
| next_task | 회사 구조 확인 후 독립 복원 사본으로 점검 |

## 변경 전 기록과 백업

1. [스모크](COMPANY_SMOKE_TEST.md)의 포트·경로 목록과 Linux `monitor status`/Windows 프로세스의 기존 소스 경로를 기록한다. Linux의 `current.json`, `runtime-location.json`, `service.json` 및 Windows Manager/Host receipt를 현지 보호 경로에 보관한다. PID는 OS 시작 식별자·실행 인자·소스 경로까지 비교한다. 현재와 이전 release 폴더·검증된 venv·manifest·회사 Adapter의 Git SHA를 보존한다.
2. 기존 소유자로부터 작업·시도·예약·보류·분석·UNKNOWN 상태를 조회한다. 작업 또는 예약이 있거나 종료가 확인되지 않으면 현행 owner와 데이터로 복구를 마치고 전환을 보류한다. 정상 종료 절차와 Worker/Host의 OS lock 해제를 확인한다. `inspect-runtime`은 서비스와 Worker가 소유권을 반환한 뒤 기존 home에서 실행한다.
3. 정지된 별도 Linux 사본에서 `apps/agent-monitor/recovery.py`의 `backup(runtime, destination)`을 사용한다. destination은 runtime 밖의 새 보호 경로다. 이 함수는 SQLite online backup API로 커밋된 WAL을 반영해 독립 DB와 `BACKUP.json`을 생성한다. 여러 DB 및 JSON 간 일관성을 위해 기존 owner의 쓰기를 멈춘 상태에서 백업한다. 백업의 각 SHA와 DB의 읽기 전용 `PRAGMA integrity_check` 결과 `ok`를 기록한다. Linux dashboard/GUI-Test/shared-settings DB와 projection DB, 예약·revision·snapshot·실패 기록을 원본과 대조한다.
4. Windows도 승인된 도구로 별도 백업을 만든다. Manager/Host가 정지하고 `executions.db`의 쓰기가 없음을 확인한 뒤 SQLite 백업 API와 로컬 설정/receipt 복제본을 사용한다. `runner_meta.connector_schema_version`, Run/attempt/분석/예약, UNKNOWN, 프로파일과 설정 revision을 기록한다. 키와 인증 데이터는 회사의 승인된 백업 절차 및 보호 저장소를 사용한다. 소스 전달 폴더에는 현지 백업을 넣지 않는다.
5. 새 코드와 복원 대상 이전 코드로 각각 독립 사본을 읽는다. 코드/설정이 다른 DB 형식을 수용하는지와 기존 설정/예약이 보존되는지를 확인한다. 이전 코드가 새 DB 형식을 처리할 수 없으면 회사가 정한 데이터 복구 지점과 그 뒤의 변경 이력을 비교한 후 별도 복원 승인 조건을 기록한다.

## 코드 롤백 및 확인

- 현재 owner가 정지하고 실행·대기·일시정지·종료 불명 작업이 정리된 상태에서 Linux `python -B "$PACKAGE/agent-monitor/apps/agent-monitor/manage.py" rollback --home "$MONITOR_HOME" --runtime "$MONITOR_RUNTIME" --release "$PREVIOUS_RELEASE"`를 사용한다. `ROLLED_BACK`의 release와 path를 확인한다. 이 명령은 보존된 source hash와 환경을 검증한 뒤 active pointer를 바꾼다. 대응되는 관리 도구로 같은 runtime/port를 시작한다. `ROLLBACK_BLOCKED`·`RESTART_BLOCKED`·`RESTART_PENDING`이면 현행 작업/예약 및 소유권을 점검한다.
- Windows는 이전의 검증된 전체 소스 폴더 및 이에 대응하는 환경에서 기존 home으로 시작한다. 기존 Manager/Host가 사용하던 포트·SSH-R·키와 재시작된 owner의 실행 경로를 확인한다. 기존 경로 전체를 회사 절차에 따라 복원한다.
- DB 복원이 승인된 경우 신버전 runtime도 별도 보호 사본으로 보존한다. Linux와 Windows 복원본을 각각 새 검증 경로에 구성한 뒤 manifest SHA·읽기 전용 DB 무결성·이전 코드 호환성을 확인한다. 운영 포인터 전환과 제어 재개는 현지 승인 범위로 수행한다. 예약·UNKNOWN·설정 revision·snapshot 및 전환 이후 유효한 실행 이력이 계속 추적되는지 확인한다.
- 이전 패키지의 `monitor status`에서 설치와 실행 소스가 일치할 때 `MATCHED`가 기대된다. 이전 API가 실제 경로 필드를 제공하지 않으면 해당 프로세스 경로와 이전 source manifest를 운영자가 별도로 비교한다.
