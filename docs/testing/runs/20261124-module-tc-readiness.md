# Test 현황의 모듈 TC 연결 판정

RQ-53 · D-56 · T-319 · REG-0122. 기준 커밋 `de275e3`, macOS arm64, Python 3.11.7. 실제 등록 어댑터와 임시 SQLite 등록소를 사용하고 Windows 응답을 모의했다. 전체 로그는 로컬 전용 `.local-reports/20261124-module-tc-readiness-iXEVNX/`에 있다.

1. Ethernet 장비 시험이 입력 대기 중인 작업에 Ethernet 스크립트 2개와 Display 스크립트 1개를 준비했다. 같은 로컬 HTTP 클라이언트로 `/api/v1/gui-test/live/capabilities`와 `/api/v1/gui-test/live/module-selection`을 조회했다.
2. 수정 전 연결된 실행기는 `ready=true`였지만 모듈 목록은 빈 배열이었다. 등록 어댑터의 `__getattr__`이 존재하지 않는 `unavailable` 속성에 대해 호출 가능한 함수를 돌려줬고, 모듈 서비스는 이를 미연결로 판정했다.
3. 모듈 서비스가 실행기의 `readiness()['ready']`를 사용하도록 수정했다. 같은 시험에서 Ethernet 2건만 반환했다. 등록이 없거나 등록 뒤 콘솔 상태를 받지 않은 경우에는 카탈로그 조회 없이 차단했다. 세 경우 모두 Run은 0건이었다.

| 실행 | 결과 | 로컬 로그 |
|---|---|---|
| 최초 시험 작성 | 모의 객체 설정 오류 3건. 제품 재현 전에 테스트 대역을 수정했다. | `red.log` |
| 수정 전 T-319 | 연결 사례 FAIL 1건, 미등록·콘솔 미수신 PASS 2건 | `red-product.log` |
| 수정 후 동일 T-319 | PASS 3건 | `green.log` |
| 모듈 선택·분석 재시도·커넥터 상태·실제 모드 API·공통 TC 경로 회귀 | PASS 147건(T-319 포함) | `related.log` |
| 회사 Windows·SSH·장비 인수 | NOT_RUN | — |

재현 및 재시험 명령은 다음과 같다.

```bash
.venv/bin/python -m pytest -q backend/gui_test/tests/test_module_selection.py -k registered_windows_module_selection
.venv/bin/python -m pytest -q backend/gui_test/tests/test_module_selection.py backend/gui_test/tests/test_module_analysis_retry.py backend/gui_test/tests/test_connector_freshness.py backend/gui_test/tests/test_live_view.py backend/gui_test/tests/test_board_connector.py tests/test_direct_connector_unit5_and_security.py::test_manager_catalog_falls_back_to_shared_tc_root_and_test_page_toggle
```

## 회사 전달본 검증

원본 수정 커밋 `6e65521219d8437d97df006f5e5366f823b23937`의 깨끗한 체크아웃에서 관련 시험 147건을 재실행했다. 패키지 안에서 T-319 세 사례를 다시 실행하고 전후 `verify --pristine` 및 이전 전달본 기준 `verify-evidence`를 통과했다. [복사 위치·release ID·해시](../../../deliveries/company-handoff-6e65521/00_START_HERE.md)와 [변경된 7개 경로](../../../deliveries/company-handoff-6e65521/MANIFEST_DELTA.tsv)를 제공한다. 로컬 로그는 `.local-reports/20261124-delivery-6e65521-bdzWd0/`에 있다.
