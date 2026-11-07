# 편집 가능한 Windows Runner 배포 계획

## 1. 요구사항 분석 · 2026-11-07

상태: **REQUIREMENTS_DEFINED / ARCHITECTURE_PENDING / IMPLEMENTATION_NOT_STARTED**. 기준 커밋은 `0178d045db16526560a155f05693c1f2dc0bbb47`이며 이 기준에서 `feature/editable-windows-runner`로 작업을 분리했다. 사용자 승인 범위는 편집 가능한 Python 소스·전용 Python·고정 의존성을 담은 오프라인 ZIP과 쉬운 빌드·실행 스크립트다. “빌드 쉽게 … 포트번호도 막 수동으로 입력해야 동작”하는 불편을 해결한다. `RQ-61 / D-65 / T-210~217 / PORT-008`은 현재 문서에서 미사용인 **후속 등록 제안 ID**이며 이 문서만으로 구현·시험 완료를 뜻하지 않는다.

### 현행 근거와 문제

- 소스 마법사는 [`setup.cmd`](../../scripts/setup.cmd)의 `py -3`와 [`setup_runtime.py`](../../scripts/setup_runtime.py)의 `Wizard.install()`에서 사용자 홈 venv/pip 설치에 의존한다. 회사 프록시에서 `annotated-doc` 설치 실패가 보고됐으며 해당 패키지는 [현재 잠금 파일](../../apps/gui-test/requirements.lock)에 있다. 정확한 회사 실패 원인은 미확인이다.
- 기존 [EXE 배포](WINDOWS_RUNNER_BUNDLE.md)는 설치 의존성을 없앴지만 코드 변경에 다시 패키징이 필요하다. [`build_windows_runner.py`](../../scripts/build_windows_runner.py)는 이미 준비된 고정 환경을 요구한다. 기존 EXE와 회사 플러그인 ZIP을 교체하지 않고 별도 편집형 배포를 추가한다.
- [RQ-59 명령 계약](SETUP_COMMANDS.md)과 [`setup_ports.py`](../../scripts/setup_ports.py)는 `CLI > 저장 프로파일 > 기본값` 및 명시적 `ports --save`를 구현했다. 기본값은 Windows Runner/브라우저 `8771/8766`, Linux 역방향 Runner/API `8771/8766`이다. [실행 안내](../gui_test/RUN_AND_DIAGNOSE.md)의 `18771/18766/8771/8765`는 별도 구성 예시다. 이를 전역 기본값으로 오인하거나 고정 URL을 안내하는 혼동을 없애야 한다.

### 기능·제약

1. **편집형 배포:** Windows x64용 전용 CPython과 잠근 Runner 의존성, 실제 실행에 사용하는 `.py`, 설정·실행·진단 진입점, 짧은 안내와 출처/체크섬을 한 ZIP으로 제공한다. venv 폴더 복사를 이동 가능한 런타임으로 간주하지 않는다. 회사 PC에는 Runner용 Python/py/pip/Node 설치나 다운로드가 필요 없어야 한다. 소스 수정은 정상 종료 후 다음 실행에 반영되며 EXE 재빌드가 필요 없다.
2. **한 명령 준비·빌드:** 소스에서 문서화된 단일 Windows 명령으로 준비와 ZIP 생성을 수행한다. 온라인 준비와 이미 확보한 Python 배포물·wheel 캐시를 사용하는 오프라인 입력을 지원한다. 런타임/의존성 버전·아키텍처·해시·누락을 검증하고 오프라인 모드에서 네트워크로 보충하지 않는다. 실패 단계·조치·로그 위치와 비정상 종료 코드를 반환하며 실패 산출물을 성공 배포본으로 남기지 않는다. 회사 프록시 우회나 의존성 임의 제거로 해결하지 않는다.
3. **쉬운 일상 실행:** 최초의 실제 TC 경로·외부 TC Python·SSH 계정·보드/토큰 설정은 유지한다. 준비된 설정에서는 단일 실행 진입점으로 Runner와 터널을 시작하고 별도 진단 진입점을 제공한다. 일상 실행마다 포트 숫자나 긴 CLI를 입력하지 않는다. 기본값·기존 저장값을 재사용하고 유효값과 실제 접속 URL을 표시한다. 실행기 바인딩·SSH 양 끝점·준비 확인·doctor가 같은 유효 설정을 사용한다.
4. **포트 충돌:** Windows 로컬 충돌을 사용자에게 숫자 탐색을 떠넘기지 않는 흐름으로 처리한다. 자동 대체 포트 선택 여부·범위·실행 중 endpoint 전달 방식은 구조 설계에서 정한다. 대체하더라도 Linux API/역방향 포트·SSH 서버 포트와 Linux 연결 URL을 몰래 바꾸지 않는다. 기존 프로세스를 종료하거나 같은 runtime의 중복 실행·UNKNOWN 차단을 포트 변경으로 우회하지 않는다. CLI 우선순위·명시 저장 계약 변경이 필요하면 D-65에 구현 선택으로 명시하며 사용자 운영 정책으로 꾸미지 않는다.
5. **보존과 격리:** 기존 `--home`, JSON 추가 필드, DPAPI 토큰, runtime/DB/runner identity, 예약·UNKNOWN·복구, RQ-60 실행/퓨징 계약을 보존한다. 배포 폴더 이동으로 새로운 사용자 runtime을 만들지 않는다. TC는 기존 외부 Python을 명시 사용하고 번들 Python을 TC 기본값으로 저장하지 않는다. OpenSSH·TC 패키지·장비 드라이버·fastboot는 별도이며 자동 설치하지 않는다. 토큰은 SSH/TC 자식·배포 ZIP·일반 로그에 포함하지 않는다.
6. **전달·증거:** 새 ZIP은 기존 승인 EXE/ZIP 및 회사 플러그인 ZIP과 별도 경로에 만든다. 배포 기준 소스와 이후 사용자 편집 상태를 구분하며 원본/대상 커밋·필수 캐시·검증·복원·미인수 범위를 PORT에 남긴다. 사용자 변경 `apps/gui-test/config/device-test.example.json`, `.vscode/`는 보존한다.

