# 2026-11-17 · 플러그인 명령 포팅 설계 리뷰

## 범위와 기준

문서 변경 기준·기존 API 조사 기준 `f0fd97c88548de4896aac350444336293a768e8f`. 문서 전용이며 제품 코드·DB·설정·서비스/장비/모델 실행 없음. 원본 main 작업 트리의 다른 변경과 미게시 커밋을 제외하고 별도 worktree에서 작성한다. 관련 요구 RQ-60/67/69/70와 명령별 목표/인수는 [PORT-011](../../porting/PORT-011.md)이 원문이다.

## 별도 세션 리뷰

- review_id: `20261117-plugin-command-porting`
- reviewer / tool / model: 별도 Codex 세션 `/root/plugin_command_review` / collaboration / 부모 세션 상속 모델. Claude 리뷰가 아니다.
- reviewed_revision / scope: 초기 `62d6b52da93c3bc64f694fd89e66033bc173914e`에서 추천 명령과 관련 API/계약 읽기. 명령 관련 core 파일은 문서 작업 기준과 동일하다. 초기 추천 목록 읽기 리뷰는 CHANGES_REQUESTED였고 아래 보완을 PORT-011에 반영했다. 최종 문서 delta에서 초기 P1/P2가 모두 해결됐음을 확인했다. 최종 문서 대상 SHA-256은 아래와 같다.
- status: APPROVED (독립 Codex 세션의 설계·포팅 문서 범위, 남은 P1/P2 없음). 제품/회사 인수 승인이 아니다.
- 최종 PORT-011 SHA-256: `6e963de4b9d511494d4652956d88c2df99d594ff58dd02a110af7c15acc705b1`. 8개 진입 문서도 읽기 검토했다. 이 기록의 최종 승인/검사 결과 보충은 증거 갱신이며 설계 내용 변경이 아니다.
- 검토자 실제 검사: `git diff --check` PASS. 자동 제품시험은 없음. 코드/계약·기존 시험 시나리오 읽기 리뷰와 제품시험을 구분한다. 링크/ID 검사는 아래 부모 세션 실행 결과다.
- 초기 판정: CHANGES_REQUESTED. 근거는 `plugin_client.py:377~393`, `shared_settings.py:130~139,190~220`, `integration.py:451~518`, `manager.py:338~343` 및 미러 계약.
- 초기 반영: connect 1회 조회와 뒤늦은 연결 알림 adapter 구분, 공통 CAS/초안 보존·Windows PENDING/APPLIED, test runs/select/reconcile·connect export·프로파일 설정 보완, analyze 기본 조회와 명시 requeue, boards/doctor/report는 status 옵션으로 통합, pause/cancel의 접수와 실제 완료 구분, catalog/integration 목록 범위 구분.
- 미검증: 회사 slash 등록·설정 UI·알림·실제 Windows/SSH/COM/BAT/TC, CMD-A01~08 전부 NOT_RUN.

## 문서 검사

최초 `python3 docs/testing/validate_docs.py`: FAIL(격리 기준에 없는 다른 세션의 FORCE_STOP.md 링크 1개). 해당 기능을 미게시 별도 전달로 명시하고 링크를 제거했다. 수정 후 재검사 PASS: 상대 링크 1,861개·요구사항 71개·시험 ID 274개 일치, 오류 0개. `git diff --check` PASS. 과거 실패를 유지한다. 제품시험은 문서 변경으로 실행한 것으로 표시하지 않는다.


## 변경·검증 한계

변경 파일은 PORT-011, 이 실행 기록, `docs/README.md`, `docs/agents/BSP_UPGRADE_PLUGIN_REQUEST.md`, `docs/agents/PLUGIN_CONTROL_API.md`, `docs/implementation/CURRENT_STATUS.md`, `docs/implementation/WORK_STATUS.md`, `docs/porting/PORT-007.md`, `docs/porting/PORT-009.md`, `docs/porting/README.md`의 10개 문서다. 기존 전역 RQ/T/결함 이력·코드·의존성·DB는 변경하지 않았다.

문서 변경이므로 자동 제품시험은 이번 변경의 검증으로 실행하지 않았다. 기존 제품시험 PASS를 새 명령 시험 PASS로 재사용하지 않는다. 후속 회사 adapter·CMD-A01~08·실장비 인수는 NOT_RUN이다. 문서 조사 기준에 없는 다른 세션의 강제 종료/TC 상태 조회 WIP는 독립 전달 대상으로 남긴다.
