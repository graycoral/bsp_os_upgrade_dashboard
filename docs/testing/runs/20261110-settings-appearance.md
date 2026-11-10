# 환경 탭 색상·저장 버튼 배치 검증

- 요구사항: RQ-55/D-59 후속 사용자 UI 수정, REG-0077, T-169~175.
- 기준: `f93f5d91a26eddeaa0144221669b7cdfed722bbb` + 미커밋 작업 트리.
- 코드 SHA256: `3305b8f6270469739ffc1b076052c44096a7df10e93c0765b45865ddaac5df98` (main.tsx/style.css의 경로와 개별 해시를 결합). 개별 해시는 아래 로컬 source-manifest.json.
- 환경: macOS arm64, Node 22.23.4/npm 10.9.9, 설치된 Google Chrome, 정적 fixture 서버와 가로챈 API. 실제 CLI·장비·Jira·회사 인수 NOT_RUN. 독립 리뷰 NOT_REVIEWED.

## 구현 범위

`apps/web/src/main.tsx`에서 고정 BSP 폼 ID를 부여하고 TestPage 뒤에 저장·점검 버튼/점검 결과를 배치했다. 외부 submit 버튼은 `form="bsp-settings-form"`으로 기존 저장·검증 경로를 사용한다. 대시보드/Jira 문맥에서는 해당 설정 편집기가 열린 경우만 표시한다. `apps/web/src/style.css`에서 BSP와 전역 Test의 호스트 테마를 지정하고 조작 영역의 우측 정렬·좁은 화면 줄바꿈을 제공한다. 공용 GUI/단독 GUI 소스·DB/API 변경 없음.

## 실행 결과

원본 전체 로그·캡처·일회성 수용 검사·이전 결과 CSV는 `.local-reports/settings-appearance-20261110/`에 로컬 전용 보존하며 Git에 포함하지 않는다.

| 명령/확인 | 결과 | 로컬 근거 |
|---|---|---|
| `bash scripts/build.sh dashboard --skip-install` | PASS / exit 0 | build.log |
| 최초 `npx playwright test settings-sync.spec.ts` | BLOCKED / exit 1; fixture 서버 listen EPERM, 1 failed/11 did not run | browser.log, browser-artifacts/ |
| 로컬 서버/Chrome 실행 권한을 확보한 동일 spec 재시험 | PASS / exit 0, 12 passed | browser-final.log, browser-final-artifacts/ |
| 일회성 `layout.check.spec.ts`의 환경 화면 수용 검사 | PASS / exit 0, 1 passed | layout.log, layout-artifacts/ |

최종 spec 명령은 `BSP_BROWSER_EXECUTABLE="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" npx playwright test settings-sync.spec.ts --output ../../.local-reports/settings-appearance-20261110/browser-final-artifacts`이며 `apps/web`에서 실행했다. 첫 환경 실패를 지우거나 시험을 변경해 통과시키지 않았다.

수용 검사는 1360px/375px에서 Test 제목 색상=BSP 제목 색상, 접기 강조색 rgb(41,101,232), Test 카드 아래의 저장 조작 위치, 페이지 너비, 외부 submit의 BSP 폼 연결과 실제 모의 저장 1회를 확인했다. 전체 화면 캡처 두 장과 Test 카드 캡처를 직접 확인했다. 기존12개는 접기·키보드·미저장 입력·탭 이동·GUI/BSP 저장 분리·숨은 필드 오류 노출·개별 저장·polling 동작을 검증한다.

현재 검증은 로컬 화면/모의 저장 범위다. 운영 baseline·독립 리뷰·실제 외부 연동 완료를 뜻하지 않는다. 이번 코드·문서 변경은 로컬에만 있으며 커밋/게시하지 않았다.


## PORT 후속 안내 보완

회사 전달 안내 누락을 보완해 [PORT-004](../../porting/PORT-004.md)와 이식 목록을 갱신했다. 호스트 소스/시험의 실제 SHA256을 재확인해 기록했고 기존 고정 대상과 미커밋 후속을 분리했다. 이번 보완은 문서 전용이며 앞선 제품 시험 결과는 위 코드/시험 해시에만 유효하다. 문서 링크·ID와 `git diff --check`를 재검증했다. 코드 커밋·독립 리뷰·회사 적용은 추가 수행하지 않았다.


## 코드 고정과 게시 준비

사용자의 커밋·푸시 지시 후 대상 코드를 `7cdc9fb6bcea18bd8f15ce7d8a72bb584a1e6b01`으로 고정했다. 검증 당시와 고정 커밋의 main.tsx/style.css 및 기존 설정 시험 두 파일의 SHA256을 재확인해 동일함을 확인했다. 제품 코드/시험 변경이 없으므로 앞선 실행을 새 실행으로 표시하거나 불필요하게 반복하지 않는다. PORT-004와 결과 CSV/회귀 기록을 이 코드 커밋에 연결하고 문서·Git diff 검사를 재수행했다. 위의 미커밋 기록은 당시 상태이며, 독립 리뷰와 실제 회사 인수는 계속 NOT_REVIEWED/NOT_RUN이다.


게시 전 HTTPS Git 인증 부재 및 SSH known_hosts 충돌로 직접 push가 실패했다. 연결된 GitHub 인증을 통해 같은 blobs/tree로 코드를 등록했고, 원격 코드 커밋 `7cdc9fb6bcea18bd8f15ce7d8a72bb584a1e6b01`의 tree `9b1d1a4653e42ce3b8c73f306efd982f2011a6bc`가 최초 로컬 코드 커밋 `18766707ea6e90c09479f5ed117bce71b4325912`의 tree와 같음을 확인했다. 메타데이터 차이로 코드 커밋 해시가 바뀌어 PORT·결과의 대상 참조도 갱신했다. 기존 SSH 신뢰 설정은 변경하지 않았다. 최종 원격 ref와 로컬 동기화는 도구 결과로 확인해 보고한다.
