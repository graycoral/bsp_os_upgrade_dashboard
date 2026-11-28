# 문서 정리 계획과 보존 기준

| 필드 | 내용 |
|---|---|
| source_repo/source_commit | graycoral/bsp_os_upgrade_dashboard · `457587d3b4b5ecb2526db39b3c420803d85d8874` |
| source_commit | `457587d3b4b5ecb2526db39b3c420803d85d8874` · `git rev-parse HEAD origin/main` 결과 일치, 최초 `git status --short --branch`는 깨끗한 `porting/copy-ready-20261122` |
| target_repo/target_commit | N/A |
| scope | 문서 동선·이식 안내·계약과 소비자. 원본 감사에서는 분류·제안만 수행 |
| changes | 이 감사 문서 신규 작성. 제품·DB 변경 NONE |
| package_release | 제품 전달용 NONE. UI 제외 시험용 `ce29893244d4a68c90d6f47efb734ce08dd447938290b759042bcb20b2e04ae5` |
| evidence / execution_evidence | 2026-11-22 Darwin arm64 · Python 3.11.7 · pytest 9.1.1. 선정 시험 18 PASS, 1 SKIPPED. 원본 문서 검사 2,122링크·81요구·304시험·90 NOT_RUN, 오류 0. 명령·로그는 [실행 근거](IMPLEMENTATION_HANDOFF.md#실행-근거) 참조 |
| open_questions / unknowns | 회사 적용 기준·서비스 소유자·인증·wheel 공급원·Windows 장비는 TARGET_UNKNOWN. 회사 적용 담당자가 04에서 확인. 실장비 T-305 NOT_RUN |
| next_task | 02에서 PORT-011과 진입 문서를 정리한 뒤 링크·앵커·pin·시험/실패 이력을 검증. 03은 정리된 계약을 사용 |

`git ls-tree -r --name-only HEAD docs` 기준 Markdown 217개. 아래 숫자는 추적된 Markdown의 상대 링크를 파일 기준으로 정규화한 고유 유입 문서 수다. 직접 코드·빌드 소비자는 별도로 확인했다. 기록 전체를 삭제 대상으로 평가하지 않고 이식 진입 동선과 관련 문서만 내용 검토했다.

| 검토 문서와 분류 | 정본·호출 참조 | 보존 이유·현행과 이력 차이 | 삭제/이동 위험과 02 작업 |
|---|---|---|---|
| `AGENTS.md` KEEP | 저장소 정책 정본, 5개 문서에서 호출. Claude·portable-feature가 직접 참조 | 운영 예외·장비 승인·단일 실행·검토 주체 | 높은 위험. 원문 유지, 회사 진입 동선만 porting으로 |
| `CLAUDE.md` KEEP | 검토 역할·결과 정본, 3개 문서. `backend/adapters/native.py:114`에는 지침 이름이 사용됨 | 원본 개발/회사/제품 런타임 역할을 구분 | 높은 위험. 전역 정책을 재복제하지 않고 AGENTS·회사 절차 링크 유지 |
| `.agents/skills/portable-feature/SKILL.md` KEEP | AGENTS와 CLAUDE 및 porting 문서에서 직접 호출 | 재사용 코드·host adapter·회사 기록 규칙 | 파일 경로와 상대 링크 보존 |
| `docs/README.md` MERGE (중복 문단) | 작업별 지도 6개 문서에서 유입, 기준선 30~44행 | 11행 ZIP·17행 명령 미구현은 과거 시점. 11~27행 날짜별 완료 상태가 코드와 시점이 다름 | 경로·외부 anchor를 유지하며 현행 1행 링크와 날짜 있는 이력으로 축약 |
| `docs/porting/README.md` MERGE (진입 설명) | 회사 적용 절차·templates·PORT index의 정본, 유입 15. 46~54행 소유권, 81~105행 적용 순서 | 3~31행 여러 날짜의 “최신” pin·ZIP, 회사 예시 포트. 현재 전달 판정은 새 manifest/실행 결과에 연결 | 과거 SHA/선행/날짜와 기존 heading을 보존. 회사 신규 담당자는 적용된 PORT → 매핑·APPLIED → 필요한 제품 접점 |
| `docs/porting/PORT-007.md` KEEP | 유입 27. 3~17행이 PORT-011 명령·소유권과 중복 | RQ-60 단일 서비스·SDK·기존 적용/복구의 독립 계약 | 동작 정의는 PORT-011/013으로 링크하고 버전별 증거 보존 |
| `docs/porting/PORT-009.md` KEEP | 유입 30. Windows GUI 계약·launcher; 68~81행 일반 GUI와 선택 CLI 분기 | 기존 미러·PuTTY·복구·고정 코드 각자 소비자 있음 | Windows 운영자 안내는 GUI 가이드로. embedded CLI 이력 혼합 금지 |
| `docs/porting/PORT-011.md` MERGE/ARCHIVE (문단) | 유입 17. 13~24·52~90행의 고정 ZIP/업데이트 사례 및 118행 아래 최초 설계 | 실제 현재 구현 `plugin_delivery.py:39`, `plugin.py:83`는 direct + 폴더. 현행 사용 예시 66행 .zip과 67~68행 direct file sync/push는 혼선을 유발 | 같은 파일과 연결 가능한 anchor를 보존하고 날짜·고정 bytes·SHA·시험은 이력에 배치. 새 사용법은 실제 지원 명령 및 새 폴더 |
| `docs/porting/PORT-012.md` KEEP | 유입 11. 회사 module callback 정본. 3행 미커밋은 11/18 시점, `git log -- backend/services/module_catalog.py`에서 `14e6402` 확인 | 원본 고정 소스·회사 미구현 여부가 서로 다름. 코드 1개 이력만으로 모든 변경의 pin을 교체할 수 없음 | 당시 WIP 표현에 날짜/범위 표시. 회사 T-290 및 원래 기준 보존 |
| `docs/porting/PORT-013.md` KEEP | 유입 12. 4~7행 원본 pin·선행 009/011/012, 9~28행 direct·DB·복구·D-48·T-305 | Node 공급자 빌드와 회사 UI 수정 시 재빌드의 조건을 구분. 실제 Windows/Linux 인수는 별도 | `b71653b` + `85f7f05` 유지. “검토됨”과 개별 리뷰 미수행은 당시 세션·대상 구분 |
| `docs/porting/PORT-014.md` KEEP | 유입 3. 3~9행 `ed6a6f0`·`3e6e4a8`·`d83cc11`, 20~24행 포트 계약 | 회사별 포트는 현지 값 확인, 8765/8766/8771의 역할 보존 | 새 묶음 SHA로 역사적 pin을 덮어쓰지 않음 |
| `docs/gui_test/TEST_BOARD_CONNECTOR_GUI.md`, `BOARD_CONNECTOR_BUNDLE.md`, `RUN_AND_DIAGNOSE.md` KEEP | 운영자 GUI 가이드 유입 31. GUI와 embedded CLI·진단은 용도별. `tests/portable_runner_smoke.py:243`이 진단 가이드 hash를 검사 | Windows GUI와 별도 ZIP CI의 소비자를 보존 | `.github/workflows/gui-test-windows-build.yml:9`가 docs/gui_test 변경을 감시. 물리 이동 시 packaging·CI 재검증 필요 |
| `docs/implementation/CURRENT_STATUS.md`, `WORK_STATUS.md`, `IMPLEMENTATION_PLAN.md` KEEP | 요약/누적 증거/계획 각각 정본. 현재 상태 유입 6. 문서 지도·AGENTS 진입 | 날짜별 과거 WIP·다른 코드 및 환경의 PASS와 실패가 보존 대상 | 현행 조치와 이력만 표식 구분. 실패/NOT_RUN 문장 삭제 금지 |
| 요구사항·결정·상태/에이전트 계약·회귀·시험 목록·CSV·`docs/testing/runs/` KEEP | `docs/testing/validate_docs.py:13`~24가 REQUIREMENTS·TEST_CATALOG·TEST_RESULTS.csv의 ID/근거 열 대조. 11/18 TC 전달 기록 유입 5 | 원래 pin/시험 실패·재검증과 시점별 ZIP bytes, 독립 검토 범위의 원증거 | `docs/testing/runs/20261118-tc-list-delivery.md`와 `20261119-direct-connector-implementation.md` 보존. 과거 452+212 PASS와 현재 PASS를 분리 |
| `docs/porting/templates/`, 나머지 PORT와 상세 설계·그림 자료 KEEP | porting README·계약·help에서 필요한 기능만 참조, `delivery.py:50`이 일부 문서 트리를 공급 | COMPANY_MAP/APPLIED는 회사 생성 양식. 그림·정책 자료는 이식 과정의 중복으로 입증되지 않음 | 이동·삭제 제안 없음 |
| 파일 단위 ARCHIVE/DELETE_CANDIDATE | 후보 없음 | 링크 수가 0이어도 명령·코드·CI·외부 북마크가 소비할 수 있음 | 근거 없는 삭제 금지. 이력 단락 ARCHIVE는 같은 파일에서 날짜별로 보존 |

**검증 순서.** ① 기준 pin에서 상태·SHA/ID·내부 anchor·실패·NOT_RUN 위치 목록을 기록한다. ② ZIP/폴더와 direct/legacy 명령의 현행 단일 안내를 만들고 진입점의 링크를 바꾼다. ③ `python3 docs/testing/validate_docs.py`와 `git diff --check`를 수행한다. 검증기는 `validate_docs.py:9`에서 fragment를 제외하므로 변경된 anchor의 heading/별칭과 skill 상대 링크는 별도로 조합해 확인한다. ④ `.github/workflows/gui-test.yml:36`·84행 CI의 빌드/시험 및 문서 hash 소비자를 대조하고 원래 실패·NOT_RUN·pin 누락을 diff로 확인한다. 복사 범위 내 문서가 바뀌면 byte release도 달라지므로 03에서 최종 문서 상태로 export한다.
