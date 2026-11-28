# 다중 플러그인과 작업별 Agent Monitor 검증

RQ-87 · T-324 · PORT-021. 기준 소스 `377832f`. 회사 Linux 계정 두 개, 실제 Windows SSH, 보드 인수는 NOT_RUN이다.

## 설계 독립 리뷰

새 Codex 리뷰 세션은 [설계](../../design/MULTI_PLUGIN_OWNERSHIP.md)를 Host, Monitor와 PORT-017·020에 대조해 CHANGES_REQUESTED로 판정했다. 작업별 멱등키와 충돌 정보 제한, 승인 목적지와 터널 세대, 작업용 Monitor의 서버 권한과 두 탭, Run 단위 인계와 기존 분석 lease 회수, 서비스 전용 principal 및 장비 경합을 보완한 뒤 같은 검토자가 APPROVED로 판정했다. Claude 실행 파일은 이 환경에서 찾지 못했다.

## 구현 및 재시험

Sol xhigh 세션이 Host·클라이언트·Monitor를 분담했다. 구현 기준 `20938ba`의 독립 코드 리뷰는 CHANGES_REQUESTED였다. 응답 유실 후 인계된 요청 정리, 승인된 Monitor 브라우저 리스너의 바인딩 보호, Windows에서 실행되는 입력의 승인 경계를 보완했다. 동일 계정의 프로젝트 표시와 다른 계정의 제한된 점유 표시도 설계에 명시했다.

| 범위 | 중간 실행에서 관찰한 결과 및 후속 검증 |
|---|---|
| 기존 DB | 초기 작업 트리에서 기존 schema_version 4 확인 3건이 실패했다. 기존 버전 값을 유지하고 공유 테이블의 버전을 독립적으로 관리한 뒤 같은 시험을 재실행했다. |
| 공유 CLI | 첫 모의 실행이 명령 프로필 검증에서 거절됐다. 실제 Python 실행 프로필과 Host 경로 계획을 사용하도록 고친 뒤 같은 프로젝트 2개 작업·다른 계정·정상 Run·scope 제한을 플러그인 subprocess에서 확인했다. |
| 웹 | 백그라운드 폴링 타이밍에 따라 첫 브라우저 검증이 실패했다. fixture 상태 게시 직후 화면을 갱신해 기본 선택을 검증하고, 실제로 열린 두 탭의 고정 및 권한 회수 표시를 확인했다. |
| 패키지 | 초기 운영 smoke의 macOS 임시 경로 별칭 때문에 준비 시간 초과가 발생했다. 운영 설치 방식과 같은 정규 경로로 구성한 후 복사본에서 기동·재사용·다른 Monitor ID 거절·작업용 리스너·정상 종료를 재시험했다. |
| macOS 전체 비교 | 개발 중 전체 실행은 2,457 PASS, 36 FAIL, 45 SKIP이었다. 실패 항목 재시험에서 7건이 통과했다. 남은 29개 시험 ID를 변경 전 `dc649ab`의 별도 작업 트리에서 같은 환경으로 실행해 29개 모두 실패함을 확인했다. Linux 프로세스 증거, 부팅 식별 및 로컬 Git 버전에 의존하는 시험을 포함한다. 원본 로그는 로컬의 `.local-reports/20261129-port021-all.pDiRNv/`, `.local-reports/port021-preflight/{baseline,current}-failed-retry.log`에 보관한다. |

독립 검토자가 `89bd8d7`에서 개인 모드의 과거 Run을 공유 작업에 인계한 뒤 재실행할 때 실행물 승인이 생략될 수 있음을 확인했다. `ccfe885`는 소유 작업과 실제 입력 해시를 함께 검사하며, 운영자가 보관된 과거 입력을 확인하는 `approve-run-input`을 제공한다. 독립 검토자는 인계만으로 재실행 권한이 생기지 않는지, 승인 후 재실행과 기존 공유 Run 재실행이 가능한지 코드·시험에 대조해 최종 **APPROVED**로 판정했다. 승인 전·후를 확인하는 Host 시험 12개도 로컬에서 통과했다.

전체 재실행은 2,478 PASS / 29 FAIL / 45 SKIP이었다. 실패한 29개 시험 ID는 위의 변경 전 비교 목록과 일치한다. 로그는 `.local-reports/20261129-port021-all.3ir6u0/pytest.log`에 있다. 실제 Windows 사용자 자격 저장소와 ACL, 서로 다른 Linux 계정과 OpenSSH 포워딩, 회사 훅 및 보드 TC 인수는 NOT_RUN이다.

## 최종 기능 검증

| 범위 | 명령 및 결과 |
|---|---|
| 업무 기능 T-324 | `bash scripts/test_multi_plugin_ownership.sh feature` — 실제 플러그인 subprocess·임시 Host·Monitor와 웹/Qt 계약 23 PASS. 로그 `.local-reports/20261129-multi-plugin.iqIG0L/ownership.log`. |
| 관련 Host 회귀 | 소유권, GUI Test 서비스, 과거 Run 복구, 분석/인계, 실제 승인 CLI를 함께 실행해 105 PASS. 로그 `.local-reports/20261129-host-enrollment-final/pytest.log`. |
| 개인 설치 호환 | `bash scripts/test_multi_plugin_ownership.sh regression` — 기존 직결, 복사형 CLI/서비스와 Monitor 회귀 202 PASS. 로그 `.local-reports/20261129-multi-plugin.GCYXqR/compatibility.log`. |
| Chromium | 단일 전체 실행에서 30 PASS / 1 FAIL. 기존 연결 알림 검사가 숨은 탭의 다음 폴링 응답을 받기 전에 5초가 지나는 현상이 `dc649ab`에서도 재현됐다. `b398081`은 실제 상태 응답 도착을 기다린 뒤 기존 화면 단언을 검사한다. 해당 사례와 개인/공유 Monitor 연계 3 PASS. 로그 `.local-reports/port021-preflight/browser-poll-sync.YDYjJd/run.log`. |
| 복사본 | `scripts/test_monitor_activation_package.py`가 개인 모드와 공유 Monitor의 기동, 설치 키, 재사용, 잘못된 대상 거절, Worker 미기동, 종료를 검사한다. 신형 소스 복사본과 호환 기준 `bf1f7d2`가 통과했다. 로그 `.local-reports/20261129-client-13/copied-activation.log`, `.local-reports/20261129-client-14/legacy-activation.log`. 실제 최종 전달 폴더의 해시와 검증 결과는 상위 전달 폴더 00_START_HERE.md에 기록한다. |
