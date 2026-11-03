# 2026-11-04 · 컴팩트 배치·배율·선택 영역 집중

RQ-50 / D-51 / T-144~148. 사용자가 오른쪽 펼침 구현 도중 크기 축소, 확대/축소 버튼, 참고 Archify HTML처럼 선택 영역 집중 보기를 추가 요청했다. 앞선 [오른쪽 펼침 검증](20261104-workflow-diagram-rightward.md)은 중간 소스의 이력이며 이번 변경의 검증과 구분한다.

## 구현 범위

- 모듈 카드 280→220px, 단계 카드 156→136px, 상위 간격 108→72px로 축소했다.
- `viewport.ts`에 화면 전용 카메라 상태를 분리했다. 확대/축소(25~160%), 100%, 전체 맞춤, 현재 배율을 제공한다. 기본 전체 맞춤은 최대 85%, 영역 집중은 최대 110%까지 화면에 맞춘다. 큰 목록/좁은 화면에서는 최소 25%와 캔버스 스크롤을 함께 사용한다.
- IP 펼침은 해당 모듈과 오른쪽 5단계로 이동, 서비스/그룹 제목 선택은 그 영역으로 이동한다. CSS zoom으로 배율을 적용하고 scrollTo의 부드러운 이동으로 선택 영역을 중앙에 둔다. 나머지 영역은 72% opacity로 약하게 표시하며 hover/키보드 focus 시 복원한다. 전체 보기/캔버스 Esc로 집중을 해제하되 펼침은 유지한다.
- 키보드·reduced-motion·모션 일시정지·상태 신선도/흐름 의미는 유지한다. 같은 작업의 탭 왕복은 배율/선택/스크롤 보존, 대상 전환은 전체 보기로 초기화한다. 크기 변경에만 ResizeObserver를 사용하며 polling마다 레이아웃을 측정하지 않는다.
- 제품 수정은 `workflow_diagram/web/DiagramTab.tsx`, `diagram.css`, 신규 `viewport.ts`. 시험은 `tests/browser.spec.ts`. adapter/host/types/API/DB/worker/운영 정책 변경과 새 의존성 없음. 참고 HTML을 런타임에서 읽지 않는다.
- 실제 ACON/회사/장비 T-149는 NOT_RUN. Windows의 Linux worker 실행은 이번 변경 범위가 아니다.

## 발견·수정·검증 이력

1. 초기 6개 브라우저 회귀 PASS. 확대/집중 시험을 추가한 실행은 **6 PASS / 2 FAIL**. smooth pan 중 서로 다른 시점의 좌표를 비교하던 시험은 모든 rect를 같은 프레임에서 측정하도록 고쳐 원래 겹침 조건을 유지했다. 실제 수동 100% 배율이 예약된 overview RAF에 의해 85%로 돌아가는 REG-0037은 RAF 실행 시 현재 mode를 다시 검사해 수정했다. 실패 로그와 JSON은 보존한다.
2. 재시험 8 PASS. 시각 확인 중 집중 화면의 탭 왕복 위치/캡처 구도를 점검해 scroll 위치를 저장·복원하고 왕복 뒤에도 중앙 좌표를 검사했다. 화면 전체 캡처의 임시 viewport 변화와 실제 viewport를 구분해 focus 증거는 viewport 캡처로 남기고 캡처 이후 중앙 위치도 확인한다.
3. 독립 GPT-6.1 Sol High 리뷰 **CHANGES_REQUESTED**: focus 상태의 실제 창 크기 변경 미보정, overview 탭 복귀의 ResizeObserver 최초 알림이 복원 스크롤을 덮는 P2 두 항목(REG-0038)을 발견했다.
4. host/graph 크기를 저장해 동일 크기 최초 알림은 무시하고, 실제 크기 변경은 focus 상태도 선택 영역을 다시 맞춘다. 1440→1000×760→1440 변경 후 중앙 정렬, 100개 모듈/375px에서 scrollTop 500의 탭 왕복·갱신 보존 회귀를 추가했다. **브라우저 9 PASS, 13.6s**, 독립 재검토 **APPROVED**. 검토자는 코드/결과를 확인했으며 직접 재실행하지 않았다.

