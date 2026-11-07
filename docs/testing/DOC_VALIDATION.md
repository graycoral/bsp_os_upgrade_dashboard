# 문서 품질 확인

검사일: 2026-10-11. 범위: 인수인계 문서. 제품 코드·외부 연동·Claude 리뷰 검증 아님.

실행: 저장소 루트에서 `python3 docs/testing/validate_docs.py`.

확인 항목: 상대 문서 링크 존재, 요구사항/시험 연결, 시험 ID 중복, 목록과 결과 CSV 일치, 결과 상태 유효성, PASS/FAIL의 필수 근거 필드, AGENTS/CLAUDE 진입점 존재.

결과: PASS. 요구사항 27개, 시험 60개, 제품 시험 NOT_RUN 60개. 실제 실행 출력은 [문서 검사 기록](runs/20261011-doc-validation.md)에 보존한다.

내용 검토: 분석 게이트 예외·최초 확인·선행 그룹 전체 완료·수정/빌드 배타·수동 시험·도구 전환·Jira 의존 대기 정책을 문서에 반영했다. 자동 검사는 의미적 정합성 전체를 보장하지 않으며 Claude 독립 검토는 NOT_REVIEWED다.

## 2026-10-12 구현·정책 변경 후 검사

`python docs/testing/validate_docs.py`: PASS. 요구사항 28개, 시험 목록 67개와 CSV 행 일치, 상대 링크 78개 확인, 오류 없음. 의존성 설치 폴더와 runtime은 문서 검사 대상에서 제외한다. 이것은 문서 정합성 검사이며 제품 자동 시험 78개 및 브라우저 3개 PASS와 별도다.

## 후속: 키 없는 진입·외부 에이전트 계약 정리

`python docs/testing/validate_docs.py`: PASS. 요구사항 29개, 시험 목록/CSV 70개 일치, 전체 인수 NOT_RUN 60개를 보존했다. [검사 출력](runs/20261012-entry-agent-evidence/doc-validation.json)에 링크 개수와 결과를 기록한다. 새 에이전트 계약의 JSON 예시 6개와 필드/해시 형식도 확인했다. [실행 기록](runs/20261012-local-entry-agent-contract.md)을 참고한다. 실제 외부 에이전트가 보낸 결과나 Claude 독립 검토의 증거는 아니다.

## 후속: 오케스트레이터 역할·보고 v2 설계

요구사항 34개, 시험 목록/CSV 85개로 확장했다. 신규 T-71~85는 NOT_RUN이며 기존 70개 결과는 유지했다. 오케스트레이터/모듈 두 전용 명세의 JSON 예시 8개, 현재/목표 계약 구분, 권한/보류/중복 규칙과 관련 문서 링크를 확인했다. [문서 전용 실행 기록](runs/20261012-orchestrator-docs.md)에서 최종 검사 출력과 파일별 내용을 확인한다. 제품 코드/DB를 바꾸거나 제품 시험을 다시 실행한 작업이 아니다.

## M0 수동 Claude 패키지 후속

요구사항은 35개, 시험 목록/결과 CSV는 91개다. 실제 agent 파일/사용 안내/수동 프로필·예시와 현재 자동 연동 미지원 표시를 검사한다. 제품·패키지 시험 및 문서 검증은 [새 실행 기록](runs/20261012-claude-agent-package.md)에 구분하여 남긴다. 이전 34개/85개 검사는 당시 문서의 기록으로 보존한다.

소스/브리지 기본값 변경 이후 요구사항 36개, 시험 목록/CSV 95개다. [새 실행](runs/20261012-settings-defaults.md)에서 새 설정·기존 회귀와 문서 정합성을 검증한다.


D-42의 RQ-37/T-96~102 및 관련 문서 링크·결과 CSV는 [내장 연결 실행 기록](runs/20261012-native-cli.md)의 doc-validation.json으로 검증한다. CLI/빌드 연결 구현과 실제 Linux 인수를 구분하고 새로운 기본값 때문에 기존 브리지 호환 문서/이력을 삭제하지 않는다.

## 2026-11-02 최종 GUI Test 요구사항 정리

RQ-39~43/시험118개를 UI·반복·대상·모델 사용량·Retry로 연결하고 중복된 중간 UI 설명을 현재 계약으로 정리했다. 정확한 결과는 [게시 검사 출력](runs/20261102-publication-evidence/docs.json)과 [실행 기록](runs/20261102-publication.md)을 따른다. 실제 연동 인수/Claude 검토와 구분한다.

## 2026-11-07 작업별 문서 읽기 / 회사 이식 절차

기준 HEAD `1cd6ce8e595644b6ec04552b8e1a8ec2e67faff3`와 미커밋 docs-only 변경을 검증했다. `python -X utf8 docs/testing/validate_docs.py`는 문서 실행 기록 작성 후 PASS, exit 0 (상대 링크 1,151, 요구사항 61, 시험 사례 217, NOT_RUN 75, 오류 0)이다. `git diff --check`도 exit 0이다. 문서 지도 기존 heading 7개 보존, WORK_STATUS 기존 내용 381줄의 순서 보존, AGENTS 보호 운영 섹션 불변, 신규 fragment 연결을 별도로 확인했다. HEAD/current 문서 지도는 각각 13,157 bytes/104 lines, 5,926 bytes/55 lines이며 CURRENT_STATUS는 1,398 bytes다. 상세 명령·로그는 [실행 기록](runs/20261107-scoped-document-reading.md) 및 `.local-reports/scoped-doc-validation-20261107-01/`에 있다. 독립 Sol 리뷰 APPROVED. 제품시험·Linux/장비/CLI/Jira 및 회사 저장소 적용은 NOT_RUN이며 이 문서 검사는 해당 인수 증거가 아니다.
