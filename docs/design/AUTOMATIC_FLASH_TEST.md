# Windows 자동 이미지 퓨징·장비 시험

상태: RQ-47/D-48 구현 및 모의 검증 작업. 실제 배치·콘솔·USB·부팅 인수 T-136은 NOT_RUN이다. 실제 실행은 사용자가 환경을 구성한 뒤 수행한다.

## 사용자 확정 흐름

이미지는 Linux 빌드 폴더에 있고 Windows에서 배치 파일을 더블클릭하면 USB 보드에 퓨징되고 보드가 재부팅한다. 콘솔에서 `reboot lkshell` → lkshell 준비 → `fast` 순으로 fastboot에 진입한다. Dashboard의 빌드·검증 이후 장비 테스트 단계에서 퓨징·부팅 확인·TC를 자동으로 이어간다. 최초 계획 확인, 선행 그룹 전체 완료, 관련 판단 게이트, 최종 사람 검토는 유지한다.

기존 수동 장비 시험은 기본값으로 유지한다. 명시적으로 활성화한 자동 프로파일만 이 경로를 사용한다. 자동 실행 도입은 기존 수동 전용 정책의 사용자 승인 예외다. 모델 호출이나 퓨징 성공만으로 장비 시험을 통과시키지 않는다.

## 구성과 실행 위치

Linux `backend/worker/hardware.py`는 BSP `device_test`가 WAITING_INPUT이고 기존 게이트를 통과할 때 현재 Attempt를 RUNNING으로 전환한다. 별도 HardwareWorker 스레드가 Windows HTTP 요청/조회를 처리하여 기존 BSP/GUI worker를 막지 않는다. Windows `gui_test/execution/flashing.py`는 공유 폴더의 이미지를 로컬 실행 폴더에 고정하고 콘솔·fastboot·배치·TC를 순차 실행한다. 기존 SSH 역방향 터널과 실행기 인증을 사용한다.

이 실행의 TC 결과는 BSP 모듈의 장비 테스트 상세에 표시한다. 별도 GUI Test Run을 중복 생성하지 않는다. 일반 TC 화면의 기존 Windows Run/반복/재실행과 구분하며, 그 경로의 운영 Job 자동 완료 차단은 유지한다. 자동 경로는 필수 사례별로 설정한 TC를 한 번씩 실행한다. Dual은 A/B를 같은 이미지로 차례대로 퓨징한 뒤 두 보드가 준비되면 TC를 실행한다. 서로 다른 이미지가 필요한 Dual 구성은 이번 버전에서 지원하지 않는다.

## 이미지와 TC 고정

기존 빌드 산출물 수입은 파일 하나를 등록하므로 이미지 폴더 대신 **manifest JSON을 빌드 산출물로 등록**한다. 외부 에이전트의 기존 v1 artifact 계약을 바꾸지 않는다. manifest 파일 자체의 SHA256은 기존 빌드 수입/검증 규칙을 사용하고, 그 안의 파일별 SHA256을 Windows 복사 시 검증한다. 이미지 파일 이름·경로를 모델 응답에서 실행 명령으로 사용하지 않는다.

```json
{
  "schema_version": 1,
  "batch": "flash.bat",
  "files": {
    "flash.bat": "<64자리 소문자 SHA256>",
    "image.bin": "<64자리 소문자 SHA256>"
  }
}
```

manifest 생성(저장소 루트에서, 실제 경로로 교체):

```text
python -m scripts.create_flash_manifest --root /build/output/build-123 --batch flash.bat --output /build/manifests/build-123.json
```

이 명령은 파일 해시만 계산하며 배치나 장비를 실행하지 않는다. 출력은 이미지 폴더 밖의 새 파일이어야 한다. 기존 manifest는 덮어쓰지 않는다. 이미지 생성 완료 후 manifest를 만들고 빌드 프로파일의 산출물 경로를 해당 파일로 설정한다. Linux 빌드 작업 폴더 안에서 산출물을 생성해야 기존 import_artifact 경계를 통과한다.

Windows 프로파일의 image_root 아래 bundle 폴더는 같은 빌드의 공유 폴더다. 경로 이탈, symlink/junction, Windows 예약 이름·대소문자 충돌을 거부하고 manifest에 열거된 파일만 복사한다. 별도 staging 한도는 기본64GiB이며 TC용16MiB/128MiB 한도를 이미지에 적용하지 않는다. 파일 최대500개, HTTP 요청 최대64KiB, manifest 산출물 최대60,000바이트다. 실행 중 이미지가 다음 빌드로 덮여도 고정 snapshot만 사용한다. 복사본 해시가 맞지 않으면 콘솔 명령 전에 실패한다.

