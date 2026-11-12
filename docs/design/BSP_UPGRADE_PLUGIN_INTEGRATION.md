# BSP 업그레이드 플러그인과 GUI Test 연동 설계

RQ-60 / D-64 · 2026-11-07 · **로컬 구현·모의 검증, 회사 인수 별도**

**읽기 기준:** §1~12는 최초 설계와 당시 코드 상태를 보존한 이력이다. 제안·초안 및 당시 미구현 설명을 현재 인터페이스로 사용하지 말고 실제 공개 진입점과 연결 진단은 §13~14 및 고정 소스 코드를 우선한다. 독립 리뷰·모의 시험·회사 인수 상태는 [PORT-007](../porting/PORT-007.md)을 따른다.

원본은 구현과 로컬 모의 검증을 수행했다. 회사 private 플러그인 적용과 실제 회사 장비 인수 T-209는 별도이며 NOT_RUN이다. 실제 장비·모델 실행은 이 문서의 승인 범위가 아니다.

원본 조사 기준은 `476d95f08169d4a4fbb4a999a94d417d9e59cef3`, 고정 구현 소스·시험 커밋은 `1a18ea6fab8b1caead3935ce70cb1e30153d631b`이다. 현재 구현의 계약은 [GUI Test](GUI_TEST_CONTRACT.md), [소스 구조](GUI_TEST_LAYOUT.md), [모듈 TC 선택](MODULE_TC_SELECTION.md), [자동 퓨징](AUTOMATIC_FLASH_TEST.md)을 따른다. [플러그인 요청서](../agents/BSP_UPGRADE_PLUGIN_REQUEST.md)와 [PORT-007](../porting/PORT-007.md)은 이 원문을 참조한다.

