# 다이어그램 탭 문서 작성·검사 · 2026-11-03

- run_id: 20261103-workflow-diagram-docs
- 작성/검사: Codex. 독립 검토: NOT_REVIEWED.
- 기준 HEAD: `e86c5cbbf53cd360a1b90eafcc1c37b050e3659e` + 이번 미커밋 문서 변경. 제품 코드 검증 기준으로 사용하지 않는다.
- 환경: Windows PowerShell. 저장소 .venv Python은 아래 실행 파일 누락으로 실행 불가였다. 코드·DB·서비스·외부 연동 변경 없음.
- 승인 범위: 문서 작성만. RQ-50 / D-51 / T-144~149 / [설계](../../design/WORKFLOW_DIAGRAM.md) / [이식 초안](../../porting/PORT-001.md).

## 변경 범위

상위 가로 연결, 그룹별 IP 접기/펼치기와 5단계, 현재 단계·서버 진행률·상태 점·진행 화살표 효과를 정의했다. 전용 폴더/adapter/기존 탭 연결, 기존 정책 보존, ACON 미확인과 API 연결의 구분, 서버 빌드 단계 보존 제안을 기록했다. 코드 경로는 예정이며 폴더/제품 시험은 생성하지 않았다.

요구사항·결정·UI/시스템 구조·구현/시험 계획·시험 목록/CSV·진행 기록·문서 지도·porting 목록을 함께 갱신했다. 기존 시험 결과와 실패 이력, 미추적 `docs/diagram-design-20261103/`·`docs/system-diagram-20261103/` 산출물은 수정하지 않았다.

## 검사

- 최초 시도: `.\.venv\Scripts\python.exe -X utf8 docs/testing/validate_docs.py`는 가상환경이 참조하는 `C:\Users\grayc\AppData\Local\Programs\Python\Python313\python.exe` 누락으로 실행하지 못했다. 표준 Python 검사기 실행은 BLOCKED(로컬 환경)이며 제품 결함/시험 실패로 처리하지 않는다. 설치나 가상환경 수정은 하지 않았다.
- 대체 검사: 기존 `validate_docs.py`를 읽고 Windows PowerShell 세션에서 동일 범위의 Markdown 상대 링크, 요구사항/시험 연결, 시험 ID 중복, CSV 순서·허용 상태·PASS/FAIL 근거 필드를 검사했다. `Get-Content -Encoding UTF8`, 정규식, `Test-Path -LiteralPath`, `Import-Csv`로 확인했으며 AGENTS.md/CLAUDE.md도 읽어 존재를 확인했다. 종료 코드 0, 아래 결과 PASS. Python 검사기가 실행된 것으로 보고하지 않는다.
- `git diff --check`: PASS(종료 코드 0). 변경 파일은 문서만이며 미추적 기존 산출물은 보존했다.
- 신규 제품 시험 T-144~149: **NOT_RUN**. 빌드·브라우저·모의 실행·회사/ACON 실제 연결 시험은 수행하지 않았다.
- 운영 정상 기준과 제품 검증 상태는 이번 문서 검사로 승격하지 않는다.

```json
{
  "status": "PASS",
  "checker": "PowerShell equivalent of validate_docs.py",
  "relative_links_checked": 568,
  "requirements": 50,
  "test_cases": 149,
  "not_run": 87,
  "errors": []
}
```

## 남은 범위

구현 지시를 받은 뒤 정확한 화면 입력 형식·의존성·ACON 상태 근거·회사 접점을 확정한다. 로컬 시험과 코드 커밋을 고정한 후 PORT-001을 전달 준비 상태로 갱신한다. 실제 회사 적용/인수는 회사 기록으로 별도 관리한다.
