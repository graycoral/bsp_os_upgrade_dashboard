# 2026-11-01 설정·반복 실행·탐색기형 목록·실행 대상

실행 ID 20261101-repeat-settings / Codex / macOS Python 3.11.7 + Chrome / RQ-39~41 / D-46 / T-115~118. 로컬 소스 변경, 미커밋. SQLite 테이블 변경 없음. 추가 JSON 필드: Run plan/slot_results/tc_repeats/cycles, Attempt slot_index/cycle/iteration/execution_target, Suite tc_repeats/cycles.

## 변경과 검증

- 설정: 소스/Suite/연결/실행을 톱니바퀴 탭으로 이동. 기본 결과 화면에 Preflight/시작 유지. 입력 unmount 없음. 명시적 돌아가기, 톱니바퀴 재클릭, Esc로 복귀 및 결과 탭 포커스 확인. sourceInCatalog=0/suiteInCatalog=0, 설정 안에서는 각각 1.
- TC별 횟수: 기본1, 아이콘 클릭 시 입력, 변경된 값만 ×N. 전체 목록 반복은 실행 설정. 1~100 정수/총10,000 한도, Suite와 Preflight snapshot에 반영.
- 고정 plan: 전체 회차마다 TC별 반복. 오류 복구는 같은 slot 재시도이고 진행률 중복 증가 없음. 이전 반복 FAIL은 이후 PASS로 지우지 않음. 종료 전 취소는 INCOMPLETE. 이전 plan 없는 Run과 기존 DB 읽기 유지.
- Chrome 실제 Mock 실행 `aed27d3fb9564fa5800945a7189dd0ac`: 01_boot=2,02_smoke=1,cycles=2 → plan/Attempt 6개, progress 6/6, PASS5/FAIL1, 01_boot 종합 FAIL/02_smoke PASS. 이후 회차의 PASS에도 초기 FAIL 보존.
- 작은 목록: 모든 기본 TC 행 bounding height=32px 측정. 이름·유형·시간을 한 줄에 표시, 편집 때만 반복 입력 확장. 정렬 드롭다운 제거. 이름↑ 순서 01_boot/02_smoke/05_observation/04_pair/03_link, 이름↓ 순서 04_pair/03_link/05_observation/02_smoke/01_boot. 선택 실행 순서는 기존 순서를 유지했다. 유형/시간 헤더 토글 및 시간↓ 표시 확인.
- 실행 대상: runner의 구조화된 보고를 Attempt에 저장. local 및 보드 이름(역할별) 표시. board_id/host/COM pin 불일치·완료 후 보고·동일 Attempt 대상 변경 거부. 기존 미기록을 설정값에서 추측하지 않음. 실제 BCM 호출은 없음.

## 시험 증거

- [GUI core/API 출력](20261101-repeat-settings-evidence/pytest.txt): **82 PASS**. 반복 순서·진행률·실패 보존·복구·중단·재시작·한도/타입/ID·Suite·API 422, 대상 이름/로컬/불일치/재열기/과거 미기록 포함. 개발 중 범위 확장에 따라 69→79→80→82 PASS. 새 실행의 최초 자동 실패 없음.
- [두 빌드 출력](20261101-repeat-settings-evidence/build.txt): Dashboard/단독 TypeScript+Vite PASS.
- Chrome 직접 검사 증거: [설정](20261101-repeat-settings-evidence/settings.png), [결과](20261101-repeat-settings-evidence/results.png). UI-09~12 자동 브라우저 회귀도 추가했으나 이전 실행에서 확인한 socket bind 권한 제약으로 격리 전체 자동 E2E는 BLOCKED이다. 직접 확인을 자동 전체 PASS로 바꾸지 않는다.
- 설정 복귀 결함 REG-0013: 결과 탭 클릭은 정상이나 톱니바퀴 재클릭은 복귀하지 않아 사용자가 막힌 것으로 인식했다. 명시적 복귀 버튼과 toggle/Esc 추가, 3경로 직접 확인. 소스는 [manifest](20261101-repeat-settings-evidence/source-manifest.json).
- 직접 자동화 중 hidden 패널의 입력에 Escape를 보낸 1회 시도는 no_visible_match였다. 표시된 돌아가기 버튼에서 Escape 재검사 성공. 제품 실패와 검증 대상 선택 실패를 구분한다.
- 서버는 활성 Mock Run 없음 확인 후 bash run.sh로 재시작. 실제 모델 계량·실보드/BCM·Windows 인수는 NOT_RUN, baseline NONE 유지. Python은 GUI 영역만 재시험했으며 이전 전체 284 PASS를 현재 전체 PASS로 재사용하지 않는다.

최종 후속 확인(2026-11-02 KST 세션까지 이어짐): 최신 서버에서 새 Mock Run COMPLETED PASS, 결과 상단 `실제 실행 대상 local · Mock · 실보드 미연결`, TC 5개 행 모두 `local` 표시 확인. BCM 보드 이름은 Python의 pin 일치 fixture로 검증했으며 실제 BCM 인수는 NOT_RUN이다. 문서 검사는 41 요구사항/118 시험/330 상대 링크 PASS.
