# Test 현황 정리·Git 정보·모듈별 TC · 2026-11-04~05

## 2026-11-06 현재 트리 후속 재검증

아래 검증 사본의 차단·대기 표시는 당시 이력이다. 승인된 RQ-20/39/52/53 및 REG-0043~47 수정을 새 GUI Test 구조의 현재 작업 트리에 보존한 뒤 별도 새 Luna Low가 Python focused **384 PASS/6 SKIP**, 두 production 빌드 PASS, 합성 브라우저 **66 PASS**, 단독 GUI **18 PASS**, 통합/단독 live-view **각 1 PASS**를 확인했다. delayed settings save와 정렬·모드 전환을 포함한다. 독립 Sol의 기존 기능 검토와 새 Astra의 구조 검토는 각각의 범위이며 후자가 기능 재검토 전체를 대신하지 않는다.

현재 작업 트리 manifest·정확한 실행 환경·로그·최초 실패와 재시도는 [20261105-gui-test-layout](20261105-gui-test-layout.md)에 기록한다. 이전 PASS를 새 코드에 재사용한 것이 아니라 현재 트리를 다시 실행한 결과다. 아래 Git fixture 격리, 65 PASS/1 FAIL의 실제 value 바인딩 누락, 404·esbuild 환경 차단과 정렬 수정 이력은 삭제하지 않는다. 실제 장비·회사 연동·모델·Jira 인수와 운영 baseline NONE은 유지한다.

## 재개 후 확인 결과

정렬을 포함한 승인 사본의 Dashboard 빌드 `aligned-build-web-2.log`와 단독 GUI 빌드 `resume-build-gui-runner-1.log`는 exit 0이다. GUI 빌드는 설치된 Vite가 지원하는 `--configLoader runner`로 설정 번들 탐색 오류를 피했으며 제품 소스는 변경하지 않았다. `resume-standalone18-1.log`의 fresh Mock 시험은 **18/18 PASS, exit 0**이다. GUI-UI-08/18의 1440/1024px 좌우 상단 차이 1px 이하와 모바일 넘침 검사가 포함된다. 주 작업자가 최종 데스크톱 스크린샷에서 두 박스 상단 정렬도 확인했다.

새 Sol 독립 리뷰 APPROVED, Python Git34+모듈/기존 회귀243 PASS 근거는 유지한다. 정렬 전 합성 66 PASS와 정렬 후 단독18 PASS는 구분한다. 정렬 후 전체 합성 재시험은 검증용 개발 서버의 esbuild/의존성 경로 탐색 오류로 차단됐으며 `resume-full66-2.log`, `resume-full66-runner-1.log`를 보존한다. 통합·단독 live-view 추가 시험은 아직 NOT_RUN이다. 전체 시험이나 새 폴더 구조 인수가 완료됐다고 판단하지 않는다.

- 요구사항: RQ-20/39/52/53, D-54~56, T-112/117/125/152/161~163.
- 범위: 주 탭 제목 아래 소개 문구 삭제, 이름 헤더 체크박스 옆 단일 트리 ＋/−, 진행률·집계 아래 컴팩트 실행 버튼, 작은 상시 세션 정보와 결과 표·로그. 후속 요청으로 상단 `결과` 버튼·중복 제목 제거와 진행률/상태별 개수의 작은 행 통합을 포함한다.
- 보존: 사전 점검 서명과 실행 조건, 중단 확인 및 대상 Run 버전, 선택·설정·과거 Run, 설정/비용 상세 접기.
- 추가 범위: 모드 전환을 환경 설정으로 이동, 미준비 연결 안내만 기본 접기, TC 원본의 읽기 전용 Git 정보, 서버 device_test 문맥에 따른 모듈별 TC 자동 목록.
- 데이터·외부 연동: Git 카탈로그 정보와 모듈 선택 조회·선택 문맥 검증을 확장한다. DB 스키마·운영 게이트·수동 기본값과 D-48 자동 소유 경계를 유지한다. 합성 fixture·임시 Git·격리 Mock로 검증하며 실제 BSP·COM·장비·Jira는 NOT_RUN.
- 기존 포터블 Runner 미커밋 변경은 이 UI 작업 범위에 포함하지 않는다.

## 검증 상태

후속 범위의 소스·시험 작성이 끝나 최종 빌드·시험을 시작했다. 과거 PASS를 현재 코드의 검증으로 재사용하지 않는다.

