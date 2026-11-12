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
