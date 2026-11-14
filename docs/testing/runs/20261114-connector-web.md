# 보드 커넥터 웹 기본 화면·CMD 진단

2026-11-14 · RQ-63~66 / T-247~250 / REG-0086~0087. HEAD `e4f53ca1ec288feb3eb1b9ccff8335a398ad321c` 위 미커밋 변경이다. 다른 세션의 RQ-67 공통 제어/Agent Monitor 작업과 분리된 변경 범위이며 기존 사용자 변경을 보존했다. 새 커밋·게시·배포 ZIP은 만들지 않았다.

## 구현과 보존 범위

- 기본 CMD/모듈 진입은 브라우저다. Qt는 명시 `--ui qt`로만 선택한다. core-only 준비와 별도 환경 fingerprint, Qt 미import 기본 진입, 기존 환경 보존·오프라인 재사용을 확인한다.
- 기존 Windows Manager에 전용 웹 경로를 연결했다. 단기 일회성 티켓·instance별 HttpOnly/SameSite 쿠키·정확한 origin/port·CSRF·본문 한도·CSP/no-store를 사용하며 기존 비브라우저 IPC를 완화하지 않았다.
- 상태/보드/제어권·PuTTY·로그4종·경로·Windows 설정·서버 공통 설정을 기존 코어에 연결했다. 설정 저장/연결의 잠금·revision 충돌과 미지값/RTS/DTR·보드 초안 보존, 실제 수집 시각 기반 stale 차단을 추가했다.
- 표준 Windows 파일 대화상자 helper와 전체경로 직접 입력을 제공한다. 모의 시험은 선택/취소 반환·실패 경계를 검사하며 실제 대화상자 인수는 NOT_RUN이다.
- CMD의 BC 진단/작동 Python override/실행별 로컬 로그/무실행 진단, 자산 누락과 구버전 Manager/브라우저 오류 안내를 추가했다. 회사 CMD 원인은 미확정이다.
- 물리 COM 소유·lease·시리얼 버퍼·RTS/DTR·TC·플래싱·Run/UNKNOWN 판정 코어는 새로 구현하지 않았다. 탭 종료/재열기는 연결과 TC를 종료하지 않는다. 원격 Windows 자동 기동·Z: 로컬 캐시 배포는 미구현 범위다.

## 시험 결과

원본 로그/스크린샷/manifest는 `.local-reports/20261114-connector-web-review/`에만 있으며 Git에 포함하지 않는다.

