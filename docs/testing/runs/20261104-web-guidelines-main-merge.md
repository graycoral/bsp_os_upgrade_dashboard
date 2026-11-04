# Web Interface Guidelines와 main 통합 · 2026-11-04 · 검증 PASS

- 기준: 감사 브랜치 `412a39a` + `origin/main` `2572aee`의 병합 작업 트리.
- 요구사항: 사용자의 감사 수정 main 병합·푸시 요청 및 RQ-19/20/38/39/50.
- 범위: native dialog 포커스·오류·진행 상태, URL 탐색, 설정 입력·동시 저장 보호, 진행률 접근성, TC 키보드·터치 이동, 대상 Run 중단 확인을 main의 컴팩트 요약·모션·단일 트리 토글과 통합한다.
- 원 작업 폴더의 기존 미커밋 변경은 이 작업 트리에서 수정하지 않는다.
- 외부 연동: 합성 또는 격리 Mock만 사용한다. 실제 BSP·장비·Jira 인수는 NOT_RUN이다.

## 식별자 충돌 해소

main의 기존 T-150(컴팩트 요약), T-151(모션), T-152(단일 트리 토글), REG-0039(아이콘 스타일 전파), REG-0040(시험 선택자 범위)은 유지한다. 감사 브랜치의 기존 T-150/151/152는 각각 T-153/154/155로, REG-0039는 REG-0041로 재할당했다. 과거 실행 기록·CSV의 감사 항목은 새 카탈로그 ID로 연결하며 원래 압축 로그·소스 manifest의 내용과 해시는 변경하지 않는다.

## 충돌 해결과 검증 대상

- Dashboard는 컴팩트 요약의 표시·긴 문자열 줄바꿈·장식 제거와 감사의 링크 탐색·skip link·진행률 이름·설정 보호를 함께 유지한다. 접근성 있는 공통 native dialog를 사용하고 모션은 내부 `.modal` 요소에 적용한다.
- CaseTree는 하나의 상태 기반 ＋/− 버튼과 빈 결과 비활성화, 접힌 자식 렌더링 생략, memo 자료구조, 키보드·터치 이동 및 이동 후 포커스 복원을 함께 유지한다.
- TestPage는 입력 방식별 모션 정책과 캡처한 Run ID/버전 중단 확인을 함께 유지한다.
- 기존 motion 시험은 링크 역할과 native dialog 내부 `.modal` 선택자로 조정한다. GUI-UI-06은 단일 토글 회귀를 보존하며 실행 순서의 이름 span을 비교해 이동 버튼 글자를 제외한다.

## 현재 병합 결과

아래는 현재 병합 소스의 실행 상태다. 과거 감사·overview·motion·토글의 PASS는 각 원 실행 기록에만 유효하며 이 병합 결과의 PASS를 뜻하지 않는다.

| 검증 | 결과 | 실행자·증거 |
|---|---|---|
| 독립 코드 리뷰 | PASS | GPT-6.1 Sol High 승인; 충돌 통합 검토 |
| Dashboard production 빌드 | PASS | `npm.cmd run build`; [압축 로그](20261104-web-guidelines-main-merge-evidence/builds.log.gz) |
| GUI Test 단독 production 빌드 | PASS | `npm.cmd run build:gui-test`; [압축 로그](20261104-web-guidelines-main-merge-evidence/builds.log.gz) |
| 전체 합성 브라우저·단위 회귀 | PASS | 51/51; `T-150~155`, overview·motion 및 기존 회귀; [로그](20261104-web-guidelines-main-merge-evidence/workflow51.log.gz) |
| 단독 GUI E2E | PASS | 18/18; fresh standalone Mock runtime; [로그](20261104-web-guidelines-main-merge-evidence/standalone18.log.gz), [결과 JSON](20261104-web-guidelines-main-merge-evidence/standalone18-results.json.gz) |
| 배포 패키지 pytest | PASS | 6/6; Python 3.13.5; [압축 로그](20261104-web-guidelines-main-merge-evidence/package-pytest6.log.gz) |
| Linux/Windows CI | NOT_RUN | main push 뒤 자동 실행 예정 |
| Linux worker 통합 E2E | BLOCKED | Windows worker는 `fcntl`을 요구하며 WSL은 설치되어 있지 않음 |
| 실제 BSP·장비·Jira 인수 | NOT_RUN | 사용자 실환경 범위 |

실행 ID는 `20261104-web-guidelines-main-merge`다. 최종 검증은 HEAD `412a39a097a3bc7ce2aace50b8f072339453798e`의 작업 트리에서 수행했다. 코드 fingerprint는 `7d3f7e9ae3392cc938dc8bc2f780b3026f3426512775417804a25a10f7d4dce0`, 시험 fingerprint는 `ce09bca055611e75aaa261487b0c79b8f9ad19ccae692a98f09e5bd8c1e3a526`이다. `source-manifest.json`(SHA-256 `cf20c284322fbed3872d006ec999ce5079034e8ee2f78d180fcdc1aac13df381`)에는 코드·시험 파일 해시와 실행 환경을 기록했고, 로그·결과·스크린샷은 [증거 디렉터리](20261104-web-guidelines-main-merge-evidence)에 보존했다. 초기에 소스 조정과 겹친 실행 및 첫 standalone 런처의 test discovery 오류는 재사용하지 않고 별도 압축 로그로 남겼으며, 최종 PASS는 소스 변경 종료 뒤 재실행했다. T-150~155의 병합 결과를 TEST_RESULTS.csv에 추가했다. CI는 main push 뒤 자동 실행 예정이며 실제 BSP·장비·Jira 인수는 NOT_RUN이다.
