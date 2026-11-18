# 2026-11-18 Jira 화면 정리·플러그인 모듈 선택·자동 사전 검사

RQ-75/76 · D-82 · T-288~290. 기존 working tree의 TC 목록·제한시간·커넥터 화면 변경은 보존한다. 시작 HEAD `a0b53cd4813e95b6d39f7d0ad02c0e5a13f2f6fc`; 이번 변경은 미커밋이다. 실제 회사·장비 실행과 독립 Claude 리뷰는 수행하지 않았다.

## 변경과 한계

- 환경 설정의 사내 Jira 연결 패널과 사람 검토·Jira 탭/직접 진입을 제거했다. 기존 Jira 설정·판단 이력·backend 정책을 보존한다. URL `tab=decisions`는 대시보드로 열린다.
- [모듈 후보 계약](../../design/PLUGIN_MODULE_CATALOG.md): full-host 플러그인의 명시 게시·버전 CAS·서버 영속 저장·선택 콤보박스. 후보 수신으로 config·기존 job을 덮어쓰지 않는다. 실제 회사 플러그인 게시 callback은 이 저장소에 없어 [PORT-012](../../porting/PORT-012.md)의 현지 연결이 필요하다.
- 별도 Preflight 버튼과 시작 전 통과 signature 요구를 제거했다. `/runs`의 기존 서버 Preflight·소스/시간/명령 revision·보드 연결/예약·모듈 게이트는 유지한다. 재실행도 별도 `/preflight` 왕복을 생략한다. 화면은 차단 이유를 표시하며 요청 ref로 같은 틱의 중복 클릭을 막는다.
- Preflight 비활성 조건은 busy·시간 설정 조회/저장·카탈로그 조회/소스 적용·미준비 소스·모듈 조건·연결 미확인·명령 미저장·TC 미선택·10,000회 초과였다. 회사 당시 상태/버전/로그가 없어 정확한 원인은 미확정이다. 버튼 제거가 준비 미완료·권한·UNKNOWN·장비 점유를 통과시키지 않는다.
- DB schema 이전·새 의존성·Mock 제품 제거·실제 장비 자동 시작은 이번 범위가 아니다. 최초 BSP 계획 확인·최종 검토·기본 수동 장비 시험을 유지한다.

## 검증

전체 로그·상세 결과·스크린샷은 `.local-reports/20261118-dashboard-workflow/` 아래 로컬 전용이다.

| 검증 | 결과 | 명령·근거 |
|---|---|---|
| Dashboard/standalone TypeScript·Vite | PASS · 종료0 | `bash scripts/build-ui.sh all --skip-install`; `build-2.log` |
| 모듈/API/기존 설정·플러그인·Test core 회귀 | PASS · 248개 · 종료0 | `PATH=/usr/bin:/bin:/usr/sbin:/sbin .venv/bin/python -m pytest -q tests/test_plugin_module_catalog.py tests/test_bsp_plugin_client.py tests/test_api.py tests/test_settings.py backend/gui_test/tests/test_core.py backend/gui_test/tests/test_commands.py backend/gui_test/tests/test_sources.py backend/gui_test/tests/test_execution_timeouts.py backend/gui_test/tests/test_module_selection.py`; `python-3.log` |
| 설정·소스·조정 브라우저 | PASS · 33개 · 종료0 | `browser-static-2.log` |
| GUI 시작·명령 고정·실제 모드 조회 | PASS · 9개 · 종료0 | `browser-start-2.log`; `GUI-UI-(01,05,09,13,14,15,16,18)`과 live view · 새 격리 runtime |
| standalone 소비자 | build PASS · 브라우저 NOT_RUN | 공통 UI를 함께 빌드. 단독 브라우저 전체 인수로 확대하지 않음 |
| 문서·링크/ID·diff 공백 | PASS · 종료0 | `docs/testing/validate_docs.py`, `git diff --check`; `docs-1.log`, `diff-check-1.log` |
| 회사 플러그인·Linux/Windows·장비 T-290 | NOT_RUN | 회사 실제 코드와 당시 Preflight 상태 자료 없음 |

초기 Python 시도는 246 PASS/2 FAIL이었다. 새 시험에서 동적으로 계산되는 telemetry까지 불변 비교하고 필수 package pin 없이 client를 생성한 시험 오류다. 고정 job은 저장 원문 전체로 비교하고 필수 pin을 갖춘 실패 요청으로 교정한 뒤 동일248개를 재실행했다. 제품 검사를 약화하지 않았으며 `python-1.log`를 보존한다.


## 실패 보존과 범위 구분

- 최초 정적 브라우저33개 중32 PASS/1 FAIL: 삭제한 Jira 탭 대신 대시보드 문맥을 사용한 시험에서 전체 설정 전용 접기 버튼을 찾던 동선 오류였다. 환경 설정으로 돌아가 접는 동선을 교정하고 전체33개를 재실행해 PASS했다. `browser-static-1.log`와 실패 trace 보존.
- 넓은 GUI 회귀19개는8 PASS/11 FAIL(`browser-integrated-1.log`)이었다. 기존 WIP의 작은 모드 표시명과 시험의 과거 배너명2개를 현재 의미에 맞췄다. 실패 시 분석 대기를 유지하는 기존 실행 정책과 과거 무조건 재개/FAIL 후 계속 기대가 충돌했고, 남은 예약으로 후속 시험이 연쇄 차단됐다. 제품 게이트와 실패 시험을 약화하지 않았다.
- 첫 직접 관련 묶음10개도 `GUI-UI-10`의 FAIL 후 전체 반복 완료 기대가 기존 분석 대기에 걸려7 PASS/3 FAIL(`browser-targeted-1.log`)이었다. 새 runtime에서 이번 시작 변경의 직접 인수9개를 검증해 모두 PASS했다. 실패 분석 정책/구 회귀 정리는 별도 미완료이며 광역 회귀 전체 PASS를 주장하지 않는다.
- `preflight-baseline.log`: UI를 거치지 않고 별도 `preflight()` 후 시작한 경우와 직접 `start()`한 경우 모두 mock FAIL 후 `PAUSED`/`latched=true`/시도2개로 동일하게 재현했다. 이번 버튼 제거 때문에 기존 대기가 생긴 것이 아니다. 진단에 실제 모델·장비·Jira를 호출하지 않았다.

## 로컬 화면 적용

8766의 기존 개발 API만 안전 종료 후 현재 저장소에서 재시작했다. 기존 Worker PID89030·runtime·worker epoch·BSP config 전체가 유지됨을 확인했다. health의 새 모듈 capability와 `/config/modules` 응답을 확인했다(`live-result.json`, `live-api.log`). 게시된 실제 플러그인 후보는 version0·0개이며 만들어 채우지 않았다. 실제 회사 모듈 원본 위치/게시 callback 연결이 필요하다. UI는 새로고침하면 반영된다. 커밋·게시·장비/회사 운영 적용은 하지 않았다.

검증 코드 식별: `workingtree:sha256:6ea6e573275cfcd76426309df731b803c59bda77fac88a4cadee053d138f7f0b`. 시험 식별: `workingtree:sha256:50e834e111fac24c4c4f69a3c64588963145b612a96b70755d69af8b6badf79e`. 해시 파일 집합은 로컬 `verified-files.json`에 기록했으며 전체 릴리스 해시가 아니다.