| 실행 | 결과 | 근거 |
|---|---|---|
| 변경 전 기준 회귀 | 76 PASS / Windows 5 SKIP | baseline-unrestricted.log. 앞선 baseline.log의 8 FAIL은 샌드박스 소켓 거부이며 이력을 보존 |
| 최초 구현 API/설치/Qt/패키징 | 1 FAIL / 93 PASS / 10 SKIP | implementation-1.log. 본문 한도 시험이 JSON Content-Type 없이 보내 출처 검사가 먼저 403을 반환. 유효한 JSON 요청의 64 KiB 초과를 검사하도록 시험 요청을 수정 |
| 재시험 | 94 PASS / 10 SKIP | implementation-2.log |
| 영향 범위 회귀 | 233 PASS / 18 SKIP | regression-233-pass.log |
| Astra 전 영향 범위 회귀 | 236 PASS / 18 SKIP | regression-236-pass.log. launcher/web/기존 connector·multiplexer/shared connector/layout/package/editable bundle/setup runtime |
| 첫 브라우저 준비 | FAIL | browser-1-startup-failed.log. 시험 import를 저장소의 실제 Playwright 설치 위치로 수정. 추가 패키지 설치 없음 |
| 최초 실제 Chromium 흐름 | 4 PASS / 1 FAIL | browser-2-action-race-failed.log 및 browser-1794633997188963000/. 연속 조작의 두 번째 요청 누락 REG-0087 |
| 수정 후 브라우저 | 7 PASS | browser-3-seven-pass.log. 원래 제어 차단 시험을 유지하고 공통 설정·문자열/경로 시험 추가 |
| Astra 전 Chromium | 7 PASS | browser-4-seven-pass.log, browser-1794634590397031000/. 1360px/390px 화면/키보드·편집 초안/보드 복원·연결 재열기·제어 차단·로그·공통 설정 override/서버 경로·문자열 안전 표시 |
| Astra 독립 재현/회귀 | 2 FAIL 재현 → 신규 web 34 PASS | astra-repros-2.log, astra-regressions-before.log 및 astra-regressions-after.log. 기존 탭 CSRF 무효화와 비활성 보드 RTS/DTR 소실을 재현 후 수정 |
| 동시 설치 접점 변경의 fixture 미반영 | 7 FAIL / 231 PASS / 18 SKIP | regression-public-tools-fixture-failed.log. 별도 작업이 추가한 prepare_public_tools/BC-56을 launcher unit fixture에서 모의 처리하지 않아 실패. 제품 bootstrap을 제거하지 않고 외부 설치 경계를 fixture에 반영 |
| 네 지적 수정 후 영향 범위 회귀 | 238 PASS / 18 SKIP | regression-238-pass-before-tabs.log. 외부 설치 fixture 경계 반영 후 재시험 |
| 네 지적 수정 후 Chromium | 10 PASS | browser-6-ten-pass-before-tabs.log. 동일 Manager 두 탭의 초안/저장, local/shared 지연 저장의 입력·폴더 선택 잠금, pending status timeout/stale·복구 |
| 동시 변경 통합 후 관련 회귀 | **241 PASS / 20 SKIP** | regression-1.log. 뒤이어 추가된 필수 도구 준비 접점의 모의 시험/Windows SKIP 포함 |
| 최신 통합 Chromium | **12 PASS** | browser-1.log. 보드 설정/로그 탭·방향키/초점·ARIA 관계와 여러 숨긴 COM 오류 순차 표시/수정, 별도 저장 공간 UI의 모의 접점 시험 포함 |
| 실제 Windows CMD/DPAPI/PowerShell/파일 대화상자 | **NOT_RUN** | 관련 20 SKIP 중 CMD/필수 도구 Windows 직접 시험 포함. 자동 Windows 시험은 소스에 추가했으나 이 세션에서 Windows CI를 실행하지 않음 |
| 회사 Z:/UNC·실제 COM/USB/SSH·회사 TC/PuTTY | **NOT_RUN** | T-250 및 기존 T-234/239 |

회귀 명령:

```sh
QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q -rs \
  tests/test_board_connector_launcher.py backend/gui_test/tests/test_connector_web.py \
  backend/gui_test/tests/test_board_connector.py backend/gui_test/tests/test_serial_multiplexer.py \
  backend/gui_test/tests/test_shared_connector_control.py tests/test_gui_test_layout.py \
  backend/gui_test/tests/test_package.py tests/test_editable_runner_build.py tests/test_setup_runtime.py
.venv/bin/python scripts/test_connector_browser.py
```

로컬 시험은 설치된 Node 22/Chromium 실행 파일 경로를 환경으로 전달했다. 모의 TCP/Chromium 실행은 샌드박스 소켓 제한을 해제한 허가된 환경에서 수행했다. 제품 설정·회사 접속·실장비 실행은 하지 않았다. Python/API 시험과 source/wheel/bundle 자산 검사 통과는 새 Windows 배포본 기동 성공을 뜻하지 않는다.

## 리뷰와 다음 확인

설계의 최종 기준은 웹 기본 전환이다. [Astra xhigh 리뷰 기록](20261114-connector-web-review.md)에서 설계와 실제 코드 검토를 구분한다. 사용량 제한 오류 후 해제 시각이 지나 재시도한 구현 리뷰에서 네 건의 CHANGES_REQUESTED를 받았으며 아래처럼 수정했다. 최종적으로 같은 Astra xhigh가 **웹 기본 전환과 네 지적의 수정 범위를 APPROVED**했다. 검토자는 새 web 단위 34건을 독립 PASS하고 회귀 238 PASS/Windows 18 SKIP·Chromium 10 PASS 로그를 확인했다.