| 검증 | 상태 | 근거 |
|---|---|---|
| Dashboard production 빌드 | 수정 후 재실행 대기 | 수정 전 `final3-build-web.log` exit 0; REG-0046 복구 후 승인된 사본에서 다시 빌드 |
| GUI Test production 빌드 | 정렬 수정 후 재실행 대기 | 이전 범위 `final3-build-gui-test.log` exit 0; 최종 정렬 사본은 웹 산출물 재생성 필요 |
| Git·모듈 TC 단위/계약 시험 | PASS | Git 34 + 모듈/기존 GUI·하드웨어 모의 회귀 243 = 277 PASS, exit 0; `final3-git-unit-retest.log`, `final3-python-regression.log` |
| 합성 브라우저 회귀 | 이전 범위 66 PASS → 정렬 후 재시험 대기 | REG-0046 수정 후 66 PASS; 이후 REG-0047 정렬·시험 추가로 최종 재실행 필요 |
| 단독 GUI E2E | 준비 차단 → 재시험 대기 | 원래 경로가 이동해 첫 호출 실패; 사본 웹 산출물 미생성 상태의 실패를 보존하고 올바른 준비 후 재실행 |
| 독립 코드 리뷰 | APPROVED | 새 Sol High가 REG-0046의 value 복구와 전체 prop word diff를 재확인; 승인 코드 29개 해시와 검증 사본 일치. 새 폴더 구조는 별도 범위 |

## 독립 리뷰와 수정

새 Sol High 세션이 지정한 UI·시험 8개 파일의 diff와 관련 코드를 읽고 검토했다. 최초 소스 검토에서 REG-0043 두 항목을 발견했다. 헤더 ＋/−의 24px를 기존 28px로 복구하고 좁은 패널에서 이름 정렬 버튼의 최소 32px를 보장했다. 부모 12px만으로 작아지는 세션 대상·Mock 설명에는 12px를 명시하고 자식의 실제 글자 크기 시험을 추가했다. 기존 28px 시험을 완화하지 않았다. 최종 재검토는 APPROVED이며 브라우저 시험 PASS를 대신하지 않는다. 검토 범위 밖의 포터블 Runner 변경은 포함하지 않았다.

추가 범위는 새 독립 Sol High 세션에서 다시 검토했다. REG-0044의 Git 미지원 원격 형식, REG-0045의 자동 배정 전 목록 선택·일시 조회 실패 복구·오프라인 동결 목록 문제를 수정하고 각각 방지 시험을 추가했다. 최종 소스 검토와 실제 시험 결과는 별도로 기록한다. 작업 중 기존 포터블 Runner 전달 커밋으로 HEAD가 `197be63`까지 이동했으며 그 작업은 이 기능의 검토 범위에 포함하지 않는다. 최종 manifest는 실행 당시 HEAD와 기능 파일의 실제 SHA256을 함께 기록한다.

## 최초 실행과 환경 재시도

샌드박스 안의 빌드는 Vite 설정 경로 접근 거부로 실패했고 승격한 최종 두 빌드는 exit 0을 확인했다. 최초 합성 시험은 브라우저 실행 경로 미설정으로 없는 Playwright 기본 브라우저를 찾고, Vite 경로 접근 거부도 발생해 20 PASS/14 FAIL/18 NOT_RUN이었다. 원본 `workflow-synthetic.log`를 보존하고 설치된 브라우저 경로를 명시한 권한 재시도로 구분한다. 이 최초 실패를 제품 결함이나 최종 PASS로 바꾸지 않는다.

후속 요청 전 중간 소스에서는 Chrome 경로를 지정한 합성 재시험 52 PASS, 단독 GUI 17 PASS/1 FAIL이었다. GUI-UI-14에서 최소 TC 패널 너비의 이름 정렬 글자·화살표가 잘리는 실제 배치 문제를 발견해 REG-0043 보완 대상으로 추가했다. 원본 `standalone-browser-e2e.log`와 결과 JSON·실패 증거를 보존한다. 이 중간 결과와 리뷰는 이후 `결과` 버튼/제목 제거·작은 진행률 통합을 포함한 최종 소스의 검증을 대신하지 않는다.

최종 Git 단위 시험 첫 실행은 33 PASS/1 FAIL이었다. 비 Git 폴더용 pytest 임시 경로를 보고 폴더 아래에 두면서 실제 개발 Git 저장소의 하위 폴더가 된 시험 fixture 격리 문제였다. OS 임시 경로의 Git 저장소 밖 폴더로 격리하고 원래 `not_repository`/빈 저장소·커밋 판정 조건을 그대로 유지했다. 제품 코드는 변경하지 않았으며 같은 시험 재실행은 34 PASS/exit 0이다. `final3-git-unit.log`의 최초 실패와 `final3-git-unit-retest.log`를 모두 보존한다.

