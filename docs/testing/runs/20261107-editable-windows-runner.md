# RQ-61 편집 가능한 Windows Runner 검증 기록

최종 결과: 코드 `b42cacd1c110fd3ed0bd4898de51a3ccc3274b99`, 독립 리뷰 APPROVED, T-210~216 로컬 범위 PASS, 실제 회사 인수 T-217 NOT_RUN, 운영 baseline NONE. 최종 Runner ZIP은 28,345,689 bytes, SHA-256 `85cc8bb9889aea1bbed0d31e9cfcd17795c4e42b99944d4788b96ea89c350f6d`이다. 빌드 입력 ZIP은 29,103,279 bytes, SHA-256 `95779f087ce035a493c375470eeda602e17abd191fa5f9c463462e658ac803c6`이다. 외부 회사 전달 ZIP 해시는 순환을 피하기 위해 외부 `.zip.sha256`과 provenance에 기록한다.

독립 오프라인 빌드 종료 코드 0과 실제 ZIP smoke 종료 코드 0을 확인했다. help, imports, 실제 Host socket·인증·최종 lock (포트 54390), 수정 소스, 캐시 없는 재포장, 재포장 후 수정, 이동·수정·재포장 출처의 7개 검사가 PASS다. 보고서는 `C:/Temp/rq61-validation/20261107-final-unicode-smoke-report`, 메타데이터와 빌드 시험 로그는 `.local-reports/rq61-independent-20261107-unicodefix/`에 있다. 독립 빌드 시험 34 PASS는 앞선 207 PASS에 포함 범위가 겹치므로 합산하지 않는다. 고정 코드와 전달 소스 17개 파일 일치 확인은 `.local-reports/rq61-handoff-assembly/source-equivalence-unicode.json`이다. 아래 진행 상태는 당시 이력이다.

재현 명령은 저장소 루트에서 실행한 실제 명령이다. `C:/Temp/bsp-rq61-release`는 고정 커밋의 깨끗한 checkout, `C:/Temp/rq61-validation/20261107-150000-cache`는 전달 입력 ZIP을 구조 그대로 추출한 캐시다. `--basetemp`와 report 경로는 쓰기 가능한 새 경로로 바꿀 수 있다.

| 검증 | 명령 |
|---|---|
| 집중 회귀 | `.venv/Scripts/python.exe -m pytest tests/test_editable_runner_build.py tests/test_editable_runner_runtime.py tests/test_setup_active_endpoints.py tests/test_setup_runtime.py tests/test_windows_runner_bundle.py tests/test_setup_commands.py -q --basetemp=C:/Temp/rq61-validation/20261107-150000 -p no:cacheprovider` |
| backend | `.venv/Scripts/python.exe -m pytest backend/gui_test/tests -q --basetemp=C:/Temp/rq61-validation/20261107-150000-full -p no:cacheprovider` |
| 수정 빌드 시험 | `.venv/Scripts/python.exe -m pytest tests/test_editable_runner_build.py -q --basetemp=C:/Temp/rq61-validation/20261107-unicodefix -p no:cacheprovider` |
| 오프라인 빌드 | `C:/Temp/bsp-rq61-release/scripts/build-editable-runner.cmd -Offline -CachePath C:/Temp/rq61-validation/20261107-150000-cache -OutputPath C:/Users/grayc/work/dashboard/bsp_os_upgrade_dashboard/dist/editable-windows-runner/BSP-Windows-Runner-Editable.zip` |
| 실제 ZIP smoke | `.venv/Scripts/python.exe tests/editable_runner_smoke.py --zip C:/Users/grayc/work/dashboard/bsp_os_upgrade_dashboard/dist/editable-windows-runner/BSP-Windows-Runner-Editable.zip --report-dir C:/Temp/rq61-validation/20261107-final-unicode-smoke-report --actual-host` |

명령과 결과의 기계 판독 근거는 `.local-reports/rq61-independent-20261107-unicodefix/final-validation.json`이다.

2026-11-07. 원본 기준 `0178d045db16526560a155f05693c1f2dc0bbb47`; 산출물 해시 미정. 구현과 독립 리뷰 지적 수정 후 최종 독립 시험 진행 중이다. T-210~217은 최종 결과 기록 전 NOT_RUN이다. 실제 회사 SSH·COM·장비 인수 T-217은 별도다.

