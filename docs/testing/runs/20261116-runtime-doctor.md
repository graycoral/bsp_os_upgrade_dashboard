# 한 명령 runtime 진단

RQ-68 / T-254 / REG-0097. 기준 `bf6b734a8d080fdfe9d52e7a24d8c48f1556df41`에 루트 실행기와 runtime 진단을 보완했다.

## 문제와 변경

사용자는 회사 서버에서 INITIAL_RUNTIME_ADOPTION_BLOCKED와 HELD_RESERVATIONS를 확인했다. 추가 예약 정보를 얻기 위해 긴 Python 코드를 입력하게 한 절차를 수정했다. 이전 수동 명령은 실행 방식에 execution 필드를 사용했으며 실제 저장 필드 simulation으로 정정했다. 새 진단은 저장 형식을 직접 읽는다.

`bash run.sh doctor`가 Python 탐색·runtime 선택·기존 Worker/서비스 소유권 확인·DB 상태 요약을 수행한다. `run.sh --port 8765`의 최초 이관 보류 화면에도 같은 요약이 자동 표시된다. 별도 스크립트 파일을 추가하지 않고 기존 run.sh/manage.py/recovery.py로 연결했다.

출력은 형식·계약 문제, 미해결 코드, 실행 상태, 실제 예약 자원 수, 소유 세션 상태, mock/hardware 실행 방식, 종료 미확인 건수다. HELD_RESERVATIONS 항목 수와 실제 예약 수를 구분한다. 소유 세션 누락은 OWNER_MISSING, 읽을 수 없는 DB는 예약 상세 확인 불가로 표시한다. 상태 값은 정해진 이름으로 제한하고 작업 이름·경로·COM·토큰·로그 원문을 요약에서 제외한다.

진단은 일반 파일·전체 테이블의 해시를 생략한다. 실제 이관의 inspect-runtime 경로는 전체 revision을 계산한다. 이관·예약 해제는 기존 잠금·계약·실행 상태 확인과 정상 취소/종료 확인 절차를 따른다. 이번 변경은 진단 자동화이며 회사 예약 해제·이관 완료 여부는 미확인이다. DB schema 변경은 없다.

## 검증

원본 로그와 manifest는 `.local-reports/20261116-runtime-doctor/`에 로컬 전용으로 보관한다.

| 실행 | 결과 | 근거 |
|---|---|---|
| 기존 main의 최초 이관 보류 메시지 시험 | 예상 1 FAIL | `before-fix.log` |
| 초기 manager/recovery/lifecycle/delivery/setup 회귀 | 136 PASS / 7 SKIP | `tests.log` |
| 최종 격리 checkout 회귀 | 137 PASS / 8 플랫폼 SKIP | `final-tests.log` |
| 실제 `bash run.sh doctor --home <시험 home>` | PASS | `doctor-smoke.log`, 모의 PAUSED 예약 1개를 자동 요약 |
| `bash -n run.sh`, `git diff --check` | PASS | 로컬 명령 exit 0 |

최종 명령은 `python -m pytest tests/test_agent_monitor_manager.py tests/test_agent_monitor_recovery.py tests/test_agent_monitor_lifecycle.py tests/test_agent_monitor_delivery.py tests/test_setup_runtime.py -q`다. 원본 main의 격리 checkout에 이번 코드·시험 5개만 적용했다. 예약 여러 개/소유 세션 하나, 소유 세션 누락, 종료 미확인 시도, DB 읽기 오류, Worker 잠금, 다른 runtime 거부, 신규 설치 준비 없음, 사내 식별자 비노출, 진단의 파일·전체 DB 해시 생략을 검증했다. doctor에 필요한 Python이 없을 때는 안내 후 종료한다.

코드 manifest SHA-256 `5118c42b66cb690dd467e42a896c805436c3f5ac23bbe5e7b45f00e94537d2ea`. 시험 manifest SHA-256 `db3b55135f7b8887b5cb679188e2c826dfb835c512beaaa84ba5224fa649226c`. 회사 Linux의 실제 예약 복구 및 이관은 NOT_RUN이다.

수정 코드·시험 기준은 `aa25c1b17e0039ed6ddc9bb3c11c106022487d0f`다. 문서 검사 1701개 링크 PASS를 확인했다.