Python 회귀의 종료 전 로그 관찰에서 상태를 잘못 읽은 중간 보고가 있었지만, 완료한 원본 `final3-python-regression.log`와 `final3-python-regression-retry.log`는 모두 243 PASS/exit 0이다. 추가 반복 시험 없이 실제 종료 코드와 최종 summary로 정정했다. 기존 Starlette/httpx 사용에 대한 deprecation 경고 1개가 있으며 패키지 변경이나 실패·skip으로 처리하지 않았다.

최종 합성 브라우저 첫 실행은 65 PASS/1 FAIL이었다. delayed settings save 시나리오의 trace에서 두 번의 PUT과 reload GET이 동일한 최신 설정을 반환했지만 입력칸은 비어 있었다. 실행 환경 입력 7개의 controlled value 누락(REG-0046)이 제품 원인이다. 원래 바인딩을 복구하고 기존 시험 그대로 재검증한다. 독립 리뷰의 이전 APPROVED는 이 발견 뒤 CHANGES_REQUESTED로 정정했으며 최종 수정 기준으로 재검토한다. 이력·실패 아티팩트와 기대값은 보존한다.

REG-0046의 원래 value 바인딩은 Terra Low가 한 prop만 복구했고 독립 Sol이 전체 word diff를 재확인해 해당 기능 범위를 재승인했다. 재시험 준비 중 별도 세션의 RQ-54/D-57 [GUI Test 구조 분리](../../design/GUI_TEST_LAYOUT.md)가 기존 `gui_test/`를 이동했다. 이 기능 변경은 이동 전 manifest와 새 경로에 보존되며 구조 변경 자체는 별도 검증 범위다. 일시적으로 옛 경로와 import가 불일치한 동안에는 새 시험을 시작하지 않고, 진행 중 결과를 최종 코드의 PASS로 재사용하지 않는다. 경로·진입점이 정리되면 새 구조 기준으로 남은 검증을 이어간다.

구조 변경과의 충돌을 피하기 위해 남은 기능 시험은 별도 로컬 검증 사본으로 분리한다. 고정 기준 `197be637cd7d9bd0430751b177f601f5d54789cf`에 이동 전 보존본과 승인된 입력값 복구본을 겹쳐 만든 뒤 독립 리뷰의 기능·시험 29개 파일 SHA256과 대조한다. 이 사본의 결과는 **RQ-20/39/52/53 기능 코드의 검증**이며 RQ-54 새 구조 자체의 빌드/패키지/통합 인수로 사용하지 않는다. 새 구조의 최종 검증은 [별도 기록](20261105-gui-test-layout.md)의 책임 범위다. 원본 작업 폴더를 되돌리거나 이동 결과를 덮어쓰지 않는다.

검증 사본은 `.local-reports/tc-final-feature/`이며 Luna가 `snapshot-hash-check.csv`에서 리뷰 대상 29/29 파일의 완전 일치를 확인했다. Node 도구는 기존 설치본을 읽는 사본 내부 junction으로 재사용한다. 새 의존성 설치나 원본 디렉터리 복원은 없다. REG-0046 수정 뒤에는 이 사본에서 Dashboard 빌드·실패 시나리오·전체 브라우저·단독 GUI·모드 전환을 재검증한다. 복사와 시험 원본은 모두 로컬 전용이다.

REG-0046 수정 사본에서 delayed-save 1 PASS/전체 합성 66 PASS를 확인했다. 이후 사용자가 좌우 패널 상단 정렬(REG-0047)을 추가로 요청해 공통 toolbar로 이동하고 GUI-UI-08/18에 1440/1024px의 1px 정렬 조건을 추가했다. 원본의 새 공유 UI와 사본에 같은 수정을 반영했고 Sol이 코드 2개·시험 1개와 최신 29개 해시를 재확인해 APPROVED했다. 이 후속 수정 뒤 두 빌드·브라우저·단독 GUI·모드 전환을 다시 검증하며 이전 66 PASS와 최종 결과를 구분한다.

추가 준비 실패: 사본의 단독 GUI 정적 파일을 생성하기 전에 실행해 404 기반 실패가 발생했다. 제품 판정 근거로 사용하지 않고 `.local-reports/20261104-test-results-cleanup/snapshot-standalone-missing-static-backup.log`에 전체 결과를 보존한다. 이후 단계는 두 빌드 완료·정적 index 존재를 확인한 뒤에만 실행한다. 빌드 재실행의 권한 호출이 지연되어 실행 담당 상태를 분리해 확인 중이며 실패를 PASS로 바꾸지 않는다.

전체 로그·결과 JSON·스크린샷·소스 manifest는 `.local-reports/20261104-test-results-cleanup/` 아래 로컬에만 보존하며 Git에 포함하지 않는다. 빌드·시험 종료 코드와 실패 시도는 보존한다. 운영 baseline NONE을 유지한다.
