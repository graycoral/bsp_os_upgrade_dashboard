# TC 루트 위임 실행 및 모의 ADB 검증

RQ-78/81 · T-321 · REG-0139. 원본 기준 `ba31de7aff550a220d890b1725a56645c9e47b97` 위 미커밋 작업본. macOS 로컬 TestClient, 임시 Host·SQLite·실제 자식 Python 및 모의 ADB 전송기를 사용했다. 모의 장치는 복사한 fixture를 로컬 sh에서 실행한다. 실제 USB, Windows ADB, 회사 CLI, 장비와 dmesg 전송은 NOT_RUN이다.

- 결함 재현. `tests/test_connector_run_replay.py`의 목록 전송 실패, 미선택 파일 디코딩, 미설정 루트 세 사례가 수정 전 모두 실패했다. 경로 실행 최초 사례도 미지원 인자로 실패했다.
- Python 회귀. `pytest -q`로 `tests/test_connector_run_replay.py`, `test_direct_connector_unit3.py`, `test_direct_connector_unit4.py`, `test_direct_connector_unit5_and_security.py`, `test_company_connector_delivery.py`, `test_connector_observation.py`, `backend/gui_test/tests/{test_source_snapshots,test_sources,test_source_transport}.py`를 실행했다. 관련 회귀 148 PASS. 저장한 공통 루트와 ADB 서버 준비를 포함한 최종 진입점 4파일 재시험 58 PASS. POSIX ADB 모의를 사용하는 최종 replay 파일 19 PASS. Windows 네이티브 ADB 실행은 별도 인수 항목이다. 경로 실행은 요청에 TC 배열 없이 세 폴더를 처리했고 A/B COM 인자, ADB 시리얼 고정, push·remote shell·정리, 종료 0과 명시 결과, 실패 중지, 원격 종료 불명, 재접수를 확인했다. 초기에 CLI 계약의 옵션 누락과 시험의 목록 응답 타입 오해가 각각 실패했으며 계약과 단언을 수정했다.
- 실제 export한 참조 CLI로 루트만 지정해 prepare/send한 후 같은 Run을 다시 조회하는 단독 시험 1 PASS. Qt offscreen 실행 목록 단독 시험 1 PASS. Chrome에서 카탈로그 미수신 중 Run 순서와 상태 표시 1 PASS.
- 명시적 전체 목록 요청에서 임시 파일 2,001개를 탐색했다. 모의 Windows 전송 시간 초과에도 재탐색 0회, Linux 조회 2,001개, Windows 표시 데이터 974개·523,941바이트였고 로컬 합계는 0.254초였다. 실제 현장 소요시간은 미측정이다.
- 전체 로그는 로컬 전용 `.local-reports/20261128-selected-tc/` 아래에 있다. 최초 실패 `red.log`, `path-red.log`, 중간 실패 `host-regression.log`, `adb-results.log`, 후속 `verified.log`, `adb-final.log`, `replay-final.log`, `path-entrypoints-final.log`, `package-path.log`, `qt.log`, `browser-focused.log`, `large-list.log`를 보존했다. 브라우저는 최초 npx 탐색 실패 후 설치된 Node와 Chrome으로 재실행했다. 전체 커넥터 웹 29건 중 25 PASS, 4 FAIL이다. 경로 실행 표시는 PASS이며 실패 4건은 기존 T-308 찾아보기 안내의 동일 사례다. 전체 결과는 `browser-retry.log`에 보존했다.

변경 위치와 적용·복구는 [PORT-013](../../porting/PORT-013.md)과 [운영 안내](../../gui_test/BOARD_CONNECTOR_EXECUTION.md#tc-루트-실행과-adb)를 따른다. 미배포 로컬 검증이며 독립 리뷰는 NOT_REVIEWED다. 이후 진행한 dmesg 50줄 전달은 [후속 실행 기록](20261128-failure-evidence.md)을 따른다.

## ADB 모드와 실행 직전 확인

RQ-78/81 · T-321 · REG-0139 후속. 준비 확인을 생략한 원래 코드에서 오프라인 후 복구·인증 미완료·지속 오프라인·셸 무응답을 주입한 4건이 모두 실패했다. 수정 후 Windows 커넥터는 시리얼과 셸 응답을 확인하고 나서 TC를 전송한다. 보드에서 ADB를 활성화하는 실제 명령과 출력은 [현장 재확인 표](../../gui_test/BOARD_CONNECTOR_EXECUTION.md#보드-adb-모드-진입-절차--현장-재확인-필요)에 남겼다.

별도 Codex 세션이 준비·전송 경로를 읽고 상태 문자열 오인, 마지막 준비 조회와 취소의 경합, 전송 직후 원격 실행 전 경계 누락을 보고했다. 시리얼 이름과 ADB 진단을 구분하고 취소·기한·콘솔 증거를 원격 실행 직전에 다시 검사하도록 수정했다. 독립 세션의 수정본 재검토 결과는 이 ADB 변경 범위에 한해 APPROVED다. 테스트 중 진단문 판정 시험의 자식 프로세스 기동이 모의 제한 0.4초를 초과한 2건을 기록했고, 해당 판정 시험은 실제 형식의 stderr와 종료 코드를 직접 주입하도록 변경했다. 전송·셸 통합 시험은 모의 ADB 자식 프로세스를 그대로 사용한다. 실패와 재시험 원본은 로컬 전용 `.local-reports/20261128-adb-ready/`에 있다. 실제 Windows·보드 UART·USB는 NOT_RUN이다.

최종 회귀는 `tests/test_connector_run_replay.py`, `tests/test_direct_connector_unit3.py`, `tests/test_company_connector_delivery.py`를 함께 실행해 50 PASS였다. 문서 검사와 `git diff --check`도 통과했다.
