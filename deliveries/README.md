# 회사 전달 폴더

| 버전 | 복사 기준 |
|---|---|
| 현재 · Test 현황의 Windows 실행기 판정 수정 · `6e65521` | [복사할 폴더와 적용 절차](company-handoff-6e65521/00_START_HERE.md) · [변경 경로·전후 SHA-256](company-handoff-6e65521/MANIFEST_DELTA.tsv) |
| 이전 · PORT-017 회사 CLI·직결 Run 인수 · `9f91123` | [복사할 폴더와 검증값](company-handoff-9f91123/00_START_HERE.md) · [변경 경로·전후 SHA-256](company-handoff-9f91123/MANIFEST_DELTA.tsv) |
| 이전 · PORT-016 웹 퓨징 설정 · `14634ed` | [복사할 폴더·검증·회사 적용](company-handoff-14634ed/00_START_HERE.md) · [이전 버전 대비 변경 경로](company-handoff-14634ed/MANIFEST_DELTA.tsv) |
| 이전 · `8abe926` | [기존 전달·복구 자료](company-handoff-8abe926/00_START_HERE.md) |

일반 개발 커밋과 회사 전달 버전은 별도로 관리한다. 같은 버전을 배포할 때는 검증된 폴더를 재사용한다. 회사에 새 버전을 전달할 때는 새 폴더에서 export·검증하고 이전 폴더를 복구용으로 유지한다.
