# 다이어그램 문서 동작·효율성·연동 리뷰 · 2026-11-03

- review_id / run_id: `20261103-workflow-diagram-review`
- 요청: 새 세션에서 문서를 리뷰하고 판단에 따라 문서 개선. 코드 구현은 계속 금지.
- 기준: main `e86c5cbbf53cd360a1b90eafcc1c37b050e3659e` + 미커밋 RQ-50 문서. 앞선 [작성·검사 기록](20261103-workflow-diagram-docs.md)은 수정하지 않는다.
- 작성·반영: Codex 주 세션. 별도 컨텍스트 리뷰: `fresh_docs_review`(대화 이력 없는 Codex 세션, 파일 읽기만 수행).
- 최초 검토: **CHANGES_REQUESTED**(아래 문서의 동작·연동 기준 부족). 보완 후 별도 세션 재검토: **APPROVED — RQ-50 문서 설계 범위만**, 남은 문서 차단 항목 없음. 구현/제품 시험/회사 인수 승인이 아니다.
- 범위: [설계](../../design/WORKFLOW_DIAGRAM.md), [PORT-001](../../porting/PORT-001.md), RQ-50/D-51, UI·구조·구현 계획 및 T-144~149. 제품 코드 대조는 읽기 전용 정적 분석이다.
- 제품/회사/ACON 시험: **NOT_RUN**. 구현 코드가 없으며 문서 리뷰를 제품 승인으로 사용하지 않는다. 독립 Claude 검토는 수행하지 않았다.

## 코드 대조 근거

| 근거 | 확인한 사실 | 문서에 미치는 영향 |
|---|---|---|
| [main.tsx](../../../apps/web/src/main.tsx) App/refresh | 약 1.8초 polling, online 최초 true, jobs/job/events를 하나의 try/catch로 처리, job의 일부 버전/선택 보호 | 조회 관찰을 추가하고 events 실패·초기 상태·선택 세대/역순 응답을 분리할 예정 접점 필요 |
| [policy.py](../../../backend/domain/policy.py) project/valid/module_done/progress | current_stage는 첫 미완료, RUNNING에도 blocked_reason 가능, 유효 성공 기준과 서버 진행률 | 대기 단계와 실행 단계를 구분하고 게이트/진행률을 프런트에서 재판정하지 않음 |
| [store.py](../../../backend/storage/store.py) save | 저장 때 version과 updated_at을 갱신 | 저장 시각을 최근 조회/heartbeat 시각으로 사용하면 장시간 작업을 오판 |
| [engine.py](../../../backend/domain/engine.py) cancel/claim/finish | 취소 접수와 종료 분리, 이전 Attempt와 현재 결과/유효성 분리 | 취소 중·재시도·이전 성공을 현재 완료로 바꾸지 않음 |
| [hardware.py](../../../backend/worker/hardware.py), [HardwareStatus.tsx](../../../apps/web/src/HardwareStatus.tsx), [자동 퓨징 계약](../../design/AUTOMATIC_FLASH_TEST.md) | 자동 실행은 같은 BSP Attempt의 device_test에 속함; 준비/퓨징/TC와 최종 결과 구분 | Test 부가 표시만 허용, GUI Test 임의 Run이나 퓨징 완료로 Test를 완료하지 않음 |
| [api.ts](../../../apps/web/src/api.ts), [보고 계약](../../design/AGENT_STATUS_CONTRACT.md) | 현재 6개 단계, Data는 any 기반, v1 agent 중간 %/heartbeat 미지원 | 명시적 화면 모델/5단계 표시 변환 필요; 없는 실시간 %를 만들지 않음 |
| [설정](../../../backend/settings.py) ModuleSpec/Profile | 모듈 최대 100개, 이름 최대 80자, boot/main 그룹 | 100개·80자·모두 펼침을 로컬 시험 규모로 설정 |
| [Vite 설정](../../../apps/web/vite.config.ts), [TS 설정](../../../apps/web/tsconfig.json), [package.json](../../../apps/web/package.json), [전역 CSS](../../../apps/web/src/style.css) | React alias/dedupe·외부 폴더 포함·호스트 의존성·전역 선택자 존재 | 폴더만 복사한다고 호환 보장 불가; 격리 호스트와 CSS 양방향 영향을 검사 |

## 발견 사항과 조치

아래 발생 조건은 정적 코드/문서 대조에서 도출한 검증 시나리오다. 실제 브라우저 재현·제품 FAIL 이력으로 기록하지 않는다. 모두 RQ-50에 해당한다.