### 인수 조건 제안

| 시험 ID | 통과 기준 |
|---|---|
| T-210 | 한 명령으로 준비/빌드한다. 검증된 로컬 캐시만으로 오프라인 재빌드하며 누락·변조·잘못된 버전/아키텍처·의존성 실패를 명확히 거부한다. 로그와 실제 종료 코드가 남는다. |
| T-211 | ZIP을 저장소 밖 한글·공백 경로에 풀고 다른 로컬 경로로 옮겨도 시스템 Python/py/pip 없는 PATH와 인터넷 없이 설정/도움말 및 모의 Runner가 실행된다. 번들 밖 원본 설치에 의존하지 않는다. |
| T-212 | 압축 해제한 `.py`의 무해한 fixture 변경이 재시작에 반영된다. EXE 재빌드·pip 설치가 없고 배포 출처와 수정 상태를 혼동하지 않는다. |
| T-213 | 기본값·저장값·CLI 우선순위와 명시 저장을 검증한다. 비기본 기존 구성도 인자 없는 일상 실행으로 재사용하며 출력 URL·SSH argv·doctor 대상이 일치한다. |
| T-214 | 로컬 포트 점유를 숫자 재입력 없는 설계 흐름으로 처리하고 유효 endpoint를 진단에서도 사용한다. 원격 포트 불변·중복 실행 차단·경합 실패·소유 자식만 정리를 검증한다. |
| T-215 | 기존 home/설정/DPAPI/runtime·UNKNOWN·예약을 재사용한다. 외부 TC Python·토큰 격리·loopback 인증·중단/복구와 관련 RQ-46/47/51/58/59/60 회귀가 유지된다. |
| T-216 | 새 ZIP의 파일 목록·잠금 버전·체크섬·소스 기준과 짧은 빌드/실행/진단/복원 안내가 일치한다. 민감 정보·사용자 설정·runtime·개발 로그가 없고 기존 승인 산출물이 보존된다. |
| T-217 | 회사 PC 정책·실제 공유 경로/SSH/TC Python·장비 연결 인수. 로컬 모의 결과와 별도이며 실제 수행 증거 전 **NOT_RUN**. |

### 가정·미확인 범위

현재 [연결 계약](../gui_test/WINDOWS_RUNNER.md)의 인증된 loopback HTTP + SSH 포워딩을 유지한다. 직접 사내 HTTP/LAN 바인딩·새 TLS/인증 체계, 실제 SSH/COM/퓨징/TC·모델/Jira 실행은 이번 구현·모의 검증 범위 밖이다. API/DB·BSP 게이트 재설계도 범위 밖이다.

실제 회사 Windows 버전/아키텍처, 프록시 오류 원문, 승인된 Python 배포물·반입 정책·서버 포트/SSH 정책은 확인되지 않았다. 기존 Windows x64 범위로 로컬 구현을 진행할 수 있어 요구사항 단계의 차단 사유는 없다. 정확한 CPython 배포물·wheel 집합과 해시는 실제 확보/검사 후 구조·구현에서 고정하고, 실제 회사 인수·다른 아키텍처 지원은 주장하지 않는다. 저장/자동 포트 선택의 구체적 설계와 필요한 D-63 후속 명시는 다음 단계의 결정 사항이다.

