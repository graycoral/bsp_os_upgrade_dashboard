# GUI Test × BSP Dashboard — 연동 구현 요구사항 (승인된 설계)

- 기준일: 2026-10-25 / 상태: **설계 기준 확정, 구현 미착수**
- 공통 TC 실행·UI·상태·리포트 요구사항: [`GUI_TEST_REQUIREMENTS_FINAL_REVIEW.md`](GUI_TEST_REQUIREMENTS_FINAL_REVIEW.md)
- 공개 기준 프로젝트: [`graycoral/bsp_os_upgrade_dashboard`](https://github.com/graycoral/bsp_os_upgrade_dashboard), 확인한 `main` 커밋 `14bb35ea66a328a9de204fbb039cc5d303778b52`(2026-10-12). **회사 수정판의 현재 코드/엔드포인트는 미확인**.
- 표기: `[채택 설계]`은 사용자 승인된 권장 구현 기준. `[실환경 확인]`은 실제 회사판 인터페이스 확인 필요.

## COM 계약(확정)

- **RBC → RBM 보드/COM 조회는 기존 기능**이다. 조회가 되면 Dashboard에서 보드와 해당 COM을 선택하고, RBM 미연결이면 수동 입력 후 Preflight로 확인한다.
- **기존 TC 실행 명령은 COM 포트를 인자로 이미 받는다(사용자 확인).** TestRunner Adapter는 선택된 Single COM A, Dual COM A/B를 기존 명령의 인자 자리에 전달한다. **명령 플래그/인자 순서만 실제 명령 예시로 후속 확정**한다. 별도 COM 전달 프로토콜을 신규 개발하는 요구사항이 아니다.
- **확정:** 사용자 결정과 승인된 권장안을 모두 적용한다. 보드·COM 조회 기능과 기존 COM 명령 인자 지원은 확정이며, 구체 API·명령 문법은 현장 확인한다.

## 1. 통합 범위 및 책임

| 담당 | 구현 범위 |
|---|---|
| 기존 Dashboard React | 기존 좌측 메뉴에 `Test 현황` 추가, TC 트리·Git·보드/COM·실행 상태·로그·결과 리포트 표시 |
| 기존 Dashboard FastAPI + Worker | **내부 GUI Test API/Run Manager** 추가. 상태·예약·명령·Attempt·결과 이력 관리; 장시간 TC 실행은 HTTP 요청과 분리 |
| Remote Board Connector (RBC) | Windows에서 연결된 보드를 기존 시스템에 등록·연결하는 **기존 기능** 유지 |
| RBM | **등록 보드·보드 ID·연결 상태·COM 정보 조회**에만 활용. TC 실행/결과 전송/점유의 책임 주체로 가정하지 않음 |
| TestRunner Adapter | 기존 Windows→Linux TC 성공 경로에서 Python TC를 실행한다. **선택 COM을 기존 CLI 인자로 전달**하고 로그·판정을 수집한다. 별도 신규 전용 TC 실행 API는 1차 필수 아님 |
| Dashboard `device_test` | **전체 Run 종료 후** 검증된 모듈·필수 시험별 PASS/FAIL을 자동 수신, 수동·자동 이력 보존 |

- Dashboard 통합 모드의 Run은 **Linux TestRun Manager가 단일 기준**이며, 기존 Dashboard에 내장한다. Windows 단독 Run은 **별도 로컬 Run**이고 Dashboard와 공유·동기화·원격 제어하지 않는다.
- Dashboard 모드의 `Test 현황`에서 **대상 BSP Upgrade Job 선택은 선택사항**이다. Job이 없으면 일반 TC Run만 실행하고 `device_test` 자동 반영은 하지 않는다.
- 기존 Dashboard 전체 업그레이드 진행률과 GUI Test의 TC 진행률은 **서로 다른 지표**다.

## 2. Dashboard 화면 및 연동 시작

1. 좌측 `Test 현황`에서 Linux Git 브랜치·커밋/TC 목록·선택 Suite·실행 순서 확인.
2. 선택적으로 **BSP Upgrade Job**을 지정. Job 연동 시에는 Job ID, 모듈 ID, 현행 이미지 해시/버전, `plan_version`, 현재 `device_test attempt_id`, 실행/소스 fingerprint를 고정.
3. 보드·COM 확보는 **RBC ↔ RBM 기존 조회**를 우선 사용. RBM에 보드 ID와 COM 목록이 포함됨(사용자 확인). Single은 보드 1대, Dual은 동일 Windows 호스트의 **서로 다른 보드 2대** 선택.
4. RBM 연결 실패 시 보드 ID·호스트·COM A/B 수동 입력 허용. 연결 가능성 자체는 실행 직전에 검증. **사용자 입력만으로 보드가 검증됐다고 판단하지 않음**.
5. Job 연동 Run은 해당 모듈 `device_test`가 실행 가능한 단계인지, 빌드 이미지/시험 계획/현재 Attempt가 준비됐는지 **실행 전 검증**. 미준비면 Job 연동 테스트를 차단하고 **Job 미연동 일반 테스트만** 허용.
6. 일반 TC 실행에 필요 없는 **Dashboard 매핑 정보 누락**은 TC 실행을 막지 않지만, 완료 후 `device_test` 자동 동기화는 보류.
7. Run 진행/완료 후 TC 결과·Attempt·근거·동기화 상태를 Dashboard에 표시. Dashboard API 연결 장애가 TC 판정을 변경해서는 안 됨.

## 3. 이미지·보드·시험 기준 검증

| 시점 | 필수 확인 |
|---|---|
| Preflight | 선택한 Job의 이미지·SW 버전·계획·Attempt·핑거프린트가 현재 기준인지, 실제 **Board A/B**에 해당 이미지가 적용됐는지 |
| 각 TC 시작 직전 | 대상 보드·COM 연결 유효성, 논리적 예약, 기존 실험 환경 접근성 |
| 전체 Run 종료 후 반영 직전 | 원래 고정한 Job/이미지·계획·Attempt/매핑 버전·시험 기준과 **Dashboard 현재 상태**의 일치 및 증빙 유효성 |

- 보드에서 이미지·SW 버전 자동 식별을 지원하면 우선 사용한다. 그렇지 않으면 **사용자 증빙 확인**을 허용하되, 사전에 합의한 동일성·승인 기준을 충족해야 자동 반영 가능하다. 이미지 파일 SHA-256과 장치 SW 버전 문자열이 직접 같다고 가정하지 않는다.
- RBC/RBM 장애로 수동 선택해도 **보드 ID·실제 이미지의 유효성**이 입증되면 자동 반영 허용. 그렇지 않으면 TC 결과만 보존하고 `SYNC_BLOCKED`로 유지.
- Run 도중 Job 이미지·계획·Attempt가 바뀌면 현재 TC의 안전한 종료를 확인한 후 **다음 TC 실행 중지**, 사유·이력을 보존한다. 이전 기준 Run을 새 기준의 시험으로 간주하지 않으며 새 기준 재시험은 **새 Run**이다.

## 4. TC ↔ Dashboard 모듈·필수 사례 매핑

- Git과 함께 **버전 관리되는 매핑 설정 파일**을 사용한다. 안정적인 TC ID를 `Job/Module/필수 시험 항목`에 연결한다. 한 필수 사례에 **여러 TC 매핑** 가능.
- 실제 Run에는 매핑 파일 버전·해시, TC 소스 버전, Dashboard Job·Plan 버전을 기록한다. **필수 TC 누락·중복 식별·매핑 불일치**는 해당 모듈의 자동 반영을 차단한다.
- **미매핑 TC**도 Job 연동 Run에서 선택·실행할 수 있으나 `device_test` 필수 사례 판정에 직접 포함하지 않는다. **Run 전체 판정과 리포트에는 포함**한다.

예시 계약(실제 모듈 ID와 사례 목록은 회사 코드에 맞춰 매핑):

```json
{
  "schema_version": 1,
  "mapping_revision": "rev-001",
  "modules": [
    {
      "module_key": "example-module-id",
      "required_cases": {
        "boot": ["tc_boot_001"],
        "functional": ["tc_eth_001", "tc_eth_002"]
      }
    }
  ]
}
```

## 5. 집계 및 `device_test` 자동 반영

1. **전체 Run 완료 전에는 어떤 모듈도 최종 PASS/FAIL로 반영하지 않는다.** Run이 `INCOMPLETE`이면 모든 모듈의 자동 반영을 보류한다(미매핑 TC의 Error도 포함).
2. Run이 **PASS 또는 FAIL**로 확정된 뒤, 모듈별 필수 사례의 **모든 필수 TC**를 별도로 집계한다: 전부 PASS → 사례 PASS, 하나 이상 FAIL + 나머지 판정 완료 → 사례 FAIL, 누락/오류/미검증 → 해당 모듈 반영 보류.
3. 한 Job의 여러 모듈을 같은 Run에서 검증할 수 있다. **모듈 A가 PASS, 모듈 B가 FAIL**이면 전체 Run은 FAIL이지만, 각 모듈의 `device_test`에는 서로 독립된 결과를 반영한다. 다른 모듈의 FAIL이 A의 PASS를 무효화하지 않는다.
4. 반영 직전 이미지 SHA/보드 SW 동일성 근거, TC/매핑/Plan 버전, 소스 fingerprint, 유효한 현재 Attempt, 보드/시험 근거를 **서버 측에서 재검증**한다. 클라이언트의 PASS 주장만 믿지 않는다.
5. 반영은 모듈·필수 사례별 원본 `run_id/attempt_id/tc_ids/result/evidence_refs`를 기록하고, **중복·역순·오래된 결과 전송**을 방지한다.
6. 동기화 실패 시 **TC 결과는 그대로 보존**한다. 연결 타임아웃·일시 장애에 한해 제한적으로 자동 재시도, 이후 사용자 수동 재시도. 기준 불일치/충돌은 자동 재시도하지 않고 재검증 대기. 동기화 결과는 `PENDING / SUCCEEDED / FAILED / BLOCKED` 등 별도 상태.
7. **Demo/Mock 결과는 운영 Dashboard의 `device_test`를 변경할 수 없다.**

## 6. 기존 수동 결과 및 완료된 Job과의 정합성

- 기존 `device_test` 수동 PASS/FAIL 결과와 승인·Attempt는 **수정/삭제하지 않고 이력으로 보존**한다. 신규 자동 시험이 **최신이고 유효한 시험 기준**을 충족하면 현재 값을 갱신한다. 단순 도착 시각이 더 늦다는 이유만으로 우선하지 않는다.
- **이미 완료된 `device_test`/Job**을 갱신할 때도 **새 Attempt/결과 리비전**을 생성하고 현재 상태와 후속 의존 결과를 재평가한다. 이미 COMPLETED인 Job은 최종 완료·과거 사람 검토의 **현재 유효성을 무효화**, 재검증 상태로 되돌린 뒤 필요한 검증과 최종 사람 검토를 다시 요구한다. 과거 최종 승인 기록은 보존한다.
- 영향 분석은 **기존 Dashboard 모듈/단계 의존 관계를 우선 활용**, 부족한 의존성만 버전 관리되는 파일로 보완한다. 명확히 영향받는 결과만 무효화하고 독립된 유효 결과는 유지. 의존 관계 불명확 시 **검토 대기**로 기록한다.
- **재검증 실행 승인**: 상태 갱신과 확인된 영향 범위의 무효화는 즉시 수행한다. 그러나 **재검증 대상·순서는 사용자에게 제시하고 승인 후 실제 재시험**한다. 근거 없이 필수 재검증을 제외하지 않는다.

## 7. 공개 코드 기준의 변경 접점 및 구현 주의점

| 공개 기준 파일 | 통합 작업 |
|---|---|
| `apps/web/src/main.tsx`, `api.ts` | `Test 현황` 메뉴, TC/COM·로그·결과·리포트 UI 및 API 호출 |
| `backend/api/main.py` | GUI Test 조회/실행/상태/결과 API 추가. 기존 Host/Origin/요청 헤더 안전 정책 유지 |
| `backend/domain/engine.py`, `policy.py` | Run·Attempt·상태 유효성·필수 사례 집계·최신 자동 결과 반영·완료 Job 재개/영향 무효화 |
| `backend/worker/main.py` | TestRunner Adapter 호출·중단·복구·로그 수집(HTTP 요청과 분리) |
| `backend/storage/` | Test Run·예약·결과·이벤트·동기화 아웃박스 영속화; 기존 DB/이력 보존 |

**핵심 제약:** 공개 기준 코드의 기존 `manual-test`는 `device_test`가 **`WAITING_INPUT`인 현재 Attempt**에만 제출 가능하고, 현재 빌드 artifact ID/SHA와 Plan/fingerprint가 필요하다. 따라서 **완료된 Job의 자동 결과 갱신(결정 63~64)은 기존 수동 등록 API 재호출만으로 구현되지 않는다.** 정식 자동 결과 접수와 새 Attempt 생성·검증·무효화 처리가 필요하다. 실제 사내 코드의 변경 여부부터 확인한다.

`[채택 설계]` 자동 접수는 기존 FastAPI 내 **명시적인 자동 시험 결과 명령**으로 구현하고, `expected_version`/멱등 키/입력 fingerprint 검사 후 상태·이력·의존성 무효화·동기화 의도를 **원자적으로 기록**한다. 새 엔드포인트 이름은 기존 회사 API와 조정한다. **존재하지 않는 API를 기존 기능으로 표기하지 않는다.**

## 8. 필수 인수 테스트

| ID | 시나리오 | 합격 기준 |
|---|---|---|
| INT-01 | RBM에서 내 보드/COM 자동 조회 | Board A/B 선택 및 해당 COM 콤보박스 동작, **선택 COM이 기존 TC 실행 인자 슬롯으로 정확히 전달** |
| INT-02 | RBM 장애·수동 입력 | 수동 입력 COM을 기존 TC 실행 인자에 전달, 보드 ID·실행 가능성 검증, 시험 근거 불명 시 자동 반영 차단 |
| INT-03 | Job 미선택/미준비 | 일반 TC 실행 허용, `device_test` 미갱신 |
| INT-04 | 이미지·Plan·Attempt 불일치 | 연동 실행 차단 또는 완료 후 동기화 보류, 과거 결과 보존 |
| INT-05 | 정상 완결 Run | 필수 매핑 사례 누락 없이 모듈별 판정·전송 근거 저장 |
| INT-06 | 한 Run의 두 모듈: PASS/FAIL | 전체 FAIL, 두 모듈 결과 독립 반영 |
| INT-07 | 미매핑 TC FAIL | 전체 FAIL, 매핑된 필수 사례 계산에는 미포함 |
| INT-08 | 미매핑 TC ERROR | 전체 INCOMPLETE, 모든 모듈 자동 반영 보류 |
| INT-09 | 기존 수동 PASS 뒤 자동 FAIL | 과거 PASS 보존, 새 유효 Attempt 기준 현재 FAIL 갱신 |
| INT-10 | COMPLETED Job에 유효 FAIL | Job 재검증 상태, 영향받은 결과 무효화, 최종 사람 검토 요구 |
| INT-11 | 영향 분석 불명/재검증 승인 전 | 보류 유지, 독립 결과 보존, 재시험 자동 시작 없음 |
| INT-12 | 동기화 응답 유실·중복 전송 | 결과 이중 반영 없음, 상태 조회·제한 재시도·수동 복구 |
| INT-13 | Demo에서 PASS 전송 시도 | 운영 `device_test`·운영 DB 변경 없음 |
| INT-14 | 기존 Dashboard 회귀 | 기존 수동 시험·선행 게이트·진행률·최종 승인/이력 기능 보존 |
| INT-15 | Windows 단독 GUI와 통합 GUI가 동일 보드 동시 사용 | 공통 배타 제어 미검증 시 같은 호스트의 병행 사용 금지, 물리 COM 충돌 방지 운영 절차 검증 |
| INT-16 | Single 및 Dual 인자 매핑 | RBM 정상·수동 대체 각각에서 선택 COM을 기존 TC 실행 명령의 해당 인자에 전달. 다른 보드·호스트 COM 혼선 차단 |

## 9. 회사판 확인 항목 및 최종 검토 결과

### 반드시 확보할 실환경 자료

1. 회사판 Dashboard의 **현재 브랜치/커밋과 React·FastAPI·Worker·DB 모듈 구조**(공개 원본 대비 Delta).
2. `device_test` 실제 상태 전이, 수동 결과 접수 API, **완료 Attempt 재검증/Job 재개 가능 여부**, 현재 이미지/시험계획/근거 검증 규칙.
3. RBC/RBM의 **보드 ID·호스트·COM API**, 조회 갱신 주기, 장치 식별값, 실제 접근/잠금 지원 범위. **보드/COM 정보가 조회된다는 기능 자체는 확인됨**.
4. Linux Python TC의 **실제 명령 COM 옵션명·인자 순서·호출 호스트**와 로그·중단·프로세스 재연결 가능 범위. **COM CLI 인자 지원은 사용자 확인 완료**.
5. 현재 시험 계획의 `boot`/`functional` 등 필수 사례와 TC 폴더의 실제 ID 관계, 이미지/보드 버전 동일성의 인정 가능한 증빙.

### 정합성 리뷰에서 드러난 구현 위험

- **Run 관리 충돌 해결:** Windows 단독은 Dashboard와 공유하지 않는다. Linux의 단일 관리자/제어권 이전은 **Dashboard 통합 모드 내부**에서만 강제한다.
- **자원 점유 충돌:** Linux Dashboard Run 관리자와 Windows Local Runner가 **같은 물리 Windows 보드**를 동시에 예약할 수 있다. RBC/RBM 조회만으로 배타 사용은 보장되지 않는다. `[채택 설계]` 공통 점유가 검증되지 않은 1차에서는 **동일 Windows 호스트에서 두 모드의 동시 하드웨어 실행 금지**. 이를 명시하고 검증 전 배타 보장 성공으로 판정하지 않는다.
- **완료 Job 재개:** 공개 기준 `manual-test` 인터페이스는 완료 후 자동 덮어쓰기를 지원하지 않는다. **자동 결과 전용 상태 전이·DB 변경·회귀 시험이 필수**다.
- **최종 판정과 모듈 판정:** 선택한 미매핑 TC의 미해결 Error가 **모든 모듈 동기화를 막는 규칙**은 사용자 확정 사항이므로 구현에서 임의 완화하지 않는다.
- **보드 이미지 검증:** 자동 식별을 지원하지 않으면 정해진 수동 증빙 없이 PASS 자동 반영 금지.

> 이 문서는 통합 코드를 작성할 수 있는 요구사항 기준이다. 실제 사내 Dashboard의 지원 인터페이스·실행 명령·보드 식별을 확인하기 전에는 검증되지 않은 기능을 완료로 표시하지 않는다.
