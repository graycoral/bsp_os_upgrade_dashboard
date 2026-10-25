# GUI Test — GitHub 모듈 분리 및 회사 적용 구현 계획

- 대상: `graycoral/bsp_os_upgrade_dashboard` (2026-10-12 공개 `main` 기준)
- 상태: **승인된 폴더 분리/개발 순서 설계(문서만 작성)**. 아래 파일은 구현 완료/동작 보증을 의미하지 않음.
- 참조 요구사항: `GUI_TEST_REQUIREMENTS_FINAL_REVIEW.md`, `DASHBOARD_GUI_TEST_INTEGRATION.md`

## 1. 고정 정책

| 항목 | 구현 정책 |
|---|---|
| TC 실행 명령 | **기존 명령이 COM 포트 인자를 지원함은 사용자 확인 완료**. 실제 명령의 실행 파일·플래그·인자 순서 등 **구체 문법은 추후 정의**한다. Core·UI·Mock은 우선 구현 가능하며 실제 명령을 임의로 만들지 않는다. |
| Dashboard 통합 COM | RBC↔RBM이 제공하는 보드 ID/Windows 호스트/COM 후보를 선택. RBM 실패 시 Dashboard에서 수동 입력하며 Preflight로 검증. |
| Windows 단독 COM | Windows 로컬 Python 서비스에서 COM 포트 목록 자동 조회 후 콤보박스 제공. 보드 A/B 매핑 사용자 확인. |
| COM 적용 | UI가 `ConnectionSnapshot`(host, board_a/com_a, optional board_b/com_b)을 Runner에 전달한다. Runner는 **이미 지원되는 기존 TC 실행 명령의 COM 인자 슬롯에 해당 값들을 매핑**한다. Single 1개/Dual 2개의 정확한 옵션명·인자 순서는 실제 명령 확인 후 확정한다. |
| Single/Dual | 폴더 경로에 `dual` 포함 시 Dual. Dual은 동일 Windows PC의 서로 다른 물리 보드 두 대. |
| 통합/단독 | **GUI·결과 판정·메타데이터 계약은 재사용**, Run 영속 관리자는 모드별로 분리. 단독 Run은 Dashboard·RBM 연결/공유 없음. |
| Dashboard 결과 | 전체 Run PASS/FAIL 확정 및 매핑·Job·이미지·계획·Attempt 검증 뒤 해당 모듈 `device_test`에 자동 반영. 데모는 절대 운영 상태 변경 금지. |

## 2. 채택된 저장소 구조

```text
bsp_os_upgrade_dashboard/
├── gui_test/                       # 회사로 분리 반입할 주 패키지
│   ├── README.md                   # 설치/실행/회사판 연동 안내
│   ├── pyproject.toml              # 공통 Python 패키지 의존성
│   ├── core/
│   │   ├── models.py               # Run, TC, Attempt, ConnectionSnapshot
│   │   ├── discovery.py            # Git/폴더 탐색, dual 분류
│   │   ├── results.py              # Test Result 파서·PASS/FAIL/INCOMPLETE
│   │   ├── manager.py              # 순차 실행, pause/resume/cancel, 예약
│   │   └── reporting.py            # JSON/CSV/HTML/PDF 및 로그 참조
│   ├── adapters/
│   │   ├── runner.py               # 실행 계약 + COM CLI 인자 매핑(실제 옵션 문법은 후속)
│   │   ├── rbm.py                  # Dashboard 모드용 RBM 조회 어댑터
│   │   ├── windows_ports.py        # 단독 모드 Windows COM 포트 열거
│   │   └── mock.py                 # 독립 E2E 데모 전용
│   ├── api/
│   │   └── router.py               # Dashboard에서 포함할 FastAPI Router
│   ├── web/
│   │   ├── TestPage.tsx            # 공유할 React Test 화면
│   │   └── components/             # TC 트리, 포트 선택, 로그, 보고서
│   ├── standalone/
│   │   ├── server.py               # Windows 로컬 웹 API 및 Run 관리 진입점
│   │   └── start.ps1               # Windows 단독 시작
│   ├── config/
│   │   ├── tc_metadata.example.json
│   │   └── dashboard_mapping.example.json
│   ├── demo/                        # 독립 저장소/가상 이벤트 시나리오
│   └── tests/                       # core·API·데모 회귀 시험
├── backend/api/main.py             # router 포함 최소 변경
├── apps/web/src/main.tsx           # 기존 좌측 `Test 현황` 메뉴 최소 변경
└── apps/web/                         # 공유 TestPage UI 빌드 연결/alias 점검
```

- 이 폴더 구조는 **제안 경로**이며 현재 GitHub에 생성된 파일 목록이 아니다.
- `gui_test/`는 Python 패키지 식별자로 사용할 수 있는 밑줄 표기를 사용한다.
- `gui_test/web/`의 React 컴포넌트를 기존 `apps/web`의 Vite/TypeScript 빌드에서 가져오려면 **빌드 설정·CSS·import 경로의 실제 검증**이 필요하다. UI 중복 복제를 기본안으로 삼지 않는다.
- 회사 복사용 배포는 `gui_test/` 폴더를 ZIP으로 묶고, 기존 Dashboard에 적용할 최소 진입점 패치를 함께 제공한다. 기존 `backend/` 전체 덮어쓰기는 금지한다.

## 3. 공통 인터페이스 (예시 개념 계약)

```json
{
  "run_id": "run-id",
  "mode": "dashboard | standalone | demo",
  "windows_host": "host-id",
  "connections": [
    {"role": "A", "board_id": "board-a", "com": "COM3"},
    {"role": "B", "board_id": "board-b", "com": "COM4"}
  ],
  "tc_source_revision": "git-sha",
  "tc_ids_ordered": ["tc-id-1", "tc-id-2"]
}
```