| ID / 심각도 | 위치·발생 조건 | 영향 | 반영/권장 수정 | 검증 |
|---|---|---|---|---|
| WD-R1 / 높음 | 초기 설계 4절: current_stage를 실행 단계로 사용하거나 SUCCEEDED만 확인 | 대기/무효화 상태가 실행/완료로 표시될 수 있음 | 설계 4.1절: 실제 RUNNING, validity, code/build 조합, 현재/이전 Attempt 구분 | T-145 |
| WD-R2 / 높음 | 초기 설계 3절: 연결됨+대기 또는 ACON 단절+실행 지속 | 한 점이 두 의미를 가져 연결/실행 사실을 잃음 | 3.1절: 연결 점과 실행 배지 분리; 공통 연결의 범위와 미확인 정의 | T-146~147 |
| WD-R3 / 높음 | 초기 설계 4절: online 최초 true, events만 실패, 오래 저장되지 않는 RUNNING | 확인 전 푸른 점/거짓 단절/실행 중단 오판 | 4.2절: snapshot 관찰·events 실패·저장/관찰 시각 분리, 신선도와 복귀 규칙 | T-146 |
| WD-R4 / 높음 | 초기 설계 4~5절: 긴 refresh·늦은 실패·A→B→A 선택 | 다른 작업/이전 관찰이 현재 화면을 덮거나 요청 누적 | 4.2절: 호스트 세대/순서/version 보호·중복 병합·정상 동등 version 관찰 수용 | T-146/148 |
| WD-R5 / 중간 | 초기 설계 2~3절: 일반 IP 분석 중 상위 선 전체에 흐름 | 분석도 선행 완료를 기다리거나 완료 게이트를 연 것처럼 보임 | 3.2절: 연결선별 의미·게이트 라벨·일반 그룹 내부 분석 활동 구분 | T-147 |
| WD-R6 / 중간 | 초기 설계 5절: 많은 IP/반복 snapshot/숨긴 탭/접힌 단계 | 전체 재배치·숨은 DOM·모션·별도 조회 비용 증가 | 5.1절: 펼친 단계만 DOM·안정 배치·비활성 모션 정지·100개 실측·추가 조회 0 | T-147~148 |
| WD-R7 / 중간 | 초기 설계 5절/PORT: 앱 타입/컴포넌트 역참조·전역 CSS·React/시험 도구 누락 | 기능 폴더를 옮겨도 원본 앱 전체가 필요하거나 깨짐 | 의존 방향과 작은 화면 모델, CSS/SVG id 범위, peer/lockfile/시험 진입점 목록, 격리 호스트 검증 | T-148 |
| WD-R8 / 높음 | 초기 설계 3~4절: CANCEL_REQUESTED 또는 자동 퓨징 완료 | 아직 실행 중인 작업을 종료/장비 시험 완료로 오판 | 3.1/4.1절: 취소 처리·불명·자동 준비와 실행 표시, 현재 BSP 결과만 완료 근거 | T-145/147 |
| WD-R9 / 중간 | 코드/목표 상태 설계: N/A 분모 제외와 module_done 조건 차이 | 100%를 게이트 완료로 오인할 수 있음 | 현재 차이를 4.1절에 명시. 서버 의미 그대로 표시; 정책 정합화는 별도 검토로 남김 | T-145 |
| WD-R10 / P2 · 별도 세션 | 4.2절 초기 보완안: 중복 refresh 병합 뒤 요청이 영구 pending | 잠금이 해제되지 않아 재조회가 계속 막힘 | 유한 조회 timeout/취소·논리 무효화·잠금 해제·재조회·늦은 응답 폐기 명시. 기존 실행 명령 정책 보존 | T-146 |
| WD-R11 / P2 · 별도 세션 | main.tsx의 명령 VERSION_CONFLICT 복구 GET이 작업 선택 변경 뒤 도착 | refresh만 보호하면 다른 작업 snapshot이 화면을 덮음 | polling/명령 복구 등 모든 snapshot 유입에 공통 수용 경계; 조회 취소와 BSP 실행 취소 구분 | T-146 |
| WD-R12 / P3 · 별도 세션 | 5.1절 초기 시험안: 빈 이력의 100개 fixture만 측정 | 전체 job JSON의 실제 전송/파싱 비용 누락 | 대표 Attempt/자동 보고 이력·bytes·파싱/변환/렌더 비용 분리 측정. 새 API는 지금 도입하지 않음 | T-148 |

## 반영 범위와 남은 판단

문서·인수 조건을 보완했으며 제품 코드는 수정하지 않았다. 별도 폴더 재사용 방향은 유지하되 회사 연결 범위를 탭 등록 외에 조회 관찰과 응답 수용 보호까지 구체화했다. 코드를 읽고 찾은 현재 제약을 이미 구현된 개선처럼 기술하지 않는다.