## 2. 구조 설계 · 2026-11-07

상태: **ARCHITECTURE_DEFINED / DETAILED_DESIGN_PENDING / IMPLEMENTATION_NOT_STARTED**. §1의 범위에 따라 배포·기동 계층만 확장한다. RQ-60 API, 예약·전송·퓨징·TC·복구 코어와 Linux worker는 재사용한다. 직접 LAN HTTP와 Windows→Linux polling 전환은 제외한다.

### 2.1 배포와 책임 경계

새 산출물은 `dist/editable-windows-runner/BSP-Windows-Runner-Editable.zip`이다. 기존 EXE/회사 ZIP을 교체하지 않는다. 다음 경로는 배포 루트 기준이며 저장소의 Python import 구조를 유지한다.

| 구성 | 책임·공개 접점 |
|---|---|
| `runtime/` | CPython 3.12.10 x64 embeddable. 시스템 Python/레지스트리/PATH에 설치하지 않는다. |
| `deps/` | 잠금 파일과 일치하는 wheel을 빌드 시 설치한 라이브러리. 회사 실행에서 pip/다운로드 없음. |
| `src/backend/gui_test/`, `src/scripts/` | 기존 실행 코드와 마법사의 실제 편집 대상. 최소 `backend/__init__.py`·필수 설정 예제도 명시 수집한다. |
| `setup.cmd`, `launch.cmd`, `diagnose.cmd` | 동봉 Python의 절대 경로로 최초 설정, `run`, `doctor`를 호출한다. 인자와 종료 코드를 보존한다. |
| `repack.cmd` | 수정한 소스와 현재 runtime/deps를 네트워크·wheel 캐시 없이 새 ZIP으로 묶는다. 실행 중 배포본을 덮어쓰지 않는다. |
| `bundle.json`, `build-info.json`, 체크섬·안내 | 배포 모드/버전, 원본 소스 기준, 실제 파일 해시, 의존성/라이선스와 수정 상태를 구분한다. |

