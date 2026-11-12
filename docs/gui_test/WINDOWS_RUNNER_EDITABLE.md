# 편집 가능한 Windows Runner

전용 CPython 3.12.10 x64, 고정 의존성 31개와 실제 실행하는 Python 소스를 함께 전달한다. 회사 PC에서 Runner용 Python/py/pip/Node 설치나 다운로드 없이 사용할 수 있다. 2026-11-12부터 새 EXE는 생성하지 않으며 원본의 기존 EXE ZIP·체크섬은 제거했다. 함께 전달한 원본 저장소의 `docs/design/EDITABLE_WINDOWS_RUNNER_PLAN.md`, `docs/porting/PORT-008.md`에 범위와 검증 기준을 기록한다. 이 문서를 포함한 Runner ZIP에 해당 저장소 문서가 포함된다는 뜻은 아니다. 로컬 빌드·모의 검증과 실제 회사 인수는 구분한다.

## 원본에서 한 명령 빌드

Windows AMD64, 64비트 PowerShell 5.1 이상, 정상 UCRT와 쓰기 가능한 폴더가 필요하다. 시스템 Python·pip·Git는 필수가 아니다. 저장소 루트의 CMD에서 실행한다.

```bat
scripts\build-editable-runner.cmd
scripts\build-editable-runner.cmd -Offline -CachePath "D:\Runner inputs"
scripts\build-editable-runner.cmd -Offline -CachePath "D:\Runner inputs" -OutputPath "D:\delivery\Runner.zip"
```

기본 출력은 `dist/editable-windows-runner/BSP-Windows-Runner-Editable.zip`과 옆의 `.zip.sha256`, 기본 입력 캐시는 `.local-reports/editable-runner-cache`다. 온라인 빌드는 고정 HTTPS URL의 누락된 입력만 받는다. 오프라인은 네트워크로 보충하지 않으며 누락·변조·pin/ABI 불일치 때 실패한다. 잘못된 기존 입력을 자동 교체하지 않는다.

오프라인 원본 빌드를 전달하려면 저장소와 다음 캐시를 함께 옮긴다. 회사에서 소스만 고쳐 재묶는 경우에는 이 캐시가 필요 없다.

```text
inputs.lock.json                 packaging 입력 manifest와 같은 JSON 값
runtime/python-3.12.10-embed-amd64.zip
bootstrap/pip-25.0.1-py3-none-any.whl
wheels/                          입력 manifest의 정확한 31개 wheel
```

`packaging/editable-windows-runner-inputs.lock.json`이 정확한 파일명·URL·raw SHA256·크기를 고정한다. `apps/gui-test/requirements.lock`은 기존 31개 pin을 유지한다. requirements의 해시만 UTF-8 BOM 제거·LF 정규화를 적용한다. runtime/wheel/소스는 실제 bytes를 해시한다. pip 25.0.1은 빌드에서만 쓰고 배포 runtime에 설치하지 않는다. runtime의 PSF 라이선스와 의존성의 배포 메타데이터·라이선스를 보존한다.

CMD는 자식 PowerShell에만 `-ExecutionPolicy Bypass`를 전달한다. 사용자·컴퓨터 정책은 저장하거나 변경하지 않는다. 조직의 강제 정책·실행파일 차단은 관리자의 승인된 절차로 해결해야 한다. 로그는 매 실행 고유한 `.local-reports/editable-bootstrap-*/`와 `.local-reports/editable-runner-*/` 아래 남긴다. 성공 출력에는 ZIP·SHA256·로그 경로, 실패 출력에는 단계·조치·로그와 비정상 종료 코드가 나온다. 인자 오류는 2, 빌드 실패는 1이다. 실패한 빌드는 이전 정상 ZIP을 교체하지 않는다.

## 압축 해제 후 설정·일상 실행

ZIP 전체를 쓰기 가능한 로컬 폴더에 푼다. `runtime/`, `deps/`, `src/`를 함께 유지한다. 한글·공백 경로를 사용할 수 있다. 회사에서 다음 CMD는 PowerShell을 사용하지 않는다.

```bat
setup.cmd
launch.cmd
diagnose.cmd
setup.cmd --help
setup.cmd ports
```

최초 연결 설정에는 Linux SSH 계정, 실제 TC 경로, 번들 밖에 설치된 외부 TC Python과 보드·토큰이 필요하다. OpenSSH Client, TC 패키지, fastboot와 장비 드라이버는 별도다. 번들 Python은 Runner 전용이며 TC Python으로 지정하지 않는다. 기존 사용자 홈의 `.bsp-dashboard/windows` 설정·DPAPI 토큰·실행 기록을 재사용한다. `--home "D:\existing setup"`은 외부의 기존 사용자 홈을 지정한다. 사용자 설정·토큰·TC·DB·로그는 배포 폴더 밖에 둔다.

일상 실행은 `launch.cmd`, 진단은 `diagnose.cmd`다. 종료는 Ctrl+C로 요청하고 진행 중 작업의 정상 종료를 기다린다. 진단은 비대화형이며 서비스를 시작하거나 TC·퓨징을 실행하지 않는다. catalog 조회는 실행 중 서버의 임시 소스 스냅샷을 만들 수 있다.

