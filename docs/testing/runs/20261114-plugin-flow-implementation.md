# 2026-11-14 플러그인 전체 흐름 보완

RQ-69/D-73/T-260~264/REG-0091. 기준 `5775661ddcf7b6f9020fdc9ee058b2a12098f819` 이후 작업 트리다. 기존 커넥터 화면 배치 수정은 보존하고 이번 구현과 구분한다. 새 EXE/ZIP, 실제 SSH/장비/모델 호출은 수행하지 않았다. 독립 [Astra/xhigh 리뷰](20261114-plugin-flow-audit.md)의 최초 CHANGES_REQUESTED와 후속 판정을 함께 확인한다.

## 수정

- 최초 연결: 플러그인의 명시 Linux 접속 정보+서비스 identity를 JSON으로 export하고 Windows 기존 실행기에서 import/파일 선택한다. 로컬 키·보드 설정 보존, 원자 저장/백업, 활성 Manager·진행/예약/UNKNOWN 차단.
- 준비: TC 명령 프로파일 CAS 저장/선택, Windows 이름별 플래싱 patch·실제 적용 revision·관측 조건 확인, 기존 로컬 프로파일 보존. fastboot 경로/장비 조회는 별도 읽기 인터페이스.
- 공통 제어: 각 요청의 서비스 식별 확인, standalone 저장 공간 scope, TC 소스/목록·텍스트 로그·완료 세션 영구 삭제 facade, 등록/콘솔 최신성 및 지연 콘솔 응답 거부.
- 분석: TC 실패와 별개로 플래싱/부팅의 batch·콘솔·입력 근거를 제한된 크기로 전달. 마스킹 후 문자열 자르기.
- BSP: 별도 명시 범위의 BspPluginClient가 기존 Engine API·운영 게이트·단일 Worker를 사용한다. GUI Test 단독 서버는 BSP 제어를 거부한다.
- 전달: 공개 API·PORT-007/009·회사 요청문·보드 커넥터 가이드·생성 패키지 INSTALL 안내 갱신.

DB 테이블 이전 없음. 기존 documents·Windows JSON에 부가 값이 저장된다. 수락된 Run과 실패/UNKNOWN 이력을 변경하지 않는다. 실제 영구 삭제나 cache 정리는 사용자 runtime에서 실행하지 않았다.

## 실행 기록

전체 출력은 `.local-reports/20261114-plugin-flow/`, `20261114-plugin-bootstrap/`, `20261114-plugin-profiles/`, `20261114-flow-audit/`에만 보관한다. 초기 실패와 수정 후 결과를 아래에 보존한다.

| 실행 | 결과 | 근거 |
|---|---|---|
| 삭제 API·기존 영구 삭제 회귀 | 9 PASS | `plugin-flow/deletion-01.log` |
| 초기 공통 제어/분석/BSP 집중 | 71 PASS / 1 FAIL | `plugin-flow/core-01.log`; BSP action 응답을 전체 snapshot으로 가정한 새 시험 수정 |
| 공통 제어·분석·BSP·공통 설정 재시험 | 37 PASS | `plugin-flow/core-02.log` |
| 마스킹 후 truncation 추가 회귀 | 23 PASS | `plugin-flow/core-03.log` |
| 첫 광역 Python | 951 PASS / 5 FAIL | `plugin-flow/broad-01.log`; Git shim 환경 1건, 신규 identity/Manager 경계에 맞지 않은 기존 fixture 4건. 기록 보존 후 재시험 |
| 수정 후 광역 Python | 973 PASS | `plugin-flow/broad-02.log`; 실제 /usr/bin/git 경로 사용 |
| 공통 설정 Chromium | 6 PASS | `plugin-flow/browser-01.log` |
| 문서 검사 | PASS | `plugin-flow/docs-02.log`; 최초 results/catalog 불일치는 신규 T-260~264 결과 행 추가 후 수정 |
| native endpoint까지 확대한 검사 | 1148 PASS / 19 SKIP / 18 FAIL | `plugin-flow/final-01.log`; 실패는 모두 변경하지 않은 test_setup_active_endpoints.py의 macOS 미지원 process identity 경로. Windows/Linux 실제 실행 시험을 Mac 성공으로 대체하지 않음 |
| 공개 프로파일 최종 집중 | 168 PASS | `plugin-profiles/profiles-production-mount-final.log`; 실제 router만 사용 |
| Astra/xhigh 최종 독립 회귀 | 144 PASS / APPROVED | `flow-audit/final-independent-regression-02.log`; 미해결 P1/P2 없음, 기존 UI 배치 WIP 제외 |
| 최종 관련 광역 회귀 | **1145 PASS / 19 SKIP**, 종료 0 | `plugin-flow/final-02.log`; 위 native endpoint 파일 제외, 제품/시험의 조건을 약화하지 않음 |

T-264 실제 회사 Windows 11/Python3.13·SSH·COM/fastboot·회사 BAT/TC·모델·ACON 인수는 NOT_RUN이다. 로컬 mock/API 시험을 회사 인수로 표시하지 않는다.

## 원문 명령과 검증 범위

최종 관련 광역 명령은 아래와 같다. `PATH`는 이 환경의 Git shim 대신 실제 Git을 사용하고 Qt는 offscreen으로 실행한다.

```bash
PATH=/usr/bin:/bin:$PATH QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest backend/gui_test/tests tests/test_api.py tests/test_engine.py tests/test_bsp_plugin_client.py tests/test_agent_monitor_delivery.py tests/test_agent_monitor_lifecycle.py tests/test_agent_monitor_recovery.py tests/test_agent_monitor_manager.py tests/test_board_connector_launcher.py tests/test_setup_runtime.py tests/test_setup_flashing_discovery.py tests/test_setup_commands.py -q
```

브라우저는 고정 로컬 Node/Chromium과 임시 runtime에서 `scripts/test_dashboard_browser.py shared-control.spec.ts --reporter=line`을 실행했다. 사용자 서비스·보드에 연결하지 않았다. 새 frontend 변경은 이번 구현에 없으므로 기존 UI WIP의 별도 검증과 합산하지 않는다.

확장 검사에서 `tests/test_setup_active_endpoints.py`는 Windows/Linux의 실제 프로세스 생성 시각·부모 관계를 요구한다. 기존 `execution/launch.py::process_identity`는 Windows API와 Linux `/proc`만 지원해 macOS에서 `None`을 반환했다. 해당 18개 실패(3개 child-launch 실패 포함)의 원인을 원문 로그에 보존하며, 무관한 제품 코드를 변경하거나 가짜 identity로 시험을 통과시키지 않았다. Windows/Linux 실행 환경에서 재시험해야 한다.

## 최종 기준

관련 코드 검증은 T-260~263 PASS, 독립 리뷰 APPROVED다. 모든 플랫폼의 전체 시험 통과나 회사 인수를 뜻하지 않는다. 최종 `.local-reports/20261114-plugin-flow/source-manifest.json`에는 변경/추가 Python 코드·시험 35개를 고정했고 최종 시험 후 바이트 일치를 확인했다.

- 제품 SHA256: `777129c129915232ddf64f8441f89583902f41b8fcd2c6a5cad5f9bd4089edd7`
- 시험 SHA256: `1cfec95dca295288f9b9860573eb0164a7d19929ee7bb668e3eea1b5b989a45f`
- 현재 로컬 작업 트리. 커밋·푸시와 새 EXE/ZIP 생성은 하지 않았다.