TC는 Windows catalog의 소스 revision, parser, timeout, 선행 TC 정보까지 요청에 고정한다. 로컬 TC snapshot의 catalog와 정확히 일치해야 실행한다. 모든 필수 사례를 비어 있지 않은 TC 목록에 연결하며 중복 TC는 한 번 실행하고 여러 사례에서 결과를 참조한다. 설정 순서가 선행 조건을 만족해야 한다. 기존 Single `python3 {tc_path} -p {com_a}`, Dual `python3 {tc_path} -n {node_a} -n2 {node_b}`를 고정 Windows Python으로 실행한다.

## 설정

1. 기존 [Windows 실행기](../gui_test/WINDOWS_RUNNER.md)의 TC source_root, Python, boards와 SSH 터널을 구성한다.
2. [Windows 퓨징 예제](../../gui_test/config/flashing.example.json)의 내용을 Windows 실행기 설정의 `flashing` 키에 넣는다. 기본 enabled=false이며 실제 값을 확인한 뒤 활성화한다.
3. Linux runtime에 [자동 시험 예제](../../gui_test/config/device-test.example.json)를 `device-test.json`으로 복사한다. 최상위 enabled와 해당 모듈 enabled를 모두 활성화한다. 모듈 키는 BSP 모듈의 정확한 이름이다. profile은 Windows 프로파일 이름, bundle은 image_root 아래 상대 폴더다. connection은 등록 보드와 정확히 일치해야 한다. cases는 해당 모듈의 required_cases와 정확히 같은 키를 사용한다.
4. 설정은 시작할 때 읽으므로 실행 중 작업을 먼저 정리한 뒤 각 서비스를 다시 시작한다. 환경 토큰은 기존 GUI_TEST_RUNNER_TOKEN을 사용하며 설정 파일에 넣지 않는다. 자동 설정이 없거나 disabled이면 수동 동작을 유지한다. enabled인데 manifest/매핑이 불완전하면 이유를 표시하고 자동 실행하지 않는다.

필수 실제 값: fastboot.exe 절대 경로, 공유 이미지 루트, 검토한 배치 SHA256, 배치의 명확한 성공 문구, 실패 문구 목록, 보드별 COM/baud rate/개행(cr·lf·crlf)/lkshell 프롬프트/정상 부팅 준비 문구/fastboot serial. COM과 node를 serial로 추정하지 않는다. 콘솔은 현재 8N1을 사용한다. 다른 framing/flow control이 필요하면 실제 인수 전에 확장이 필요하다. 예제에는 사용자 미확인 값을 채워 넣지 않았다.

배치는 등록된 해시 버전만 실행하며 GUI에서 임의 셸 문자열을 받지 않는다. 배치 실행은 로컬 복사본의 폴더에서 cmd.exe /d /c로 수행하고 인자를 추가하지 않는다. 인수 전에 배치가 `BSP_FASTBOOT`의 절대 도구 경로와 `ANDROID_SERIAL`의 대상 보드를 사용하거나 그에 상응하는 고정 도구·대상을 사용하는지 검토해야 한다. 모든 fastboot 실패를 비정상 종료 코드로 전달하고 성공 문구는 전체 완료 후에만 출력해야 한다. 별도 창을 여는 start, 대화형 pause, 다른 폴더/공유 경로의 미고정 파일 참조가 있으면 수정 또는 전용 프로파일 검증이 필요하다. 배치 해시 등록은 그 검토를 마친 운영 설정이다. 현재 실제 배치 내용을 받지 않았으므로 이 호환성은 검증하지 않았다.

## 실행·완료·실패 계약

인증된 POST `/v1/flash-tests`는 id, runner_id, profile, bundle, manifest, source_revision, connection, template, cases, tests, baseline을 받는다. id는 현재 BSP device_test Attempt ID다. Host가 요청 해시와 예약을 jobs에 먼저 저장한 뒤 작업을 시작한다. 기존 `/v1/executions/{id}/reconcile`로 조회한다. 같은 ID/같은 요청은 기존 결과, 다른 요청은 충돌이다. 실행 전 거부는 not_started 기록으로 남는다.

