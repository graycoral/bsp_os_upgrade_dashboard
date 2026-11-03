# 2026-11-03 자동 이미지 퓨징·TC

상태: 로컬 구현·독립 리뷰·Windows 모의 검증 완료. Linux 전체 회귀/Windows 독립 패키지 CI 확인 중. 기준 main31ad210, feature/automatic-flash-test. RQ-47/D-48/T-131~136.

사용자 승인: 자동 퓨징·TC 구현과 요구사항 문서 갱신. 실장비 실행은 하지 않는다. 실제 배치·baud rate·준비 문구·fastboot serial은 미확인이다. 설정 예제는 비활성이며 실제 인수는 NOT_RUN이다.

새 Astra 세션 flash_astra_review에서 읽기 전용 구현 리뷰, 별도 GPT-6-sol 세션 flash_sol_tests에서 가짜 IO/임시 DB 시험을 진행한다. 주 작업자는 결함을 수정하고 결과를 검토한다. 과거 PASS를 이번 코드의 증거로 재사용하지 않는다.

## 최초 지적·수정

- REG-0026: Astra P1. FlashService.run의 Capture 초기화가 보호 영역 밖이고 예외 시 stop 반환값을 무시하여 살아 있는 자식을 종료 확인으로 처리할 수 있었다. 생성/수집/정리 전체를 추적하고 종료 불명 또는 실행 중 퓨징 예외는 UNKNOWN으로 유지한다. 별도 솔 회귀 시험과 최종 리뷰 결과는 아래에 추가한다.
- 새 시험의 tombstone 기대값 조정: 기존 ID에 지연 POST하면 fingerprint 불일치로409가 맞는 계약이다. 시험 작성 중 응답 기대를409/실행 없음으로 수정하며 제품 오류로 주장하지 않는다.

최종 실행 결과·코드 해시·검증 범위는 시험 완료 후 추가한다. 실장비/실제 배치/USB 인수 T-136, 기존 T-130은 NOT_RUN을 유지한다. 운영 baseline을 승격하지 않는다.


## 추가 검토와 수정

- 이미지 복사 전 stat뿐 아니라 복사 중 누적 바이트도 제한하고 일반 파일 여부를 확인한다. growing file로 용량 검사를 우회하지 못한다.
- 결과 적용 시 Linux 자원·Attempt·token 소유권을 대조하고 잘못된 lease는 UNKNOWN으로 유지한다.
- 진행 중 endpoint 설정 변경과 같은 URL의 다른 Windows runtime 재연결을 구분한다. 영속 runner_id를 요청·조회·결과와 tombstone에서 검사한다.
- REG-0027: 콘솔 read/command 초기화 경합으로 이전 프롬프트가 새 상태로 잘못 사용될 수 있어 같은 lock 및 OS 입력 큐 초기화를 추가했다. 명령/개행 및 오래된 프롬프트 회귀는 가짜 serial로 수행한다.
- REG-0028: 새 device_test 실행의 stage.result를 비워 과거 TC 결과와 혼동하지 않도록 했다. 이전 Attempt의 결과·automation 이력은 보존한다.
- 계획 확인 모달의 수동 전용 설명을 기본 수동/활성화된 자동 퓨징·TC 방식으로 갱신했다.
- standalone 패키지는 gui_test만 배포하므로 저장소 전용 manifest 생성기 시험은 루트 tests에 둔다. 해당 시험을 삭제하거나 전체에서 skip하지 않는다.

## 검증 환경·초기 실패 보존

Windows Python3.13.5/Node24.21/Edge, 임시 파일·가짜 콘솔·fastboot·배치 및 독립 DB만 사용했다. 실제 USB/COM/회사 배치/모델/BSP 작업은 실행하지 않았다.

초기 관련 회귀는148 PASS/3 FAIL이었다. tests/test_api.py의 두 시험은 POSIX 절대 경로(/fixture/nonexistent, /srv/custom bsp)를 가정하여 Windows에서 실패했다. 나머지 한 건은 긴 --basetemp 때문에 Windows 경로 한도를 넘었다. 짧은 새 임시 경로로 재실행하고 POSIX 두 시험은 Linux CI에서 검증한다. 최초 출력은 보존한다. Starlette httpx deprecation warning은 제품 실패와 구분한다.

문서 검사 최초 호출은 Windows 기본 cp949로 실패했다. -X utf8로 재실행하여 검사하며 제품 시험 PASS로 계산하지 않는다.


## 최종 로컬 결과

| 항목 | 결과 | 근거 |
|---|---|---|
| 새 Astra 읽기 전용 구현 리뷰 | APPROVED | [검토 및 실제 파일 해시](20261103-automatic-flash-test-evidence/astra-review.json); 주 작업자가10개 해시 일치 확인 |
| 별도 GPT-6-sol 관련 Python 회귀 | 163 PASS / 2 deselected / warning1 | [최종 원본](20261103-automatic-flash-test-evidence/python-final-package-safe.txt); 두 POSIX 경로 시험은 Linux에서 검증 |
| T-135 Edge 화면 | 1 PASS | [원본](20261103-automatic-flash-test-evidence/browser-T135-package-safe.txt), [화면](20261103-automatic-flash-test-evidence/T-135-browser.png); 단계/TC 수/접기/키보드/긴 로그 검증 |
| Dashboard·standalone UI 빌드 | PASS | [원본](20261103-automatic-flash-test-evidence/build-final-package-safe.txt) |
| 문서 검사 | PASS | [UTF-8 검사](20261103-automatic-flash-test-evidence/doc-validator-final.txt); 이 검사는 제품 통과가 아님 |
| 실제 배치·Linux 공유·COM·USB·보드 | NOT_RUN | T-130/T-136, 사용자 환경 인수 필요 |

시험 코드와 제품 기준은 [별도 시험자가 기록한 SHA256 목록](20261103-automatic-flash-test-evidence/source-hashes-final.csv)을 따른다. 최초 [148 PASS/3 FAIL](20261103-automatic-flash-test-evidence/python-regression.txt)과 [tombstone 시험 기대 수정](20261103-automatic-flash-test-evidence/flash-initial.txt)을 보존한다. 동일 Engine Attempt에서 실제 HTTP adapter/TestClient 경계를 거쳐 FakeIO 퓨징 결과가 반영되는 통합 시험, 재시도 시 이전 결과·automation 보존 시험이 포함된다. REG-0026~0028의 모의 회귀는 VERIFIED이며 실제 보드 복구 인수로 승격하지 않는다.
