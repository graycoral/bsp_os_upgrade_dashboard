# GUI Test 검증 기록

기준: 공개 Dashboard `14bb35ea66a328a9de204fbb039cc5d303778b52`, feature/gui-test.
구현/로컬 검증일: 2026-10-25. 모든 신규 실행은 Mock/임시 DB로 진행했습니다.
실제 TC·SSH·사내 RBM·물리 COM·회사판 Dashboard 인수는 NOT_RUN입니다.

## 검증과 추적

| 요구사항 | 자동 검증 위치 | 범위 |
|---|---|---|
| TC-01~08, IO-03/04, AC-02/08/13/14 | tests/test_core.py | 폴더/Git 읽기·소스 고정, Dual, 중복/순서/매핑, Suite/프로파일, 인자 배열 |
| IO-06~08, RUN-01~08, AC-03~06/09 | tests/test_core.py | 원자 예약, 동시 시작, 상태/명령/재시도, 취소·종료 불명·복구, 완료 불변 |
| RUN-09, AC-11 | tests/test_core.py, ../../tests/e2e/gui-test.spec.ts | 단일 브라우저 제어권, 이전 승인, 만료 후 명시적 인수 |
| RES-01~05, AC-07 | tests/test_core.py | 엄격한 문구/종료 코드/예외, 원본 로그, 출력 한도/마스킹 |
| RPT-01/02, UI-01~03 | tests/test_api.py, ../../tests/e2e/gui-test.spec.ts | 상태·로그·내보내기, 공유 UI, JSON 내용, 재접속 |
| INT-03~12 | tests/test_dashboard.py | Run 전체/모듈 집계 분리, 미매핑 FAIL/ERROR, 기준 변경, outbox/응답 유실, 수동 이력/완료 Job 재검증 |
| INT-13/14 | tests/test_api.py 및 기존 tests/ | 데모 격리, 운영 DB 보존, 기존 수동시험·게이트·설정 회귀 |
| AC-01/10, INT-01/02/16 | demo/e2e.py, 브라우저 시험 | Mock 전체 흐름, Single/Dual COM 전달, 독립/통합 모드 |
| AC-12, INT-15 | 하드웨어 실행 차단 + README | 공통 물리 잠금 미검증 시 운영 불가. 물리 충돌 시험 NOT_RUN |
| IO-01 | tests/test_core.py | Windows COM 열거 API의 모의 OS 시험. 실제 장치 NOT_RUN |

## 로컬 실행 기록

- 변경 전 Python: **217 PASS**.
- 신규 Python 첫 실행: **61 PASS / 2 FAIL**. 빈 프로파일 저장이 500으로 실패했고, 탐색 시험이 정렬 순서를 잘못 가정했습니다.
- 수정: 빈 프로파일은 422 validation 오류로 반환, 탐색 시험은 path로 대상 선택. 재시험 **63 PASS**.
- Git 고정/선행 순서/매 TC 보드 확인/Windows 열거 계약 시험 추가: **67 PASS**.
- 기존+신규 전체 Python(추가 4개 전): **280 PASS**. 최종 결과는 하단 기록을 따릅니다.
- Headless 통합 데모: **7 PASS** — 정상, FAIL, 연결 오류 복구, Timeout, UNKNOWN, 동기화 실패, 응답 유실.
- Dashboard 브라우저: **9 PASS** — 기존 5개 + 신규 4개. 공유 UI의 최종 레이아웃 보정 후 재검증 결과는 하단 기록.
- 표준 Playwright Chromium 다운로드는 환경에서 불완전 ZIP으로 실패. 로컬 별도 npm 패키지의 Chromium 153 실행 파일로 브라우저를 검증했으며 제품 의존성에는 추가하지 않았습니다.
- 최초 문서 검사: VALIDATION 작성 전 링크 1건 실패. 파일 작성 후 최종 검사로 확인합니다.

증거는 `docs/testing/runs/20261025-gui-test.md` 및 해당 evidence 폴더에 저장합니다. GitHub CI는 Linux 전체 회귀와 Windows 설치/런타임 smoke를 별도로 수행하며 CI 확인 전 Windows PASS로 쓰지 않습니다.

## 구현 경계

- 실제 TC/RBM/보드 이미지 확인은 의도적으로 미연동, 운영 실행·운영 자동 결과 쓰기를 차단합니다.
- Git 탐색 Core는 로컬 Git을 지원하고 GUI는 현재 Mock 브랜치만 노출합니다. 실제 원격 TC 탐색은 해당 Adapter 접점에 연결해야 합니다.
- 새 Run PASS 계승을 자동 적용하지 않으며 모든 선택 TC를 재시험합니다.
- 기본 로그 정책은 영구 보관과 ZIP 내보내기입니다. 회사별 자동 원본 로그 정리/승인된 보존 정책은 운영 Adapter 도입 시 별도 적용해야 합니다. 현재 증빙 자동 삭제 없음.
- 기존 Dashboard의 boot-group/integration 의존 관계를 사용하며 회사판 추가 DAG는 현장 확인이 필요합니다.
- 독립 Claude 검토는 NOT_REVIEWED. 실제 검토 없이 완료했다고 표시하지 않습니다.

## 최종 로컬 결과

**Python 284 PASS (기존 217 + 신규 67), 통합 브라우저 9 PASS, 단독 브라우저 4 PASS, headless 통합 시나리오 7 PASS.** Dashboard/단독 TypeScript·Vite 빌드 성공. wheel 설치 후 저장소 밖에서 start/status/restart/UI/단독 시나리오/stop 성공. 실제 Windows CI 결과는 PR의 checks를 확인하며 물리 장비/사내 연동은 계속 미검증입니다.
