# 2026-11-18 · TC 목록 전달 누락 수정과 main 통합

RQ-73/D-79/T-280~281·T-284/REG-0113. 기준 main `7b96ad590af1759bab2fe699d138bf082ec441c0`. root는 a0b53cd 위의 다른 WIP가 있어 격리 worktree `connector-tc-list-delivery-20261118`에서 TC 변경만 선별했다. models/timeouts/default120/Mock UI와 다른 root 변경은 포함하지 않는다. DB·실행 제어/예약·장비/모델 실행은 없다.

## 변경과 리뷰

테스트 스크립트 전체 목록과 보드별 구조화 상태를 공통 경로/고정 source/runner와 대조한다. 웹/Qt/Agent Monitor·preview·기본 전달/연결 ZIP을 같은 소스로 묶고 readonly PluginClient/test list GET을 제공한다. [계약](../../design/BOARD_CONNECTOR_CONTRACT.md#tc-목록과-상태-조회--rq-73d-79), [PORT-011](../../porting/PORT-011.md#2026-11-18--tc-목록-포함-전달-후속).

별도 `/root/plugin_portable_astra_review`, gpt-6-astra high의 초기 CHANGES_REQUESTED(P2 metadata dict 가정)를 반영했다. 실제 SharedSettings에 null/list/dictID metadata를 저장해 TC만 stale·미러 유지하는 회귀를 추가했다. UNKNOWN 미확정/확정 PASS 분리도 확인한다. 최종 TC 코드·계약과 클라이언트 GET delta는 APPROVED이며 남은 P1/P2 없음. 검토자는 시험을 직접 실행하지 않았다. 코드 hash/고정 commit은 후속 기록한다.

## 현재 실행 결과

전체 로그는 `.local-reports/20261118-tc-list-delivery/`에 로컬로만 보존한다. 최초 독립 copy HTTPview 시험은 TestClient의 기본 주소가 실제 loopback 경계와 달라 1 FAIL/37 PASS(`initial.log`)이었다. 보안 규칙을 유지하고 실제 loopback client로 수정한 후 42 PASS(`initial-2.log`). 확장 회귀287 PASS(`regression-1.log`), Chromium 미러16 PASS/커넥터18 PASS(`browser-mirror-1.log`, `browser-web-1.log`), 양UIbuild PASS(`build-1.log`). 추가 test list 접점 후 같은 확장 회귀를 다시 실행해 최종 288 PASS(`regression-final.log`)를 확인했다. 실제 회사·Windows/장비 T-281 NOT_RUN이다.

과거 `20261117-connector-test-status.md`는 원래 WIP 증거로만 보존하며 현재 코드 PASS로 재사용하지 않는다. 패키지 갱신 시 running service/Manager 재사용과 source 적용을 구분하는 절차는 PORT에 적었다. 실제 사용자 서비스/장비 재시작은 하지 않는다.


## 최종 로컬 검증

| 검증 | 결과·근거 |
|---|---|
| Python 영향 회귀16개 파일 | 288 PASS·종료0, `regression-final.log`; TC·미러/재시작·플러그인/공유설정·복사배포·source/manifest/전송·패키지 |
| 미러 Chromium | 16 PASS, `browser-mirror-1.log`; 목록의 readonly·source변경·선택보드·stale 포함 |
| 커넥터 웹 Chromium | 18 PASS, `browser-web-1.log`; 목록5개·상태·source교체·텍스트 안전성·제어없음 |
| 양 UI build | PASS·종료0, `build-1.log`; Node22.23.5, 기존 lock/dependencies 재사용 |
| 문서/공백 | PASS, `docs-final.log`; 최종 수치는 고정 전달 후 기록 |

위 실행은 원본 local/mock·loopback fixture·offscreen Qt·독립 copy subprocess이며 회사/실장비 PASS가 아니다. 실제 T-281 NOT_RUN. 기본 timeout600과 models/timeouts/shared_settings_ui·ExecutionTimeoutSettings/SharedControl/TestPage 파일의 main 대비 diff0을 확인했다. 루트 작업 폴더의 다른 미커밋 변경은 보존한다.

## 독립 리뷰 근거

review_id `20261118-tc-list-astra-high`, 별도 `/root/plugin_portable_astra_review`, model `gpt-6-astra`, reasoning `high`. 최종 TC 코드/계약·추가 readonly client/command delta APPROVED, 남은 P1/P2 없음. 검토자는 실제 시험을 직접 실행하지 않았다.

```text
48da4b2a8bf1c3e4ec87378809f727ebd12cd17065f995a80e76216b0a69c8fb  backend/gui_test/connector/test_status.py
38bac8d38aea670926a64d8d63626fea20f4ed044788f8be1fb7aa690b269507  backend/gui_test/connector/api.py
a55daea97eee25dead90c339bf269b3683307d41a02ffc05645760bc8b234c24  backend/gui_test/core/discovery.py
b6d6e2dcff29740e9f53dcbfb50b567ab822a55b51f6a558d8ca6ec4bc89b2fa  apps/agent-monitor/plugin_delivery.py
107c83eaa8351df970018f658f41545f67ff9328df914b2e4dc17175c96e57f8  backend/gui_test/standalone/plugin_client.py
7b4a507561f39a2fdffb8dec62aa9b00d9de09aa30e87662432bd601ab623123  backend/gui_test/standalone/plugin_commands.py
```

변경 내용과 이전 WIP의 차이, 기존 service/Manager에 새 code가 적용됐는지 확인하는 절차는 PORT-011을 따른다. 새 기본 UI 포함 전달 폴더/ZIP은 고정 source commit에서 다시 생성해 manifest/byte hash·실제 preview 화면까지 검증한다. 기존 패키지는 복구용으로 보존한다.