작성 중 repack의 MAX_PATH 실패를 수정했다. 작성자 pytest ACL 및 PowerShell fixture 오류는 시험 환경·fixture 오류로 제품 결과와 구분한다. 독립 리뷰에서 orphan byte-1 lock, PowerShell native 잘못된 PE 실행 파일의 거짓 종료 코드 0, doctor AUTH/TIMEOUT/CONNECT 분류, sidecar publish 실패와 rollback 실패가 이전 복구 백업을 삭제하는 문제를 발견해 수정했다. venv redirector의 부모 PID와 실제 Runner ancestry 차이는 시험에서 별도로 발견했다. 관련 실행 기록은 `.local-reports/rq61-review/`에 있다. 각 실패의 상세 증거와 최종 재시험 결과는 확정 후 보강한다. 기존 실패 기록을 삭제하지 않는다.

작성자 시험 146 PASS / 4 SKIP은 독립 최종 결과가 아니다. 빌드 입력 ZIP SHA-256 `95779f087ce035a493c375470eeda602e17abd191fa5f9c463462e658ac803c6`, 29,103,279 bytes, 34 entries; 독립 담당자가 새 캐시 추출과 오프라인 빌드를 진행 중이다.

고정 코드 커밋은 `edbd1ea12824aaef3c9c64128004cf8664b63779`이다. 독립 코드 리뷰는 수정 사항 재확인 후 **APPROVED**이며 리뷰 대상 9개 production 파일의 집계 SHA-256은 `f770c4bd9092a16b3ffc4d19b7ae2a9a77db300d52cbeb8744d94e2fe6765295`다. 근거는 `.local-reports/rq61-review/review-final.json`과 `production-sha256.json`이다. 독립 Luna 시험은 집중 회귀 207 PASS / 7 SKIP, 전체 backend 494 PASS / 28 warnings이며 각각 종료 코드 0이다. 로그는 `.local-reports/rq61-independent-20261107-150000/targeted.log`, `full.log`다. 새 캐시 오프라인 빌드도 종료 코드 0이다.

초기 실제 ZIP smoke는 help 종료 코드 0만 확인했고 import와 Host 시작 결과는 기록되지 않았다. 출력 수집이 소실되어 종료 상태와 원인을 확인하지 못했다. 고정 커밋으로 다시 빌드하고 동일 시험을 재실행 중이다. 후보 ZIP SHA-256 `d088dc7dc03d1bca4ea18267790a069d2d1e638e5276b0e1756e0593b0b08948`은 최종 배포 해시가 아니다. T-211·212·216 및 최종 산출물 판정은 실제 ZIP 증거를 기다린다.

초기 미완료 smoke는 import 시작부터 결과 수집까지 122초가 걸려 120초 child timeout 가능성이 높으나 traceback·종료 상태와 원인은 확정되지 않았다. CIM 확인에서 관련 Python/Host 프로세스는 남지 않았다.

`edbd1ea`에서 다시 빌드한 ZIP SHA-256 `3f15ff0691256e471e5dec4d882492b389bc37df45b1634ea2b6be362aa4dea1`의 실제 smoke는 Host socket·인증·최종 lock, help·import·수정 소스 반영은 PASS였으나 캐시 없는 재포장 시 한글 ZIP 파일명에 ASCII checksum sidecar를 쓰면서 `UnicodeEncodeError`로 종료 코드 1이었다. 이 실패 산출물은 전달하지 않는다. UTF-8 수정 커밋 `b42cacd1c110fd3ed0bd4898de51a3ccc3274b99`에 대해 독립 빌드 시험 34 PASS (2.58초), 독립 리뷰 APPROVED다. 최초 시험 명령은 basetemp 호출 문제로 종료 코드 4였으며 변경 없는 재실행이 PASS다. 근거 `.local-reports/rq61-independent-20261107-unicodefix`, `.local-reports/rq61-review/review-final-unicode.json`, `production-sha256-unicode.json`; production 집계 SHA-256 `5b2e7ce33111a892899902cb21348e4c584cc7e038406bc9f1c2833b9d5c62c1`. 나머지 8개 소스 해시는 변경되지 않았다. 새 커밋의 클린 빌드와 실제 ZIP 재시험은 위 최종 결과와 같이 PASS다.
