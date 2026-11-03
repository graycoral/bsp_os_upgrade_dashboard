# 2026-11-04 · 오른쪽 단계 펼침과 진행 화살표

RQ-50 / D-51 / T-144~148. 사용자 후속 요청으로 모듈의 상세 5단계를 오른쪽 가로로 펼치고 지정된 로컬 `docs/system-diagram-20261103/bsp-system.html`의 classic dark 스타일을 반영한다. 남색 점 격자, 역할별 테두리, RUNNING 단계의 진입선에 이동 화살촉과 청록 신호를 제공한다.

## 범위와 기준

- 시작 기준: main `1adafc6` 이후 작업 트리. 작업 중 별도 세션이 병합한 빌드 실행 정책 변경은 보존한다.
- 제품 수정: `workflow_diagram/web/DiagramTab.tsx`, `web/diagram.css`. 시험: `workflow_diagram/tests/browser.spec.ts`.
- adapter/host/types/API/DB/worker/조회 주기/실행 정책 변경 없음. 기존 작업의 독립 펼침·탭 왕복 유지·작업 전환 초기화를 보존한다.
- 참고 HTML은 디자인 자료이며 배포 의존성으로 추가하지 않는다. 전용 폴더와 기존 React 도구만 사용한다.
- 실제 ACON/회사/장비 T-149는 NOT_RUN. Linux worker/실제 BSP 실행을 이 시험으로 대신하지 않는다.

## 실행 기록

주 작업자의 초기 브라우저 회귀: `BSP_BROWSER_EXECUTABLE`을 설치된 Chrome으로 지정하고 `node workflow_diagram/tests/run.cjs browser.spec.ts` 실행. **6 PASS, 9.4s**. 격리 빌드도 PASS. 실행 로그는 `.local-reports/workflow-diagram/rightward-browser-initial.log`이며 최종 증거 묶음에 함께 보존한다. NO_COLOR/FORCE_COLOR 경고는 시험 실패가 아니다.

- 오른쪽 5개 단계의 x 좌표 증가와 모듈과 같은 행의 y 좌표 검사.
- 키보드 Enter/Space 독립 펼침, 같은 작업 유지/작업 전환 초기화.
- 완료 분석 다음 RUNNING 설계 진입선만 활성화. 화살촉 CSS transform의 실제 시간별 변화 검사.
- 모션 일시정지/재개, reduced-motion, stale 전환 시 신호 제거 검사.
- 100개/80자 이름/375px: display 55.7ms, expand 144.7ms (각 예산 1,500ms), 대표 JSON 7,046,307bytes / parse 13ms. 추가 네트워크 요청 0. 전체 카드 겹침 없음.
- 비활성 관찰 10회에서 DiagramView 진입 3→3. Profiler 0은 production 계측 한계이며 렌더 횟수 근거로 사용하지 않는다.
- 주 작업자가 `rightward-running.png`를 열어 가로 단계·실행 강조·그룹 간 분리·역할별 색상과 텍스트를 시각 확인했다. 실제 운영 화면이 아닌 synthetic fixture다.

과거 실행 증거를 현재 변경의 검증으로 재사용하지 않는다.

## 독립 코드 리뷰

기존 독립 검토 세션 `/root/code_review` (GPT-6.1 Sol High)의 후속 검토 결과 **APPROVED**. 가로 배치의 실제 너비 확보, 키보드/aria 유지, 신선한 RUNNING 진입선의 모션과 stale/일시정지/숨김/reduced-motion 정지, 전용 CSS/marker 범위를 확인했다. 저장된 화면과 초기 브라우저 결과를 검토했으며 리뷰 세션 자체는 시험을 재실행하지 않았다. 독립 Claude 검토 또는 실제 회사 인수를 의미하지 않는다.

| 검토 파일 | SHA256 |
|---|---|
| web/DiagramTab.tsx | 2c72bbd68ece8b97150e9bd8925825d670902d43ebe3c7869cc50035ef7c116d |
| web/diagram.css | fab5fd362e051cedbf2f87a5b2a72e412992b821a7d0a6186683132dc8e23e3e |
| tests/browser.spec.ts | 354e96be2fa0b14e3fb8fd570bc7ade1990c0c98281a07b596d5d51ca38ab3b2 |

## 빌드 및 현재 서버