포트 우선순위는 CLI > 저장 프로파일 > 기본값이다. Windows Runner/브라우저 기본값은 `8771/8766`이다. CLI로 지정하지 않은 로컬 포트가 점유·예약 상태면 이번 실행에서 OS가 배정한 다른 loopback 포트를 사용한다. 실행·진단에 출력된 실제 URL로 접속한다. 명시적 CLI 포트는 고정이며 충돌하면 실패한다. 원격 Runner/API 기본값 `8771/8766`, SSH 포트, Linux URL과 저장 프로파일은 자동 변경하지 않는다. 포트를 바꿔 중복 Runner나 UNKNOWN 차단을 우회하지 않는다.

```bat
setup.cmd ports --port 18771 --dashboard-port 18766 --remote-dashboard-port 8765 --save
```

위 명령은 별도 구성 예시다. `ports --save`만 희망 포트를 저장한다. 원격 포트를 바꾸면 Linux 쪽 설정도 명시적으로 맞춰야 한다. Linux API와 기존 HTTP 계약은 재사용하며 회사 Runner ZIP만 편집형으로 교체하는 범위에서는 Linux 코드를 다시 패키징하지 않는다. 양쪽의 기존 계약·포트·접속 정책을 먼저 확인한다.

## Python 수정과 오프라인 재묶기

대시보드의 웹 화면/CSS 재빌드만으로 Windows Runner를 재설치할 필요는 없다. Linux UI/API/worker와 Windows Runner는 별도 실행물이다. Runner 코드나 양쪽 API/capability 계약이 바뀐 경우에만 해당 Runner 갱신 여부를 확인한다. 같은 Python·의존성을 쓰는 편집형 Runner의 소스 변경은 해당 `src/` 파일을 백업·선별 갱신하고 정상 종료 후 재시작하면 된다. 설정을 다시 입력하거나 runtime/deps를 교체할 필요는 없다. 자동 다운로드/자동 업데이트 기능은 현재 제공하지 않는다. 기존 EXE는 내부 Python 소스 편집이 불가능하므로 EXE 코드 변경 시에는 새 배포가 필요하다.

2026-11-12 설정 편의 변경(RQ-62)은 `src/scripts/setup_flashing.py` 한 파일의 변경이다. [PORT-008 후속](../porting/PORT-008.md)의 기준/해시와 회사 수정 여부를 비교해 적용한다. PATH/SDK의 fastboot 자동 탐색, 읽기 전용 serial 조회와 프로파일 공통 콘솔 입력을 제공한다. 원본 `scripts/setup_flashing.py`와 배포의 `src/scripts/setup_flashing.py`는 같은 파일이다. 웹 재빌드와 이 소스 갱신을 구분한다.

Runner를 정상 종료한 뒤 `src/backend/gui_test/` 또는 동봉된 `src/scripts/*.py`를 수정하고 다시 실행한다. `.py`를 직접 읽으므로 EXE 재빌드나 pip 설치가 필요 없다. runtime/deps와 배포 marker는 수정하지 않는다. 외부 TC·사용자 설정은 기존 외부 경로에서 관리한다.

```bat
repack.cmd --output "D:\delivery\Runner-edited.zip"
```

`--output`을 생략하면 배포 폴더 옆에 새 UUID 이름의 ZIP을 만든다. 기존 출력 파일과 실행 중 배포 폴더 안 경로는 거부한다. wheel 캐시·인터넷·pip 없이 runtime/deps/marker의 전체 무결성, 수집 파일 목록과 Python 문법을 확인한다. 기존 `.py` 편집과 GUI Test 패키지 안 `.py` 추가를 허용하며, 원본 파일 삭제·비소스 변경·불필요한 추가 파일은 거부한다. 사용자 설정·로그를 넣어 오류가 났다면 해당 파일을 배포 밖으로 옮긴다. 수정한 TC나 제품 동작을 실행하거나 통과 판정하지 않는다.

`build-info.json`에는 원본 소스 revision·해당 범위 dirty 상태(확인 불가 시 null), 현재/최초 소스 해시, 부모/새 배포 ID와 최초 소스 대비 `modified`를 기록한다. 재묶기는 원본 revision을 새 Git 커밋처럼 바꾸지 않는다. `SHA256SUMS`는 자신을 제외한 모든 동봉 파일, `.zip.sha256`은 ZIP 전체를 확인한다. 체크섬은 코드 서명이나 제품 시험 통과 증명이 아니다.

## 복원과 미인수 범위

문제가 생기면 Runner를 종료하고 원래 ZIP을 **다른 새 폴더**에 다시 푼 뒤 기존 외부 사용자 홈을 지정해 실행한다. runtime/deps만 임의로 덮어쓰거나 기존 DB·UNKNOWN 기록을 지우지 않는다. 원본·수정 ZIP과 각 체크섬·시험 근거를 함께 보관한다. 실제 회사 Windows 정책·SSH·공유 경로·TC Python·COM·장비 인수 T-217은 실제 수행 근거 전 `NOT_RUN`이다.
