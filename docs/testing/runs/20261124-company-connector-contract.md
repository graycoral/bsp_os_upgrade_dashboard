# 2026-11-24 회사 플러그인 직결 인수 계약

RQ-84 · T-311~318 · REG-0121. 기준 커밋 `018637c6c2ea8751e6bd4ac4094d4babac5aa380`과 기존 작업 트리에서 설계와 구현을 각각 새 세션으로 진행했다. 설계 산출물은 [인수 설계](../../design/COMPANY_CONNECTOR_DELIVERY_CONTRACT.md), 회사에서 실행할 명령과 DB 이전·복원은 [PORT-017](../../porting/PORT-017.md)에 있다.

- 구현 전 회귀 기준은 `python -m pytest -q tests/test_direct_connector_unit3.py tests/test_direct_connector_unit4.py tests/test_plugin_module_catalog.py tests/test_plugin_delivery.py` 44 PASS다.
- 기존 두 회사 전달본 `8abe926 → 14634ed`에 release-evidence와 verify-evidence를 실행했다. 파일 37개의 전후 SHA-256 비교표가 이전 MANIFEST_DELTA.tsv와 바이트 단위로 일치했다.
- 회사 활성화 등록·실제 Windows 장비·실제 별도 릴리스 채널 검증은 T-318 NOT_RUN이다. 이 기록은 모의 플래싱과 실제 장비 퓨징을 구별한다.
- 원본 로그는 로컬 전용 `.local-reports/company-delivery-contract-XzeHzv/`에 있다.

| 실행 | 결과 |
|---|---|
| 기존 직결 Host·CLI·전달·모듈과 신규 계약 세 파일 | 77 PASS (기존 44 + 신규 33). 구현 세션 로그 `.local-reports/company-contract-integration-YfMXud/pytest.log`. |
| 주변 회귀 | 137 PASS. `tests/test_direct_connector_unit*.py`, `tests/test_agent_monitor_{delivery,manager}.py`, `tests/test_bsp_plugin_client.py`, `tests/test_plugin_{module_catalog,runtime,delivery}.py`. `related.log`. 위 실행과 중복됨. |
| 실제 export 후 패키지 내부에서 신규 시험 | 처음 30 PASS / 1 FAIL. 모의 Windows 설정에 실행용 Python 명령 프로파일을 채우지 않아 Host가 COMMAND_NOT_ALLOWED로 거부했다. 유효한 fixture를 준비한 뒤 33 PASS, 실행 전후 verify --pristine PASS. `package-suite.log`, `package-suite-2.log`. |
| 플래시 프로파일 HTTP 계약 | 모의 Host가 반환한 등록 프로파일을 기존 클라이언트가 비활성으로 읽는 실패를 재현했다. 실제 응답 필드 매핑을 수정하고 등록 프로파일과 이미지 동기화·준비를 검증했다. `.local-reports/connector-flash-receipt-before-7pkkUd/pytest.log`와 `.local-reports/connector-replay-final-yExYdp/pytest.log`. |

시험 환경은 macOS arm64, Python 3.11.7, loopback HTTP·임시 SQLite·모의 보드다. FastAPI TestClient의 httpx 사용 중단 예정 경고 1건이 있었다. 결과 CSV는 변경 파일 및 관련 시험 파일들의 작업 트리 지문을 사용한다.

## 고정 커밋과 전달 검증

구현 커밋은 `9f911235d98df0120593d3028a27fcfdee5cead3`이다. 독립 체크아웃에서 커밋 대상 Git 트리가 일치함을 확인하고 회귀·신규 시험을 함께 실행했다. 첫 실행 168 PASS / 1 SKIP은 복사본 API 기동 시험의 사전 빌드 UI가 없었기 때문이다. 이전 고정 납품본의 UI 입력이 동일함을 확인하고 검증된 두 UI 번들을 복사한 뒤 해당 시험을 재실행해 1 PASS를 확인했다. 합계 169개 고유 시험 PASS다. 같은 트리의 문서 검사와 PORT-017 JSON 예시·패키지 링크 검사도 통과했다. 원본 로그는 `clean-pytest.log`, `ui-case.log`, `clean-docs.log`, `clean-package.log`다.

같은 커밋의 clean source와 위 UI에서 전체 패키지를 생성하고 pristine 검증 및 14634ed 대비 변경 35개 파일의 증거를 독립 해시로 대조했다. 실제 파일과 고정 digest는 [회사 전달 기록](../../../deliveries/company-handoff-9f91123/00_START_HERE.md)에 있다.
