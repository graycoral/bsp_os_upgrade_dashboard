# 2026-11-04 · TC 트리 단일 토글

기준 `9eb0acd`. RQ-39/D-52 후속 사용자 정정: 두 개의 ＋/− 버튼을 현재 상태에 따라 바뀌는 버튼 하나로 바꾼다. 표시 중인 필터 트리의 모든 폴더가 펼쳐지면 −, 일부라도 접히면 ＋다. 폴더가 없으면 비활성화한다. 클릭/Enter/Space로 전체 접기/펼치기를 전환하며 선택·실행 순서와 필터 변경 시 기존 펼침 초기화를 유지한다.

제품 수정은 `gui_test/web/CaseTree.tsx`의 표시 상태 계산/버튼뿐이다. 기존 28px 전용 스타일·API·DB·worker는 변경하지 않는다. 사용자 지정에 따라 경미한 구현 GPT-6.1 Terra Low, 시험 작성 별도 Sol Medium, 실행 Luna Low, 독립 리뷰 별도 Sol High를 사용했다. Sol High 정적 검토 **APPROVED**. 작성 중 한국어 라벨 인코딩 오류를 발견해 UTF-8 직접 패치로 바로잡았으며 시험은 실제 한국어 접근성 이름을 검사한다.

T-152는 기존 GUI-UI-06을 강화해 버튼 하나·아이콘/접근성 이름/title/aria-expanded 동기화, 전체/부분 접힘, 클릭·키보드, 빈 검색 결과 비활성화, 선택/순서 보존을 확인한다. 이전 REG-0039 설정 텍스트 버튼 검사도 유지한다. 모의 환경 검증이며 실제 장비 실행은 없다.

## 결과

최초 GUI-UI 실행은 **17 PASS/1 FAIL**이었다. GUI-UI-06의 `.gt-tree-actions` 선택자가 CaseTree 토글과 `TestPage.tsx:228`의 카탈로그 표시 버튼을 함께 찾은 시험 범위 오류였다. 제품의 단일 토글은 올바르게 구현되어 있었다. 선택자를 CaseTree 전용 `.gt-tree-icon-actions`로 수정하고 모든 기존 assertion을 유지했다. [REG-0040](../REGRESSION_LEDGER.md)에 결함을 기록한다. [최초 로그](20261104-tree-toggle-evidence/standalone18.log.gz)와 [실패 맥락](20261104-tree-toggle-evidence/initial-error-context.md.gz), [당시 단일 − 화면](20261104-tree-toggle-evidence/initial-single-toggle.png)을 보존한다.

빌드 최초 명령은 저장소 루트에서 실행해 `package.json` 부재로 ENOENT가 발생했다. 올바른 `npm.cmd run build:gui-test --prefix apps/web` 재실행은 PASS, 일반 `npm.cmd run build --prefix apps/web`도 PASS였다. 과거 PASS를 현재 결과로 재사용하지 않는다.

최종 실행 ID `20261104-tree-toggle-retest`: Luna Low 단독 GUI **18 PASS / 0 FAIL / 0 SKIP / 0 flaky**, 53.5초. [재시험 로그](20261104-tree-toggle-evidence/standalone18-retest.log.gz), [JSON](20261104-tree-toggle-evidence/standalone18-retest-results.json.gz), [통합 빌드](20261104-tree-toggle-evidence/build-web.log.gz), [단독 빌드](20261104-tree-toggle-evidence/build-gui-test.log.gz). 기존 Windows 전용 wrapper가 bare npx 호출을 설치된 node/Playwright CLI 직접 호출로 치환했으며 제품과 판정 조건은 유지했다. 독립 Sol High가 선택자 수정까지 재검토해 **APPROVED**했다. 리뷰어는 시험을 별도로 실행하지 않았다.

[소스·시험 SHA256](20261104-tree-toggle-evidence/manifest.json)이 검증 기준이며 수정 커밋은 이 기록을 처음 포함하는 커밋이다. 앞선 메인 화면 workflow44는 이번에 재실행하지 않았다. 실제 BSP/회사/장비 인수와 운영 정상 기준 승격은 범위 밖이다.

검증된 정적 빌드를 실행 중인 8766 서비스에 반영했다. HTML 일치, JS/CSS HTTP200·SHA256 일치와 적용 전후 작업 목록 동일을 [확인](20261104-tree-toggle-evidence/serving.json)했다. API 프로세스는 재시작하지 않았다.
