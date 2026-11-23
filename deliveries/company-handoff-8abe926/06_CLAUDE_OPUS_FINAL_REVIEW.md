# 06. 사내 이식 결과 독립 코드·계약·배포 리뷰

> **담당 하네스:** **사내 Claude Code + Amazon Bedrock, 반드시 신규 세션**
> **지정 모델:** **Claude Opus**, 깊은 추론
> **권한:** 원칙적으로 READ-ONLY. 문제를 발견하면 수정 요청/패치 제안만 작성하고, 구현과 리뷰 분리.
> **검토 대상:** 05 단계 변경 코드·복사된 패키지·원본 manifest·회사 계약·실제 시험 근거.

## 검토 목표

Sol에서 만든 원본 패키지와 Sonnet에서 사내 적용한 코드가 서로 호환되고, 사내 기존 기능·runtime·DB·안전 게이트를 보존하며, 이후 원본 GitHub를 업데이트해도 **추가 변경을 최소화**할 수 있는지 독립적으로 검토한다. 구현자가 작성한 문서의 '완료' 선언만 신뢰하지 말고 소스와 시험을 직접 대조한다.

## 검토 순서

1. 사내 정책, `docs/porting/{COMPANY_BASELINE,COMPANY_MAP,COMPANY_PORT_PLAN,APPLIED,COMPANY_SMOKE_RESULTS,COMPANY_PORT_CHANGELOG}.md`를 읽고 현재 회사 소스 HEAD를 기록한다.
2. 원본 `PLUGIN_PACKAGE.json`, `AGENT_MONITOR_SOURCE.json`, PORT 기능별 pin과 회사 실제 복사/수정 코드를 대조한다. 계약 필드와 실행 파일이 동일 release인지 확인한다.
3. **COPY_AS_IS 코드는 무단 수정되었는가?** 변경되었다면 회사 Adapter로 이동 가능 여부, 회귀 위험, 원본 upstream 반영 필요성을 판단한다.
4. 사내 플러그인 명령·service hook/Manager/Worker/Windows Connector가 한 수명·단일 소유권으로 동작하는가? 이중 프로세스·DB·설정 원본·서비스 종료 충돌이 없는가?
5. `8765/8766/8771` 등 포트·runtime·home의 실제 설정과 다중 checkout/SSH-R 사용 시 충돌을 검토한다. 예시 값을 운영 사실로 추정하지 않는다.
6. 배포 무결성, 사전 빌드 정적 자산, 설치 의존성, 구버전 서비스 재사용과 롤백 실패 시나리오를 검토한다.
7. 기존 job/TC 상태·paused/running·failed run·analysis latch·settings CAS/DB migration·중복 요청 idempotency·권한/게이트 보존을 검증한다.
8. 실제 회사에서 보고한 ERROR가 사라졌다는 근거가 있는지, 최소 한 번 이상 재현→수정→재시험 연결이 있는지 확인한다.
9. PASS/FAIL/BLOCKED/NOT_RUN 표시가 실제 명령·로그·테스트 환경과 일치하는지 확인한다. Mock/로컬 결과를 실장비 인수로 승격한 부분을 찾는다.
10. 남은 위험과 장기 유지비용(회사 포크 파일 수, 추후 원본 버전 반영 절차, Adapter API 안정성)을 리뷰한다.

## 심각도·판정

- `P0`: 데이터 손실·운영 장비/작업 안전·보안 침해·불가역 위험 — 즉시 차단.
- `P1`: 주요 기능 미동작·복사 실패·버전/의존성 불일치·심각한 회귀 — 인수 보류.
- `P2`: 중요하나 우회 가능, 재발 방지 필요.
- `P3`: 문서·품질 및 개선 제안.

리뷰 결과는 `APPROVED`, `CHANGES_REQUESTED`, `BLOCKED` 중 하나로 **정확한 근거**와 함께 남긴다. 실장비 미실행이 명확한 경우 제품/실장비 인수 상태는 따로 `NOT_RUN`으로 표시한다. 자동 테스트가 다 통과해도 회사 환경 인수가 없으면 종합 완료로 단정하지 않는다.

## 필수 산출물 (사내에만 저장)

`docs/porting/INDEPENDENT_REVIEW.md`

| ID | Severity | 파일/라인·재현 근거 | 영향 | 권장 조치 | 필수 회귀 테스트 | 상태 |
|---|---|---|---|---|---|---|

문서 끝에 다음을 명시한다.

- `source_commit`, `target_commit`, `package_release`, 원본 vs 사내 차이 요약
- 실제 독립 검토한 파일과 **검토하지 않은 범위**
- 검증된 로컬/회사/실장비/보안 검증 범위 및 각 증거
- `APPROVED / CHANGES_REQUESTED / BLOCKED`와 근거
- 남은 회사 운영 선행 조건·OPEN_QUESTION과 다음 담당
- 다음 릴리스에서 원본 패키지를 **복사만 해서 업데이트할 수 있는지** 또는 Adapter 수정이 필요한지

추가 수정을 요청하면 **다시 Sonnet 구현 세션**으로 보내고, 수정된 diff에 대해서 **별도 Opus 재검토**를 수행한다. 같은 세션에서 자기 구현을 독립 승인하지 않는다.
