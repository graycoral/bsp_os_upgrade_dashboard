# 현재 상태

확인일: 2026-11-07. 확인 기준 커밋: `1cd6ce8` (이 문서 변경 전). 이 요약은 실행 증거를 대체하지 않는다.

| 영역 | 현재 상태와 근거 |
|---|---|
| 공통 BSP·조정 | 로컬 구현·모의 검증 단계. v1 기본, v2·조정은 새 job opt-in. [운영 안내](../agents/ORCHESTRATION_V2_OPERATIONS.md), [검증](../testing/runs/20261106-orchestration-v2.md) |
| GUI host·이식 | 로컬 검증 및 독립 리뷰 근거가 있다. 회사 인수 T-190은 NOT_RUN. [PORT-004](../porting/PORT-004.md), [병합 검증](../testing/runs/20261106-portability-merge.md) |
| BSP 플러그인 RQ-60 | 로컬 구현·모의 검증. T-208 Linux 설치·복원 및 T-209 회사 인수 NOT_RUN. [기록](../testing/runs/20261107-bsp-upgrade-integration.md) |
| TEST BOARD CONNECTOR RQ-61 | T-210~216 로컬 PASS, 회사 SSH·COM·장비 인수 T-217 NOT_RUN. [기록](../testing/runs/20261107-editable-windows-runner.md) |
| TEST BOARD CONNECTOR RQ-62 · 2026-11-12 후속 | 설정 경로/serial 자동 탐색·공통 입력 및 플러그인 안내; 집중 모의 62 PASS. 기존 회귀의 환경/시험 결함은 별도 기록. EXE ZIP·체크섬 제거·신규 EXE 생성 없음. 독립 리뷰 NOT_REVIEWED, 회사 T-221 NOT_RUN. [기록](../testing/runs/20261112-runner-setup.md) |
| 외부 인수 | 실제 Linux·모델·장비·사내 Jira 및 회사 환경 검증은 각 실행 증거가 필요하다. 운영 baseline은 [NONE](../testing/BASELINE.md). |

기능별 상태와 미완료는 해당 [PORT](../porting/README.md), [시험 결과](../testing/TEST_RESULTS.csv), [누적 진행 기록](WORK_STATUS.md)과 실행 기록을 확인한다. 과거 PASS를 현재 코드의 검증으로 재사용하지 않는다.

## 2026-11-12 보드 커넥터 GUI 후속

RQ-63/D-67: 독립 Qt GUI와 같은 Mac preview, 공통 registry/보드 자동 표시, RX 콘솔·중앙 오류 cursor를 소스 구현했다. 기존 timeout/영구 삭제 WIP와 연계하고 고정 snapshot/Run pin/배타를 보존한다. 로컬 모의·Qt·브라우저 검증을 마쳤으며 [실행 기록](../testing/runs/20261112-board-connector-gui.md)을 따른다. 회사 T-228 NOT_RUN, 새 EXE/전달 ZIP 없음. 후속 사용자 지시로 커밋·게시를 진행하며 고정 대상은 PORT-009를 따른다. [PORT-009](../porting/PORT-009.md).

최종 근거: 광역605 PASS/간헐적 Mac killpg 1 FAIL 후 관련 집중53 PASS, 브라우저13 PASS, 양 UI build PASS. 전체 단일 실행 PASS나 실제 Windows/회사 통과로 표현하지 않는다. Astra는 [잔여 4건 코드 수정](../testing/runs/20261112-board-connector-code-review.md) 범위만 APPROVED다.

게시 전 재검증: 동일 광역 Python **606 PASS**, Chrome **13 PASS**, 양 UI build 및 최신 Qt 로그 4탭 검사 PASS. 이전 실패는 이력으로 보존하며 네이티브 앱 클릭 자동화는 도구 접근 거절로 BLOCKED다.

## 2026-11-13 · 경로 읽기 전용 표시

커넥터 연결 탭에 서버 선택/실행 원본과 Windows 작업 폴더 표시를 추가했다. 요청 전·이전 실행·단절을 구분한다. 경로 표시 제품 커밋은 `9fa5a0f88a8b26d333be3906cf3d63fa767d570d`이며 CI 복구 변경을 보존해 통합했다. RQ-63/T-229, [검증 기록](../testing/runs/20261113-board-connector-paths.md). 실제 Windows·회사 인수 NOT_RUN.

## 2026-11-13 연결 토큰 제거

RQ-64/D-68: Runner·등록·플러그인 공유 토큰 설정과 확인을 제거했다. SSH·loopback·실행 소유권은 유지한다. T-230 최종 집중 259 PASS / Windows 전용 10 SKIP. 광역 Mac 프로세스 identity 시험 제약과 최초 실패는 [실행 기록](../testing/runs/20261113-tokenless-connections.md)에 남겼다. 회사 T-231 NOT_RUN, 독립 리뷰 NOT_REVIEWED, 미커밋·미게시다. 자동 설치 구현은 방향 재정리 요청에 따라 계속 보류한다.