읽기 안내: [회사 역할별 안내](../gui_test/BSP_UPGRADE_COMPANY_GUIDE.md)와 §13~14를 먼저 읽고 담당 범위의 초기 설계 및 코드를 확인한다. 회사 절차는 [PORT의 회사 적용과 사용 순서](../porting/PORT-007.md#회사-적용과-사용-순서)를 따른다.

## 1. 확정 요구와 설계 제안의 경계

| 구분 | 내용 |
|---|---|
| 사용자 확정 | 회사 내부 Linux `bsp-upgrade` 플러그인에서 GUI Test 기능을 이용한다. 플러그인 설치물에 백엔드와 선택적 화면을 포함하고 실행은 별도 영속 프로세스가 맡는다. |
| 사용자 확정 | Linux의 installer BAT 절대 경로를 전달한다. BAT와 같은 폴더의 이미지 묶음 전체를 Windows로 복사하며 BAT가 퓨징과 재부팅을 수행한다. |
| 사용자 확정 | TC 패턴은 설정된 Linux TC 소스 루트 기준이다. 선택 파일뿐 아니라 의존성을 포함한 TC 루트 전체를 전달한다. |
| 사용자 확정 | 모듈에 맞는 TC 패턴을 자동 제안하고 기본값을 저장한다. 사용자는 미리 보거나 변경할 수 있고 실행마다 별도 확인을 강제하지 않는다. |
| 사용자 확정 | 기존 Windows Runner·COM 설정·저장된 TC 명령을 재사용한다. 플러그인은 실행 요청 후 ID를 받아 조회하며 콜백을 요구하지 않는다. |
| 사용자 확정 | 최초 PASS는 다음 TC로 진행한다. 최초 일반 FAIL은 총 최대 3회 안에서 PASS 2회를 얻어야 통과한다. 최종 실패 뒤 남은 TC는 실행하지 않는다. |
| 사용자 확정 | 부팅 실패·kernel panic에는 일반 TC 재시도를 적용하지 않는다. 기존 결과·보고서를 최대한 재사용하며 실제 시도 기록을 보존한다. |
| 설계 제안 | 아래 HTTP 경로·필드명, 저장 위치, 패턴 우선순위, 조기 실패 종료, 서비스 제어 방식, 로그 한도·준비 제한시간은 구현을 위한 제안이다. |
| 최초 설계 당시 미구현 | 플러그인용 간소화 API, headless 실장비 호스트, installer 경로 전달, 새 재시도 집계, 독립 COM 관찰 로그와 해당 배포 패키지. 현재 구현은 §13~14와 PORT를 따른다. |

설계 제안은 사용자 확정 운영 정책으로 승격하지 않는다. 배포 현장에서 필요한 경로·보드·계정 설정과 제품 설계의 미결정을 구분한다. 기존 BSP 계획·선행 그룹·수동 기본값·최종 사람 검토와 D-48 소유권을 이 연동으로 우회하지 않는다.

## 2. 현재 구현에서 재사용할 경계

| 실제 소스 | 현재 동작과 확장 경계 |
|---|---|
| `backend/gui_test/api/router.py` | live prefix는 `/api/v1/gui-test/live`. 시작·조회·보고서·이벤트·로그 API가 있다. |
| `backend/gui_test/core/models.py` | 현재 StartRequest는 `tc_ids`, `connection`, `source_revision`을 요구한다. installer 경로·glob 입력은 없다. |
| `backend/gui_test/core/manager.py` | Preflight, 저장 명령 revision, 불변 Run, Board/COM 예약, 멱등 원장과 Attempt를 관리한다. |
| `backend/gui_test/core/results.py`, `repetition.py` | 일반 실행은 반복 slot을 집계한다. 서로 다른 slot의 FAIL은 이후 PASS로 없어지지 않는다. 새 정책을 단순 반복 3회로 구현할 수 없다. |
| `backend/gui_test/runtime.py` | `make_manager`는 `windows-http`를 dashboard 모드에서만 허용한다. 현재 standalone에 설정만 복사해 실장비 headless 모드로 쓸 수 없다. |
| `backend/gui_test/standalone/server.py` | ProcessLock·수명 관리·공통 Worker 조립을 참고할 수 있다. 현재 단독 서버 자체를 신규 실장비 호스트로 간주하지 않는다. |
| `backend/worker/main.py` | GUI Worker와 함께 BSP Worker·HardwareWorker를 시작한다. 플러그인 전용 실행에 이 진입점을 그대로 쓰면 범위 밖 BSP 실행 책임까지 포함된다. |
| `backend/gui_test/execution/host.py`, `flashing.py` | Windows 실행 identity·예약·프로세스 근거·자동 퓨징 기능을 재사용할 후보. 현재 자동 퓨징은 BSP 프로파일·manifest 경로이며 새 Run과 연결하는 조립이 필요하다. 특히 `FlashService.run`은 timeout/출력 초과와 예외에서 `tree.stop()`을 호출하므로 퓨징 중 강제 종료 금지 요구를 위해 반드시 변경해야 한다. |
| `backend/services/gui_test_host.py` | Dashboard 어댑터 조립 접점이다. 공통 코어가 이 호스트를 역참조하지 않는 현재 구조를 유지한다. |

현재 `POST .../runs`는 `Idempotency-Key`와 `X-Gui-Session` 헤더를 요구하고 HTTP 202로 Run 전체를 반환한다. 실장비 실행에는 `execution=hardware`와 저장한 `command_profile`·`command_revision`도 필요하다. 식별자 응답 필드는 **`id`**다. URL의 `{run_id}` 변수명을 새 응답 필드로 오인하지 않는다.

현재 `GET .../capabilities`의 Runner 연결 준비는 보드 부팅·로그인 완료를 증명하지 않는다. 현재 `GET .../source`의 execution readiness도 TC 소스 전송 capability 확인이며 부팅 준비와 별개다.

## 3. 배치 구조와 소유권

```text
Linux bsp-upgrade 플러그인
  └─ HTTP 요청·조회 ─ GUI Test API + 단일 GUI Worker / 영속 runtime
                         ├─ 선택적 GUI 화면 / 기존 Run 조회·보고서
                         └─ 기존 SSH 경로 ─ Windows Runner
                                                ├─ installer 묶음 실행
                                                ├─ TC Python 실행
                                                └─ RX 전용 콘솔 관찰자
```

백엔드는 플러그인 호출·대화·브라우저 수명과 독립적으로 유지한다. 플러그인은 시작 전에 서비스 상태를 확인하고 없으면 설치된 서비스 관리 수단으로 올린다. 재호출·동시 호출은 같은 runtime의 서비스 하나를 재사용한다. 개별 요청 종료·플러그인 재시작으로 API·worker·터널·Windows Runner를 종료하지 않는다.

제안하는 Linux headless 호스트는 기존 Manager/Store/Worker/WindowsRemote를 조립하는 얇은 진입점이다. 새 TC 실행 엔진이나 두 번째 장비 스케줄러를 만들지 않는다. 기존 Dashboard가 같은 runtime을 운영 중이면 그 호스트를 재사용하며 별도 GUI Worker를 중복 시작하지 않는다.

서비스 확인은 포트가 열렸다는 사실만으로 끝내지 않는다. 제안 서비스 registry는 `runtime_id`, `service_instance_id`, `package_version`, `integration_contract_version`, `config_revision`, `controller_principal_id`, `worker_epoch`, `runner_id`를 보존한다. 계약 초기 버전은 `bsp-upgrade-integration-v1`로 제안한다. worker OS 잠금과 살아 있는 identity를 함께 확인하며 PID 재사용·오래된 heartbeat만으로 소유권을 넘기지 않는다. API/worker 설정·버전 또는 Windows identity가 다르면 신규 실행을 거부하고 기존 기록은 조정한다. 실제 health 구현은 §13~14를 따른다.

Linux API는 기본 loopback으로 제한하고 로컬 호출 인증·서비스 계정 권한을 적용하는 것을 제안한다. 기존 Windows Runner 토큰을 플러그인 요청 본문·로그에 복사하지 않는다. 원격 접근이 필요하면 회사 호스트의 인증/터널 정책을 연결한다. Windows Runner와 SSH 터널도 장기 실행 서비스로 준비되어야 하며 Linux 플러그인 생명주기의 자식으로 종료되면 안 된다.

Linux 배포 기본안은 systemd service adapter와 별도 영속 runtime이다. 서비스 관리자가 재시작·로그인 후 기동을 맡고 플러그인은 인증된 health 확인 후 같은 서비스를 시작한다. systemd가 없는 회사 호스트는 같은 수명/잠금 계약을 만족하는 supervisor로 교체한다. 서비스 이름·포트·계정은 배포 설정이며 이 문서는 존재하지 않는 설치 명령을 제공하지 않는다.

## 4. 플러그인 요청과 응답 초안

아래는 최초 설계의 경로·본문 제안이다. 현재 구현의 공개 진입점은 §13과 고정 소스를 따른다. 플러그인의 명령은 HTTP action을 뜻한다. 임의 셸 명령을 문자열로 전송하는 인터페이스가 아니다.

```http
POST /api/v1/gui-test/live/integration/runs
Idempotency-Key: bsp-ethernet-20261107-001
Content-Type: application/json
```

```json
{
  "installer_path": "/srv/builds/image-123/install.bat",
  "tc_patterns": ["test/python3/*ethernet*.py"]
}
```

| 입력 | 제안 계약 |
|---|---|
| `Idempotency-Key` | 필수. 기존 최대180자 제한 재사용. 하나의 실행 의도에는 재접속 후에도 같은 키를 유지한다. 새 실행에만 새 키를 만든다. |
| `installer_path` | 필수 Linux 절대 파일 경로. 허용된 배포 루트 안의 BAT여야 한다. Windows 경로나 다운로드 URL이 아니다. |
| `tc_patterns` | 필수 비어 있지 않은 문자열 배열. 플러그인이 저장 기본값·모듈 매핑·사용자 변경을 해석한 최종 패턴 목록이다. 배열 여러 항목은 합집합이다. |
| `prepared_token` | 선택. §5의 미리보기/준비에서 얻은 불변 입력 결합 토큰. 생략하면 서버가 같은 준비 절차를 자동 수행한다. |

COM, Windows host, TC 명령 문자열, 로그인 비밀정보, runner URL, 서비스 설정 변경은 요청으로 받지 않는다. 서버의 구성된 기본 Single/Dual 보드와 저장 명령을 사용하며 목록의 첫 보드를 임의로 고르지 않는다. 플러그인의 모듈 이름·ID는 추천용 메타데이터일 뿐 운영 BSP `module_context`가 아니다. 현 초안은 이 메타데이터를 시작 본문에 요구하지 않는다.

HTTP 202 응답은 기존 Run 전체를 재사용한다. 다음은 응답의 **일부 필드만 발췌**한 예이며 새 축약 응답 스키마가 아니다.

```json
{
  "id": "3f8c1a90472d4e6b9a102c8d5f0b7e63",
  "state": "QUEUED",
  "overall_result": "INCOMPLETE"
}
```

수락은 완료·장비 준비·퓨징 성공을 의미하지 않는다. 제안 수락 트랜잭션은 원본 요청 hash, 인증 principal, config/profile revision과 비밀정보를 제외한 profile 내용, 기본 보드/COM·runner identity, TC source descriptor, retry policy 버전, Run ID를 함께 고정한다. 잘못된 본문·필수 설정 없음·만료/불일치 token은 수락 전 오류다. 현재 Manager.start는 Preflight를 동기 수행하므로 이 수락/준비 분리를 위한 확장이 필요하다.

느린 파일 고정·전송·준비는 worker가 수행한다. 새 Run은 `environment_ready=false`와 준비 phase로 시작하고 검증된 manifests/Windows ack가 모두 저장되기 전 하드웨어 claim을 금지한다. 준비 실패는 수락한 Run의 이유와 미실행 결과로 남긴다. 비밀 값 대신 보안 저장소 참조를 고정하고 credential 교체를 소스/보드 변경으로 오인하지 않되 인증 불가 상태에서는 실행하지 않는다.

token 없는 요청의 **202 시점에는 원본 파일 bytes가 아직 고정되지 않는다**. 생산자는 완료된 installer 디렉터리를 publish하고 실행 요청 후 이를 수정하지 않는 조건을 지켜야 한다. 서버는 복사 전 파일 목록·크기·mtime과 hash 기준을 수집하고 복사/재확인 시 변경을 검출하면 `SOURCE_CHANGED`로 준비 실패 처리한다. 성공한 staging manifest를 원자 publish한 시점에 bytes가 고정된다. 아직 작성 중인 빌드 폴더를 받아 나중 버전으로 조용히 실행하지 않는다. token 경로는 이미 고정된 bytes만 사용한다.

동일 키·동일 원본 요청은 같은 `id`와 저장된 수락 응답을 반환한다. 다른 본문에 같은 키를 쓰면 기존 `IDEMPOTENCY_CONFLICT` 의미로 거부한다. 설정 해석·파일 읽기·복사보다 먼저 중복을 조회하고 최종 저장은 원자적으로 재확인한다. 응답 유실 때 새 키로 실행을 만들지 않는다. 서버가 해석한 profile/source revision이 바뀌어도 이미 수락된 요청의 의미는 바뀌지 않는다.

현재 `X-Gui-Session`은 GUI 제어 소유권에 사용된다. 제안 v1은 설치별 인증 principal을 registry의 영속 controller로 매핑한다. 플러그인 재시작마다 새 GUI 세션을 만들지 않으며 마지막 관측 시간은 서비스가 갱신한다. 브라우저는 기본 읽기 전용이다. 권한 있는 GUI 제어권 인계는 현재 Run version과 controller를 CAS 검증한 명시 동작으로 처리하고 충돌은 409로 반환한다. 내부 principal의 취소·조정 요청도 같은 검증을 통과해야 한다. heartbeat는 영구 제어권 독점 근거나 취소 금지 조건이 아니다.

제어권 인계가 UNKNOWN 장비의 예약 해제·복구 성공을 뜻하지 않는다. 제어 주체는 취소 의도를 기록하거나 영속 receipt의 재조회/조정을 요청할 수 있으나 물리 종료 근거 없이 다음 단계·새 퓨징을 시작할 수 없다. 기존 action API의 expected_version 원칙을 재사용하고, 새 principal 연결과 준비/퓨징 phase 제어는 확장한다. 기존 endpoint에서 세션 헤더만 생략해도 동작한다고 가정하지 않는다.

| 목적 | 재사용할 현재 경로 |
|---|---|
| 상태와 결과 폴링 | `GET /api/v1/gui-test/live/runs/{run_id}` |
| 보고서 | `GET /api/v1/gui-test/live/runs/{run_id}/report/{format}` (`json`, `csv`, `html`, `pdf`, `logs`) |
| 필요시 이벤트·시도 로그 | `GET .../runs/{run_id}/events`, `GET .../runs/{run_id}/logs/{attempt_id}/{stream}` |

`state`, `overall_result`, `results`, `attempts`, `reason`은 기존 Run 필드를 활용한다. 전체 새 결과 envelope·콜백·별도 PASS 등록 API는 만들지 않는다. 폴링 기본은 2초, 오류 시 jitter를 포함한 지수 backoff 최대30초로 제안한다. HTTP 실패나 폴링 중단만으로 TC 실패·종료를 확정하지 않는다.

## 5. 모듈별 기본 패턴과 미리보기

플러그인은 안정적인 모듈 키와 표시 이름을 구분하고, 모듈별 기본 패턴과 전역 기본 패턴을 영속 설정에 저장한다. UI에서 수정한 이번 실행의 값과 기본값으로 저장하는 동작은 구분한다. 모듈을 다시 조회할 때 사용자 편집을 덮어쓰지 않는다.

**제안 우선순위:** 이번 실행의 명시적 변경 → 정확히 매핑된 모듈 기본 패턴 → 전역 기본 패턴. 자동 추론한 별칭을 저장 매핑과 동등하게 취급하지 않는다. 값이 없거나 0개 일치면 실행 전 해결하도록 안내하며 모든 TC로 자동 대체하지 않는다. 모듈 매핑이 존재하지만 잘못되거나 일치하지 않으면 전역 기본값으로 조용히 우회하지 않는다.

예를 들어 Ethernet 모듈에는 `test/python3/*ethernet*.py`를 기본값으로 저장할 수 있다. 이것은 회사의 실제 파일명 확인 전 예시이며 모든 모듈에 고정 적용할 패턴이 아니다. 사용자는 제안된 패턴·일치 TC·순서를 실행 전 미리 보고 변경할 수 있지만 매 실행마다 승인 대화상자를 거칠 필요는 없다.

미리보기와 시작은 같은 서버 준비/선택 함수를 사용한다. 보조 제안 `POST /api/v1/gui-test/live/integration/preview`는 시작 본문 중 경로·패턴으로 준비를 요청하고 202의 `preparation_id`를 반환한다. `GET /api/v1/gui-test/live/integration/preparations/{preparation_id}`는 `state=PREPARING|READY|FAILED`와 실패 이유를 제공한다. READY에서 기존 카탈로그의 `tests`, `tc_ids`, `catalog_revision`과 `prepared_token`을 반환한다. 이것은 준비 메타데이터이며 새 TC 결과 포맷이 아니다. 실제 진입점은 §13을 따른다.

준비 token은 원본 요청 hash, principal, 고정 config/profile·policy·보드·runner identity, installer/TC 불변 manifest와 선택 ID/순서에 결합한다. 서버가 난수 opaque token의 hash를 영속 저장하며 client 값으로 manifest를 대체하지 못하게 한다. token은 READY 후30분 유효·새 실행 한 번 사용을 제안한다. 동일 멱등 키의 재전송은 token 유효성 검사보다 저장 응답 조회를 우선하여 같은 Run을 반환한다. 다른 키로 이미 소비한 token을 사용하면 충돌이다.

`prepared_token`을 포함한 시작은 path/pattern·principal·config/profile/runner revision과 만료를 재검증하고 **미리 본 고정 파일**을 사용한다. 불일치는 stale 오류이며 최신 파일로 자동 대체하지 않는다. 원본 폴더가 이후 바뀌더라도 token의 불변 사본은 바꾸지 않는다. 미리보기 없는 시작은 동일 준비 절차를 자동 수행하며 인간 확인을 기다리지 않는다. plugin은 만료된 미사용 준비를 자동 재생성할 수 있으나 사용자 편집을 보존하고 달라진 선택을 표시한다.

패턴 해석의 제안 기본값은 `/`를 사용하는 루트 상대 glob이며 `*`는 한 경로 요소, `**`는 여러 요소를 대상으로 한다. Linux의 대소문자 구분을 유지한다. 절대 패턴, `..`, 제어문자·NUL, 셸 확장/명령 치환은 거부한다. v1 제안 제한은 패턴1~100개·각1~1024자, 선택 TC 최대500개다. 기존 카탈로그/선행 검증이 더 엄격하면 그 제한을 따른다.

glob은 카탈로그 항목의 `path`를 선택하는 필터다. 기존 카탈로그의 TC identity, 비활성 사유, Single/Dual, timeout, `after`를 그대로 적용한다. 선택 ID를 중복 제거하고 기존 안정적인 위상 정렬 규칙을 활용한다. 누락 선행 TC·잘못된 의존·순환은 거부하고 범위 밖 TC를 자동 추가하지 않는다. Python 파일을 단순 나열해 실행 대상으로 삼지 않는다.

기존 RQ-53의 `modules` 명시 소속과 정규화 토큰 판별을 재사용할 수 있으나 내부 BSP Job/Attempt/plan/fingerprint/gate 검증까지 대체하는 것은 아니다. 내부 운영 Job에 결과를 반영하려면 기존 신뢰된 호스트 연결과 소유권 검증이 별도로 필요하다. 플러그인의 임의 module ID만으로 모듈 완료·D-48 중복 배정을 허용하지 않는다.

## 6. 사전 검사와 두 종류의 스냅숏

수락 요청은 다음을 하드웨어 명령 전에 확인한다.

1. 수락 시 고정한 서버 설정·저장 명령·보드·policy를 사용하고 Windows Runner의 연결·identity·필수 capability를 다시 검사한다. 현재 설정으로 기존 수락 snapshot을 바꾸지 않는다.
2. installer 경로와 TC 루트의 허용 범위·파일 안전성을 검증한다. 이미지 묶음과 TC 전체 루트의 manifest/hash를 고정한다.
3. 고정 TC 카탈로그에서 패턴을 해석하고 실행 가능 항목·의존 순서를 확정한다. 0개 일치, 잘못된 Dual 보드, 실행 불가 TC는 장비 조작 전에 거부한다.
4. Windows에 두 스냅숏을 전송해 내용·완료 응답을 검증한다. 실행 중 원본 디렉터리가 바뀌어도 고정 사본을 사용한다.
5. 아래 영속 부모 batch 예약과 worker 소유권을 확보한 뒤 부팅 준비를 시작한다. 경합은 기존 예약 오류로 알리고 중복 실행하지 않는다. 예약 전 준비/전송은 장비 명령을 수행하지 않는다.

현재 Windows `Host.start`와 `FlashService.start`는 jobs의 RUNNING/UNKNOWN을 검사하여 **host 전체**를 예약한다. 이를 한 번의 flash job 종료와 다음 TC job 시작으로 나누면 빈 구간이 생긴다. 제안 v1은 Windows jobs에 영속 부모 batch를 만들고 기존 host 전체 직렬화 범위를 보존한다. 부모는 `batch_id`, `run_id`, `owner_token_hash`, 단조 증가 `owner_epoch`, `runner_id`, 자원/입력 hash, phase receipt를 보관한다.

모든 퓨징·TC·재시도 자식은 같은 부모와 owner token/epoch를 제출하고 서버가 부모의 identity·입력·허용 phase를 대조한다. 부모를 RUNNING/UNKNOWN으로 유지한 채 인증된 자식만 해당 예약 안에서 실행하도록 공통 시작 검사를 확장한다. 토큰 없는 기존 GUI 실행과 D-48도 같은 예약 검사에서 차단해야 한다. 자식 완료·COM close·Linux 연결 해제는 부모 예약을 풀지 않는다.

재시작 때 영속 부모를 조정하고 살아 있는 자식을 확인한 후에만 owner epoch를 갱신한다. 이전 epoch의 시작·완료·해제 요청은 거부한다. 전체 자식 종료와 묶음 종료 receipt를 확인한 트랜잭션만 부모 예약을 해제하며 UNKNOWN은 TTL로 해제하지 않는다. Linux도 같은 batch에 연결한 보드/COM 예약을 유지한다. 이는 기존 실행기의 예약 확장이고 새 스케줄러가 아니다.

installer 묶음은 BAT의 부모 디렉터리 전체와 하위 구조다. BAT만 복사하거나 이미지 파일명을 임의 추측하지 않는다. 복사·실행 경로는 별도 실행 디렉터리로 고정하며 **BAT 실행 cwd는 해당 installer 디렉터리**, 기본 인자는 없음으로 제안한다. 추가 인자가 필요한 회사 BAT는 저장된 승인 프로파일에서 지정하고 플러그인 임의 명령으로 받지 않는다. 기존 BAT basename·안전 경로 검증과 고정 Windows `cmd.exe /d /c` launcher를 유지하며 임의 셸 문자열을 조합하지 않는다.

TC 묶음은 설정 TC 루트 전체의 허용 파일이다. 현재 `execution/source.py`의 숨김 경로·`.git`·`.venv`·`venv`·`__pycache__`·`node_modules`·`.runtime` 제외와 link/reparse point·루트 이탈 거부, Windows 경로 충돌 검증을 보존한다. 필수 의존성이 제외 경로에 있으면 명시적으로 오류를 해결하고 몰래 제외 규칙을 해제하지 않는다.

기존 `execution/source_snapshots.py`의 TC 파일 수·파일별/전체/archive 제한은 그대로 검증한다. 이미지에 TC용 16MiB 파일·128MiB 전체 제한을 적용하지 않는다. installer 전체 상한은 기존 FlashService 설정의 기본 **64GiB**를 재사용하고 배포 프로파일에서 명시적으로 조절하는 것을 제안한다.

현재 `FlashService.copy_bundle`은 Windows `image_root`의 파일을 읽는 로컬 복사이지 Linux 전송 기능이 아니다. 새 `installer_stream_v1` capability가 있는 Runner에 기존 인증 HTTP/SSH 터널로 1MiB 단위 binary stream을 보내는 방식을 제안한다. 거대 JSON/base64·메모리 ZIP을 만들지 않는다. 전송 receipt는 transfer ID·manifest hash·파일별 검증 완료와 offset을 저장하고 부분 파일은 `.partial` staging에 둔다. 재전송은 같은 ID/hash로 확인된 offset부터 계속하고 hash/길이가 다르면 해당 준비를 실패시킨다. 모든 파일을 검증한 후 같은 volume에서 디렉터리를 원자 publish한다.

제안 디스크 사전 조건은 Linux에 입력 총량+1GiB 여유, Windows에 staging과 실행 사본을 포함한 입력 총량의2배+1GiB 여유다. TC snapshot 용량은 추가 합산하고 복사 중에도 실제 남은 공간을 확인한다. 완료된 immutable 사본을 실행별 복사하는 기본안이며 reflink/중복 제거를 전제하지 않는다. 예약된 공간 계산은 동시 전송 간 공유한다.

전송 timeout은 하드웨어 시작 전 같은 receipt의 제한적 재시도(기본3회, 2/4/8초)를 허용한다. 파일 쓰기·검증 실패는 실행 차단이다. 미참조 부분 전송은 마지막 활동24시간 후 정리할 수 있으나 활성 Run·준비 token·UNKNOWN 부모가 참조하는 사본은 자동 정리하지 않는다. 두 종류 모두 전송 중 변경·부분 복사·해시 불일치·디스크 부족을 통과로 처리하지 않는다.

## 7. Windows 퓨징과 TC 순서

다음은 한 실행 묶음의 순서다. installer 퓨징은 TC 일반 재시도마다 반복하지 않는다.

1. Windows Runner가 쓰기 가능한 설정 COM을 열고 필요한 콘솔 로그인 상태를 만든다. 비밀정보는 로컬 보안 설정에서만 읽는다.
2. `reboot lkshell`을 보내고 해당 보드의 lkshell 준비 marker를 확인한다.
3. `fast`를 보내고 fastboot 준비·대상 identity를 확인한다. 고정 sleep만으로 준비를 판정하지 않는다.
4. 등록한 BAT hash·타깃 계약을 대조한 뒤 고정 installer 디렉터리에서 실행한다. 정상 종료 코드·프로세스 종료·성공 marker와 실패 marker 부재를 함께 확인한다.
5. BAT의 재부팅 이후 새로 수신한 로그인 프롬프트를 기다린다. 재부팅 전 버퍼·로그의 오래된 login 문자열을 준비 근거로 사용하지 않는다.
6. Runner의 제어 COM handle을 닫는다. 관찰자는 수신을 계속하고, TC가 같은 쓰기용 가상 COM을 열어 기존 TC 코드로 로그인한다.
7. 고정 순서로 TC를 실행하고 아래 판정·중단 정책을 적용한다. 별도의 전체 재퓨징은 새 실행으로만 다룬다.

COM을 닫는 것은 TC에 포트 사용을 넘기는 동작이다. §6의 부모 batch 예약은 전체 묶음이 확정 종료할 때까지 유지한다. 다른 GUI Run·D-48도 동일 Windows 예약을 확인한다. 외부 터미널 프로그램까지 통제했다고 주장하지 않는다.

현재 FlashService의 등록 `batch_sha256`, `success_marker`, `failure_markers`, 보드 COM·fastboot serial 검증을 유지한다. 실제 fastboot 장치가 등록 대상 하나인지 확인하고 BAT에 `ANDROID_SERIAL`과 설정된 `BSP_FASTBOOT`를 전달한다. BAT는 해당 serial을 준수하고 내부 fastboot 실패를 최종 종료 코드/marker로 전파하는 검토된 스크립트여야 한다. 임의 BAT가 이 계약을 자동 지원한다고 가정하지 않는다.

최초 설치와 BAT 변경 시에만 스크립트·타깃 지정·실패 전파 계약을 등록/검증한다. 이후 동일 hash는 매 실행 자동 대조하며 별도 사람 승인을 반복하지 않는다. 변경된 hash·다중/다른 fastboot 대상·부정확한 성공 근거는 하드웨어 실행 또는 후속 TC를 차단한다. BAT의 하위 실행 파일/스크립트도 불변 installer manifest로 묶고 검토한 실행 구조에서 벗어나면 재등록한다.

Dual TC에는 저장된 A/B 보드가 모두 필요하다. 기존 동일 이미지 Dual 정책을 참고하여 각 보드를 순차 퓨징하고 모두 새 부팅 준비를 확인한 후 TC를 시작하는 것을 제안한다. 서로 다른 이미지 Dual과 선택된 보드의 일부만 퓨징하는 정책은 현재 요청에 없다.

준비 marker, 로그인 절차, fastboot 식별자는 보드 프로파일 값이다. timeout 제안 기본은 기존 profile의 콘솔120초·fastboot60초·퓨징1800초·부팅180초이며 TC는 기존 카탈로그 timeout을 따른다. 퓨징 timeout은 강제 종료 시간이 아니라 감독상 UNKNOWN 전환 기준이다. 제한시간 초과와 kernel panic은 같은 사건이 아니다. BAT 비정상 종료·부팅 실패·panic·근거 불명은 TC 일반 재시도 경로로 보내지 않는다.

2026-11-12 RQ-62 후속: 마법사는 동일 보드군의 콘솔 값을 프로파일 공통 입력으로 받고 기존 보드별 실행 필드에 펼쳐 저장한다. `fastboot init success`는 fast 이후 로그의 보조 근거이고 lkshell 준비값이 아니다. 실제 USB 대상 확인은 기존 serial 단일 일치 검사를 유지한다. 사용자 확인 BAT 후 프롬프트 `**** login : `는 `login :` 부분을 공통 기본값으로 사용하며 마지막 줄에만 한정하지 않는다. 새 로그인 후 `root`는 기존 TC가 입력한다. Runner 선행 로그인으로 TC가 기대하는 프롬프트를 소비하지 않는다. 기존 observer의 `login_markers`에도 같은 실제 문자열이 있어야 한다. 이 설정 편의 후속은 플러그인 HTTP payload·capability·DB를 변경하지 않는다. 프로파일 변경 시 기존 revision 검사를 유지하므로 Runner 정상 재시작 후 새 미리 보기로 고정한다. 실제 회사 플러그인 저장소의 반영은 [PORT-007 후속](../porting/PORT-007.md)에서 별도로 구분한다.

## 8. TC 재시도와 기존 결과 보존

| 시도 순서 | 논리 TC 판정·다음 행동 |
|---|---|
| PASS | 즉시 PASS, 다음 TC |
| FAIL → PASS → PASS | 최종 PASS, 다음 TC; 최초 FAIL Attempt 보존 |
| FAIL → PASS → FAIL | 최종 FAIL, 나머지 TC 미실행 |
| FAIL → FAIL | 최대3회 안에서 PASS2가 불가능하므로 조기 FAIL 종료를 **제안**. 사용자가 확정한 것은 최대3회·PASS2 조건이며 이 조기 종료 선택은 구분한다. |
| ERROR / TIMEOUT / UNKNOWN | 일반 FAIL로 환산하지 않는다. 종료·장비 상태를 확인할 때까지 자동 재시도하지 않는다. |
| 부팅 실패 / kernel panic | 일반 재시도 없이 현재 묶음 중단. 다음 TC나 자동 재퓨징으로 진행하지 않는다. |

기존 엄격한 결과 줄·종료 코드·프로세스 종료 확인을 판정 입력으로 재사용한다. 임의 로그의 PASS 단어·BAT 성공·다운로드 완료를 TC PASS로 쓰지 않는다. TC 한 개의 시도는 최대3회이며 반복 Suite의 3개 독립 slot과 다르다.

Run에는 `integration` 메타데이터를 추가하는 설계안을 채택한다. `contract_version`, `request_hash`, `config_revision`, `preparation_id`, installer/TC manifest 참조, `batch_id`, `phase`, `retry_policy`를 보존한다. `retry_policy=initial-pass-else-two-of-three-v1`을 제안하며 최대3회·최초 PASS 즉시 통과·수학적으로 불가능할 때 조기 실패를 담는다. 이는 사용자에게 필드별 승인을 받았다는 뜻이 아닌 구현 설계 기본값이다.

기존 `attempts`에는 모든 원시 시도·로그·종료 근거를 남긴다. 기존 `results`/`slot_results`에 정책을 적용한 논리 TC 결과를 연결하는 **집계 확장**이 필요하다. 대상 TC마다 논리 slot 하나를 유지하고 재시도는 그 slot의 별도 Attempt로 기록한다. policy가 정한 최종 판정만 slot에 확정하며 중간 실패는 raw Attempt에 남긴다. 기존 일반 Run의 반복 판정을 바꾸지 않고 새 정책 없는 과거 Run은 종전 방식으로 읽는다.

최초 FAIL을 삭제하거나 raw FAIL을 PASS로 고쳐서는 안 된다. 보고서·UI에는 “최종 PASS, 3회 중 PASS2/FAIL1”을 기존 시도와 함께 설명할 수 있어야 한다. 새 결과 문서 형식 대신 기존 JSON/CSV/HTML/PDF/logs export에서 추가 정책·논리 판정이 정확히 드러나도록 조정한다.

최종 TC 실패나 panic으로 남은 항목이 PENDING이면 기존 전체 집계 **INCOMPLETE**를 유지한다. 실패한 TC와 중단 이유는 별도로 표시한다. 모든 대상이 확정 PASS/FAIL인 경우만 기존 aggregate에 따라 전체 PASS/FAIL이 된다. 중단되었다는 이유로 남은 TC를 FAIL이나 SKIP으로 덮어쓰지 않는다.

## 9. 콘솔 관찰 로그와 판정 근거

TC는 현재 COM을 직접 사용하므로 Runner와 TC가 동일 물리 포트를 동시에 여는 구조를 가정하지 않는다. 제안은 승인된 splitter만 물리 COM을 소유하고 쓰기용 가상 포트 하나와 RX 전용 관찰 포트를 제공하는 것이다. Runner가 유일한 쓰기 포트를 사용한 후 닫고 TC가 같은 포트를 사용한다. 관찰자는 TX·RTS·DTR을 구동하지 않아야 한다. splitter가 제어선 격리를 지원하는지도 검증한다.

서명된 드라이버·회사 사용 라이선스·Windows 버전 적합성·RX-only 및 제어선 격리는 설치 선행 조건이다. 특정 상용 제품의 기능·라이선스·무중단 동작은 확인되지 않았다. 제품명만으로 지원을 약속하지 않는다. splitter가 적합하지 않으면 현재 설계의 동시 관찰을 준비 완료로 표시할 수 없다.

현재 `execution/capture.py`는 제한된 TC stdout/stderr 수집이며 물리 콘솔 전체 로그가 아니다. 제품 콘솔 수집의 제안 기본은 메모리 tail64KiB, 회전 파일8MiB×8개(64MiB), 수신→기록 bounded queue1MiB다. 값은 배포 설정으로 조정한다. 수신·증거 판정과 디스크 기록을 분리해 느린 파일 I/O가 TC·COM writer를 막지 않게 하고 queue 포화에서 producer를 기다리게 하지 않는다. overflow·decoder 오류·재접속 때 누락 구간과 byte sequence를 기록한다. 보관 파일 회전은 이미 판정한 데이터의 retention이며 실시간 취득 누락과 구분한다.

byte stream은 incremental decoder와 최대4KiB 판정 잔여 버퍼로 처리한다. marker가 chunk/UTF-8 경계에 걸쳐도 찾되 설정 marker 최대1024byte를 넘는 값은 거부한다. `boot_epoch`, `phase_epoch`, 단조 수신 offset, TC Attempt별 시작/끝 offset을 저장한다. 단계 전환·재부팅 경계에서 decoder의 미완성 패턴 상태를 비우고 경계 이전 partial과 이후 bytes를 이어 준비 marker로 인정하지 않는다. 제어 요청 전 관찰 수신 기준을 확보하고 재부팅 전 버퍼를 새 login 증거로 사용하지 않는다.

panic 판정은 보드 프로파일의 명확한 서명과 해당 epoch의 수신 구간으로 제한한다. timeout은 panic 증거가 아니다. 관찰 누락 구간과 겹치는 현재 준비/시도에는 상태 정상·PASS·안전한 재시도를 추론하지 않고 UNKNOWN으로 처리한다. 적극 퓨징 중 panic을 검출해도 BAT를 자동 강제 종료하지 않으며 중단 의도·근거를 기록하고 종료를 조정한 뒤 후속 단계를 차단한다.

제품 로그 정책은 인증정보 마스킹 후 runtime에 저장, 계정 제한 접근, Run JSON에 전체 raw bytes 미포함, 기존 logs export에 offset·gap·관련 파일 참조 연결을 기본으로 한다. 활성/UNKNOWN의 판정 receipt·gap·시도 구간은 자동 청소하지 않고 용량 부족은 readiness 실패로 처리한다. 관찰 데이터 회전으로 사라진 과거 본문은 사라졌다고 표시한다. 별도 [LOG_HANDLING](../testing/LOG_HANDLING.md)은 개발 시험 로그에만 적용하며 제품 로그 보관 정책의 근거로 사용하지 않는다.

## 10. 단절·취소·재시작과 저장 호환

플러그인이나 브라우저가 종료돼도 이미 수락한 실행은 지속한다. Linux–Windows 통신 단절은 실행 종료 증거가 아니며 원래 runner identity·요청 ID로 조회/조정한다. 현재 tombstone·프로세스 종료 확인 규칙을 활용하고 지연 POST 때문에 두 번 퓨징하지 않도록 한다.

취소는 영속 의도다. 다음 표는 제안 실행 정책이며 현재 코드가 모두 지원한다는 뜻이 아니다.

| 단계 | timeout·취소 | 재시작/단절 처리 |
|---|---|---|
| 준비/전송 | 장비 조작 전이므로 전송을 안전하게 멈추고 준비 실패/취소. 부분 파일은 receipt로 관리 | 같은 준비 ID/hash로 제한적 전송 재개. 아직 퓨징하지 않았다는 receipt 검증 |
| 콘솔/fastboot 준비 | 추가 명령 금지, 상태 확인 후 종료. 종료 불명이면 UNKNOWN | phase receipt·runner identity로 상태 조회. BAT 자동 시작/재시작 금지 |
| FLASHING | timeout·출력 초과·panic·취소는 중단 의도/UNKNOWN. **자동 tree.stop·Job Object close·BAT 재실행 금지** | 영속 process receipt로 기존 BAT/자식 상태를 계속 감독. 확정 종료 전 예약 유지 |
| 부팅 대기 | 준비 timeout은 실패/UNKNOWN 근거를 기록하고 TC 차단. 취소는 추가 명령 중지 | BAT 완료 receipt와 새 boot epoch를 확인. 과거 prompt 재사용·재퓨징 금지 |
| TC 실행/재시도 | 기존 허용된 TC 프로세스 취소/timeout 처리 후 트리 종료 확인. 일반 FAIL과 구분 | 부모/자식 receipt·현재 논리 slot을 대조. ERROR/TIMEOUT/UNKNOWN 자동 재시도 금지 |
| 묶음 종료 | 자식 종료·결과/중단 사유 저장 후 부모 예약 해제 | 중복 완료/해제는 멱등 처리하고 stale epoch 거부 |

현재 `FlashService.run`의 timeout/출력 초과 분기와 예외 정리 모두 `tree.stop()`을 호출한다. 새 퓨징 감독 경로는 이를 분리하고, 로그를 제한·계속 drain하면서 실행 중 BAT의 소유 handle을 감독 프로세스에 유지해야 한다. timeout 예외를 내며 handle을 닫는 방식도 Job Object 종료를 유발할 수 있으므로 금지한다. 서비스 정상 종료/업그레이드는 active flash를 기다리거나 종료를 거부한다. OS/전원 강제 종료까지 무중단을 보장하지 않으며 이때 UNKNOWN 예약을 복구한다.

worker 재시작은 저장된 phase·Run·Attempt·스냅숏·runner identity·부모 예약을 조정한다. 기존 Manager의 UNKNOWN 복구는 최근 TC Attempt 중심이므로 **TC 이전 준비/퓨징/부팅 receipt를 조회하는 복구 경로를 추가해야 한다**. “RUNNING이 오래됨”·TC Attempt 없음·404만으로 미실행을 결론 내리거나 BAT를 다시 보내지 않는다. 종료 증명 또는 기존 tombstone 의미의 미실행 확정 뒤에만 안전한 다음 동작을 선택한다.

기존 Run/Attempt/Suite와 실패 이력은 보존한다. 추가 메타데이터가 없는 과거 데이터는 기존 의미로 읽는다. 새 정책을 이해하지 못하는 구버전 worker로 진행 중 Run을 재개하지 않는다. 업그레이드 전 runtime·설정·스냅숏 참조를 백업하고, 복원은 별도 runtime과 일치 버전에서 검증한다. 구체적인 DB 이전 필요 여부는 필드 배치 확정 후 결정한다.

## 11. 로컬 구현과 패키징 책임

| 담당 범위 | 구체적인 작업·현재 재사용 경로 |
|---|---|
| 이 저장소 Python/API | `backend/gui_test/api/`, `core/`, `runtime.py`: integration 모델·진입점, 선택·준비 서비스, 기존 Run/예약/집계 확장. 새 파일명은 구현 시 응집도에 맞춰 정한다. |
| 이 저장소 headless 호스트 | `standalone/server.py`의 수명/잠금과 `core/worker.py`를 재사용해 실장비 GUI 전용 조립. Dashboard 연결은 `backend/services/gui_test_host.py`에 남긴다. |
| 이 저장소 Windows | `adapters/windows_remote.py`, `execution/host.py`, `flashing.py`, `source.py`, `source_snapshots.py`: 전송·identity·묶음 예약·한 번 퓨징·로그·재시도 정책 연결. |
| 이 저장소 선택적 UI | `packages/gui-test-ui/src/`, `apps/gui-test/`: 기존 Run/보고서와 정책·준비/중단 이유 표시. UI 없이 API/worker가 실행되어야 한다. |
| 이 저장소 패키징 | `apps/gui-test/package.py`, `pyproject.toml`, `requirements.lock`, `package-lock.json`: Linux 백엔드/선택적 정적 UI 묶음과 manifest·잠금 의존성·설치 안내. 기존 소스/설치 import 경계를 보존한다. |
| Windows 배포 | `scripts/build_windows_runner.py`, `windows_runner_entry.py`, `setup_runtime.py`: 기존 Runner ZIP/EXE 형식을 확장하고 별도 배포한다. splitter·TC 외부 Python은 환경 선행 조건으로 분리한다. |
| 회사 플러그인 | 저장 모듈 매핑·기본 패턴, 미리보기/변경, 설치된 서비스 확인·기동, 안정적인 요청 키, ID 저장·폴링·기존 결과 링크를 구현한다. |
| 회사 호스트/운영 | 인증·서비스 계정·허용 경로·보드/COM·저장 명령·TC 루트·SSH·Runner·splitter 준비, 실제 BAT/장비 인수와 회사 구조 대응을 기록한다. |

현재 문서 변경에는 위 코드·시험·패키지가 포함되지 않는다. 문서 검토 완료 후 승인된 구현 단계에서 이 저장소의 코드·모의 시험·패키지를 만들고 회사 플러그인에서 재사용한다. 회사 담당자에게 별도 실행 엔진 재구현을 요구하지 않는다. 실제 회사 플러그인 설치 hook·사내 빌드 규약은 접근 가능한 회사 코드가 없어 현지 어댑터 연결이 필요하다.

## 12. 검증 계획과 남은 결정

아래는 최초 설계의 검증 계획이다. 실제 로컬 실행과 회사 인수 상태는 PORT 및 실행 기록을 따른다. 기존 시험의 과거 PASS를 새 기능의 증거로 사용하지 않는다.

| ID | 인수 조건 | 기존 재사용 시험 근거 |
|---|---|---|
| T-200 | 호출/브라우저 종료 후 지속, 동시 단일 worker, runtime/version 불일치·PID 재사용·stale owner 거부, principal 유지·제어권 CAS | `test_portable_host.py`, `test_live_view.py`; 새 lifecycle 시험 필요 |
| T-201 | 수락 config 고정, 중복/충돌/응답유실·동시 요청, 준비 전 claim 금지, 기존 id·조회·보고서 | `test_api.py`, `test_core.py`; integration 시험 추가 |
| T-202 | 모듈 기본값·편집 보존·0개/의존, 불변 preview token·만료/변조/소비/다른 설정 거부, 확인 없는 준비 | `test_module_selection.py`, `test_sources.py`; plugin 계약 시험 추가 |
| T-203 | 전체 묶음 고정·작성 중 소스 거부, 다중GiB streaming·부분 재개·원자 publish, 링크/충돌/초과·디스크·UNKNOWN 청소 거부 | `test_source_snapshots.py`, `test_source_transport.py`, `test_flashing.py` |
| T-204 | 명령·capability·Single/Dual·COM, 등록 BAT hash/serial/성공·실패 전파, 임의 명령·다중 타깃 거부 | `test_commands.py`, `test_windows_runner.py` |
| T-205 | 퓨징1회·fresh login, chunk 경계·stale partial/epoch·queue drop·회전 구분, panic 후속 차단과 퓨징 중 kill 금지 | `test_flashing.py`; 새 콘솔 fixture 필요 |
| T-206 | 최초 PASS 즉시 진행, F/P/P 회복, F/P/F 중단, 최대3회·원시 이력·논리 집계 | `test_core.py`; 정책 전용 시험 추가 |
| T-207 | 단계별 취소/timeout/출력초과·preTC 복구, flash→TC 사이 D-48/GUI 침입·stale epoch 거부, UNKNOWN 예약·중복 퓨징 금지 | `test_flashing.py`, `test_windows_runner.py`; integration 복구 시험 추가 |
| T-208 | Linux 백엔드/선택 UI 묶음, BSP 없는 설치·서비스, 별도 Windows 패키지·호환·복원 | `test_package.py`, `test_portable_host.py`, `tests/test_windows_runner_bundle.py` |
| T-209 | 회사 Linux/Windows/SSH/BAT/보드/실제 TC/splitter RX-only·제어선·로그 연속성 인수 | 실제 환경 전용; 모의 시험으로 대체 불가 |

표에서 `test_*.py`는 별도 경로가 없는 경우 `backend/gui_test/tests/` 기준이다. 영향받는 기존 D-48·RQ-53·RQ-54·RQ-56·RQ-57·RQ-59 회귀와 구형 데이터 읽기를 함께 검증한다. 독립 설계 검토와 제품 시험 통과는 별도 상태로 기록한다.

미정 사항을 다음처럼 분리한다.

- **추가 사용자 질문 없이 구현할 설계 기본값:** 본문의 v1 HTTP/메타데이터·pattern 우선순위·immutable token30분·수락 config 고정·64GiB streaming·묶음 예약·controller CAS·로그 상한·2초 polling·조기 실패와 단계별 복구. 모두 공학적 제안으로 채택한 기본값이며 사용자에게 항목별 승인받았다는 뜻은 아니다. 기본값이 실제 회사 요구와 충돌할 때 영향받는 접점만 조정한다.
- **자동 처리할 일:** 준비/기본값 적용·동일 요청 재조회·동일 BAT 검증·파일 해시·TC 선택·정상 실행/정책 재시도·제한적 전송 재개·증거 기반 기존 프로세스 재연결. 미리보기·개별 TC·동일 등록 BAT마다 사람 확인을 요구하지 않는다.
- **회사 첫 배포에서 필요한 사실:** 설치 hook·인증 방식·안정적인 서비스 계정·아래 장비/소스 값과 실제 BAT 타깃 계약. private plugin 코드가 없어 이 연결을 완료했다고 주장하지 않는다.
- **회사에서 제공할 환경값:** 실제 installer/TC 루트, 모듈 키와 패턴, 기본 Single/Dual 보드, COM·TC Python/저장 명령, 로그인/marker·panic signature·timeout, 이미지 용량과 로그 한도, 인증·터널·라이선스가 맞는 splitter. 비밀 값은 문서·저장소로 받지 않는다.
- **자동 해결하지 않는 예외:** 새/변경 BAT 등록 검토, 실제 물리 상태를 증명할 수 없는 UNKNOWN·전원/USB/장비 복구, 회사 정책과 설계 충돌. 정확한 증거 없이 강제 해제·재퓨징을 자동 수행하지 않는다. 준비값이 없으면 readiness 실패를 명시한다.

## 13. 후속 구현의 공개 진입점과 선택 화면

고정 구현 커밋의 재사용 Python 코어는 `core/integration.py`의 `IntegrationRequest`, `IntegrationService`, `resolve_patterns`, `select_patterns`다. 원본 import 접두사는 `backend.gui_test`, wheel은 기존 `gui_test`다. `IntegrationService.start(key, principal, request)`는 기존 Run을 수락하고, `prepare_run`/`prepare_one`은 기존 GUI Worker만 호출한다. worker는 느린 준비/전송과 TC 실행을 분리하며 준비 receipt가 READY이기 전 claim을 거부한다. `core/repetition.py`의 `integration_decision`은 논리 slot에만 적용하며 raw Attempt와 일반 Run 반복 정책을 보존한다. `integration.logical_results`와 기존 보고서에서 정책 결과·시도 수를 확인한다.

`standalone/integration.py:create_app`과 `main`은 BSP/HardwareWorker를 import하지 않는 GUI 전용 호스트다. runtime의 `gui-test.json`에 `runner=windows-http`와 `integration` 설정을 두고 기본 보드/저장 명령 revision/Runner identity/등록 flash profile/허용 installer roots/TC root를 지정한다. 비밀 값은 `GUI_TEST_RUNNER_TOKEN`, `GUI_TEST_INTEGRATION_TOKEN` 서비스 환경으로 주입한다. API bearer 인증 principal은 `--principal`의 안정된 값이며 브라우저별 session과 구분한다. GUI 전용 호스트와 기존 Dashboard GUI worker는 같은 GUI DB OS lock을 사용한다. 잠금 충돌에서 worker를 하나 더 기동하지 않는다.

구현된 서비스 호출은 §4~5의 `/integration/runs`, `/integration/preview`, `/integration/preparations/{id}`다. 내부 principal은 `/integration/runs/{id}/actions/{action}`에 기존 Command(`expected_version`, `data`)와 멱등 키를 보내며 `cancel`, `pause`, `resume`, `reconcile`, `transfer-control`을 사용한다. 인계는 `data.controller`와 `data.expected_controller`를 현재 version/controller와 함께 CAS 검증한다. 인계/취소는 UNKNOWN 물리 상태의 해제 근거가 아니다. 기존 GUI 제어 endpoint로 integration Run의 예약·복구를 우회할 수 없다.

선택 UI는 같은 기존 TestPage를 사용한다. 인증된 서비스 클라이언트가 `POST /api/v1/gui-test/live/integration/browser-session`을 호출하면 60초·1회용 읽기 전용 bootstrap 경로를 받는다. `PluginClient.browser_access()`의 `url`을 브라우저로 연다. `/auth`는 fragment의 일회용 값을 즉시 URL에서 제거하고 같은 origin의 form POST로 교환한다. 서비스 bearer token은 URL·브라우저 저장소에 전달하지 않는다. session은 30분 HttpOnly/SameSite=Strict cookie이며 GET 상태/로그/보고서만 허용한다. 브라우저 session으로 실행/설정/제어권 변경은 403이다. 읽기 화면을 열어도 서비스 principal·worker 수명·BSP 완료 상태는 바뀌지 않는다.

원본 source export와 설치 예:

```sh
python apps/gui-test/package.py --integration --output .local-reports/<run-id>/bsp-gui-test-plugin-source.zip
# 선택 화면 포함 전 한 번 빌드
npm ci --prefix apps/gui-test
npm run build --prefix apps/gui-test
python apps/gui-test/package.py --integration --include-ui --output .local-reports/<run-id>/bsp-gui-test-plugin-with-ui.zip
python apps/gui-test/package.py --stage-headless-wheel <empty-stage>
python -m pip wheel <empty-stage> --no-deps --no-build-isolation -w <wheels>
python -m gui_test.standalone.integration --runtime <persistent-runtime> --port 8767
```

`--stage-headless-wheel`은 UI 빌드 없이 설치 namespace를 준비한다. UI wheel은 기존 `--stage-wheel`을 사용한다. 설치 시 회사 서비스 계정/경로에 맞춰 `apps/gui-test/bsp-gui-test.service.example`을 조정한다. 새 장기 실행 프로세스를 플러그인 호출의 자식으로 관리하지 않는다. 기존 승인된 Windows EXE를 자동 교체하지 않으며 별도로 준비한 matching Runner와 `source_snapshot_v1`, `installer_stream_v1`, `batch_reservation_v1`, `bsp_upgrade_integration_v1`을 확인한다. source ZIP 생성은 제품 시험/실장비 인수가 아니다.

회사 plugin-side 매핑은 `standalone/plugin_client.py`의 `PluginClient.connect`(서비스/Runner 진단), `PatternDefaults.suggest`(이번 실행 변경 우선), `preview`/`preparation`(선택 미리보기), `start`(안정된 key), `run`(ID 조회), `browser_access`(기존 상세 화면)다. `SystemdService.start`는 설치된 고정 service unit의 start만 호출하며 서비스 stop을 plugin lifecycle에 연결하지 않는다. 실제 private plugin 저장소의 버튼·설정 저장소·설치 hook 위치는 회사 COMPANY_MAP에 기록한다.

## 14. 후속 사용자 요구 · 연결 실패 표시와 파일 진단

2026-11-07 후속 요구: **연결을 시도했는데 실패한 경우 플러그인에서 확인할 수 있고 로그 파일에도 남아야 한다.** Run이 아직 없는 bootstrap/health/auth/version/worker-ready와 backend→Windows Runner 연결/capability 실패도 대상이다. Run ID를 임의로 만들지 않고 연결 시도 자체의 correlation ID를 사용한다. 이 확장은 T-200/204의 연결 실패·인증·진단 검증에 포함하며 모의 결과를 회사 인수로 바꾸지 않는다.

공통 `core/diagnostics.py:DiagnosticRecorder(log_dir=None, callback=None)`는 UTC 시각·correlation ID·단계·소요시간·시도 횟수·안전한 대상 origin·오류 code·간결한 원인·조치 힌트·로그 경로를 구조화하여 callback과 회전 파일에 기록한다. 기본 경로는 서비스/플러그인 실행 계정의 `~/.bsp-upgrade/gui-test-logs/connections.jsonl`이고 8MiB×8개(현재 파일+백업7개)로 제한한다. 회사별 log directory는 recorder 또는 `PluginClient(log_dir=..., diagnostic_callback=...)`로 주입한다. backend Runner adapter도 recorder 주입을 지원한다. 계정별 경로가 다르면 플러그인과 backend 기록의 correlation ID·로그 경로를 연결하여 표시한다.

`PluginClient.last_diagnostic`, 오류의 `TestError.diagnostic`, callback 인자는 회사 플러그인 상태 영역에서 바로 표시할 수 있는 값이다. `connect()`는 서비스 health/identity/worker를 확인한 뒤 기존 capabilities 연결 상태를 읽으며 하드웨어 시작 명령을 보내지 않는다. bounded service start 재시도는 같은 correlation ID와 증가하는 attempt를 사용한다. 연결이 끊겨도 원래 실행 의도의 멱등 키와 Run ID를 보존한다. Runner 진단은 capabilities connection·기존 API 오류의 추가 `diagnostic`·Run integration 준비 오류에 연결하며 새로운 시험 결과 envelope를 만들지 않는다.

로그는 bearer/basic credential·password/token·URL userinfo/query·환경 전체·원시 exception repr를 저장하지 않는다. 고정 오류 설명과 방어적 scrubber를 사용한다. 로그 경로가 쓰기 불가하거나 용량 부족이면 `log_error=DIAGNOSTIC_LOG_UNAVAILABLE`과 조치 힌트를 플러그인에 반환하며 원래 연결 실패를 덮어쓰지 않는다. backend가 내려가도 플러그인 계정의 로컬 기록은 남길 수 있다. 서비스/Runner 원본 로그가 다른 호스트에 있으면 접근 가능한 경로만 연결하고 접근 불가를 성공으로 표시하지 않는다.

현재 문서 작성에는 환경값이 없어도 진행할 수 있다. 실제 배포·장비 인수에는 위 값과 후속 구현·고정 커밋·시험 증거가 필요하며, 문서 완성을 이식 준비 완료로 표시하지 않는다.
