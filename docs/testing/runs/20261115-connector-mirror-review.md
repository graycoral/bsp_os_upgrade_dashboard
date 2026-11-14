# 보드 커넥터 미러 독립 코드 리뷰

2026-11-15 · RQ-70 / D-75 · T-267~269 · REG-0093

## 판정과 기준

**APPROVED — 로컬 구현·모의 검증 범위.** 최종 검토 범위에 미해결 P1/P2 없음. 실제 Windows Manager·SSH·COM·PuTTY·장비·회사 플러그인 인수 T-269는 **NOT_RUN**이다. 이 판정은 실제 장비 운영이나 배포 인수를 대신하지 않는다.

사용자가 요청한 Astra 독립 리뷰로 수행했다. 구현 담당과 분리해 코드를 읽고 결함을 전달했으며, 검토자는 제품 코드나 시험 코드를 수정하지 않았다. 이 리뷰 문서만 작성했다. Claude 검토 완료를 의미하지 않는다.

- 작업트리: `/Users/younghokim/dashboard/.worktrees/connector-mirror-20261115`
- 기준 커밋: `6866b410c35b59efe6454a1a8557e5041ca2af2f`와 이번 미커밋 변경. 원래 변경이 남아 있는 작업트리는 수정하지 않았다.
- 최종 검토 파일 22개의 SHA-256 목록: `.local-reports/20261115-mirror-astra/final-02/source-sha256.txt`
- 목록 파일 SHA-256: `8838686296048aee12091ec6b9230511fd0c769677b8a2501920e99e0af3c119`
- 최종 시험 전후 검토 파일 변경 없음. 이후 제품 코드·시험 변경에는 해당 변경의 추가 검토가 필요하다.
- 공개 고정 커밋은 게시 후 기능 PORT와 구현 실행 기록에서 별도로 고정한다. 미커밋 검토를 게시 검증으로 표시하지 않는다.

읽은 기준은 `AGENTS.md`, `CLAUDE.md`, `portable-feature/SKILL.md`, 문서 지도·현재 상태, `BOARD_CONNECTOR_CONTRACT.md`, `PLUGIN_CONTROL_API.md`, 새 `BOARD_CONNECTOR_MIRROR.md`, 개발 로그 처리 규칙이다.

## 검토 범위

`connector/mirror.py`, `mirror_client.py`, API·registry·shared settings·Manager·Windows 설정 연결과 full/standalone HTTP 경계를 검토했다. 공유 `ConnectorMirror.tsx`, Dashboard 호스트 폴링·live 범위, PluginClient와 새 단위·HTTP·브라우저 시험도 대조했다.

기존 Manager·Host만 장비를 소유하며, 새 명령 채널이 TC 배정이나 Windows 자동 시작을 추가하지 않는 것을 확인했다. 다음 경로를 집중 검토했다.

- runner·Manager 세션·설정/전송 세대 고정, 등록·콘솔·미러 상태의 freshness.
- 원자적 command 생성·claim, 동일 key 재요청, 만료·순서 역전·응답 유실·재시작과 실제 receipt만으로 완료 확정.
- 중앙 설정 CAS와 편집 시작 시 Windows profile 기준, 적용 전 검증·TC/예약/UNKNOWN 거부·안전 종료·재연결·Host의 실제 설정 해시.
- 비공개 observer 설정·비활성 보드·pending 플래싱 설정 보존, 전송 전 전체 JSON 크기 제한.
- non-browser 상태/claim/receipt, standalone CSRF와 정확한 settings/control 범위, full Dashboard 경계, 기존 runtime/package pin.
- UNKNOWN은 재실행하지 않고 새 Manager 세션·최신 유휴 Host·반환된 입력 소유·CAS를 확인한 명시 요청만 ABANDONED로 기록. 이후 실제 receipt가 도착하면 원래 claim을 검증해 결과와 확인 이력을 보존.

## 발견과 수정 확인

초기 판정은 **CHANGES_REQUESTED**였다. 아래 발견과 중간 실패를 지우지 않고 최종 재검증 결과를 함께 남긴다.

