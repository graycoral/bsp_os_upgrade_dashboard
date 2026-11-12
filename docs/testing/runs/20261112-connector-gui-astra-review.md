# TEST BOARD CONNECTOR GUI · Astra 설계 리뷰

2026-11-12. 사용자 지시로 독립 `gpt-6-astra` 세션이 계획·관련 코드/계약을 검토했다. 기준은 `6734c843c46e986ce5c35a0851c38ac009661b98`와 미커밋 계획/timeout·삭제 WIP다. 판정 **CHANGES_REQUESTED**. 제품 시험 **NOT_RUN**. 실제 Claude 리뷰로 표시하지 않는다.

[GUI 계획](../../design/TEST_BOARD_CONNECTOR_GUI_PLAN.md)에 다음 수정 방향을 반영하고 이미 승인된 Sol 구현으로 진행한다.

| 지적 | 반영한 구현 조건 |
|---|---|
| F1 높음 | 영속 registry/facade를 API·기존 단일 Worker가 공유; 인증·왕복 확인; 기존 Run identity 고정; plugin auth/health 접점 |
| F2 높음 | TC 미설정 bootstrap, 공통 서버 소스/Windows 대응 소유; snapshot 실행에 불필요한 source_root 입력 제거; legacy 보존 |
| F3 높음 | 전체 inventory/status를 기존 가용 boards/verify와 분리; host 배타·UNKNOWN·freshness 보호 |
| F4 높음 | 기존 snapshot 기본 유지, 직접 실행은 별도 opt-in mode/capability; 기존 plugin preview/자동 BSP 고정 계약 유지 |
| F5 중간 | 독립 관리자 수명, GUI 닫기와 안전 종료 분리, SSH 인증/포트 경쟁 처리 |
| F6 중간 | 기존 timeout/영구 삭제 계약 재사용; 첫 GUI는 공간 조회 우선, 새 자동 정리는 미완료 요구로 보존 |
| F7 중간 | 동일 Qt 화면의 Mac preview, 격리 home/금지 호출 guard; 실제 창과 offscreen 시험 구분 |

상세 리뷰는 로컬 전용 `.local-reports/connector-gui-astra-review-20261112/review.md`에 보관하고 Git에 포함하지 않는다. 계획 반영은 제품 구현/검증 통과가 아니다. 사용자 재승인 없이 Sol이 구현하며 Windows/회사 SSH·COM·TC, 배포 EXE/ZIP, 커밋/푸시는 별도다.

리뷰 전 확장 계획 문서 검사: `python3 docs/testing/validate_docs.py` PASS, 상대 링크 1,199·요구사항 62·시험 221·오류 0. `git diff --check` PASS. 제품/시험 소스 17개 SHA256 보존 확인. 로컬 로그 `.local-reports/connector-gui-expanded-plan-b9ae6723/`는 Git에 포함하지 않는다. 이후 제품 변경은 새 실행으로 검증한다.
