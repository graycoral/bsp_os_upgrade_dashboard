# 2026-11-04 · 메인 화면 Hallmark 정리와 TC 트리 아이콘

기준 HEAD `97a509d`. RQ-19/20/24/11, RQ-39, D-52. 사용자가 Hallmark 감사의 다섯 개선 항목을 승인했고, 후속으로 Test cases의 전체 펼치기/접기를 작은 ＋/− 아이콘으로 요청했다. 완료 후 재실행·main 머지·푸시도 승인했다.

## 변경 범위

- 메인 화면의 다섯 진행률 카드를 하나의 요약 띠로 정리한다. 서버의 순서·퍼센트·분자/분모·N/A와 전체/최종 검토 의미를 보존한다.
- 장식 영문 라벨과 정적 U/장비 테스트 상단 표시를 제거한다. `.app--overview` 아래 가독성·단일 진행률 강조색·반응형 규칙을 적용한다.
- 소스 기준/작업 경로는 긴 문자열을 줄바꿈한다. 모듈 표는 내부 가로 스크롤을 유지하며 검색/그룹/키보드 펼침은 동일하다.
- Test cases의 전체 펼치기/접기는 28px SVG ＋/− 버튼으로 바꾼다. 한국어 접근성 이름·title·핸들러를 보존하고 설정 화면의 텍스트 버튼과 구분한다.
- API/DB/worker/명령/상태 계산 변경, 실제 BSP·Jira·장비 호출은 없다. 데이터 마이그레이션은 필요 없다.

## 역할 및 검토 이력

사용자 지정대로 요구사항/아키텍처는 GPT-6 Astra Extra High, 상세 설계는 Astra High, 구현은 GPT-6.1 Sol High, TC 아이콘과 작은 후속 수정은 GPT-6.1 Terra Low, 시험 작성은 별도 Sol Medium, 실행은 GPT-6 Luna Low, 독립 리뷰는 별도 Sol High 세션에서 수행했다. Claude 검토로 표현하지 않는다.

초기 독립 리뷰에서 상단 장식 제거 누락, 소스/경로 줄바꿈 대상 누락, 계획 확인 안내의 작은 저대비 글씨를 발견해 수정했다. 601~760px의 상태 범례 숨김도 보완했다. TC 아이콘 규칙의 설정 화면 영향은 REG-0039로 추적한다. 최종 리뷰와 시험 상태는 아래 결과를 따른다.

## 격리와 검증 기준

원본 작업 폴더에서 별도 모션 작업이 같은 파일을 수정하고 있었다. 초기 혼합 작업 트리의 시험 로그는 39 PASS였지만 공용 JSON/화면 산출물이 동시 실행으로 덮였으므로 최종 검증 근거로 재사용하지 않는다. 해당 실행에서 빌드가 시작된 후 중단되어 빌드 PASS로 기록하지 않는다.

`ui/hallmark-overview-final`의 별도 worktree에 이번 변경만 옮겼다. 다른 작업의 motion.css·진행 막대 transform·입력 방식 핸들러·다이어그램 카메라 변경은 포함하지 않는다. 사용자 runtime과 저장된 작업을 시험 fixture로 사용하지 않는다. 브라우저 회귀는 임시 Vite/Mock 서비스 및 API fixture를 사용한다.

## 최초 격리 결과 · a621545

격리 worktree에서 GPT-6 Luna Low가 실행했다. T-150 PASS, REG-0039 로컬 VERIFIED.

| 검증 | 결과 | 근거 |
|---|---|---|
| `node workflow_diagram/tests/run.cjs` | 40 PASS / 0 FAIL / 0 SKIP, 1.0분 | [로그](20261104-hallmark-overview-evidence/workflow-suite.log.gz), [JSON](20261104-hallmark-overview-evidence/workflow-results.json.gz) |
| `npm.cmd run build --prefix apps/web` | PASS | [로그](20261104-hallmark-overview-evidence/web-build.log.gz) |
| `npm.cmd run build:gui-test --prefix apps/web` | PASS | [로그](20261104-hallmark-overview-evidence/gui-test-build.log.gz) |
| GUI Test 단독 브라우저 회귀 | 18 PASS / 0 FAIL / 0 SKIP, 51.6초 | [재시험 로그](20261104-hallmark-overview-evidence/standalone-gui-browser-retry.log.gz), [JSON](20261104-hallmark-overview-evidence/standalone-gui-results.json.gz) |

