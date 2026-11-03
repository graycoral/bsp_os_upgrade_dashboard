# Test 현황 실제 연결 보기 검증

RQ-49 / D-50 / T-142~143. 기준 main d8e11b3. 실행기 설치가 불가능한 상태에서도 실제 연결 작업공간의 미설정/미연결 상태를 확인하도록 한다. Mock 데이터와 실제 데이터는 별도 저장소이며 설정된 manager/worker는 재사용한다. 실제 회사 SSH/TC/COM/장비 호출은 하지 않는다.

새 Astra 최초 리뷰는 CHANGES_REQUESTED: 모든 action에 연결을 요구해 오프라인 pause/cancel/제어권 변경까지 막는 REG-0031을 발견했다. 실행을 가능하게 하는 resume/recover만 연결 검사하도록 고쳤다. 독립 Astra 재검토 APPROVED, 메모리 API 시험에서 로컬 조작200·resume/recover503을 확인했다. 별도 GPT-6-sol이 제품 시험을 담당한다. 이를 실제 장비 인수나 Claude 검토로 표현하지 않는다.

로컬 시험의 고정 코드·시험 기준은 `07002bd0d02db8ebb1c7eb056096741695e1780e`이다. T-130/T-136/T-141 실환경 시험은 NOT_RUN 유지, 정상 제품 기준 NONE을 변경하지 않는다.

초기 독립 로컬 시험: GUI Python181 PASS(신규6 포함), 두 UI 빌드 PASS, Chrome 신규 브라우저1 PASS. 추가로 실행한 backend API 시험은 Windows에서 Linux 절대 경로를 사용한2건 FAIL(107 PASS)을 보존한다. 통합 worker E2E는 Windows fcntl 부재로 BLOCKED이며 Linux CI로 확인한다. 이는 실제 장비 실패가 아니다.

주 작업자의 결과 검토에서 브라우저 시험이 전환/재로드 뒤 수동으로 Test 현황을 다시 열어 REG-0032를 가린 점을 발견했다. 유효한 guiExecution URL이면 통합 앱이 해당 화면으로 시작하도록 수정했고 Astra가 재승인했다. 시험도 추가 탐색 없이 전환/재로드를 확인하도록 강화했다. 이전 통과와 최종 재시험을 구분한다.

최종 로컬 재시험: 수정된 Dashboard 빌드 PASS, 전환/재로드/복귀 뒤 추가 메뉴 클릭 없는 Chrome 시험1 PASS. GUI Python181 PASS와 단독 UI 빌드 PASS는 동일 관련 코드에 대해 확인했다. 주 작업자가 화면 캡처·시험 코드·보고서를 검토했다.

[독립 시험 보고](20261103-live-test-view-evidence/verification.md), [화면 증거](20261103-live-test-view-evidence/live-view.png), [검증 파일 해시](20261103-live-test-view-evidence/sha256.txt), [Astra 검토 요약](20261103-live-test-view-evidence/astra-review.txt). Linux/Windows CI 결과는 릴리스 GPT-6-sol 세션에서 후속 기록한다.