| ID | 심각도 | 재현 조건·영향 | 최종 확인 |
|---|---|---|---|
| MR-01 | P1 | 공개 profile을 전체 설정으로 다시 저장하면 숨긴 `redact_values`와 observer 확장값이 삭제됨. 무관한 보드명 수정 후 비밀 마스킹이 사라질 수 있음 | 실제 `public_profile → Settings.validate`로 초기 재현. owner의 nested 보존, editable key만 전송, effective 설정 snapshot과 회귀 확인 |
| MR-02 | P2 | dirty draft를 보존하면서 최신 poll의 중앙 revision으로 저장해 다른 편집을 덮어씀 | draft revision·Windows profile revision 고정, 충돌 시 초안 보존과 재조회 조건 확인 |
| MR-03 | P2 | 보드 편집 저장 시 중앙 pending 플래싱 설정을 빠뜨려 요청 전체에서 삭제 | 기존 pending 설정에 editable key만 반영하는 경로와 브라우저 회귀 확인 |
| MR-04 | P2 | Windows TC 출력 한 건과 envelope가 standalone 64 KiB 한도를 초과해 미러 게시·명령 수신 중단 | 전송 전 UTF-8/ASCII JSON 60,000바이트 예산, tail·board 식별 유지·잘림 전달 회귀 확인 |
| MR-05 | P2 | 오류는 최초 100개만 표시하고 명령 목록은 최신순 배열의 뒤 12개를 표시해 최신 결과 누락. FAILED의 실제 message도 표시하지 않음 | 최신 오류 window, 명령 앞 12개, 실제 result code/message와 회귀 확인 |
| MR-06 | P2 | 이전 APPLIED를 그대로 믿으면 Windows 설정 drift 후에도 적용 성공으로 판단. 보완 중에는 TC busy만으로 기존 적용 근거를 취소하는 상태회귀가 있었음 | 실제 저장 snapshot·Host 해시 대조, drift만 BLOCKED, 이미 적용된 동일 설정은 TC 실행 중 보존하는 회귀 확인 |
| MR-07 | P2 | 긴 적용 잠금이 heartbeat를 막거나 재연결 probe와 heartbeat가 등록·cursor를 경합할 수 있음 | 적용 중 flag·짧은 control lock·별도 probe 직렬화, 적용 중 로컬 저장 차단과 모의 회귀 확인 |
| MR-08 | P2 | Windows에서 축소한 보드를 Dashboard에서 복원하면 COM만 돌아오고 inactive RX observer가 복원되지 않음 | owner에서 기존 inactive observer와 비공개 값 복원, 암묵적으로 변경한 필드도 Host 증거에 포함하는 회귀 확인 |
| MR-09 | P2 | UI가 실행별 `logs_truncated`를 검사하지만 실제 계약은 projection 최상위 필드여서 잘림 경고 누락 | 실제 계약 shape로 UI 조건과 브라우저 fixture 수정 확인 |

UNKNOWN 복구는 결과를 추정해 성공·실패 처리하거나 원래 명령을 재실행하지 않도록 별도 검토했다. 같은 Manager 세션, 오래된 상태, 실행·예약·UNKNOWN·PuTTY 소유, 잘못된 CAS와 scope는 거부하는 시험을 확인했다.

## 독립 검증

아래 원본 로그와 해시 목록은 모두 로컬 전용이며 Git에 포함하지 않는다.

| 실행 | 결과 | 근거 |
|---|---|---|
| 초기 결함 재현 | 확인, exit 0 | `.local-reports/20261115-mirror-astra/initial-reproductions.log`: observer 비공개 값 삭제 및 TC 출력 envelope 65,629바이트 확인 |
| 작업 중 신규 미러 3개 시험 파일 | 88 PASS / 1 FAIL | `.local-reports/20261115-mirror-astra/independent-01/pytest.log`: 테스트가 request 인자의 Path까지 JSON 직렬화한 TypeError. 실제 APPLIED assertion 이후의 시험 오류였으며 payload만 검사하도록 수정 |
| 첫 코드 동결 독립 회귀 | 198 PASS, exit 0 | `.local-reports/20261115-mirror-astra/final-01/pytest.log`. 이후 MR-08/09 추가 발견으로 최종 승인 보류 |
| 최종 수정 후 독립 회귀 | **199 PASS**, exit 0, 9.10초 | `.local-reports/20261115-mirror-astra/final-02/pytest.log`, `exit_code`, `source-sha256.txt` |
| 최종 변경 공백 검사 | PASS | `git diff --check` |

최종 독립 실행 명령:

```bash
/Users/younghokim/dashboard/bsp_os_upgrade_dashboard/.venv/bin/python -m pytest -q \
  tests/test_connector_mirror.py \
  tests/test_connector_mirror_client.py \
  tests/test_connector_mirror_http.py \
  backend/gui_test/tests/test_shared_connector_control.py \
  backend/gui_test/tests/test_board_connector.py \
  backend/gui_test/tests/test_connector_web.py \
  backend/gui_test/tests/test_tokenless_connections.py \
  backend/gui_test/tests/test_serial_multiplexer.py
```

현재 의존성의 Starlette/httpx deprecation warning 1건은 시험 실패가 아니다. 의존성을 바꾸거나 시험을 약화시키지 않았다. 브라우저 시험 코드와 구현 담당의 Chromium 실행 근거도 확인했으나 위 독립 199건은 Python 회귀이며, Chromium을 독립 재실행한 건수로 합산하지 않는다. 전체 Python·UI 빌드·최종 Chromium 결과는 [구현 실행 기록](20261115-connector-mirror.md)을 따른다.

## 남은 범위

Windows 프로세스 identity·LaunchLock·PuTTY 창 수명·SSH 터널 복구·실제 COM RX/TC 배타의 운영 인수는 모의 시험으로 대체하지 않는다. 회사 Plugin/ACON 소스와 실행 환경이 없으므로 현지 UI·권한·설치 연결도 별도 검증이다. 전송 로그는 제한된 tail이며 전체 실행 근거는 기존 실행 로그 경로를 사용한다. UNKNOWN의 명시적 확인은 이전 명령의 실제 성공·실패 증거가 아니다.
