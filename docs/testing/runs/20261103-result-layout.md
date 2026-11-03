# 2026-11-03 결과 우선 화면과 실행 분리

기준 main cbb87ea67edebdf774f89e49f78e8d60ce7ee4b5. RQ-39/T-112/T-117. 사용자 요청으로 결과 카드를 상단에, 접이식 실행 카드를 아래에 분리한다. Run 선택은 설정 아이콘 바로 왼쪽으로 옮겨 설정 화면에서도 실행 이력을 선택할 수 있다. 결과 요약·진행률·완료/비용은 유지하고 세션 정보·결과 상세·로그는 각각 접을 수 있다. 실행 조작의 기존 게이트와 상태 전이는 보존한다. 결과 상세/실행은 기본 열림, 세션 정보/로그/비용은 기본 접힘이다.

UI만 변경하며 API/DB/실제 운영 실행은 없다. GUI-UI-18은 카드 순서·세션 선택 배치·접힘과 Preflight 독립·결과 요약 유지·키보드·모바일을 확인한다. 기존 설정 복귀/실행/중단/재개/Retry/리포트/비용 회귀도 유지한다. 새 Astra `/root/layout_astra_review` 코드 리뷰 APPROVED. 별도 GPT-6-sol `/root/layout_sol_tests`의 시험 결과 대기.


최초 리뷰는 CHANGES_REQUESTED(REG-0023): 키보드 guard의 적용 위치가 잘못되어 separator 키 조작을 막고 Run 선택의 방향키를 탭 이동이 가로챘다. 주 작업자가 위치를 수정하고 Astra 재리뷰를 받았다. 첫 제품 빌드 전에 수정했으므로 초기 제품 시험 FAIL로 주장하지 않는다. GUI-UI-08(키보드 크기 조절)과 GUI-UI-18(세션 키 이벤트 분리)이 방지 시험이다.

리뷰 raw SHA256:

```text
TestPage.tsx 2dd77643b7350b20698b2bfd23eda16f6f1f895a2bc86a96028f9b801e2dacde
test.css 972258b08786841a4a797b1313ef61676a8f43130ad70510d3119dc4c22608e1
gui-test.spec.ts 5f7956d0ea307f2f292312349b0000c4c35c00b1569ef648ac0a8928fa95e43d
```

초기 별도 제품 시험: 두 UI 빌드 PASS, 브라우저16 PASS/2 FAIL. GUI-UI-03은 관찰 모드 표시가 기본 접힘 정보 안으로 들어가 숨겨져 실패했다(REG-0024). GUI-UI-04는 앞 시험이 중단/예약 해제를 마치지 못해 Board/COM already reserved로 새 Run이 시작되지 않은 연쇄 실패였다. 주 작업자는 Run ID 위치는 유지하면서 제어 중/관찰 모드 표시만 결과 요약에 상시 표시하도록 수정했다. 시험 기준을 완화하지 않고 깨끗한 runtime에서 전체 재시험한다.

REG-0024 수정 코드도 Astra 재리뷰 APPROVED. 최종 TestPage.tsx raw SHA256은 b46b7e4f9734d795d09e4c1910644c3079a99d356fb8b6ad04386420db23aa0f이며 CSS/시험 파일 해시는 위와 동일하다. 제어 상태는 접힘과 무관하게 요약에 표시한다.


## 로컬 최종 결과

별도 GPT-6-sol 새 runtime에서 두 UI 빌드 PASS, 브라우저18/18 PASS(57.2초, skipped0/unexpected0/flaky0). GUI-UI-03/04/08/18 모두 PASS. 주 작업자가 최종 소스3개와 Astra/시험 해시 일치 및 [모바일 캡처](20261103-result-layout-evidence/result-layout-mobile.png)를 확인했다. 초기 실패와 재시험은 다음 증거로 구분한다.

- [초기 실패 로그](20261103-result-layout-evidence/initial/browser.log), 초기16 PASS/2 FAIL과 오류 화면/문맥은 initial 디렉터리에 보존.
- [최종 브라우저 JSON](20261103-result-layout-evidence/final/browser-results.json), [로그](20261103-result-layout-evidence/final/browser.log), [빌드](20261103-result-layout-evidence/final/build.log).
- [최종 시험 소스](20261103-result-layout-evidence/final/source-after.json), [아티팩트 manifest](20261103-result-layout-evidence/final/artifact-manifest.json). 시험 중 UI_SPEC 문서만 정리했으며 제품/시험3개 파일은 변하지 않았다.

Windows/Python3.13.5/Node24.21/Edge, 격리된 Mock 환경이다. UI 변경으로 로컬 전체 Python을 반복하지 않았으며 Linux 통합 브라우저는 PR CI에서 확인한다. Windows fcntl 미지원으로 통합 runner를 시작할 수 없다는 기존 환경 제약은 이번에 재실행하지 않았다. 실제 Linux 운영/TC/COM/모델 호출은 하지 않는다.

별도 GPT-6-sol 문서 검사 PASS(exit0, 상대 링크456개, 요구사항46개, 시험130개, 오류0). 같은 evidence 디렉터리의 `doc-validation.json`에 원본을 보존한다.