PREPARING → ENTERING_LKSHELL → ENTERING_FASTBOOT → FLASHING → WAITING_BOOT → TESTING → COMPLETED 순이다. Dual은 보드별 진입·퓨징·부팅 확인을 반복한다. fastboot 열거 결과가 선택 serial 한 개와 정확히 일치해야 배치를 실행한다. 플래시 전 콘솔을 열어 재부팅 문구를 수집하고, 부팅 확인 후 닫아 TC에 포트를 넘긴다. 콘솔이 재부팅 중 사라지면 준비를 추정하지 않고 실패한다. COM 변경·콘솔 재연결 자동 탐지는 실제 인수 후 확장 범위다.

배치 종료 코드0, 프로세스 트리/파이프 종료, 성공 문구, 실패 문구 없음, 보드별 부팅 준비 확인이 모두 있어야 TC로 진행한다. TC는 기존 엄격한 `Test Result: PASS|FAIL` 판정기를 사용한다. ERROR/timeout/결과 누락은 장비 시험 성공이 아니다. 서버가 요청 ID·해시, 현재 이미지·소스·계획·검증 Attempt·필수 사례, 모든 보드의 퓨징/부팅 근거, TC 목록·parser·최종 출력/종료 코드를 재검사한 뒤 **같은 BSP Attempt**를 완료한다. 호스트의 퓨징 프로세스 및 준비 확인 근거이며 보드 저장소의 독립 readback 해시 증명은 아니다. 일반 GUI Run의 이미지 증명으로 재사용하지 않는다.

일시 중지는 신규 배정을 막는다. 이미 배정된 Windows 퓨징·TC 묶음은 완료까지 계속한다. TC 취소 endpoint로 퓨징을 강제 종료할 수 없다. BSP 취소 요청은 해당 묶음의 종료를 확인한 뒤 CANCELLED 처리하며 퓨징 중 즉시 중단을 뜻하지 않는다. 최종 사람 검토는 자동 수행하지 않는다.

터널/브라우저 단절은 Windows 작업을 죽이지 않는다. Linux는 UNKNOWN으로 표시하고 조회로 복구한다. POST 전후 장애에서도 같은 작업을 다시 전송하지 않으며 조회 시 없는 ID는 tombstone으로 고정해 지연 요청을 차단한다. 정상 Windows 서비스 종료는 실행 중 퓨징 스레드를 기다린다. 호스트 강제 종료/프로세스 종료 불명/퓨징 timeout은 UNKNOWN이며 예약을 유지한다. Windows 강제 종료 시 Job Object가 자식을 종료할 수 있으므로 중단 없는 퓨징을 보장하지 않는다. 이 상태의 실장비 복구·수동 해제 UI는 이번 버전에 없으며 DB 삭제로 우회하지 않는다.

Linux 자원 lease와 Windows 공통 jobs 예약으로 자동 묶음끼리, 자동 묶음과 일반 TC가 겹치지 않는다. 외부 터미널·다른 독립 프로그램의 장비 사용까지 잠그지는 못한다. TC당 로그64KiB, 전체 pipeline 근거 약1MiB에서 제한하고 기존 마스킹을 적용한다. 불명 상태는 자동 재시도하지 않는다. 명확한 실패는 기존 모듈 재시도에서 새로운 Attempt로 시작한다. 이전 자동 실행 기록은 이전 Attempt에 보존한다.

## 저장·검증

Linux의 기존 SQLite schema_version=1을 유지한다. Windows 실행 DB에는 기존 기록을 보존하며 runner_meta 테이블과 영속 runner identity를 추가한다. BSP stage/attempt JSON에 automation, automation_blocked를 추가하고 기존 leases를 사용한다. Windows jobs에는 kind=flash-test 및 구조화된 단계/프로세스 근거를 저장한다. GET /v1/identity로 준비 시 고정한 runner_id를 실행 요청·복구 조회·결과/tombstone 모두에서 대조한다. 같은 URL이 다른 Windows runtime으로 연결되면 UNKNOWN을 유지하고 새 호스트의 미실행 기록을 원래 작업 종료로 오인하지 않는다. 복구에는 원래 Windows runtime과 터널 설정이 필요하다. 설정 없는 이전 DB/수동/Mock는 그대로 읽는다. 화면은 BSP 모듈 상세의 상태·완료 TC 수·사례 결과와 접이식 로그를 표시한다.

시험 T-131~135는 가짜 콘솔/fastboot/배치와 임시 파일·DB·TC로 검증한다. T-136은 사용자의 실제 Linux 공유 폴더·Windows·보드·배치 인수다. [실행 기록](../testing/runs/20261103-automatic-flash-test.md)에 코드 기준, 독립 Astra 리뷰, 별도 GPT-6-sol 시험과 미검증 범위를 기록한다.
