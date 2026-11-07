# 작업별 문서 읽기와 회사 이식 절차 문서 검증

- 기준 HEAD: `1cd6ce8e595644b6ec04552b8e1a8ec2e67faff3`
- 대상: 위 HEAD와 2026-11-07 현재 uncommitted docs-only diff. 파일 변경 범위는 `git status --short` 및 `git diff --stat`에서 확인한다.
- 독립 리뷰: Sol high 리뷰 APPROVED. 최초 P2는 회사 적용 비교 기준에서 기존 미반영 변경 누락 위험이었다. `docs/porting/README.md`와 `docs/porting/templates/APPLIED_TEMPLATE.md`에 선택 기능의 마지막 적용 기준, 관련 변경 목록의 완전 반영 기준, 미반영 변경 합집합 재대조를 보완했다. 리뷰는 문서 검토이며 제품/회사 실행이 아니다.
- 이 실행은 문서·링크·추적성 검사만 다룬다. BSP 제품시험, Linux/장비/CLI/Jira 인수, 회사 저장소 실행은 하지 않았다.

## 실행 결과

| 검사 | 실제 명령/방법 | 결과 |
|---|---|---|
| 문서 validator (기록 생성 전 예비 실행) | `python -X utf8 docs/testing/validate_docs.py` stdout/stderr를 `.local-reports/scoped-doc-validation-20261107-01/validate_docs.*.txt`에 직접 리디렉션 | PASS, exit 0; 상대 링크 1,149, 요구사항 61, 시험 사례 217, NOT_RUN 75, 오류 0 |
| 문서 validator (이 실행 기록 생성 후 최종 재실행) | `python -X utf8 docs/testing/validate_docs.py` | 아래 최종 재실행 참조 |
| 공백 검사 | `git diff --check` | 아래 최종 재실행 참조 |
| 문서 지도 heading 보존 | HEAD와 working tree의 Markdown heading 목록 비교 | 기존 heading 7개 중 7개 보존, 같은 순서 |
| WORK_STATUS 원문 | `git show HEAD:docs/implementation/WORK_STATUS.md`와 현재 파일 비교 | 추가된 현재 요약/이번 정리 항목/문서 지도 이력 보존 항목을 제외한 기존 내용 보존 및 순서를 확인했다. (신규 삽입 위치 허용, 원문 삭제 여부 확인) |
| AGENTS 운영 불변 범위 | HEAD와 현재 파일의 `바꾸면 안 되는 운영 정책`, `구현 절차`, `회귀 방지와 완료 조건`, 사용자 확정 예외와 D-40/D-42/D-48 예외 섹션 비교 | 변경 없음 |
| 신규 링크 fragment | `docs/README.md`의 WORK_STATUS fragment를 대상 heading과 대조 | `2026-11-07--문서-지도-이력-보존`이 `2026-11-07 · 문서 지도 이력 보존` heading에 대응함을 확인했다. |
| 대표 읽기 경로 | 문서 지도, Runner, plugin, 회사 이식 경로의 상호 문서 링크와 필수 원문 지침 확인 | Git/docs/Runner/plugin/company 경로가 관련 문서로 이어지며 원본 문서 전체를 반복 필수 읽기로 두지 않는다. 이는 문서 경로 확인이지 제품 검증이 아니다. |

## 크기 측정

`docs/README.md` HEAD/current 바이트와 줄 수 및 `docs/implementation/CURRENT_STATUS.md` 바이트는 아래 최종 수치를 참조한다. 토큰 절감량을 추정하거나 전체 토큰 실측으로 표현하지 않는다.

## 미실행 범위

제품 단위·통합 시험, BSP 연결, Linux 빌드/인수, 장비 시험, CLI 추론, Jira, 회사 저장소 적용은 실행하지 않았다 (`NOT_RUN`). 이 문서 검사로 제품 PASS나 회사 인수 완료를 주장하지 않는다.

## 최종 재실행 및 수치

중간 검사에서는 WORK_STATUS가 생성 전 실행 기록을 참조해 링크 오류 1건으로 실패했다. 기록 파일을 생성한 후 아래 최종 재실행은 통과했다.

기록 파일 생성 후 `python -X utf8 docs/testing/validate_docs.py`: PASS, exit 0, relative_links_checked 1151, requirements 61, test_cases 217, not_run 75, errors 0. `git diff --check`: PASS, exit 0. 표준 출력·오류와 종료 코드는 `.local-reports/scoped-doc-validation-20261107-01/final-validator.*` 및 `final-diff-check.*`에 보존한다. validator는 문서 추적성 검사이며 제품시험을 포함하지 않는다.

HEAD 기준 `docs/README.md`: 13,157 bytes / 104 lines. 현재: 5,926 bytes / 55 lines. 기존 heading 7개는 순서대로 모두 유지됐다. `docs/implementation/CURRENT_STATUS.md`: 1,398 bytes. WORK_STATUS의 기존 381줄은 추가된 요약·이번 작업 기록·지도 이력 보존 항목의 삽입을 허용한 뒤 순서 보존을 확인했다. AGENTS의 운영 정책, 구현 절차, 회귀 방지 및 D-40/D-42/D-48 예외는 HEAD 대비 동일하다. 새 fragment는 대상 heading의 GitHub Markdown slug와 일치한다.

토큰 절감 추정이나 전체 token 실측은 하지 않았다. 회사 저장소 적용, BSP 제품시험, Linux/장비/CLI/Jira 검증은 모두 NOT_RUN이다. 독립 Sol 리뷰는 APPROVED이며 실제 제품/회사 검증 승인을 의미하지 않는다.
