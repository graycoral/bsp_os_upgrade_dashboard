# PORT-002 · 종합 화면과 공통 모션

원본 코드 기준: `ab4580c36f1aad2ab627a1f12beb440da7004845`. 이 기준에는 종합 화면 `a621545`, 모션 `59e2e04`, 트리 토글 `2572aee` 및 접근성 감사 후속 통합이 포함된다. 회사 측 기존 접근성·모달·탐색 구현을 확인하고 다이어그램을 함께 이식할 때는 [PORT-001](PORT-001.md)을 참조한다. 회사 적용과 실제 장비 인수는 별도다.

| 원본 위치 | 이식 범위 |
|---|---|
| `apps/web/src/main.tsx`, `style.css`, `motion.css` | 종합 진행 띠, 반응형 표시, 입력 방식과 모션 |
| `gui_test/web/TestPage.tsx`, `test.css`, `motion.css` | 통합 및 단독 GUI Test의 트리 토글과 버튼 모션 |
| `gui_test/web/CaseTree.tsx`, `tests/e2e/gui-test.spec.ts` | 펼침 상태 기반 단일 토글 구현과 전체/부분 접힘·키보드 회귀 시험 |
| `apps/web/src/audit.css`, `ProgressBar.tsx`, `gui_test/web/AuditDialog.tsx`, `audit-dialog.css` | 공유 접근성 감사 스타일·진행률·모달과 모달 스타일 |
| `workflow_diagram/web/viewport.ts`, `DiagramTab.tsx`, `diagram.css` | 즉시 배율·이동과 흐름 효과; PORT-001 참조 |
| `workflow_diagram/tests/` 및 GUI Test 시험 | T-150~155와 영향받는 화면 회귀 |

회사 구조에 맞춰 셸과 스타일 진입점을 조정하고 기존 접근성 감사의 모달 포커스·설정 입력 보호·키보드 조작·URL 탐색을 보존한다. 종합 수치와 N/A는 서버 값을 사용하며 API, DB, 실행 게이트 변경은 없다. 회사 환경의 CSS 충돌, 작은 화면과 단독 GUI 빌드를 확인한다. 데이터 이전은 필요 없으며 되돌릴 때 회사의 해당 UI 변경만 복원하고 공유 코드와 실행 데이터를 보존한다.

호스트는 `audit.css`, `ProgressBar.tsx`, `AuditDialog.tsx`를 직접 가져오며 `AuditDialog.tsx`는 `audit-dialog.css`를 가져온다. 회사에 동등한 구현이 있으면 연결을 조정하고, 없으면 필요한 파일을 함께 이식한다. 원본 루트에서 `node workflow_diagram/tests/run.cjs`, `npm.cmd run build --prefix apps/web`, `npm.cmd run build:gui-test --prefix apps/web`으로 회귀와 빌드를 실행한다. 러너·브라우저 설정은 [시험 안내](../../workflow_diagram/tests/README.md)를 따른다.

원본 증거는 [종합 화면](../testing/runs/20261104-hallmark-overview.md), [모션](../testing/runs/20261104-ui-motion.md), [트리 토글](../testing/runs/20261104-tree-toggle.md), [접근성 감사 통합](../testing/runs/20261104-web-guidelines-main-merge.md)을 참조한다. 추가 실행은 [이번 실행 기록](../testing/runs/20261104-ui-finish.md)에 기록한다. 회사 적용 범위·커밋·시험과 미완료는 회사 `APPLIED.md`에 남기며 원본 PASS를 회사 인수로 간주하지 않는다.