- Single은 `connections`에 A만 포함한다. 값은 실제 실행에서 조회/입력한 값으로 생성하며 예시는 가상이다.
- `runner.execute(tc, connections, timeout, context)`라는 **논리적 계약**을 먼저 정의한다. **COM 전달은 기존 명령줄 인자 사용으로 확정**한다. 단, 실제 인자명·위치·호출 경로는 현장 명령 확인 전까지 가정하지 않는다.
- 동일한 `Test Result: PASS|FAIL` 파서와 전체 집계 규칙을 두 모드에서 호출한다. UI는 판정 로직을 중복 구현하지 않는다.

## 4. 기존 Dashboard 최소 연결점

| 파일 | 필요한 변경 |
|---|---|
| `backend/api/main.py` | `gui_test.api.router` 등록, 기존 Host/Origin/요청 헤더 보호 유지 |
| `apps/web/src/main.tsx` | 기존 메뉴에 `Test 현황` 추가, `gui_test/web/TestPage`로 진입 |
| `backend/domain/engine.py` | 별도 버전 검증된 자동 `device_test` 결과 접수 경로. 기존 `manual-test` 직접 덮어쓰기 금지 |
| `backend/worker/main.py` | HTTP 요청과 독립된 GUI Test 실행/상태 복구 경로 연결. 기존 Worker 수명 주기·게이트 유지 |
| `backend/storage/` | Test Run/Attempt/로그/아웃박스 스키마 추가 시 migration과 백업/회귀 시험 |

회사판의 실제 코드가 공개 저장소에서 변경됐을 수 있으므로 위 위치는 기준이며, 먼저 회사판 Delta를 확인한다. **기존 메인 소스를 통째로 덮어쓰지 않고 `gui_test/`와 최소 진입점 패치만 이식**한다. 운영 DB에 데모/테스트 데이터를 넣지 않는다.

## 5. 승인된 GitHub 작업 방식

- 기존 `main`은 직접 수정하지 않는다. `feature/gui-test` 계열 별도 브랜치에서 단계별 구현하고 테스트·리뷰 후 PR로 통합한다.
- 처음에는 `gui_test/` 하위에 **공통 Core, API 계약, 공통 React 화면, Windows 단독 진입점, Demo와 테스트**를 개발한다. 실제 TC 실행 명령의 구체 문법을 모르면 Demo로 검증하고 운영 하드웨어 기능은 미연동으로 표시한다.
- 회사 반입용 산출물은 `gui_test/` 디렉터리 ZIP + 기존 Dashboard에 적용할 **최소 패치** + 의존성/보안/배포 안내로 구성한다. 공개 GitHub와 사내 코드/데이터는 분리한다.
- 이 문서는 구현 지침에 대한 승인이지 **이미 GitHub에 변경을 커밋했다는 뜻이 아니다**.

## 6. 단계별 구현 및 완료 조건

| 단계 | 구현 가능 기능 | 통과 기준 |
|---|---|---|
| 1: 폴더 분리·데모 | Core 모델, TC 폴더 트리, Single/Dual, Mock RBM/COM/TC, 선택/상태·리포트 UI | Dashboard와 Windows 단독 웹 모두 **Mock으로 실행 흐름 테스트**, 운영 데이터 영향 0 |
| 2: Windows 독립 COM | Windows COM 열거, 연결 프로파일, 저장/복원, 로컬 백그라운드 Run 관리자 | Windows에서 실제 COM 선택, 브라우저 닫아도 Run 관리 지속 |
| 3: 실제 TC Adapter | **실제 기존 명령의 COM 옵션/인자 순서 확인 이후** 실행/종료/타임아웃/로그 수집 연결 | Single/Dual의 선택 COM이 기존 명령 인자로 정확히 전달되는지 확인한 뒤 실장비 TC 실행, `Test Result:`와 종료 코드 검증 |
| 4: Dashboard 통합 | 회사판 RBM 보드·COM 조회, 수동 대체, Job 매핑·이미지/계획/Attempt 검증, `device_test` 결과 반영 | 기존 수동 시험·Job 이력 보존, 자동 결과 반영·재검증 회귀 시험 |
| 5: 배포·회사 이식 | 패키지 ZIP, 오프라인 의존성/보안 설정/설치 안내, 전체 회귀 | 사내 승인 환경에서 설치·실행·업데이트/복구 가능 |

## 7. 회사 반입 전 제한 및 확인

- 공개 GitHub에는 회사의 보드 정보, 사내 주소·계정·SSH 키, 사내 TC 원본, 보안 문서, 실제 테스트 로그를 넣지 않는다. 설정 예제는 가상 데이터만 사용한다.
- 사내 GitHub 접속이 차단될 수 있으므로 `gui_test/`를 **ZIP으로 전달하고 회사 Dashboard 코드에 최소 패치 적용**할 수 있게 한다. Python/Node 패키지는 사내 허용 저장소 또는 승인된 오프라인 설치 방식으로 준비한다.
- 단독 Windows Local Runner와 Linux 통합 Runner가 한 Windows 호스트의 동일 물리 보드를 동시에 쓰는 것은 모드별 별도 예약만으로 방지되지 않는다. **공통 물리 잠금 검증 전에는 같은 호스트의 양 모드 병행 실장비 실행을 금지**한다.
- 공개 `main` 기준과 회사판 현재 코드의 차이, RBC/RBM API, 보드 이미지 동일성 증빙, TC 명령의 구체 COM 옵션/인자 순서 및 프로세스 실행 호스트를 현장에서 검증해야 한다. **COM 인자 지원 여부는 미정이 아니다.**