`runtime/python312._pth`는 표준 라이브러리·runtime·`../deps`·`../src`만 상대 경로로 지정하고 `import site`와 환경 `PYTHONPATH`에 의존하지 않는다. 실행은 bytecode 생성을 끄고 `.py`를 사용한다. CPython의 [embeddable 안내](https://docs.python.org/3.12/using/windows.html#the-embeddable-package)에 따라 의존성을 애플리케이션과 함께 제공한다. 원본/의존성 위치에 절대 개발 경로를 기록하거나 venv를 복사하지 않는다.

### 2.2 준비·빌드와 회사 재묶기

원본 저장소의 `scripts/build-editable-runner.cmd` 한 명령이 PowerShell bootstrap → 동봉 CPython으로 실행하는 표준 라이브러리 기반 builder를 연결한다. `-Offline -CachePath <dir>`을 지원한다. 최소 준비 환경은 Windows x64, PowerShell 5.1 이상, 쓰기 가능한 로컬 폴더와 정상 UCRT이며, 온라인은 승인된 HTTPS 경로, 오프라인은 완전한 입력 캐시가 필요하다. 시스템 Python/py/Node/PyInstaller는 요구하지 않는다. 조직이 PowerShell/실행파일을 차단한 경우 해당 단계와 로그를 표시하며 정책을 변경하지 않는다.

builder는 별도 staging에서 고정 CPython ZIP, **빌드에만 쓰는 고정 pip wheel**, 잠금된 Windows CPython 3.12 wheel 집합을 검증한다. pip를 build 전용 영역에서 실행해 `deps/`에 설치하며 회사용 runtime에는 설치/업데이트 기능을 넣지 않는다. 온라인 준비는 누락된 고정 입력만 받고 오프라인은 네트워크 호출 없이 실패한다. `apps/gui-test/requirements.lock`이 버전 기준이고, 별도 packaging 입력 manifest는 정확한 wheel 이름·SHA-256·플랫폼과 해당 lock의 해시를 고정한다. 내용 불일치·소스 빌드가 필요한 배포물·누락·해시 오류를 거부한다. 임의 최신 버전 조회/get-pip 실행으로 대체하지 않는다.

CPython ZIP SHA-256은 `4acbed6dd1c744b0376e3b1cf57ce906f9dc9e95e68824584c8099a63025a3c3`이며 [PSF SBOM](https://www.python.org/ftp/python/3.12.10/python-3.12.10-embed-amd64.zip.spdx.json)의 CPython 항목과 일치한다. 조정자가 `.local-reports/rq61-inputs/`에 원본 ZIP·SBOM·다운로드 기록을 확보했다. 기존 wheelhouse 31개는 `wheelhouse-inspection.json`에서 lock의 이름/버전과 일치하지만 ABI/import·배포 검증은 아직 수행 전이다. pip bootstrap artifact의 버전·URL·해시는 상세 설계/구현에서 실제 확보 후 고정해야 한다.

검증된 runtime/deps와 명시 수집한 소스만 ZIP에 넣고 파일 체크섬·빌드 기준·라이선스를 기록한다. import/진입점 smoke 이후 새 ZIP을 publish하며 실패하면 이전 정상 산출물을 보존한다. `repack.cmd`는 원래 runtime/deps 무결성을 검사하되 소스 변경은 허용하고 새 소스 해시/부모 배포 ID/`modified`를 기록한다. 소스 수정 자체를 변조 오류로 차단하지 않으며, 재묶기를 제품 시험 통과로 표시하지 않는다. 설정·토큰·runtime·로그·개발 캐시는 수집하지 않는다.

### 2.3 실행 모드와 자식 프로세스

`execution/bundle.py`의 실행 환경 경계를 `source / frozen / editable`로 구분한다. editable은 고정 배포 marker와 실제 동봉 interpreter 경로가 일치해야 하며 `sys.frozen`을 위조하지 않는다. `Wizard`는 editable에서 `sys.executable`을 사용하고 venv 생성/pip 설치를 생략한다. 현재 비frozen의 venv 선택(`setup_runtime.py:291`), TC Python 기본값(`:379`), 설치(`:420`)를 분리하는 것이 필수다. `Host`도 editable에서 외부 TC Python을 명시 검증한다. 번들 Python이나 배포 내부 Python을 TC 기본값으로 쓰지 않는다.

설정과 DB는 기존 사용자 home/`--home`에 그대로 두며 배포 위치 이동으로 새 runtime을 만들지 않는다. 실행기만 동봉 Python을 사용한다. SSH/TC/배치의 외부 환경에는 Runner 토큰·번들 전용 변수/PATH가 전달되지 않게 기존 정리 함수를 확장한다. editable 자식은 기존 비frozen gate/Windows Job Object 경로를 사용하고 frozen 전용 DLL 처리와 `--contained-child`는 보존한다. 새 런타임으로 이 경로의 중단·실패·재시작 회귀를 검증한다.

### 2.4 로컬 포트와 실행 수명

희망 설정의 **CLI > 저장값 > 기본값**, 기본 포트 및 `ports --save`의 명시 저장 원칙은 유지한다. Windows Runner/브라우저 포트는 CLI로 명시했으면 고정하고 충돌 시 실패한다. CLI가 없으면 저장값/기본값을 먼저 시도하고 점유·예약 실패 때 OS가 배정한 다른 loopback 포트를 이번 실행에만 사용한다. 원격 Runner/API·SSH 포트, Linux URL과 저장 프로파일은 자동 변경하지 않는다. D-65에는 이 실행 중 대체 정책을 D-63의 후속 구현 선택으로 기록한다.

`run` 흐름은 **home별 launch OS lock → 기존 host lock 충돌 확인 → Runner 소유 socket 확보·기동 → 인증 identity 준비 확인 → SSH 기동 → 실제 URL 표시**다. 기존 `create_app` lifespan의 `ProcessLock(runtime/runner.lock)`(`execution/host.py:290`)은 최종 단일 실행 보장으로 유지한다. 사전 host lock 확인은 획득 후 즉시 해제하며 새 launcher lock과 혼동하지 않는다. 기존 직접 host/구 EXE가 실행 중이면 포트를 바꿔 두 번째 실행하지 않는다. 사전 검사 이후 경합해도 최종 host lock 실패를 준비 완료로 간주하지 않는다.

포트 검사 후 다른 서비스가 가로채는 문제를 피하려고 새 Wizard 기동 경로는 `host.py`의 **main만** 확장한다. child가 loopback socket을 직접 bind하고 동일 socket을 Uvicorn `Server.run(sockets=[...])`에 넘긴다. 선호 포트 실패 시 CLI 고정 여부에 따라 실패하거나 port 0으로 한 번 대체한다. child는 이번 launch ID/PID·실제 포트의 작은 시작 receipt를 부모에게 전달한다. 부모는 자기 child의 살아 있음과 receipt를 검증하고 그 포트의 인증 identity가 준비된 뒤만 SSH를 시작한다. Host API·실행 결과 계약에는 필드를 추가하지 않는다.

SSH `-R` 대상은 실제 Runner 포트, `-L`은 선택한 실제 Windows 브라우저 포트를 사용한다. 브라우저 포트는 사전 probe로 선택하되 OpenSSH bind와의 경합은 원자화할 수 없으므로 SSH 실패로 반환한다. 인증/원격 정책 오류를 로컬 포트 충돌로 추측하여 반복 로그인하지 않는다. 기존 양방향 SSH를 유지하며 브라우저 터널 선택 기능은 추가하지 않는다.

부모는 `<home>/runtime/active-endpoints.json`에 launch 식별자·소유 프로세스 식별 근거·runner identity·실제 로컬 포트·원격 포트·단계/URL을 원자 기록한다. 토큰은 없다. 이 파일은 설정/완료 증거가 아닌 **현재 실행 발견용 receipt**다. `doctor/check`는 CLI 포트가 없을 때 살아 있는 소유자와 현재 launch에 속한 receipt를 검증하여 실제 Runner를 조회한다. 명시 CLI가 있으면 이를 사용한다. PID 재사용/사라진 소유자/오래된 receipt를 현재 실행으로 믿거나 다른 포트로 조용히 성공 처리하지 않는다. `ports`는 희망값과 유효한 실제값을 구분하고 저장은 희망값에만 적용한다. 종료 시 자기 launch의 receipt만 정리하고 기존 child 정상 종료/UNKNOWN 보존 정책을 유지한다.

### 2.5 후속 작업 경계와 주요 위험

| 단위 | 소유 범위·검증 |
|---|---|
| 빌드·패키징 | 신규 CMD/PowerShell/bootstrap-builder, packaging 입력 manifest, repack/배포 안내. T-210~212/216. |
| 실행·포트 | `setup_runtime.py`, `setup_ports.py`, `execution/bundle.py`, `execution/host.py` main과 필요한 환경 정리 접점. T-213~215. RQ-60 코어 수정 금지. |
| 시험·문서 | 별도 시험 작성/실행·독립 리뷰, RQ-61/D-65 등록, PORT-008과 실행 기록. T-217은 실제 인수 전 NOT_RUN. |

공유 `setup_runtime.py`는 한 구현 소유자만 수정하고 빌더는 정해진 실행 인터페이스를 소비한다. 소스/deps/_pth 격리와 Windows native wheel·UCRT 호환, 기존 EXE/소스 회귀, 새 socket/lock/receipt 경합, 수정된 소스의 출처 표시가 핵심 위험이다. 위 입력과 인터페이스로 상세 설계는 진행 가능하며 빌드 bootstrap pip 고정·실제 import·회사 반입 정책은 구현/인수에서 확인할 항목이다. 이 설계 자체는 새 ZIP 생성 또는 회사 인수 완료를 뜻하지 않는다.

## 3. 상세 설계 · 2026-11-07

상태: **DETAILED_DESIGN_DEFINED / IMPLEMENTATION_NOT_STARTED**. §1~2를 아래 계약으로 고정한다. API·DB schema 변경은 없다. 내부 함수 분할은 구현자가 결정하고 공개 helper는 독립 시험의 접점으로 유지한다.

### 3.1 빌드·배포 계약

원본 명령: `scripts\build-editable-runner.cmd [-Offline] [-CachePath <dir>] [-OutputPath <zip>]`. CMD → `powershell.exe -NoProfile -ExecutionPolicy Bypass -File build-editable-runner.ps1` → 검증·추출한 embedded Python → 표준 라이브러리 `scripts/build_editable_runner.py build --source-root ... --cache-path ... --output ... [--offline]` 순이다. 기존 저장소 builder 관례대로 이 child PowerShell 프로세스에만 실행 옵션을 주며 사용자/컴퓨터 정책을 저장·변경하지 않는다. 강제 그룹 정책·실행파일 차단은 오류로 반환하며 우회 재시도하지 않는다. 시스템 Python/py/pip/Git는 필요 없다. 회사 일상 setup/run/doctor/repack은 CMD+동봉 Python만 사용하여 PowerShell과 무관하다. 인자는 배열로 전달하고 실제 종료 코드를 보존한다. 기본 cache는 `.local-reports/editable-runner-cache`, 출력은 §2.1 경로다.

`packaging/editable-windows-runner-inputs.lock.json` v1은 `python_version="3.12.10", platform="win_amd64", requirements_sha256, runtime, pip, wheels`를 담는다. artifact 필드는 `filename, url, sha256, size`; wheel은 `name, version, tags` 추가. runtime 해시는 §2.2, pip는 **25.0.1 / pip-25.0.1-py3-none-any.whl / 1,841,526 bytes / `c46efd13b6aa8279f33f2864459c8ce587ea6a1a59ee20de055868d8f7688f7f`**로 고정한다. 확보한 `.local-reports/rq61-inputs/pip-download.json`의 공식 URL 및 `wheelhouse-inspection.json`의 31개 이름·버전·해시를 구현 manifest로 옮긴다. 최신 버전 조회/get-pip는 없다.

cache 구조는 `inputs.lock.json`, `runtime/<zip>`, `bootstrap/<pip-wheel>`, `wheels/<31 wheels>`다. cache lock 사본은 저장소 manifest와 같은 JSON 값이어야 한다. `<cache>/build.lock`의 비차단 OS lock을 bootstrap부터 완료까지 보유한다. 온라인은 누락된 고정 artifact만 받고 손상 파일은 오류로 반환한다. 오프라인은 완전한 캐시만 사용하고 네트워크 함수를 호출하지 않는다. 크기·해시·wheel METADATA/호환 tag·pin 집합·requirements 해시를 검사하며 sdist, ZIP 경로 이탈/링크/중복/대소문자 충돌을 거부한다. `requirements_sha256`만 UTF-8 BOM 제거 후 CRLF/CR을 LF로 정규화한 UTF-8 bytes의 해시이며 pin 집합도 별도로 정확히 검증한다. runtime/wheel 및 배포 source/immutable 해시는 실제 raw bytes 기준이다.

임시 build Python에만 pip wheel 경로를 넣어 검증된 wheel들을 `pip install --no-index --no-deps --no-compile --only-binary=:all: --target <stage/deps>`로 설치한다. 최종 `_pth`의 새 프로세스 import smoke 후 출력 옆 임시 ZIP을 원자 publish한다. 동일 출력도 OS lock으로 보호하고 실패 시 이전 ZIP을 보존한다. 로그는 고유 `.local-reports/<run-id>/`, 오류는 단계·파일·조치·로그 경로 및 nonzero(인자 오류 2)다. 배포본에는 pip bootstrap/cache/staging을 넣지 않는다.

| 배포 접점 | 고정 계약 |
|---|---|
| `bundle.json` v1 | `mode="editable", python="runtime/python.exe", source="src", dependencies="deps", python_version="3.12.10", platform="win_amd64"` |
| `runtime/python312._pth` | `python312.zip`, `.`, `../deps`, `../src` 네 줄. `import site` 없음 |
| `setup.cmd / launch.cmd / diagnose.cmd` | `"%~dp0runtime\python.exe" -B -m scripts.setup_runtime` + 각각 기본 메뉴/`run`/`doctor`; `%*`·종료 코드 전달 |
| `repack.cmd` | 같은 Python으로 `-B -m scripts.build_editable_runner repack --bundle-root "%~dp0." %*` |
| 수집 허용 목록 | `src/backend/__init__.py`, `src/backend/gui_test/**/*.py`와 필요한 패키지 데이터의 명시 목록; `src/scripts/{setup_runtime,setup_ports,setup_flashing,build_editable_runner}.py` 및 필요 시 빈 `__init__.py`; requirements lock·`windows-runner.example.json`; runtime/deps/라이선스·안내 |

`device-test.example.json`, `.vscode/`, 사용자 설정/토큰/DB/runtime/로그, `.git`, venv, `.pyc`/`__pycache__`는 수집하지 않는다. 배포 `runtime/`은 interpreter 전용이다. 필요 데이터는 추출본 smoke로 확인하여 allowlist에만 추가한다. 실행은 항상 `-B`로 새 `.py`를 읽는다.

`build-info.json` v1: `bundle_id`(UUID), `parent_bundle_id`(최초 null), `source_revision/source_dirty`(미확인 null), `modified`, `built_at`, `inputs_lock_sha256`, `original_source_hashes`, `source_hashes`, `immutable_hashes`. hash map은 배포 상대 POSIX 경로→SHA256; immutable은 runtime/deps 및 bundle.json의 전체 집합이다. `SHA256SUMS`는 자신 외 모든 배포 파일, 옆 `.sha256`은 ZIP 자체를 검사한다. `repack --output <new.zip>`은 immutable 추가/누락/변경을 거부하되 src `.py` 편집/추가를 허용한다. 원본 hash map을 보존하고 새 hash·부모 ID·새 ID·원본 대비 modified를 기록한다. 기본 출력은 배포 폴더 옆 새 ID ZIP이며 기존 파일 덮어쓰기를 거부한다. 캐시/네트워크/pip 없이 문법만 검사하고 편집 앱/TC를 실행하지 않는다. 재묶기는 제품 시험 통과가 아니다.

### 3.2 실행·포트·발견 계약

`bundle.py`는 interpreter 부모의 배포 marker와 canonical `runtime/python.exe`, 자신의 `src/backend/gui_test/execution/bundle.py` 위치가 함께 일치할 때 editable로 판정한다. marker가 있는데 잘못되면 오류이며 source로 후퇴하지 않는다. 판정은 배포 식별이며 코드 서명이 아니다. Wizard는 editable에서 `sys.executable`을 쓰고 설치 메뉴는 포함된 의존성을 안내한다. 외부 TC Python과 `--home`은 배포 루트 밖이어야 한다. 기존 home/DPAPI/DB/UNKNOWN을 재사용한다. SSH/TC 환경에서 token·번들 전용 변수/PATH를 제거하되 editable에 frozen DLL reset을 적용하지 않는다. 기존 비frozen Job Object/gate 자식 경로에도 `-B`를 보존한다.

표준 라이브러리 신규 `execution/launch.py` 하나가 socket·OS lock·receipt를 담당한다. `LaunchLock`은 기존 `ProcessLock`과 같은 Windows byte-0/POSIX flock 규칙이다. setup은 FastAPI를 import하는 `standalone.server`를 최초 설정 시 import하지 않는다. `<runtime>/setup-launch.lock`을 run 전체 수명 동안 잡고 기존 `runner.lock`은 사전 획득/즉시 해제로 검사한다. Host lifespan의 최종 `ProcessLock`은 유지하며 직접 host/구 EXE와 경합하면 실패한다.

부모는 32자리 소문자 hex `launch_id`와 `<runtime>/launch-<id>.json`을 만들고 child main에 `--launch-id`, `--startup-receipt` 및 부모 PID/생성시각을 전달한다. 부분 인자·runtime 밖 경로는 거부한다. Runner 포트 origin이 CLI가 아닐 때만 `--allow-port-fallback`을 전달한다. child는 `127.0.0.1`에 exclusive bind한 같은 socket을 `uvicorn.Server(...).run(sockets=[socket])`에 넘긴다. 점유/권한·예약 오류이면 허용된 경우 port 0을 한 번 재시도한다. Windows `SO_EXCLUSIVEADDRUSE`를 쓰고 listener 공유는 하지 않는다. 직접 host의 기존 호출은 유지한다.

| 파일 | schema 1 계약 |
|---|---|
| `launch-<id>.json` | `version, launch_id, owner, runner, runner_id, runner_port`; owner/runner는 `{pid: positive-int, creation_time: string}`. Windows `GetProcessTimes` 생성시각으로 PID 재사용 구분 |
| `active-endpoints.json` | 시작 receipt 필드 + `dashboard_port, remote_runner_port, remote_dashboard_port, ssh_port, phase, runner_url, dashboard_url`; phase는 `runner_ready|ssh_starting|ssh_running`, URL은 포트에서 계산한 loopback 값. token/계정 없음 |

child는 자신이 bind한 실제 포트·실제 Python interpreter의 process identity·Host identity를 원자 기록한다. 부모는 nonce·owner·자기 Popen 루트 프로세스의 PID/생성시각/생존·포트 범위를 확인한다. Windows venv redirector 때문에 receipt의 실제 interpreter PID가 Popen 루트와 다르면, OS 부모 프로세스 연결을 따라 해당 루트의 후손임을 검증한다. 각 연결의 생존·생성시각, 부모가 자식보다 늦게 생성되지 않았음, 루트의 기대 생성시각을 재확인하며 순환·32단계 초과·불명확한 연결은 거부한다. 실제 interpreter도 살아 있어야 하고 해당 socket의 인증 `/v1/identity`가 같은 runner_id를 반환해야 SSH를 시작한다. `read_startup`의 `runner` 인자는 Popen 루트 identity이며 반환 receipt의 `runner`는 검증된 실제 interpreter identity다. active receipt도 같은 실제 interpreter를 기록하고 `read_active`는 owner까지의 OS 소유 연결을 같은 방식으로 검증한다. receipt 존재나 임의의 살아 있는 PID·다른 서비스의 응답만으로 준비 완료가 아니다. host lock 실패/child 종료는 준비 실패다. owner 정보의 전달 인자는 `--owner-pid <int> --owner-created <string>`으로 고정하며 schema와 공개 helper signature는 유지한다.

브라우저 포트는 Runner와 다르게 exclusive probe하고 CLI가 아니면 port 0으로 대체한다. probe 해제 후 기존 SSH `-L`은 실제 브라우저 포트, `-R`은 receipt Runner 포트를 쓴다. 원격 포트/SSH 포트는 바꾸지 않는다. SSH bind 경합·인증/정책 실패는 오류로 끝내며 자동 재로그인하지 않는다. 실제 URL을 안내하되 SSH 생존만으로 터널 확인 완료를 주장하지 않는다.

희망 포트/origin과 실제값을 분리하여 `ports --save`는 희망값만 저장한다. Windows doctor/check/ports는 launch lock이 잡혀 있고 owner/runner 생성시각·생존, 시작/active receipt nonce가 일치할 때만 실제값을 사용한다. 해당 로컬 포트의 명시 CLI가 우선이며 Linux는 이 발견 경로를 사용하지 않는다. 죽은 owner/풀린 lock의 stale receipt는 경고 후 설정값 사용; 살아 있는 owner의 malformed/mismatched receipt는 오류다. 조회 후 launch 교체 여부와 인증 runner_id도 확인한다. 종료 시 자기 nonce의 receipt만 제거하며 기존 소유 child 정상 종료·UNKNOWN 정책을 유지한 뒤 lock을 놓는다. stale 파일은 다음 lock 소유자만 대체한다.

### 3.3 공개 helper·소유 경계·검증

| 모듈 | 독립 시험용 공개 signature |
|---|---|
| `scripts/build_editable_runner.py` | `load_input_lock(path) -> dict`; `verify_cache(cache, manifest) -> dict`(filename→검증 Path, 읽기 전용); `build(source_root, cache, output, *, offline=False) -> Path`; `repack(bundle_root, output=None) -> Path`; `main(argv=None) -> int` |
| `execution/bundle.py` | 기존 함수 + `editable_root() -> Path \| None`; `runtime_mode() -> str`(`source|frozen|editable`); `bundle_roots()`는 editable 루트 포함 |
| `execution/launch.py` | `LaunchLock(path)` context manager; `process_identity(pid) -> dict \| None`; `bind_loopback(port, *, allow_fallback=False) -> socket.socket`; `read_startup(path, *, launch_id, owner, runner) -> dict \| None`(미생성만 None); `read_active(runtime, *, inspect_process=None) -> dict \| None`(기본 process_identity); `write_receipt(path, value) -> None`; `remove_owned_receipts(runtime, launch_id) -> None` |

검증 오류는 ValueError, OS 실패는 OSError, lock 충돌은 RuntimeError다. 실행기는 기존 RunFailure로 단계 정보를 붙인다. 신규 production Python 모듈은 builder와 launch 두 개로 제한한다.

- **빌더 Sol 소유:** 신규 `scripts/build-editable-runner.{cmd,ps1}`, `scripts/build_editable_runner.py`, `packaging/editable-windows-runner-inputs.lock.json`, `docs/gui_test/WINDOWS_RUNNER_EDITABLE.md`. 배포 wrappers/README는 builder가 생성한다. 기존 runtime 파일 수정 없음.
- **실행 Sol 소유:** `scripts/setup_runtime.py`, `scripts/setup_ports.py`, `execution/{bundle,host}.py`, 신규 `execution/launch.py`, 필요한 기존 child 환경/argv 접점. builder/문서 수정 없음.
- **별도 시험 작성:** 신규 `tests/test_editable_runner_build.py`, `tests/test_editable_runner_runtime.py`, `tests/test_setup_active_endpoints.py` 및 필요한 기존 시험. **조정자:** RQ-61/D-65/T-210~217·PORT-008·진행/실행 기록과 본 설계 상태. 사용자 예제/`.vscode/` 변경 보존.

T-210은 캐시 무결성/ABI·오프라인 무통신·이전 ZIP 보존, T-211~212/216은 실제 ZIP을 저장소 밖 한글/공백 경로에 추출하여 Python/py/pip 없는 PATH의 동봉 runtime·import/help/모의 run·`.py` 편집 재시작·캐시 없는 repack/재추출을 검증한다. T-213~215는 포트 우선순위/자동 저장 없음·명시 CLI 실패/원격 불변, 실제 socket/OS lock 경합·nonce/PID 재사용·doctor 실제 endpoint·자기 child 정리·TC Python/token 격리와 RQ-46/47/51/58/59/60 회귀다. SSH는 모의 child만 사용한다. native wheel/pip 호환성은 실제 build/import 증거로 확정하고 회사 SSH/COM/장비·모델 인수 T-217은 **NOT_RUN**으로 남긴다.
