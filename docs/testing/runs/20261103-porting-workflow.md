# 2026-11-03 회사 이식 절차 문서 검증

- run_id: 20261103-porting-workflow
- scope: documentation
- executor: Codex (주 작업자), 독립 Claude/OpenCode 검토 NOT_REVIEWED
- decision: DEV-PORT-01 (개발 전달 절차; 제품 RQ/T 변경 없음)
- base_revision: 31ad210b246c83455b978c705bb57c96ebde3861
- branch: docs/company-porting-workflow
- environment: Windows PowerShell, Python 3.13.5 (UTF-8 모드)
- code_revision / test_revision: 위 기준과 동일한 제품 코드·문서 검사기. 이 문서를 추가한 커밋의 문서 변경을 검사한다.
- 변경 내용: 이식 절차·요청문, 기능 안내·회사 구조·적용 이력 양식, 지침/문서 지도/변경 규칙/진행·계획·결정 연결.

## 검사 목록과 결과

| ID | 검사 | 결과 | 근거 |
|---|---|---|---|
| DOC-PORT-01 | 문서 상대 링크·RQ/T 추적·기존 결과 형식 | PASS | [검사 출력](20261103-porting-workflow-evidence/doc-validation.json) |
| DOC-PORT-02 | 원본/회사 저장 위치·읽기 순서·재사용·기준/부분 적용·시험/운영 경계 수동 대조 | PASS | 아래 주 작업자 대조 기록. 독립 리뷰 아님 |
| DOC-PORT-03 | 변경 범위·공백 오류·제품/기존 결과 보존 | PASS | [변경 범위·파일 SHA256](20261103-porting-workflow-evidence/scope.json), git diff --check |

실행 명령: `python -X utf8 docs/testing/validate_docs.py`, `git diff --check`, 변경 파일 목록과 내용 검토. 제품 시험은 문서 변경 범위상 이번 실행에서 NOT_RUN이며 과거 PASS를 재사용하지 않는다.

DOC-PORT-02 대조: 원본의 기능 안내와 회사의 구조/이력 저장 위치를 분리했고, 양식에 실제 회사 데이터나 가짜 적용 결과가 없다. AGENTS/CLAUDE의 회사 이식 경로가 공통 절차와 일치한다. 코드·시험 재사용, 선행 조건·고정 기준, 부분 적용, 데이터 호환·복원, 회사 회귀·독립 리뷰, 실제 운영 별도 지시를 확인했다. 기능별 PORT는 미발행임을 안내와 요청문에 명시했다.

최초 문서 검사 PASS 후 실행 기록·증거 링크 추가에 따라 최종 검사를 다시 수행했다. 최종 출력은 위 JSON에 기록한다. 기존 제품 요구사항/시험 목록·결과 CSV와 과거 실행 기록은 변경하지 않았다. 변경 문서의 내용 기준은 scope.json의 파일별 SHA256과 dirty_diff_hash로 식별한다(증거 파일 자체는 해시 대상에서 제외).

## 범위와 남은 작업

회사 코드에 접근하지 않았다. COMPANY_MAP/APPLIED는 빈 양식이며 회사 적용 이력이 아니다. 실제 기능별 PORT 안내서는 미발행이다. 자동 패키지 생성기나 새 제품 기능을 구현했다고 주장하지 않는다. 원본 저장소의 기존 자동 퓨징 작업과 미커밋 변경은 별도 worktree에 남아 있으며 이 문서 커밋에 포함하지 않는다. 실제 장비/BSP/Jira 실행과 회사 인수는 NOT_RUN이다.
