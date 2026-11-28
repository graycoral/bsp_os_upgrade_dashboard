# 04. 사내 플러그인 이식 사전 분석·계획

> **담당 하네스:** **사내 Claude Code + Amazon Bedrock**
> **지정 모델:** **Claude Opus**, 깊은 추론 (회사 정책이 허용하는 Opus 버전)
> **권한:** **사내 코드/환경 읽기 및 계획 작성만**. 이 단계에서 제품 코드 삭제·수정·운영 실행 금지.
> **후속 담당:** `05_CLAUDE_SONNET_COMPANY_PORT.md`의 **Claude Sonnet**

## 목적

원본에서 준비된 `copy-ready` 전달물을 사내 `bsp-os--upgrade` 플러그인에 **복사 중심으로 이식**한다. 이미 사내에서 구현된 기능이나 추가된 기능을 덮어쓰지 않는다. 이식 과정에서 실제 발생했던 에러를 로그·코드로 조사하고 **원본 공통 결함 vs 사내 Host Adapter/설정 vs 설치 환경**으로 분류한다.

## 사내 데이터 경계

- 모든 사내 코드, 절대 경로, 계정, SSH, 사내 API/Jira/보드, 로그 및 회사 정책 정보는 **사내 허용된 저장소·Bedrock 세션에서만** 다룬다.
- 공개 GitHub 원본에는 일반화된 문제 유형/재현 테스트만 반영할 수 있고, 회사 파일/로그 내용은 반출하지 않는다.
- Claude Code가 파일을 읽는 것과 실행 권한이 있는 것은 다르다. 장비 flashing, 데이터 삭제, 서비스 강제 종료 등은 별도 승인 필요.

## 입력

- 원본 copy-ready 폴더 (`plugin.py`, `agent-monitor/`, `PLUGIN_PACKAGE.json`, `AGENT_MONITOR_SOURCE.json`)
- 원본 `docs/porting/README.md` 및 관련 PORT-007/009/011/012/013/014
- 원본 `docs/porting/review/{PORTABILITY_AUDIT,DEPENDENCY_MATRIX,COPY_READY_RESULT,COMPANY_SMOKE_TEST,ROLLBACK}.md`
- 회사 저장소 `AGENTS.md`/`CLAUDE.md`/운영 정책, `docs/porting/{COMPANY_MAP,APPLIED}.md` (없으면 원본 템플릿 참조)
- 이미 사내에서 발생한 오류 로그가 있으면 **사내 보안 절차에 따른 최소 관련 구간**

## 분석 지시

1. 회사 지침과 회사 Git 브랜치/HEAD/미커밋 상태를 먼저 확인한다. 제공 폴더 manifest/hash를 검증한다.
2. 기존 사내 플러그인의 slash 명령 진입점, install/activate hook, 기존 dashboard API/worker, 소스 소유권, 서비스 실행자, runtime/DB/설정 위치, Windows 실행 수명과 권한을 조사한다.
3. 기능별 적용 상태를 `ALREADY_EQUIVALENT`, `PARTIAL`, `MISSING`, `COMPANY_CUSTOM`, `UNKNOWN`으로 기록하고 **증거 없이 완료라고 하지 않는다**.
4. 원본에서 변하지 않는 `COPY_AS_IS`와 사내에 맞게 수정해야 하는 `ADAPTER_ONLY` 위치를 파일/심볼 단위로 분류한다. 회사 특화 코드를 원본 package로 뒤섞지 않는다.
5. 실제 오류를 `REPRODUCED`, `EVIDENCED_NOT_REPRODUCED`, `UNCONFIRMED`로 구분한다. 예: 불완전한 파일 closure, Python dependency, Node 빌드, 잘못된 import/path, 포트 충돌, 구버전 서비스 재사용, Windows SSH/COM/터널, DB migration.
6. 백업·복원·동시 실행/예약/미완료 작업 중 서비스 변경 정책을 확인한다. 위험한 상태에서는 이식 시나리오를 보류한다.
7. 회사와 원본의 release/pin/버전을 대조하고 PORT별 선행 변경을 확인한다. 원본 전체 HEAD를 회사 기능 전체의 적용 기준으로 간주하지 않는다.
8. 명확한 P0/P1 차단 항목, 모호한 운영 정책은 **선택지·위험·권장안·필요 승인**을 갖춘 `OPEN_QUESTION`으로 남긴다. 회사가 답한 기존 질문은 반복하지 않는다.

## 문서 산출물 (모두 사내 저장소에만 저장)

- `docs/porting/COMPANY_MAP.md`: 원본 경로/심볼 ↔ 사내 파일/어댑터 대응, 이미 존재하는 기능, 소유권.
- `docs/porting/COMPANY_BASELINE.md`: 사내 시작 커밋, 기존 적용 PORT/pin, 서비스/runtime/DB 스키마 상태(민감 값은 기록하지 않음).
- `docs/porting/ERROR_TRIAGE.md`: 오류마다 ID/심각도/로그 포인터/재현/원인 추정과 근거/조치 장소(원본 vs 회사)/재시험.
- `docs/porting/COMPANY_PORT_PLAN.md`: 작업 단위, **복사할 파일 디렉터리**, 수정해야 하는 최소 Adapter, 금지 범위, 순서, rollback, 시험.
- `docs/porting/OPEN_QUESTIONS.md`: 회사 정책이나 환경 의사결정이 필요한 항목만.

## Sonnet 세션 인수인계

다음 표를 `COMPANY_PORT_PLAN.md` 끝에 넣는다.

| Work ID | 기준 source commit/release | 회사 기존 파일 | 복사/어댑터 | 시험 | 차단 조건 | 완료 기준 |
|---|---|---|---|---|---|---|

**선택지 결정이 필요한 P0/P1 문제는 구현으로 우회하지 말고 해당 범위를 BLOCKED로 남긴다.** 나머지 독립적인 범위는 Sonnet이 계획에 따라 진행하도록 구체적으로 적는다.