별도 GPT-6 Luna Low 세션의 두 UI 빌드 재실행 PASS. 초기 sandbox의 esbuild `spawn EPERM`/접근 오류와 재실행 exit 0을 같은 로그에 보존했다. 통합 Dashboard는 `index-BTVjdWAs.js` / `index-CSN5XrLv.css`, 단독 GUI Test는 `index-DBvtvPV7.js` / `index-CdiBXQS2.css`다. 기존 `http://127.0.0.1:8766`의 HTML/JS HTTP 200 및 새 `wd-edge-inline`/`wd-traveler` 코드 제공을 확인했다. 정적 자산 변경이므로 API 프로세스 재시작 없이 반영됐다. 기존 GUI Test 8767도 유지한다. 실제 작업/상태를 시험 데이터로 덮어쓰지 않았다. Windows에서 Linux worker를 실행하지 않았으므로 자동 BSP 단계 진행은 별도 환경이 필요하다.

## 전체 회귀의 초기 환경 실패

별도 GPT-6 Luna Low 세션의 최초 전체 실행: **20 PASS / 7 FAIL / 6 NOT_RUN, exit 1, 31.8s**. browser 6개와 첫 host-integration 1개는 assertion 전에 esbuild dependency optimization의 `Cannot read directory "../../..": Access is denied` 및 React production cjs resolve 오류로 중단됐다. 시험을 약화시키거나 이 결과를 삭제하지 않는다. 같은 제품/시험 소스에서 이미 브라우저 6개가 통과한 주 작업자의 현재 unrestricted 세션으로 전체 회귀를 재실행한다. 빌드/시험 환경 실패이며 제품 결함으로 단정하지 않는다.

## 회사 이식

PORT-001의 고정 기능 커밋 `199b04b5c080e41ec9794326828fbc4874cef633`은 이전 아래 펼침 버전이다. 이 후속 변경은 아직 미커밋이며 후속 전달용 커밋 고정이 필요하다. 기존 호스트 접점에 추가 패치는 없다. 코드와 시험·문서를 함께 가져가며 실제 회사 인수는 별도로 수행한다.

## 최종 전체 재시험

주 작업자의 현재 unrestricted 세션에서 동일 소스로 `node workflow_diagram/tests/run.cjs` 재실행: **33 PASS / 0 FAIL / 0 SKIPPED, exit 0, 33.75s**. 시각은 2026-11-04 00:04:54 KST (2026-11-03T15:04:54.999Z), Windows / Node 24.21.0 / 설치된 Chrome 156 / 기존 React 19.3.0·Vite 7.3.7 toolchain이다. T-144~148 최신 CSV를 이 실행으로 갱신했다. 별도 시험 세션의 최초 실패와 주 작업자 재시험을 구분한다.

- 100개/375px 최종 display 60.9ms, expand 114.4ms, parse 11.1ms, adapter 관찰 최대 1ms. 각 표시/펼침 1,500ms 및 adapter 100ms 예산 내.
- 추가 네트워크 요청 0, 기존 polling 7,200ms 비교 4=4, 비활성 DiagramView 진입 3→3 유지.
- 최종 제품/시험 SHA256은 [source-manifest](20261104-workflow-diagram-rightward-evidence/source-manifest.json), [시험 통계](20261104-workflow-diagram-rightward-evidence/summary.json)에 고정했다. 위 독립 리뷰의 세 파일 해시와 재시험 소스가 일치한다.
- [최초 전체 실패 로그](20261104-workflow-diagram-rightward-evidence/full-initial.log.gz), [최종 전체 PASS 로그](20261104-workflow-diagram-rightward-evidence/full-retry.log.gz), [최종 Playwright JSON](20261104-workflow-diagram-rightward-evidence/final-results.json.gz).
- [통합 빌드](20261104-workflow-diagram-rightward-evidence/build-dashboard.log.gz), [GUI 빌드](20261104-workflow-diagram-rightward-evidence/build-gui.log.gz), [진행 중 오른쪽 펼침 화면](20261104-workflow-diagram-rightward-evidence/rightward-running.png), [375px 화면](20261104-workflow-diagram-rightward-evidence/narrow.png).

전체 Python 백엔드 회귀·실제 Linux/ACON/장비 인수는 이번 UI 변경에서 실행하지 않았다. 데이터/실행 정책 변경이 없으며 운영 baseline은 그대로다. 현재 UI/시험 변경은 아직 커밋·푸시하지 않았다.
