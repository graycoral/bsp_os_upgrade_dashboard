# 2026-11-04 · 작은 서브 다이어그램·그룹 접기·화이트 테마

RQ-50/D-51 사용자 후속 요청. 기준 HEAD `709fa74f98754244e705781fe516904d4d862a05`. 서브 단계 카드·글씨를 더 줄이고 선행/일반 그룹을 독립적으로 접고 펼친다. 사용자가 참고 Archify는 화이트였다고 정정하여 light 테마를 적용했다.

- 단계 폭136→96px, 최소높이112→72px, 제목12→10px, 상태/설명11→9px, 단계 연결선32→20px. IP 카드220→180px. 확대/축소 기능은 유지한다.
- 그룹 제목의 영역 집중은 유지하며 별도 ＋/− 버튼을 제공한다. 접으면 내부 IP/단계 DOM을 제거하지만 이름·개수·실행 요약·진행률과 하위 IP 펼침 상태를 보존한다. 같은 작업의 탭 왕복에서 접힘을 유지하고 새 작업/대상에서 초기화한다. 집중한 모듈이 숨겨지면 전체 보기로 복귀한다.
- 참고 HTML의 light 색상 계열을 반영한 흰 카드/밝은 점 격자/역할별 테두리/짙은 글자와 진행 화살표. 주변 약화 opacity는82%다. 호스트 다른 화면 테마는 변경하지 않는다.
- 변경 제품은 `workflow_diagram/web/DiagramTab.tsx`, `diagram.css`이며 시험은 `tests/browser.spec.ts`. viewport/adapter/host/types/API/DB/worker/조회 주기와 실행 정책은 변경하지 않았다. 실제 ACON/회사/장비 시험은 수행하지 않았고 T-149는 NOT_RUN이다.

## 검증

주 작업자 실행 `node workflow_diagram/tests/run.cjs`: **37 PASS / 0 FAIL / 0 SKIPPED, exit0, 35.89s**. Windows/Node24.21.0/Chrome156, 2026-11-04 00:21:22 KST 시작. light 변경 전 작은 카드/그룹 구현도37 PASS였으며 [중간 로그](20261104-workflow-diagram-light-groups-evidence/intermediate-dark.log.gz)를 최종 light 증거와 구분한다.

새 시험은 그룹 독립 접기, Enter/Space, 요약 보존, 숨긴 IP DOM 제거, 펼침 복원, 집중 해제, 탭 왕복/작업 전환을 검증한다. 기존 배율·집중·창 크기·조회/상태 회귀도 함께 실행했다. 100개/80자/375px 표시44.5ms·모두 펼침198.5ms, adapter 최대0.7ms, 대표 JSON7,046,307bytes/파싱10.1ms. 추가 API 요청0, polling4=4, 비활성 실제 DiagramView 진입7→7. 모든 기존 예산 내이며 production Profiler0을 렌더 횟수로 해석하지 않는다.

`scripts/build.ps1 -SkipInstall`을 PowerShell 프로세스 Bypass로 호출: 통합/단독 GUI 두 빌드 **PASS**. 통합 자산 `index-atPE1d1z.js`, `index-BshgOdDf.css`. localhost:8766 HTML/CSS HTTP200 및 최신 light 자산 제공 확인. 기존 서버를 유지하며 운영 작업 데이터를 변경하지 않았다.

독립 GPT-6.1 Sol High 검토 **APPROVED**. 그룹 수명·키보드/aria·색상/작은 카드·상태 의미를 코드와 저장 화면으로 확인했다. 직접 재실행하지 않았으며 실제 Claude/회사 인수가 아니다. 검토/최종 소스 SHA256:

| 파일 | SHA256 |
|---|---|
| DiagramTab.tsx | 9a8ff59159f48eb0f91b504c3fa14fac32ff63410cd57c0e5b50bd5aa84680cd |
| diagram.css | eb2737f21dd494a19944982a99a58259c0005429809c5192e6176b60d09bb1c5 |
| browser.spec.ts | 3d88787a42e1cab82957ef242d48e3682860f516b0db852242eec1dcb8047841 |

증거: [소스·시험·통계](20261104-workflow-diagram-light-groups-evidence/source-manifest.json), [전체 시험](20261104-workflow-diagram-light-groups-evidence/full.log.gz), [Playwright JSON](20261104-workflow-diagram-light-groups-evidence/results.json.gz), [두 빌드](20261104-workflow-diagram-light-groups-evidence/build.log.gz), [화이트 집중 화면](20261104-workflow-diagram-light-groups-evidence/light-focus.png), [그룹 접힘 화면](20261104-workflow-diagram-light-groups-evidence/collapsed-group.png). 주 작업자도 두 화면을 열어 배치·색상·접힘 표시를 확인했다.

완료 후 커밋·푸시하라는 기존 사용자 지시에 따라 기능과 이식 기준을 게시한다. 전체 Python/실제 BSP·회사·장비 인수는 이번 UI 변경에서 수행하지 않았다.
