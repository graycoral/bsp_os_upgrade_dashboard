# 2026-11-17 · 보드 커넥터 정리·강제 종료 Astra 독립 리뷰

- review_id: 20261117-connector-cleanup-review
- reviewer/tool/model: 별도 협업 세션 `/root/astra_review`, `gpt-6-astra`.
- reviewed_revision/scope: `1da1da2173c84689662de669d6a95fb8775c7037` 위 격리 후보. 제품·시험 manifest 22개 항목(삭제2 포함), SHA256 `685e5cd7d416a9511d525760294c84266273eeabe35756a6723fcf02e18b825b`. 명칭·설치/스크립트·패키징·명시적 로컬 강제 종료·소비 시험을 검토했다. 별도 제한시간/telemetry 작업은 제외했다.
- status: **APPROVED — 코드·로컬 모의 검증 범위**.
- final findings: 추가 P1/P2 없음. 실제 OS/회사 인수 승인은 아님.
- tests_actually_run: 최종 격리 후보에서 `tests/test_force_stop.py tests/test_board_connector_launcher.py`를 별도 실행해 **51 PASS / 12 SKIP**. 제품·시험 22개 SHA 대조 불일치0. 제품 파일 수정·실제 서비스 종료 없음.
- unverified_integrations: T-272 실제 Linux pidfd·Windows handles/Toolhelp/CMD/COM·회사 장비 강제 종료·새 배포 ZIP은 **NOT_RUN**.
- follow_up_owner: Codex. 사용자 승인에 따라 이번 변경만 커밋/main 병합하고 회사 인수와 구분한다.

## 검토 이력과 수정 확인

1. 초기 독립 fake 시험 12 PASS, CHANGES_REQUESTED. 자식 PID snapshot 후 세대 재사용, post-exit 발견 target 누락, CLI 시작 barrier 경합을 지적했다.
2. pin 이후 PPID 재확인·발견 즉시 checkpoint·공통 connector-start.lock을 확인했다. 독립 fake17 PASS. Windows 종료/Wait 전에 명령이 중단될 경우 post-scan 증거가 남지 않는 추가 P2로 CHANGES_REQUESTED를 유지했다.
3. Terminate 전에 durable phase/termination_started를 기록하고 해당 부모 Wait·post-scan·checkpoint 후만 completed로 표시하도록 보완했다. 중단 후 미완료 부모가 사라지면 tree_unverified/pending을 유지한다. KeyboardInterrupt·late child 회귀를 포함해 보완을 확인하고 최종 APPROVED했다.

원시 대화/시험 출력은 로컬 도구 세션에 남으며 이 문서는 실제 받은 판정의 요약이다. 구현자 광역 회귀와 독립 51건은 [실행 기록](20261117-connector-cleanup.md)에서 구분한다. REG-0103의 첫 실패/CHANGES_REQUESTED는 지우지 않았다.

## 최신 main 병합 delta 독립 리뷰

- status: **APPROVED**.
- scope: main `12a82a6`와 검증 feature의 병합 후보. 최초 제품 manifest와 달라진 `scripts/setup_runtime.py`, `tests/test_windows_runner_bundle.py`, `tests/test_runner_ports.py` 3파일을 검토했다.
- findings: 추가 P1/P2 없음. automatic prepare_locked와 force pending/start barrier·SSH identity 저장 및 그 이후 admission 해제를 함께 확인했다. 포트 fixture의 사전 proxy 지정은 기존 bytes/포트/터널/신호 검증을 약화하지 않는다.
- independent tests: 제한 밖 재실행 **75 PASS / 3 SKIP**, force_stop/windows_runner_bundle/auto_serial_proxy/automatic_serial. sandbox 첫6 FAIL/14 ERROR는 loopback 제한으로 분리했다. 제품 파일·서비스/장비 수정·종료 없음.
- final integrated product/test SHA256: `dc469cf70b014af159672cba9e8108ca476c4c97a5ef8727d7e0d647c049af6e`.
- native/company acceptance: T-272 **NOT_RUN**. 최종 문서의 고정 커밋 pin은 부모가 검증 후 기록한다.

최종 코드·시험 고정 커밋: `af269448dfbdbc426d0403738e82453118cf8638`. 제품/시험 manifest와 검증한 통합 bytes를 유지하며 문서 pin은 별도 후속이다.

## BAT·서버 포트 최종 추가 리뷰

status: **APPROVED — 정적 코드·Mac 모의 검증 범위**. 별도 Astra 세션은 BAT→CMD 인용/인자/ERRORLEVEL, 포트/force 병용 거부, 최신 Manager 저장 경로와 exporter의 BAT bytes·CMD 포함을 확인했다. 독립 force_stop/launcher/delivery/server_port **90 PASS / 21 SKIP**, 추가 P1/P2 없음. 실제 Windows T-279·네이티브/회사 T-272는 NOT_RUN이며 제품/서비스/장비 변경·종료는 수행하지 않았다. 최종 제품/시험 25항목 SHA256 `c29c13af23043b85e82b8b66df90d816d4b4759846073c205a7ec0c117a3bf28`.

BAT·서버 포트 최종 코드/시험 pin: `9450e9f30e95e2c956f9890b3512ba2b80e5f933`. 최종 manifest25항목의 bytes를 유지한다.

## 게시 전 시험 이식성 delta

Astra 별도 세션 **APPROVED**, 독립 **18 PASS**. 테스트 fixture의 synthetic SIGKILL/SIGCONT와 공통 LaunchLock은 OS 의존 경계만 대체하며 기대값·검증·skip을 약화하지 않는다. runtime/다른 WIP 수정·실제 서비스 종료 없음. 최종 공개 코드·시험 pin: `f30f57263992ce87c58bef181b6bf13456ba0f5d`. 전체 게시 후보 재시험623 PASS/33 SKIP/기존 Mac 제약1 DESELECTED, 실제 Windows CI와 회사 인수는 별도다.


## REG-0111 · 실제 Windows 인용 재시험

Astra 별도 세션은 바깥 quote caret escape 두 줄·기존 home ampersand 시험 강화를 검토하고 독립37 PASS/20 SKIP를 확인했다. 실제 Windows CI 조건부 코드 APPROVED 판정 후 [job134056779481](https://github.com/graycoral/bsp_os_upgrade_dashboard/actions/runs/44088379448/job/134056779481)에서 launcher 실패0/16개 경로·인자·exit 매트릭스 PASS를 확인했다. 전체 CI가 green이라는 의미는 아니다. 기존 Linux7·Windows10 및 standalone demo 실패는 실행 기록에 보존한다. 최종 코드 pin은 `b6f1c30fb0ba8a3a13d1b16544fd8c0c0254a0f7`이며 회사/네이티브 강제 종료는 NOT_RUN이다.