- ACON 제공자/작업·IP 관계/관찰·만료 기준은 미확정. 미확인 표시로 기본 화면과 분리할 수 있다. 실제 연결 T-149는 해당 계약과 회사 환경이 있어야 한다.
- code/build의 표시상 묶음·연결 점/실행 배지·신선도 3주기 기본값·세션 메모리·SVG/CSS는 기술 설계안이다. 사용자 운영 정책의 새로운 확정으로 기록하지 않는다.
- 현재 N/A 완료 기준과 목표 정책의 차이는 기존 서버 범위의 후속 검토 대상이다. 이 기능에서 화면 완료율이나 빈 그룹으로 실행 게이트를 보정하지 않는다.
- 현재 API 관찰은 worker/외부 에이전트의 생존 증명이 아니다. ACON 상태 조회와 기존 API 상태 조회를 섞지 않는다.
- 회사 기술 스택/성능 목표/검증된 의존 버전/코드 커밋/시험 진입점은 구현 후 고정한다. 100개 규모는 현재 설정을 근거로 한 시험 계획이며 성능 PASS가 아니다.
- 다음 담당: 사용자 구현 지시 후 구현 담당자가 T-144~148과 PORT를 완성한다. 회사 담당자는 회사 구조·ACON 계약·T-149를 별도 기록한다.

## 실제 검사와 후속 리뷰

- 표준 검사 시도: `.\.venv\Scripts\python.exe -X utf8 docs/testing/validate_docs.py`는 참조하는 `C:\Users\grayc\AppData\Local\Programs\Python\Python313\python.exe` 누락으로 실행 불가, 종료 코드 1. 표준 검사기 실행은 환경 BLOCKED이며 제품 FAIL이 아니다. 환경 설치/변경은 하지 않았다.
- 대체 검사: validate_docs.py의 링크/요구사항 커버리지/시험 ID 중복/CSV 순서·허용 상태/PASS·FAIL 증거 필드를 PowerShell에서 동일 범위로 검사했다. `Get-Content -Encoding UTF8`, 정규식, `Test-Path -LiteralPath`, `Import-Csv` 사용. 종료 코드 0. 결과는 아래와 같다.
- 공백 검사: `git diff --check` 종료 코드 0. 제품 코드 변경 없음. 기존 미추적 시안 산출물과 이전 실행 기록을 수정하지 않았다.
- 별도 세션은 WD-R10~12를 지적한 뒤 보완 문서를 재검토하여 문서 범위 APPROVED를 회신했다. 파일 편집·제품 시험·외부 호출 없음. Claude 검토 완료로 기록하지 않는다.
- 제품 T-144~149는 NOT_RUN 유지, 운영 baseline은 NONE 유지다. 기존 PASS/FAIL 실행 이력과 T-01~143 요약은 변경하지 않았다.

```json
{
  "status": "PASS",
  "checker": "PowerShell equivalent of validate_docs.py",
  "relative_links_checked": 594,
  "requirements": 50,
  "test_cases": 149,
  "not_run": 87,
  "errors": []
}
```

별도 세션의 내용 재검토 기준 SHA256(그 시점 미커밋 파일):

| 파일 | SHA256 |
|---|---|
| docs/design/WORKFLOW_DIAGRAM.md | A4DECB3766A79450FCB266506E7D05E6A1001E77393D4FD4BAEC6A556CE33E43 |
| docs/porting/PORT-001.md | E1443B613C994190E91279972BF72F7DE6BE04D9DBD47BAA232038CBBC711493 |
| docs/testing/TEST_CATALOG.md | C8E2747D09478DA357CFB7D451C5C5A78D595491BC0F1DB726DC299934543B17 |

그 뒤 PORT-001의 `독립 검토 NOT_REVIEWED`를 `제품 코드 독립 검토 NOT_REVIEWED`로 한정하고 문서 리뷰와 구분하는 기록 문장만 추가했다. 설계/시험 조건은 그대로다. 별도 세션이 이 문장과 본 기록의 WD-R10~12/결과를 다시 확인하고 **APPROVED 유지 — 문서 설계 범위만**으로 회신했다. 최종 PORT-001 SHA256은 `9E0980ED6C8DCC8D2282F62A0CB18F23E88AE8813EA80C8800E0337C3462E655`다.

최종 확인: 대체 문서 검사에서 위 594개 링크/50개 요구사항/149개 시험 결과를 다시 확인했고, `git diff --check`와 제품 경로의 HEAD 대비 diff는 종료 코드 0이다. T-01~143 기존 CSV 행은 HEAD와 동일함을 비교 확인했다. 미커밋 문서 상태이며 커밋·게시·서비스 실행은 하지 않았다.
