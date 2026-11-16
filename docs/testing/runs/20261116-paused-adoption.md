# 일시정지 예약 유지 이관

RQ-68 / T-254 / REG-0098. 원본 기준은 `e7501bc9e2bf37b293e3fe6c4010cc083b40f7c7`이다.

## 원인과 수정

회사 진단은 HELD_RESERVATIONS 1개, 예약 자원 2개, PAUSED 세션 1개, hardware 1개였다. 기존 최초 관리 설치는 모든 예약을 이관 보류로 처리했다. GUI Test의 정상적인 일시정지는 예약을 유지하므로 이 조건에서 설치를 진행할 수 없었다.

`recovery.py`가 예약의 run ID·lease token·실행 방식·TC 종료 근거·플래싱 상태를 확인한다. 전체 runtime의 계약·실행 상태 검사까지 통과한 PAUSED 예약은 보존 가능으로 분류한다. `manage.py`의 최초 활성화는 설치·서비스·runtime 잠금 아래 DB를 백업하고 관리 설치 포인터를 기록한다. PAUSED 세션과 예약은 기존 DB에 유지된다. 관리 중인 릴리스 교체는 기존 작업 게이트를 따른다.

종료 근거 누락, UNKNOWN, 실행 중 시도, 토큰 불일치, 소유 세션 누락, 활성 lease, 플래싱 종료 미확인, 미지원 계약은 보류한다. 진단은 보존 가능한 자원 수와 보류 코드를 표시한다. DB schema 변경은 없다. 백업은 설치 home의 `backups/adoption-*`, 이관 기록은 `runtime-adoption.json`에 저장한다.

## 검증

원본 로그와 파일별 SHA-256 manifest는 `.local-reports/20261116-paused-adoption/`에 보관한다. main 기준의 격리 checkout에 이번 관리 코드 2개와 회귀 시험 1개를 적용했다. 별도 작업 중인 GUI Test 코드 7개는 이 검증과 게시에서 제외했다.

| 실행 | 결과 | 근거 |
|---|---|---|
| 수정 전 main과 새 회귀 시험 | 예상 1 FAIL | `before-fix.log`, 정상 예약의 adoptable=false 재현 |
| 초기 관리 코드 회귀 | 97 PASS | `tests.log` |
| 확장 회귀 첫 실행 | 239 PASS / 1 FAIL / 8 SKIP | `final-tests.log`, 환경 Git shim이 `git init -b main`을 지원하지 않아 실패 |
| 실제 Git을 사용한 전체 재시험 | 240 PASS / 8 SKIP | `final-retest.log`, 17.74초 |

재시험은 PATH에서 `/usr/bin:/bin`을 우선하고 아래 명령을 실행했다.

```bash
python -m pytest tests/test_agent_monitor_manager.py tests/test_agent_monitor_recovery.py tests/test_agent_monitor_lifecycle.py tests/test_agent_monitor_delivery.py tests/test_setup_runtime.py backend/gui_test/tests/test_core.py backend/gui_test/tests/test_plugin_integration_recovery.py backend/gui_test/tests/test_session_deletion.py -q
```

정상 start 진입에서 자동 이관·백업·PAUSED/예약 2개 보존, 같은 릴리스 재시도, 관리 중 릴리스 교체 보류, Worker 잠금, inspection revision CAS, 백업·포인터 실패 후 재시도를 검증했다. 종료 근거와 계약이 부족한 입력 11종 및 정상 플래싱 준비/종료 기록 6종을 포함한다. Starlette TestClient의 httpx 사용에 관한 의존성 deprecation warning 1건이 있었다.

코드 manifest SHA-256 `70b9291c1ac4b18c4121452f36720c1d9a9eff474b2f45327eee7485864d3cbc`. 시험 manifest SHA-256 `92f1bc9cef101d829743cb28a998b0b84b3a5c06b5a17ed4b9d15e852089c141`.

## 회사 적용

[PORT-007](../../porting/PORT-007.md)과 [플러그인 요청문](../../agents/BSP_UPGRADE_PLUGIN_REQUEST.md)의 최신 절을 적용한다. 플러그인 복사형 배포본에 같은 관리 코드를 포함하고 stderr의 검사·백업·연결 안내를 전달한다. Agent Monitor는 기존 실행 명령을 사용한다.

```bash
git pull --ff-only
bash run.sh --port 8765
```

회사 Linux의 실제 데이터 이관·서비스 시작 및 Windows 보드 연동은 NOT_RUN이다. 자동 이관 가능 여부는 회사 DB의 소유권·종료 근거 검사 결과로 결정한다.

수정 코드·시험 고정 커밋은 `dc646490656ae6a05d5ba00eb0f60e5b6f929cc5`다. 문서 상대 링크 1717개 검사와 `git diff --check`는 PASS다.
