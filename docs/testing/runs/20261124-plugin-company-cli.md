# 회사 CLI 후속 인수 · T-320

RQ-85 · REG-0123. 회사가 검토한 소스는 `9f91123`, 수정 전 로컬 HEAD는 `a64d6d2`다. macOS arm64, Python 3.11.7, 임시 SQLite·모의 Windows Host·복사한 패키지·임시 OpenSSH 서명키로 확인했다. 원본 로그 디렉터리는 로컬 전용 `.local-reports/20261124-plugin-strict-watch-UJombW/`다.

| 시험 | 결과와 범위 |
|---|---|
| 최초 재현 | `red.log`에 인자·감시 신규 시험 10건 FAIL. 약어, 명령 뒤 전역 인자, 환경 준비 전 거부 및 Windows 읽기 전용 옵션을 재현했다. |
| 제한망 감시 | `--read-only --no-provision`으로 임시 서버의 연결과 Runner ID 변경을 관찰했다. 모든 Windows 요청이 GET이었다. venv가 없으면 종료 6, 관리형 venv가 있으면 준비 단계 없이 재사용했다. |
| 퓨징·프로젝트 | 준비 시 BAT와 이미지의 실제 SHA-256·보드 대조, BAT 원본 삭제 뒤 같은 출력, 변경된 확인 정보에 대한 제출 거부를 검사했다. 프로젝트명에 공백·특수문자가 있는 사례, 무라벨 이력, 최신 1건 필터를 포함했다. |
| 계약·배포 | 파서와 JSON의 옵션 대조, 제외형 export와 원본 지침 보존, pristine 검증, 서명·다른 서명자·변조된 변경표·변조된 증거를 시험했다. |
| 중간 실행 | `final-regression.log`의 한 사례는 로컬 Git 루트 조회를 외부 설치로 간주한 시험의 오판이었다. 회사 확인 결과에 따라 외부 설치 금지와 사내 GET 검증을 유지했다. `all-contracts.log`의 변경표 단언은 실행 도중 개정한 릴리스별 형식과 달라 재검증했다. |
| 실제 회사 Linux·Windows/SSH, 보드 퓨징, 운영 서명키·독립 채널 | NOT_RUN |

모의 Host 퓨징 시험이 명시적인 프로파일을 제공하도록 보완한 뒤 재전송 시험 8건이 통과했다 (`replay-confirmed.log`). 작업 트리에서 관련 CLI·커넥터·모듈·재전송·패키지 회귀 131건이 통과했다 (`working-final.log`). 불완전한 관리 환경 사례 추가 후 감시·인자 시험 32건이 통과했다 (`watch-final.log`).

```bash
python -B -m pytest -q tests/test_connector_observation.py tests/test_plugin_delivery.py tests/test_plugin_module_catalog.py tests/test_direct_connector_unit{1,2,3,4}.py tests/test_direct_connector_unit5_and_security.py tests/test_company_connector_delivery.py tests/test_connector_run_replay.py tests/test_plugin_runtime.py
```

### 고정 원본과 회사 복사본

원본 `7691c0e679b4afdd5cb25e91a6e6824b0b7631b7`의 별도 체크아웃에서 위 회귀 131건 PASS (`clean-source.log`). 지침 제외형 패키지를 임시 폴더에 복사해 `test_company_connector_delivery.py`, `test_connector_run_replay.py`, `test_connector_observation.py`를 다시 실행해 48건 PASS (`clean-package.log`). 두 실행에서 FastAPI TestClient의 httpx 사용 중단 예정 경고 1건이 발생했다.

[회사 전달본](../../../deliveries/company-handoff-7691c0e/00_START_HERE.md)의 파일 531개를 manifest로 검증했다. Git 인덱스에서 복구한 두 패키지와 동작 변경표의 독립 SHA-256 대조가 통과했다 (`index-copies-verified.log`). 같은 릴리스 증거에 임시 Ed25519 시험키로 서명하고 원본 체크아웃의 검증기로 확인했다 (`detached-fixture-verify.log`). 운영키 서명과 회사 실기 인수는 NOT_RUN이다.
