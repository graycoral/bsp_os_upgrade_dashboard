# GUI Test 요구사항 문서

GUI Test 구현의 기준이 된 요구사항 원본 3개를 보관합니다. 2026-10-25에 최신 원본을 내용 변경 없이 추가했습니다.

| 문서 | 내용 |
|---|---|
| [GUI Test 요구사항](GUI_TEST_REQUIREMENTS_FINAL_REVIEW.md) | TC 탐색·Single/Dual COM·실행·복구·결과·데모·인수 기준 |
| [Dashboard 통합 요구사항](DASHBOARD_GUI_TEST_INTEGRATION.md) | Dashboard 결과 반영·기준 검증·재검증·회사판 연결 계약 |
| [GitHub 모듈 구현 계획](GUI_TEST_GITHUB_MODULE_PLAN.md) | 모듈 구조·구현 단계·테스트·배포 계획 |

원문에 기재된 **구현 미착수/구현 예정**은 문서 작성 당시 상태입니다. 요구사항 문서 자체가 구현 완료나 실장비 검증을 의미하지 않습니다.

현재 Mock 기반 구현과 Windows 설치·Dashboard 통합 방법은 [실행 README](../../gui_test/README.md), 구현 범위와 남은 제약은 [검증 문서](../../gui_test/VALIDATION.md), 시험 결과는 [실행 기록](../testing/runs/20261025-gui-test.md)을 확인하세요. 실제 TC 명령과 사내 RBM 연동은 후속 현장 검증 대상입니다.

## 원문 이후 사용자 추가 요구사항

2026-10-25 요청한 **설정·Git 브랜치 접기, TC 목록 정돈, 실행 순서 드래그**는 [RQ-39](../requirements/REQUIREMENTS.md), [D-44 / ADR-11](../governance/DECISIONS.md), [상세 화면 설계](../design/UI_SPEC.md)에 반영했다. 위 원문 3개는 보관본으로 유지하며, 후속 요구사항을 함께 읽는다. 구현/시험 결과는 [2026-10-26 UI 검증](../testing/runs/20261026-gui-ux.md), T-109~111에 연결한다.

## Windows 단독 빌드

[Windows에서 GUI Test만 빌드하기](WINDOWS_BUILD.md): 전용 빌드 스크립트, 준비물, 산출물, 오프라인 설치·실행과 문제 해결.