주 작업자는 실제 viewport의 `zoom-focus.png`를 열어 모듈/5단계의 중앙 배치와 버튼·주변 구도를 확인했다. 모두 synthetic fixture이며 실제 회사/ACON 시험이 아니다.

## 빌드·로컬 실행

`powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts/build.ps1 -SkipInstall`: 두 UI 빌드 **PASS**, exit 0. 통합 JS `index-BIm2Tt1D.js`, CSS `index-B4wNTjn9.css`; 단독 GUI 자산은 이전과 동일하다. 기존 API 8766에서 새 정적 자산을 제공하며 BSP 작업 데이터를 만들거나 변경하지 않는다.

## 검토 기준

| 파일 | 독립 리뷰 SHA256 |
|---|---|
| viewport.ts | bd85292e2e6e32b90f745dc22e3bc626a21b3c0bebd7447161faa519d308e40f |
| DiagramTab.tsx | d5364c62607f7912fa152ee245526dcb07d145052bcce8a962ff552464094c93 |
| diagram.css | c071e011e57646284c263660391f6c787915c1d73155797c80a26f3edb6964ba |
| browser.spec.ts | b471602d34c3c500f7b21b116191a686e886cf04660879bad724c86d1d4da930 |

같은 working tree의 전체 회귀 및 증거를 아래에 추가한다. 과거 PASS나 다른 코드 해시를 최신 검증으로 재사용하지 않는다. 후속 UI 변경은 미커밋이며 회사 전달용 고정 커밋은 아직 갱신하지 않았다.

## 최종 검증

`node workflow_diagram/tests/run.cjs`: **36 PASS / 0 FAIL / 0 SKIPPED, exit 0, 34.56s**. 주 작업자의 unrestricted 세션, 시작 2026-11-04 00:14:38 KST. 제품/시험 해시는 위 독립 리뷰와 일치하며 Windows·Node 24.21.0·Chrome 156·React 19.3.0·TypeScript 5.9.3·Vite 7.3.7 환경에서 검증했다.

- 100개/80자 이름/375px: 표시 52.8ms, 모두 펼침 183.4ms, JSON 7,046,307bytes/파싱 11.2ms, adapter 최대 0.9ms. 예산 내. 추가 API 조회 0.
- 7,200ms polling 비교 4=4. 비활성 관찰 10회에서 실제 DiagramView 진입 7→7. production Profiler 0은 렌더 횟수 근거가 아니다.
- 기존 adapter/호스트/상태/작업 전환/오래된 응답 회귀를 함께 실행했다. 전체 Python 백엔드와 실제 Linux/ACON/장비 시험은 이번 UI 변경에서 수행하지 않았다.
- 두 빌드 PASS와 localhost:8766의 HTML/새 JS HTTP 200, `wd-zoom-controls` 제공을 확인했다. 기존 API/GUI Test 프로세스는 유지한다.

증거: [소스 manifest](20261104-workflow-diagram-zoom-evidence/source-manifest.json), [통계](20261104-workflow-diagram-zoom-evidence/summary.json), [최초 실패](20261104-workflow-diagram-zoom-evidence/browser-failed.log.gz), [최종 전체 PASS](20261104-workflow-diagram-zoom-evidence/full-final.log.gz), [Playwright 결과](20261104-workflow-diagram-zoom-evidence/final-results.json.gz), [두 빌드](20261104-workflow-diagram-zoom-evidence/build.log.gz), [집중 보기 화면](20261104-workflow-diagram-zoom-evidence/focus.png).

사용자가 완료 후 커밋·푸시를 승인했다. 이 실행 기록의 미커밋 표시는 시험 당시 기준이며 게시 후 고정 커밋은 PORT-001에 별도로 기록한다.
