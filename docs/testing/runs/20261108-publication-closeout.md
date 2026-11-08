# PR #5 게시 완료 기록

2026-11-08 중단된 게시 작업을 복구하면서 GitHub 상태를 재조회했다. 이 문서는 [2026-11-02 게시 검증](20261102-publication.md)의 후속 완료 기록이다. 제품 변경 없이 당시 시험 결과와 병합 사실을 확정한다.

## 게시 및 검증 기준

- [PR #5](https://github.com/graycoral/bsp_os_upgrade_dashboard/pull/5)는 2026-11-03 00:58:19 UTC에 main으로 병합되었다. 병합 커밋: `50ecbea0d6423c9c07e33aca8d19d42004cc2cfc`.
- 검증한 PR head: `e3a6adb99b31899476a3d8e26b7c87b3a771abbd`. [CI 41442964617](https://github.com/graycoral/bsp_os_upgrade_dashboard/actions/runs/41442964617)은 regression 및 windows-package 모두 SUCCESS다.
- Python 299 PASS(경고 1), Dashboard 브라우저 17 PASS, 단독 GUI 브라우저 12 PASS, Mock 시나리오 7 PASS, 두 UI 빌드 및 Windows 패키지 설치·기동 검증 PASS.
- 게시 당시 요구사항 43개·시험 항목 118개·상대 링크 364개 문서 검사 PASS. 이는 해당 시점의 범위이며 이후 main의 현재 시험 수나 인수 상태를 의미하지 않는다.
- RQ-39~43의 요구사항·UI·실행 계약·구조/API/데이터·사용법·시험 및 진행 기록을 PR에 포함했다. 최초 업로드 76개 파일은 Git blob 해시를 로컬 원본과 대조했다.

## REG-0014 종결

최초 실행 41441069153, 후속 41442024136 및 41442490944에서 GUI-UI-05가 실패했다. native 이벤트 기록으로 화면 높이 1000 밖 y=1011에 놓아 drop 이벤트가 없었음을 확인했다. 손잡이 보강만으로는 해결되지 않았으며, 최종 수정은 대상 행 전체를 스크롤해 노출한 뒤 좌표를 읽고 viewport 안인지 검증하는 것이다.

수정 커밋 `e3a6adb99b31899476a3d8e26b7c87b3a771abbd`의 동일 GUI-UI-05가 대시보드·단독 GUI 모두 PASS했다. 위/아래 이동, Preflight 무효화, 완료 Run 불변 기대값은 유지했다. [회귀 기록](../REGRESSION_LEDGER.md)의 과거 실패 및 조사 이력은 보존한다.

## 복구 시 범위와 한계

복구 시 main은 `20d96813de6a54199b095e28582d69c4b3bf8910`까지 진행되어 있었다. 이후 제품·요구사항·시험 상태를 과거 사본으로 되돌리지 않고, 이 완료 기록과 기존 진행·회귀 기록의 연결만 추가한다. 최신 TEST_RESULTS/운영 baseline은 갱신하지 않는다. 당시 Mock/CI 검증은 실제 BCM/RBM/회사 TC/모델 계량 및 독립 Claude 인수가 아니다.

CI 원본 로그는 로컬 전용 `.local-reports/20261108-publication-closeout/ci-final.log`에 보존하며 저장소에 추가하지 않는다. 최종 기록은 GitHub PR/CI 상태 및 해당 로그의 건수와 대조했다. 추가 상대 링크는 원격 기준 파일의 존재를 확인했고 기존 문서 본문은 변경하지 않았다. 제품 시험은 이번 문서 보충에서 재실행하지 않았다.
