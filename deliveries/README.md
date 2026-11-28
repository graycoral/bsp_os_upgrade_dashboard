# 회사 전달 폴더

Windows에서 기존 커넥터 작업을 강제로 중단하려면 [단일 종료 스크립트](connector-recovery/stop-board-connector.py)를 해당 PC에 복사하고 PowerShell에서 `py -3 .\stop-board-connector.py`를 실행한다. 실행 중인 시험이나 퓨징도 중단될 수 있다. 기본 Profile home을 자동으로 찾고 사용자 지정 설치에는 `--home`을 사용한다. `FORCE_STOPPED`가 출력되면 해당 설치본의 로컬 종료가 확인된 것이다. [부분 종료와 재시도](../docs/gui_test/FORCE_STOP.md)

| 버전 | 복사 기준 |
|---|---|
| 현재 · 찾아보기 안내와 TC 경로 저장·목록 갱신 · PORT-019 포함 · `190e350` | [복사할 폴더와 검증값](company-handoff-190e350/00_START_HERE.md) · [동작 변경 목록](company-handoff-190e350/BEHAVIOR_CHANGES.json) |
| 직전 공식본 · PORT-018 제한망 감시·퓨징 확인·프로젝트 조회 · `7691c0e` | [복사할 폴더와 검증값](company-handoff-7691c0e/00_START_HERE.md) · [동작 변경 목록](company-handoff-7691c0e/BEHAVIOR_CHANGES.json) |
| 이전 · Test 현황의 Windows 실행기 판정 수정 · `6e65521` | [복사할 폴더와 적용 절차](company-handoff-6e65521/00_START_HERE.md) · [변경 경로·전후 SHA-256](company-handoff-6e65521/MANIFEST_DELTA.tsv) |
| 이전 · PORT-017 회사 CLI·직결 Run 인수 · `9f91123` | [복사할 폴더와 검증값](company-handoff-9f91123/00_START_HERE.md) · [변경 경로·전후 SHA-256](company-handoff-9f91123/MANIFEST_DELTA.tsv) |
| 이전 · PORT-016 웹 퓨징 설정 · `14634ed` | [복사할 폴더·검증·회사 적용](company-handoff-14634ed/00_START_HERE.md) · [이전 버전 대비 변경 경로](company-handoff-14634ed/MANIFEST_DELTA.tsv) |
| 이전 · `8abe926` | [기존 전달·복구 자료](company-handoff-8abe926/00_START_HERE.md) |

일반 개발 커밋과 회사 전달 버전은 별도로 관리한다. 같은 버전을 배포할 때는 검증된 폴더를 재사용한다. 회사에 새 버전을 전달할 때는 새 폴더에서 export·검증하고 이전 폴더를 복구용으로 유지한다.
