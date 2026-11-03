# 2026-11-01 TC 작업 화면 변경 검증

실행 ID: 20261101-tc-workspace. 수행: Codex. 환경: macOS / Python 3.11.7 / Chrome / Dashboard 127.0.0.1:8766. 기준: main 2e2d24b 내용 snapshot 이후 로컬 변경(커밋 없음). RQ-39 / D-45 / T-109~114. 실제 모델·장비·Jira 실행 없음.

## 구현

경로 중첩 트리·검색/유형 필터/표시 정렬, TC 행 드래그와 번호 없는 위아래 대체 버튼, 설정 전체 접기, TC 패널 숨김/240~600px 경계 드래그 및 키보드 크기 조절. 브라우저에 패널 상태를 저장한다. 목록 정렬과 실행 순서를 구분하며 필터 밖 선택은 보존한다.

실패 결과 행에서 단일 TC 재실행: 원본 snapshot/parent_run_id를 사용하는 새 Run, 원본 결과 보존, 기존 Preflight·예약·선행 조건 유지. 부분 재실행은 Dashboard 전체 결과를 변경하지 않는다.

usage.py의 구조화된 모델/provider별 누적값 검증/집계, Attempt JSON 영속화, worker callback 및 최종 usage 수집, progress와 TC 결과의 11px 표시. 중복/오래된 snapshot을 거부하며 미집계 비용은 null이다. 기존 DB 테이블 변경 없음. Mock는 모델 호출이 없고 기존 기록은 집계 없음으로 표시된다. 실모델 계량 어댑터는 미연동이다.

## 검증 결과와 한계

- GUI Python 시험 **69 PASS**: [출력](20261101-tc-workspace-evidence/pytest.txt). 실패 TC 단독 재실행/원본 보존, 복수 모델 입력·출력·비용, null 비용, 잘못된 값, snapshot 중복/순서, 완료 중복, DB 재열기 포함.
- Dashboard/단독 TypeScript+Vite 빌드 **PASS**: [출력](20261101-tc-workspace-evidence/build.txt).
- Chrome 직접 검사: network/dual 중첩 검색으로 1/5 표시, 이름 내림차순에서 02_smoke→01_boot, 필터로 실행 순서 불변. 설정 전체 접기 시 목록 유지, 펼침 후 Suite 입력 보존.
- TC 행의 실제 마우스 드래그로 02_smoke를 01_boot 앞으로 이동 확인. 위아래 버튼도 실행 순서를 변경하며 Preflight 해제 확인. 순서 번호 없음. 이전 완료 Run 결과는 불변.
- FAIL 데모 Run 54745a2ddb91…에서 02_smoke만 새 Run e05a37a1760f…로 실행해 1/1 PASS. 원본 이력 다시 선택 시 COMPLETED FAIL 유지. 새 Run의 progress/TC 행에 모델 호출 없음 확인.
- 패널 키보드 너비 300→320, 경계 마우스 드래그 320→400 확인. 숨긴 뒤 새로고침에서도 숨김 유지, 복원 시 너비 유지.
- 375px 검사 중 결과 표의 화면 밖 넘침 발견. 결과 표 내부 스크롤/내부 grid 최소폭을 수정하고 재빌드했다. 최종 화면 증거: [desktop](20261101-tc-workspace-evidence/desktop.png), [narrow](20261101-tc-workspace-evidence/narrow.png).
- 격리 Playwright 자동 전체 시험 **BLOCKED**: gui_test/demo/browser_e2e.py의 socket.bind에서 PermissionError [Errno 1] Operation not permitted. 추가 GUI-UI-05~08 자동 시험은 작성했지만 이 환경에서 실행 완료로 기록하지 않는다. 직접 Chrome 확인으로 자동 전체 PASS를 대체하지 않는다.
- 실제 모델별 청구값/실장비/Windows 실제 인수 **NOT_RUN**. 숫자 계량은 Python fixture로 검증했으며 현재 화면에 가상 모델 비용을 넣지 않았다. 운영 baseline NONE 유지.

## 최초 실패와 수정

1. 새 트리의 TypeScript optional target null 좁히기 오류: optional access로 수정, 두 빌드 PASS.
2. 최초 Python: 68 PASS / 1 FAIL. 재시작 시험이 runtime root 대신 DB parent를 make_manager에 전달하여 다른 DB를 열었다. 동일 Store 경로를 Manager로 다시 열도록 시험 fixture 수정(검증 강도 유지). 동일 GUI 전체 재시험 69 PASS.
3. 첫 좌표 드래그는 순서가 바뀌지 않았다. 스크롤 후 현재 행 위치를 다시 관찰하고 행 텍스트에서 드래그해 성공했다. 기능 성공으로 잘못 기록하지 않았다.

서버는 bash run.sh로 재시작했으며 Chrome에서 최신 UI 및 API 연결됨을 확인했다. `.runtime`에 확인용 Mock Run 두 개가 추가됐다. 기존 운영 Job/장비에는 영향 없다.

2026-11-01 추가 UI 정리: 별도 재실행 열을 제거하고 현재 결과의 FAIL 배지 바로 옆에 작은 Retry 버튼을 표시한다. 접근성 이름은 TC명 재실행으로 유지하며 동작·원본 보존 규칙은 동일하다.

최종 UI 확인: 별도 재실행 열 없음, 현재 결과 셀 텍스트 FAILRetry, 열 목록 TC/유형/현재 결과/Attempts/토큰·비용. 검색 패널 전환은 36px 아이콘+툴팁으로 변경했다. 최종 375px document.scrollWidth=375, 결과 표 내부 content=502/client=247로 페이지 넘침 없이 표만 스크롤된다. [소스 해시](20261101-tc-workspace-evidence/source-manifest.json), [문서 검사](20261101-tc-workspace-evidence/docs.txt).