단독 브라우저 최초 실행은 Windows에서 `subprocess.call(['npx', ...])`의 실행 파일을 찾지 못해 브라우저 시작 전 WinError 2로 실패했다. [실패 로그](20261104-hallmark-overview-evidence/standalone-gui-browser.log.gz)를 보존한다. 로컬 증거 폴더의 wrapper가 해당 호출만 `node <설치된 @playwright/test/cli.js>`로 치환해 같은 서버 harness·시험을 실행했다. 제품 코드/시험의 판정 조건을 바꾸지 않았다.

신규 overview 3개 시험은 다섯 집계·N/A·상태 수, 필터/Enter·Space, 상단 장식 제거, 320/375/414/768/1280px 페이지와 실제 소스/경로 텍스트 경계, 계획 안내 가독성/동작을 확인한다. 기존 GUI-UI-06은 아이콘 접근성 이름·표시/크기와 설정 텍스트 버튼의 잘림 방지를 추가 검증한다. 서버 실행 게이트 전체나 실장비를 재인수한 결과는 아니다.

독립 GPT-6.1 Sol High 최종 **APPROVED**. 주 작업자와 리뷰어가 [1280px](20261104-hallmark-overview-evidence/overview-1280.png), [375px](20261104-hallmark-overview-evidence/overview-375.png) 화면을 확인했다. 리뷰어는 별도 테스트를 실행하지 않았다. [소스/시험 SHA256 manifest](20261104-hallmark-overview-evidence/manifest.json)가 검증 내용 기준이며 수정 커밋은 이 기록을 처음 포함하는 커밋이다. 실제 운영/장비 인수와 정상 기준 승격은 이번 범위가 아니다.

## 최신 main 통합 결과 · a58b26f

검증 중 별도 모션 작업이 main `dbeb0a7`에 게시됐다. 기능 커밋 `a621545`에 이를 병합한 **`a58b26f764609f44dac49949197e755788e4e396`**가 최종 제품·시험 코드 기준이다. `main.tsx`는 overview 클래스/장식 제거/줄바꿈/진행 띠와 모션 import/scaleX/입력 방식 핸들러를 모두 보존했다. UI 명세·시험 목록·결과의 양쪽 추가 기록도 함께 보존했다. 초기 격리 결과를 통합 결과로 재사용하지 않았다.

Luna Low 통합 재시험: **workflow 44 PASS / GUI Test 18 PASS / 두 빌드 PASS**, 실패·건너뜀0. [workflow 로그](20261104-hallmark-overview-evidence/integration-workflow-suite.log.gz), [workflow JSON](20261104-hallmark-overview-evidence/integration-workflow-results.json.gz), [GUI 로그](20261104-hallmark-overview-evidence/integration-standalone-gui-browser.log.gz), [GUI JSON](20261104-hallmark-overview-evidence/integration-standalone-gui-results.json.gz), [통합 빌드](20261104-hallmark-overview-evidence/integration-web-build.log.gz), [단독 빌드](20261104-hallmark-overview-evidence/integration-gui-test-build.log.gz). Windows harness는 앞서 설명한 설치된 Playwright CLI 직접 호출 wrapper를 사용했다.

별도 Sol High가 통합 코드의 스타일 우선순위·모션 줄이기·즉시 포커스·막대 scaleX와 기존 개선 보존을 재검토해 **APPROVED**했다. [최종 SHA256](20261104-hallmark-overview-evidence/integration-manifest.json), [메인 1280px](20261104-hallmark-overview-evidence/integration-overview-1280.png), [375px](20261104-hallmark-overview-evidence/integration-overview-375.png), [TC 아이콘](20261104-hallmark-overview-evidence/integration-test-cases.png)을 보존한다. T-144~148/150/151 최신 결과는 이 재시험 코드에 연결한다.

문서 검사는 기본 Windows CP949 읽기에서 실패한 뒤 `python -X utf8 docs/testing/validate_docs.py`로 재실행해 PASS였다. 이는 제품 시험과 별도다. 운영 정상 기준은 NONE, 실제 회사/장비 인수는 NOT_RUN을 유지한다.

## 로컬 적용

사용자 요청의 API 종료·재실행 명령은 실행 전 자동 승인 검토에서 `blocked by policy`로 거부됐다. 프로세스 종료나 재시작은 수행하지 않았다. 안전한 대안으로 검증된 통합/GUI 정적 빌드 파일을 기존 서비스의 정적 경로에 복사했다. 기존 작업 목록 응답은 적용 전후 동일하며, 8766의 HTML과 JS/CSS HTTP200·파일 SHA256 일치를 확인했다. [적용 확인](20261104-hallmark-overview-evidence/serving.json), [정적 자산 해시](20261104-hallmark-overview-evidence/served-assets.json). 기존 작업 데이터·API 프로세스·worker를 유지한다. 사용 중인 브라우저는 새로고침하면 최신 화면을 읽는다.