1. 비활성 보드의 통신 설정: serial_settings 전체 기존 map을 보존하고 활성 patch만 합친다. 보드 2→1 저장→설정 재로드→2 복원 후 RTS/DTR을 확인한다.
2. 같은 Manager의 새 탭: 유효한 현재 세션/CSRF를 재사용하고 티켓만 일회 소비한다. 기존 탭 초안을 유지하며 저장할 수 있다.
3. 지연 저장 응답: 제출한 local/shared 폼 입력을 응답 대기 중 잠그고 서버 폴더 선택 버튼까지 함께 제한한다. 명시 저장 응답이 새 입력을 덮어쓰는 경로를 차단한다.
4. 상태 응답 대기: status 5초/일반 15초/picker 185초 요청 제한과 독립적인 15초 heartbeat 만료 감시를 둔다. 응답이 대기 중이어도 오래된 연결 표시와 제어 버튼을 제한하며 새 정상 수신으로 복구한다.

별도 공개 필수 도구 bootstrap의 자동 설치 동작 자체는 이번 GUI 리뷰/모의 시험 인수가 아니다. 실제 Windows 시험에서 회사 설치 정책·로그와 함께 확인한다. 그 제품 코드는 보존했으며 launcher unit 시험은 외부 설치를 모의 처리한다.

### 같은 작업 폴더의 후속 변경 통합

최종 manifest 비교에서 다른 작업 세션의 BC-29 공개 Python 준비·보드/로그 subtab·저장 공간 UI 변경이 같은 파일에 추가된 것을 확인했다. 기존 변경을 덮어쓰지 않고 현재 코드로 재검증했다. Astra는 탭 delta를 별도로 검토해 중복 invalid 처리와 tab↔panel ARIA 연결 누락 두 P2를 지적했다. 처리기를 첫 invalid 하나로 통합하고 안정 id/aria-controls/aria-labelledby를 연결했으며, COM 두 개가 동시에 비어 있을 때 첫 보드부터 차례대로 보이도록 시험했다. 이 두 수정의 코드·시험 delta도 APPROVED를 받았다. 저장 공간 실제 정리·BC-29 설치와 실제 Windows 인수는 이 승인 범위에 포함되지 않는다.

사용자는 [보드 커넥터 가이드](../../gui_test/TEST_BOARD_CONNECTOR_GUI.md)를, 회사 담당자는 [PORT-009](../../porting/PORT-009.md)를 진입점으로 사용한다. 회사 확인은 CMD의 BC 단계/선택 Python 로그, Windows 네이티브 파일 선택, 구버전 Manager 안전 교체, 실제 장비 제어/로그·창 종료 후 작업 유지 순으로 진행한다.

소스와 시험의 파일별 SHA256 및 aggregate는 로컬 `source-manifest.json`에 고정한다. 커밋 전 상태이므로 기존 PORT 고정 커밋에 이번 변경이 포함됐다고 표시하지 않는다. DB 이전은 없으며 복원 시 기존 home/DB/환경을 지우지 않는다. 최신 Chromium 근거 폴더는 `browser-1794635827114016000/`다. 문서 검증도 수행하며 관련 로그는 docs-*.log에 보존한다.

현재 code aggregate `33a0e96d7258bcb8d7814bfcb6af83bd6a9a3afb9d445bfd85abd6d648c57b19`, test aggregate `62197d54d22f6a8c8a9ac0a6b4b805cac3d554d0bc7e056aeac6f7579209c4ac`. 앞선 manifest는 source-manifest-before-astra-fixes.json 및 source-manifest-before-concurrent-tabs.json에 보존한다.

문서 검사 이력: docs-2.log는 1,442 링크/RQ-67/T-250 기준 PASS였다. 마지막 docs-final-2.log는 병행 작업에서 추가된 RQ-68의 T-251~256 결과 행이 아직 없어 `results/catalog mismatch`로 FAIL이다(1,468 링크, 요구사항 68개, TC 256개). 이번 T-247~250 결과 행은 모두 등록돼 있으며 해당 여섯 시험의 결과를 추정해 추가하지 않았다. 이번 변경 대상의 `git diff --check`는 PASS다. 전체 문서 검사는 RQ-68 작업의 실제 결과 등록 후 다시 수행해야 하며 과거 PASS를 현재 전체 PASS로 재사용하지 않는다.
