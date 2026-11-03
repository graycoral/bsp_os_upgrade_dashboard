# 2026-11-03 확정 TC 명령과 접히는 비용 상세

기준 main `1d849ea3567baec5484a36ba190ef063b86efaa6`, 작업 브랜치 feature/confirmed-tc-commands. RQ-46/T-127/T-129 및 RQ-42/T-114. 사용자 확인 Single `python3 tc1.py -p COM7`, Dual `python3 tc_2.py -n n295_sadk -n2 n296_sadk`를 반영한다. Windows 신규 프로파일 기본값, 선택 보드 node 필드와 노드쌍 치환, 고정 실행 파일 python/python3 별칭을 추가했다. 기존 COM 프로파일/Mock/node 없는 연결의 직렬화는 보존한다. DB 스키마 변경 없음. node를 추가한 연결 프로파일은 과거 실행기에서 미지원이므로 새 Run을 구버전으로 재개하지 않는다.

Run과 TC별 토큰·비용 상세는 기본 접힘이며 진행률 아래에 반복 포함 완료 N/M회와 간략 비용을 표시한다. 완료는 PASS/FAIL 판정 횟수이고, 미집계·부분 집계·실제0을 구분한다. 비용은 모델 보고값을 합산하며 가격을 추정하지 않는다.

## 독립 리뷰와 수정 이력

새 gpt-6-astra `/root/commands_astra_review` 읽기 전용 리뷰는 최초 CHANGES_REQUESTED였다. REG-0022: Windows Host는 python3를 허용했지만 Manager.preflight의 기존 python-only 검사가 새 기본 프로파일을 거부했다. 주 작업자가 shared validate_windows_command를 Manager/Host 양쪽에 적용하고 실제 Manager→Worker→가짜 Windows Host 경로로 Single/Dual 양쪽의 명령·완료 결과·snapshot을 검사하는 회귀를 추가했다. 최종 코드 리뷰 APPROVED. 문서에 남았던 실행 호스트/플래그 미정 문구도 확정 명령으로 수정했다. reviewer는 제품 시험/수정을 수행하지 않았다.

## 별도 테스트

새 gpt-6-sol `/root/commands_sol_tests`가 코드 수정 없이 시험한다. 초기 GUI Python148 PASS는 Manager 누락 수정 전 결과이므로 최종 결과로 재사용하지 않는다. 수정 후 GUI Python149 PASS(exit0,21.61초), Windows Python3.13.5, 가짜 COM·argparse TC. 최초/재시험 로그와 source manifest를 별도 보존한다. 최초148 PASS가 누락된 통합 경계를 증명하지 못했던 점도 유지한다.

GUI-UI-16은 기본 명령 저장과 요청 node 값을, GUI-UI-17은 비용 합계/부분 미집계/0/미집계, Run·TC 상세 접기·키보드·좁은 화면을 검증한다. GUI-UI-10은 반복 완료6/6회 요약을 검증한다. 두 UI 빌드 PASS, 단독 브라우저17 PASS(exit0, skipped0/unexpected0/flaky0). 통합 브라우저 로컬 실행은 Windows에서 backend.worker의 fcntl import 실패로 제품 시험 시작 전 BLOCKED다. Linux CI 결과를 추가 확인한다.

실제 Linux/회사 TC/노드 접속/물리 COM/모델 호출은 하지 않는다. T-130 NOT_RUN과 운영 baseline을 유지한다. 실제 비용 측정은 모의 UI 시험과 별개다.


증거: [수정 전 Python](20261103-confirmed-commands-costs-evidence/initial-python-run.json), [수정 후 Python](20261103-confirmed-commands-costs-evidence/python-run.json), [소스 해시](20261103-confirmed-commands-costs-evidence/python-source-manifest-after.json), [두 UI 빌드](20261103-confirmed-commands-costs-evidence/build-run.json), [UI 소스 해시](20261103-confirmed-commands-costs-evidence/build-source-manifest-after.json), [브라우저17 JSON](20261103-confirmed-commands-costs-evidence/browser-browser-results.json), [통합 로컬 BLOCKED](20261103-confirmed-commands-costs-evidence/integrated-blocked-run.json), [worker 오류](20261103-confirmed-commands-costs-evidence/integrated-worker.log), [좁은 화면](20261103-confirmed-commands-costs-evidence/usage-mobile.png). 같은 디렉터리에 원본 로그/전후 manifest를 보존한다. 주 작업자가 시험 후 해시와 현재 소스 일치를 확인했다.

Astra 최종 코드·문서 리뷰 APPROVED, 차단 지적 없음. 별도 GPT-6-sol 문서 검사 exit0/PASS: 상대 링크445개·요구사항46개·시험130개·오류0. 출력은 같은 evidence 디렉터리의 `doc-validation.json`에 보존한다. 주 작업자가 비용 상세 기본 접힘과 좁은 화면 캡처를 확인했다.

증거 분류 정정: `integrated-blocked-browser-results.json`은 시험 wrapper가 복사한 이전 단독17 결과와 SHA256이 동일한 잔존 파일이다. GPT-6-sol이 embedded startTime(05:09:22 UTC)이 통합 시도(05:10:14 UTC) 이전임을 확인했다. 통합 결과 증거로 사용하지 않으며 통합 로컬 결과는 시작 전 BLOCKED다. 이 파일은 복사 경위 추적용으로만 보존한다.


## 최종 CI와 게시

별도 GPT-6-sol이 정확한 head `ecc5fd5355f68393a5d553a2b680a5df9856f03d`의 pull_request workflow/job/log를 확인하고 주 작업자가 [CI 증거](20261103-confirmed-commands-costs-evidence/ci.json)를 검토했다. [회귀 CI](https://github.com/graycoral/bsp_os_upgrade_dashboard/actions/runs/41582491879)와 [Windows 독립 빌드 CI](https://github.com/graycoral/bsp_os_upgrade_dashboard/actions/runs/41582491867)가 모두 SUCCESS다.

- Linux Python3.12: 전체366 PASS(Starlette 경고1, skip0), 통합 브라우저22 PASS, 단독 브라우저17 PASS, 모의 Dashboard 시나리오7 PASS.
- Windows Python3.12: GUI149 PASS(동일 경고1, skip0), 모의 시나리오5 및 wheel 설치/서버 확인 PASS.
- PowerShell5.1/7: 독립 빌드, 오프라인 ZIP 설치/확인, 원본·설치본 모의 시나리오 각각5 PASS.

로컬 Windows 통합시험 BLOCKED를 삭제하지 않고 Linux CI 통합22 PASS로 해당 코드의 통합 회귀를 검증했다. 실제 회사 환경 인수는 여전히 NOT_RUN이다.

[PR #7](https://github.com/graycoral/bsp_os_upgrade_dashboard/pull/7)을 main `0f71a1fe0988a4b84e16771337bc27c6306649cc`로 머지했다. 후속 문서 변경은 증거 정정/최종 CI/기존 Dual 폴더 분류 안내뿐이며 제품 코드는 검증된 ecc5fd5와 동일하다. 운영 baseline은 갱신하지 않는다.

최종 게시 문서 검사도 별도 GPT-6-sol에서 PASS(exit0, 상대 링크446개, 오류0). 같은 evidence 디렉터리의 `final-doc-validation.json`에 보존한다.
