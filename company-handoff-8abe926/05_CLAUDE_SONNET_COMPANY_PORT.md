# 05. 승인된 사내 플러그인 이식

사내 Claude Code + Amazon Bedrock에서 **새 Claude Sonnet 세션**을 연다. 이 지침은 00의 단계별 게이트, 04의 Work ID 인수인계와 06의 독립 리뷰 입력을 바탕으로 작성했다.

## 시작 조건

회사 정책과 04에서 작성한 `docs/porting/COMPANY_PORT_PLAN.md`의 Work ID별 승인 범위를 확인한다. `COMPANY_BASELINE.md`, `COMPANY_MAP.md`, `ERROR_TRIAGE.md`, `OPEN_QUESTIONS.md`에서 해당 작업의 기존 기능·소유자·차단 조건을 읽는다. P0/P1 판단이 남은 Work ID는 BLOCKED로 기록하고 독립적으로 승인된 범위를 진행한다.

## 적용 순서

1. 회사 HEAD와 작업 트리, 현재 서비스의 release·소유자·home/runtime·포트, 실행 중이거나 예약된 작업을 기록한다. 전달본의 두 manifest SHA-256을 공급자 기록과 대조한 후 패키지 루트에서 `python3 -IB plugin.py verify . --pristine`을 실행한다.
2. 승인된 변경의 이전 소스·설치 경로·설정과 DB의 복구 지점을 확인한다. 동봉된 `agent-monitor/docs/porting/review/ROLLBACK.md`와 사내 운영 정책에 따라 백업 및 복구 가능성을 검증한다.
3. `COMPANY_PORT_PLAN.md`에 지정한 위치로 검증된 전달 폴더를 복사한다. 회사 고유 변경이 발견되면 해당 Work ID의 파일 차이를 먼저 대조한다. 승인된 slash 명령, install/activate hook, 모듈 게시, API 권한·UI 연결 등 회사 어댑터만 조정한다. 기존 Manager·Worker, 설정 DB와 Windows 커넥터의 소유권을 유지한다.
4. 동봉된 `agent-monitor/docs/porting/review/COMPANY_SMOKE_TEST.md` 및 Work ID별 회사 회귀 시험을 실행한다. manifest와 실제 실행 release, 기존 데이터·예약·설정 revision, UI 자산과 Windows 커넥터를 대조한다. 서비스 교체·장비 적용은 회사의 해당 운영 승인이 있을 때만 수행한다. 실패하면 로그와 기존 상태를 보존하고 해당 작업의 롤백 조건을 적용한다.
5. 04에서 확인한 오류는 이전 재현 근거와 수정 후 동일 조건의 재시험을 연결한다. 회사 코드·로그·환경 정보는 사내 승인된 위치에서만 다룬다.

## 결과와 인수인계

회사 저장소의 `docs/porting/`에 아래 기록을 작성하거나 갱신한다.

| 파일 | 남길 근거 |
|---|---|
| `APPLIED.md` | Work ID/PORT별 적용·부분 적용·보류 상태, source/target commit, package release, 복사 위치와 어댑터 |
| `COMPANY_SMOKE_RESULTS.md` | 실행 명령·환경·로그 위치, 예상값과 관측값, PASS/FAIL/BLOCKED/NOT_RUN, 장비 인수 상태 |
| `COMPANY_PORT_CHANGELOG.md` | 회사 기존 기능 보존 여부, 실제 diff와 소유자, 백업·롤백 근거, 미해결 오류와 다음 담당 |

00의 공통 인수인계 필드를 채워 회사 소스 기준과 시험 근거를 고정한다. 구현이 끝나면 새 Opus 세션에서 `06_CLAUDE_OPUS_FINAL_REVIEW.md`로 독립 리뷰를 진행한다.
