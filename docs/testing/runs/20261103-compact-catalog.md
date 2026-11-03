# 2026-11-03 TC 필터·이름 옆 전체 선택

기준: main `7ccfdc66be14849fe6b144b0699f300d2a19060b`. RQ-39, D-47 후속, T-125 및 목록 정렬 회귀. 사용자 요청은 연결 유형 필터를 작고 간결하게 표시하고 전체 선택을 이름 제목 옆으로 옮기는 것이다.

변경: 검색과 `유형 [전체/Single/Dual]`을 같은 줄에 두고 32px 높이의 입력을 사용한다. 이름 제목 앞에 24px 선택 영역을 두고 이름 정렬 버튼과 분리한다. 선택 개수는 작은 별도 줄에 표시한다. 전체/부분/빈 결과/비활성/필터 밖 선택·실행 순서는 기존 로직을 유지한다. API·DB·실행기 변경은 없다.

## 독립 검토

새 `gpt-6-astra` 세션 `/root/compact_astra_review`의 최초 결과는 CHANGES_REQUESTED였다. 240px 패널에서 고정 헤더 열 너비 때문에 이름 셀에 32px만 남아 체크박스+이름/정렬 화살표가 유형 제목과 겹칠 수 있었다(REG-0021). 이름 최소64px, 끝 열24~70px 가변으로 수정하고 같은 코드 리뷰를 다시 받았다. 재검토는 APPROVED이며 reviewer는 코드를 수정하거나 제품 시험을 실행하지 않았다.

## 별도 시험

`gpt-6-sol`의 새 세션 `/root/compact_sol_tests`에서 빌드·브라우저 회귀·240/300px 패널 및 375px 화면 geometry/screenshot을 확인했다. 주 작업자가 결과와 코드 해시를 대조하고 실패 시 수정·재시험한다. 기존 전체 Python PASS를 이번 UI 변경의 새 시험으로 재사용하지 않는다. 실제 장비·회사 TC·Linux 운영 실행은 수행하지 않는다.

GUI-UI-14는 이름 옆 체크박스 위치와 정렬 독립성, 최소 패널 너비의 이름/유형 제목 간격·화살표 잘림 여부를 검증한다. GUI-UI-15의 선택 불가/빈 필터 및 기존 나머지 UI 회귀는 유지한다. 결과와 증거는 아래에 보존한다.

## 최종 결과

- Astra 코드 재검토 APPROVED. 주 작업자가 별도 시험 결과와 검토/시험 대상 3개 파일 SHA256 일치를 확인했다.
- `powershell.exe -NoLogo -NoProfile -File scripts/build.ps1 -SkipInstall`: Dashboard·단독 GUI Test 빌드 PASS. [출력](20261103-compact-catalog-evidence/build.log).
- 독립 단독 Playwright: 16 PASS, unexpected 0, flaky 0. 실행 시작 `2026-11-03T04:42:31.173Z`, 45.8초. [JSON](20261103-compact-catalog-evidence/browser-results.json), [출력](20261103-compact-catalog-evidence/standalone-e2e.log). PowerShell stderr 파이프는 Node 색상 환경변수 경고로 shell exit 1을 반환했으나 시험 JSON/출력의 제품 시험 결과는 모두 PASS다.
- [geometry](20261103-compact-catalog-evidence/geometry.json): 240/300px 패널과 375px 모바일에서 검색/필터·헤더 겹침과 잘림, 페이지 가로 넘침 없음. 필터 84×32px, 정렬 화살표 포함 이름 버튼 폭36px. [240px](20261103-compact-catalog-evidence/desktop-240.png), [300px](20261103-compact-catalog-evidence/desktop-300.png), [모바일](20261103-compact-catalog-evidence/mobile-375.png). 주 작업자가 최소 너비 캡처도 확인했다.
- 코드·증거의 raw SHA256/UTC 시각: [manifest](20261103-compact-catalog-evidence/manifest.json). 경로는 원래 로컬 증거 위치이며 이 디렉터리에는 동일 파일을 복사했다.

환경: Windows, Python3.13.5, Node24.21, Edge, 격리된 Mock runtime. 이번 범위에서 통합 Dashboard 브라우저·전체 Python·실제 Linux/COM 시험은 재실행하지 않았다. 실제 외부 연동 인수 T-130과 운영 baseline은 바꾸지 않는다.

문서 검증: 별도 GPT-6-sol이 `docs/testing/validate_docs.py` 실행, exit0·상대 링크424개·요구사항46개·시험130개·오류0 PASS. 원본 출력은 같은 evidence 디렉터리의 `doc-validation.json`에 보존한다.
