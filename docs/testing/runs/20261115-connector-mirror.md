# 2026-11-15 · 보드 커넥터 미러

RQ-70/D-75/T-267~269/REG-0093. 사용자 승인: 구현·문서·커밋·푸시. 기준 `6866b410c35b59efe6454a1a8557e5041ca2af2f`에 별도 세션의 게시된 간략 화면 변경을 보존했다. 코드·시험 게시 기준 `c4d7664653a2ae884736e9b9824908f899b771b0`.

Windows에서 수동 실행한 Manager를 Agent Monitor의 보드 커넥터 탭에 연결했다. 상태·로그·공개 설정을 게시하고 중앙의 멱등 명령을 한 번 claim해 실제 결과를 반환한다. 물리 설정은 기존 TC/예약/UNKNOWN 게이트를 통과한 뒤 재연결·Host 해시 확인으로 적용한다. 과거 상태·결과 불명·동시 편집과 숨긴 observer/비활성 보드 설정을 보존한다. 새 TC Worker·새 의존성·EXE·ZIP·Windows 자동 시작은 추가하지 않았다.

## 현재 검증

| 검증 | 명령·범위 | 결과 |
|---|---|---|
| Python | `python -m pytest -q tests/test_connector_mirror_client.py tests/test_connector_mirror.py tests/test_connector_mirror_http.py backend/gui_test/tests tests/test_bsp_plugin_client.py` | 924 PASS, exit 0 |
| 브라우저 | `python scripts/test_dashboard_browser.py connector-mirror.spec.ts settings-sync.spec.ts --reporter=line` | 27 PASS(미러 14 + 기존 설정 13), exit 0 |
| 빌드 | `bash scripts/build-ui.sh` | Agent Monitor/standalone 모두 PASS, exit 0 |
| 문서·diff | `python docs/testing/validate_docs.py`; `git diff --check` | 최종 검사 기록은 아래 게시 확인 절 |
| 독립 검토 | Astra xhigh 코드·실패 경로·회귀 | [별도 리뷰](20261115-connector-mirror-review.md) |
| 회사 인수 | Windows 11/Python 3.13·실제 Linux SSH·UART·PuTTY·장시간 TC | NOT_RUN(T-269) |

환경: macOS, 기존 Python 3.11 venv, Node 22.23.4, 설치된 Playwright Chromium. Python 3.13 문법/런처 지원을 변경하지 않았으나 이번 작업에서 실제 Windows 3.13 실행을 대신 검증했다고 쓰지 않는다. 테스트는 임시 runtime/모의 HTTP·프로세스만 사용했다.

원본 로그는 격리 worktree의 `.local-reports/20261115-mirror-final/{python.log,browser.log,build.log,manifest.txt}`에 있으며 로컬 전용·미커밋이다. 테스트/제품 stdout의 상세 경고는 원본에 보존한다. 소스 fingerprint `1c11f72355746a5f8d6c0a12265032ad5bc031d8f1591a1f4d11e0217c485d09`, 시험 fingerprint `fff7b60eed92a1ea279cbac1f836395e88d2f2dd63b13f9030e4fb8ba2ea780f`.

## 발견·수정·재시험

- 독립 리뷰에서 공개 observer 편집의 숨긴 마스킹 값 유실, pending 플래싱 유실, 최신 revision을 붙인 stale 초안 저장, 긴 로그 전송 한도, 최신 오류/명령 누락, 재연결 probe 경합, 오래된 적용 근거, inactive RX 복원 및 실제 잘림 flag와 UI 불일치를 발견했다. 현재 회귀에 해당 경로를 추가했다.
- `.local-reports/20261115-mirror-owner-01`의 기존 모의 Manager 속성 누락 1 FAIL/68 PASS는 호환 기본값으로 수정했다. 후속 owner-02 102 PASS.
- owner-03와 regression-01의 JSON 직렬화 시험 1 FAIL은 request 인자의 Path까지 비교한 시험 오류다. 비교 범위를 실제 전송 본문으로 고쳤다. 광역 초기 893 PASS/1 FAIL 기록을 지우지 않았고 현재 광역 924 PASS다.
- channel-01은 시스템 Python에 pytest가 없어 시작하지 못했다. channel-04의 새 콘솔 freshness 조건과 과거 fixture, channel-05의 연결 전 API callback 실패는 각각 보완하고 channel-08 76 PASS, abandon-02 105 PASS를 확인했다.
- UI 초기 실행 환경/접근성 label·시험 대기 실패는 원본 로그에 보존했다. `connector-mirror-ui-20261115-*`의 후속 통합 27 PASS와 최종 최신 27 PASS를 별도로 확인했다.

## 전달·복구

[최신 요청서](../../agents/BSP_UPGRADE_PLUGIN_REQUEST.md)의 플러그인/Agent Monitor/Windows 항목을 함께 전달한다. API·필드·동작은 [미러 계약](../../design/BOARD_CONNECTOR_MIRROR.md), 적용 파일·DB 추가·백업/복구는 [PORT-009](../../porting/PORT-009.md)를 따른다. 기존 실패 이력·UNKNOWN·runtime은 보존한다. 회사 분석기·ACON 어댑터 및 실제 장비 인수는 별도다.

## 게시 확인

문서 검사 PASS(상대 링크 1,651개, RQ 70개, 시험 269개), `git diff --check` PASS. 독립 Astra xhigh APPROVED·199 PASS. 검증한 22개 제품/시험 파일로 만든 Git tree `7c1eebb1b4c1bc60cede99b3b72bc0800ef25c2d`와 GitHub API 생성 tree가 일치한다. 코드 커밋은 `c4d7664653a2ae884736e9b9824908f899b771b0`이며 전달 문서가 이 기준을 고정한다. terminal HTTPS push는 자격 증명 없음으로 실패하여 연결된 GitHub 도구와 expected main SHA를 사용한다. 원래 작업 폴더의 별도 timeout 수정/runtime은 게시 대상에서 제외하고 보존한다.
