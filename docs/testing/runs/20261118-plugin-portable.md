# 2026-11-18 · 플러그인 소유 보드 커넥터·공유 설정

RQ-74/D-80/T-282~286. 기준 `a0b53cd4813e95b6d39f7d0ad02c0e5a13f2f6fc`, 격리 worktree `plugin-portable-runtime-20261117`. 제품·회사 인수를 구분한다. 코드/설정/실행 경계·명령/파일·이전/복원은 [PORT-011](../../porting/PORT-011.md)을 따른다. 실제 회사 Git 삭제/이식·Windows/SSH/장비 실행은 하지 않았다.

## 리뷰와 수정

사용자 지정 gpt-6-astra / high 별도 세션 `/root/plugin_portable_astra_review`. 설계 리뷰 CHANGES_REQUESTED: 공통 감시/초안·intent를 회사 구현으로 넘긴 점, GUI/CLI artifact 혼동, bootstrap 반복 import, 관리 서비스 재사용·copied closure, 설정 파일 DB 단일 원본과 양방향 conflict/응답 유실·checkpoint 복구를 보완했다.

초기 코드 리뷰 CHANGES_REQUESTED: 실제 /runs summary 분류, 조회가 선택을 바꾼 문제, draft expected_revision 우회, preview 입력 변경 무시, connector_apply terminal 및 응답 유실 처리, 원본 source connect export를 수정했다. 시험을 약화하거나 과거 결과를 삭제하지 않는다. 최종 별도 Astra high 코드·계약 리뷰는 **APPROVED**다. 남은 P1/P2 없음. 검토자는 시험을 직접 실행하지 않았으며 아래 시험은 구현 세션의 실제 실행이다.

## 실행

로그는 `.local-reports/20261118-plugin-portable/`의 로컬 전용 파일이며 Git에 포함하지 않는다. 첫 runtime 시험 9 PASS(`runtime-1.log`), 독립 복사·실제 API·bootstrap/미러 포함 81 PASS(`core-1.log`). 확장 회귀·두 UI build·용어/문서 검사는 진행 중이다. 실제 회사 T-286은 NOT_RUN이다.


추가 리뷰 CHANGES_REQUESTED 이력: 실제 ConsoleHub에 없는 fresh 가정, Host stop 수락 후 응답 유실의 FAILED 오판, 확정 거부 뒤 적용 intent 잠김, 저장 직후 외부 편집을 clean hash로 오인, 정식 ABANDONED 이후 새 요청 차단, bridge 생성 후 symlink 교체를 각각 수정했다. 실제 ConsoleHub/서버 console projection·API·외부 편집/응답 유실 주입·same key/상태 보존 회귀를 추가했다. 코드 읽기에서 찾은 결함을 시험 FAIL이 이미 존재했던 것처럼 기록하지 않는다.

| 실행 | 결과·환경·근거 |
|---|---|
| 최종 Python 영향 회귀 | 320 PASS / 20 Windows SKIP, macOS Python 3.11, `regression-final.log` |
| 추가 실제 API/입력 고정/복구 | 78 PASS, `contracts-1.log` (최종 회귀에 포함, 합산하지 않음) |
| 두 UI build | PASS, Node 22.23.5, `build-3.log`; 최초 기본 PATH에서 Node 미탐지 FAIL(`build-1.log`) 후 설치된 동일 환경 경로로 재실행 |
| 미러 Chromium | 15 PASS, `browser-mirror-final.log`; 최종 보드 커넥터 한글 nav/header·상태·설정/명령/초안 회귀 |
| 보드 커넥터 Chromium | 16 PASS, `browser-connector-2.log`; 모의 browser fixture만 사용 |
| 문서/ID/공백 | `python3 docs/testing/validate_docs.py`, `git diff --check` PASS; 최종 수치는 후속 기록 |

최초 browser 실행은 기본 cache의 Chromium 미설치로 15 FAIL(`browser-mirror-1.log`)이었다. 설치된 일반 Chrome을 지정한 재시도는 느린 실행/초기 timeout을 확인하고 해당 시험 프로세스만 중단했다(`browser-mirror-2.log`, `browser-connector-1.log`). 이후 기존에 설치된 matching Chromium headless shell을 명시해 같은 시험을 통과시켰다. 실패·중단 로그를 보존하며 시험 조건/기대값을 약화하지 않았다. 실제 Windows GUI·장비 PASS로 해석하지 않는다.

명령 실행: 공통 venv Python으로 pytest의 plugin_runtime/plugin_delivery/agent_monitor_delivery/agent_monitor_manager/connector_mirror/connector_mirror_client/connector_mirror_http/board_connector_launcher와 기존 connector_bootstrap/shared_control/shared_connector_control/plugin_control_workflow/plugin_integration_http/recovery/snapshots를 함께 실행했다. browser는 `scripts/test_dashboard_browser.py connector-mirror.spec.ts`와 `scripts/test_connector_browser.py`의 새 runtime/모의 fixture를 사용했다. 기존 서비스·runtime·사용자 설정·BSP/장비/모델 호출은 하지 않았다.

## 코드 리뷰 근거

review_id: `20261118-plugin-portable-astra-high`; reviewer/model: 별도 `/root/plugin_portable_astra_review`, `gpt-6-astra`, reasoning `high`. 아래 SHA-256 소스에 대해 최종 APPROVED(코드/계약)이며 Claude 리뷰나 회사 인수로 표시하지 않는다.

```text
69c20f06a31096f0b4ee4f7ae9837a750482fde20eeff104934f3477e3c1d81b  backend/gui_test/standalone/plugin_runtime.py
c7a0e361a34a88cffdfe7ca56618b0777677fe8178485d2525dc7d3160acb596  backend/gui_test/standalone/plugin_settings_file.py
6f4747ce38275dabd4f6439608892d96be996555339754364101e8c819ef3988  backend/gui_test/standalone/plugin_commands.py
dd8522590fdfef3a388410086663a4b5ceabcaa4942a45c2a50955f129dc29f4  apps/agent-monitor/plugin.py
f8abb2fc15d64039420c45c305d83b6341f8a946b3e8fbca8d5e168f156f103f  apps/agent-monitor/plugin_delivery.py
5345048c87cf8c4e272e8fcef844359ded1959869c34f56a6b1460ba020e2cd4  backend/gui_test/connector/mirror.py
6f16dfe55207c062a3f2e72b89e8bd208e8ec08d3884c6f500ae0b4714b151a3  backend/gui_test/connector/mirror_client.py
```

## 용어와 미검증 범위

현재 제품 코드·화면·안내의 Windows 커넥터/Windows 보드 커넥터/Board Connector 표시를 보드 커넥터로 통일했다. Windows OS 위치·기존 API 식별자/경로/호환 클래스는 유지한다. 과거 WORK_STATUS·testing/runs의 실제 기록 문구는 이력으로 보존했다. 검색 전/후 근거는 로컬 `terminology-before.txt`/`terminology-after.txt`다.

T-282~285는 위 로컬/모의/독립 복사 검증 범위에 한정한다. 원본 없는 copy subprocess help/verify/re-export/import, GUI source/manifest/requirements/자산 closure·변조 거부를 수행했다. 실제 기본 UI 포함 전달물의 생성 경로·release·체크섬은 고정 코드 후 기록한다. T-286 회사 Git 반입/소비자 전환/중복 소스 제거·공통 외부 설정 적용·실제 slash/hook/알림·Windows Python/SSH/COM/fastboot/BAT/TC/재시작·복원은 NOT_RUN이다.
