# PORT-008 · 편집 가능한 Windows Runner

현재 후속은 아래 **2026-11-12 설정 편의·EXE 배포 종료** 절을 따른다. 기존 11/07 산출물·PASS는 해당 고정 코드의 이력이며 이번 변경의 인수를 대신하지 않는다. 새 EXE는 만들지 않고 원본의 기존 EXE ZIP·체크섬은 제거했다.

상태: **로컬 구현·독립 리뷰·검증 완료**. 원본 기준 `0178d045db16526560a155f05693c1f2dc0bbb47`; 대상 코드 커밋 `b42cacd1c110fd3ed0bd4898de51a3ccc3274b99`. [설계](../design/EDITABLE_WINDOWS_RUNNER_PLAN.md), [실행 안내](../gui_test/WINDOWS_RUNNER_EDITABLE.md), [검증 기록](../testing/runs/20261107-editable-windows-runner.md). 실제 회사 인수 T-217은 NOT_RUN, 운영 baseline은 NONE이다.

## 전달과 선행 조건

회사 전달물 `dist/BSP-GUI-Test-Company-Editable-20261107.zip`에는 편집 Runner ZIP, 빌드 입력 ZIP, 현재 저장소 소스 ZIP, 기존 검증 Linux 소스 ZIP/wheel, 기능 패치, 증거와 START_HERE를 담는다. Linux 구성은 기존 고정 코드 `1a18ea6fab8b1caead3935ce70cb1e30153d631b`이며 Runner 코드 기준과 구분한다. 기존 EXE와 회사 플러그인 ZIP은 보존하며 Linux API는 변경하지 않는다. 외부 ZIP 해시는 순환을 피하기 위해 외부 `.zip.sha256` 및 provenance에 기록한다.

최종 편집 Runner ZIP은 28,345,689 bytes, SHA-256 `85cc8bb9889aea1bbed0d31e9cfcd17795c4e42b99944d4788b96ea89c350f6d`이다. 고정 코드와 전달 소스 17개 파일 일치는 `.local-reports/rq61-handoff-assembly/source-equivalence-unicode.json`에 기록한다.

빌드 입력 ZIP `dist/editable-windows-runner/BSP-Runner-Build-Inputs.zip`은 29,103,279 bytes, 34 entries, SHA-256 `95779f087ce035a493c375470eeda602e17abd191fa5f9c463462e658ac803c6`이다. 입력에는 고정 공식 CPython embeddable ZIP과 pip bootstrap 및 잠긴 wheel이 포함된다. 별도 추출 캐시를 사용한 독립 오프라인 빌드는 종료 코드 0이다. 빌드에는 Windows AMD64, 64비트 PowerShell 5.1 이상, 정상 UCRT 및 쓰기 가능한 로컬 경로가 필요하다. 조직의 실행 정책과 전달물 반입 정책을 먼저 확인한다.

회사 실행 PC는 Runner용 Python/py/pip/Node 설치와 다운로드가 필요 없다. OpenSSH, 실제 TC 전용 Python과 패키지, 장비 드라이버 및 회사 공유 경로는 별도 선행 조건이다. SSH 서버 포워딩과 인증, TC 경로, 보드 및 장비 접근은 회사 환경에서 확인한다. 비밀정보와 사용자 runtime은 전달 ZIP에 넣지 않는다.

## 원본 변경 범위와 회사 연결

| 범위 | 주요 파일 | 적용 지점 |
|---|---|---|
| 패키징 | `scripts/build-editable-runner.cmd`, `scripts/build-editable-runner.ps1`, `scripts/build_editable_runner.py`, `packaging/editable-windows-runner-inputs.lock.json` | 고정 입력으로 별도 ZIP 생성; 회사 PC에 pip 설치하지 않음 |
| 실행·포트 | `scripts/setup_runtime.py`, `backend/gui_test/execution/bundle.py`, `host.py`, `process.py`, `launch.py` | editable 인식, 로컬 포트 선택과 실행 receipt; 기존 home과 실행·복구 계약 유지 |
| 검증 | `tests/test_editable_runner_build.py`, `test_editable_runner_runtime.py`, `test_setup_active_endpoints.py`, `editable_runner_smoke.py`, 기존 `test_setup_runtime.py`, `test_windows_runner_bundle.py` | 원본 시험과 영향 회귀 재사용; 회사 적용 차이를 추가 검증 |
| 안내 | `docs/gui_test/WINDOWS_RUNNER_EDITABLE.md`, 이 문서와 연결된 요구사항·시험 기록 | 빌드·실행·수정·재포장과 실제 인수 범위 전달 |

파일 목록은 회사 저장소의 실제 구조와 비교할 적용 범위이며 통째로 덮어쓰기 지시가 아니다. 회사 담당자는 기존 플러그인 등록, UI hook, 실제 TC·공유 경로와 인증을 회사 구조에 연결한다. 공통 백엔드 계약과 기능은 재사용하고 회사 특유 차이는 연결 지점에서 조정한다. PORT-007의 고정 커밋과 기존 산출물 이력은 변경하지 않는다.

## 포트·설정 및 운영

CLI > 저장값 > 기본값 순이며 Windows 로컬 Runner/브라우저 기본값은 8771/8766, 원격 Runner/API 기본값은 8771/8766이다. CLI 미지정 로컬 포트가 점유되면 현재 실행에만 OS 할당 포트를 사용하고 표시된 실제 URL을 따른다. 명시 CLI 포트 충돌은 실패한다. 원격 포트는 자동 변경·검색하지 않으므로 비기본 회사 설정은 최초에 명시해야 한다. `ports --save`만 명시 저장한다. 기존 사용자 home·토큰·DB·runtime을 재사용하고 전달 폴더 이동만으로 새 runtime을 만들지 않는다.

Runner ZIP 압축을 풀어 최초 `setup.cmd`, 일상 `launch.cmd`, 장애 시 `diagnose.cmd`를 사용한다. `src/`의 `.py` 수정은 정상 종료 후 재시작에 반영되며 재배포에는 `repack.cmd`를 쓴다. runtime·의존성 또는 저장소 소스 전체를 다시 빌드할 때 원본에서 `scripts\build-editable-runner.cmd`를 사용한다. 오프라인 빌드는 전달된 `BSP-Runner-Build-Inputs.zip`의 `inputs.lock.json`, `runtime/`, `bootstrap/`, `wheels/` 구조를 유지하며 압축 해제하고 해당 루트를 `scripts\build-editable-runner.cmd -Offline -CachePath <경로>`에 지정한다. 세부 명령과 장애 조치는 [실행 안내](../gui_test/WINDOWS_RUNNER_EDITABLE.md)를 따른다.

## 적용·복원 및 검증

회사 지침과 적용 이력 확인 후 원본 기준과 회사의 관련 파일·기존 설정을 비교하고 백업한다. 변경 범위를 선별 적용한 뒤 고정 입력과 해시를 확인하고 별도 경로에 빌드한다. 기존 EXE/ZIP, 사용자 home, 토큰 및 runtime을 덮어쓰지 않는다. 실패하면 새 배포를 중단하고 보존한 이전 배포와 설정을 사용한다. 빌드 publish 실패의 복구 파일은 확인 전 삭제하지 않는다. 실제 작업 중인 runtime은 임의로 지우거나 교체하지 않는다.

독립 리뷰 APPROVED, 독립 집중 회귀 207 PASS / 7 SKIP과 backend 494 PASS / 28 warnings, 독립 빌드 시험 34 PASS, 오프라인 빌드 및 실제 ZIP smoke 종료 코드 0이다. T-210~216은 로컬 범위 PASS다. 실제 회사 정책·공유 경로·SSH·TC Python·COM·장비 확인 T-217은 NOT_RUN이다. 로컬 모의 결과를 실제 회사 인수로 표시하지 않는다. 적용 이력에는 회사 커밋, 선택한 변경, 보존·복원 확인 및 시험 증거를 남긴다.

## 2026-11-12 후속 · 설정 자동 탐색·공통 입력 / EXE 배포 종료

RQ-62/D-66/REG-0078, T-218~221. 원본 기준 `5c6310f4a2fce255149801a4fc6403a5037bba51`, 후속 대상 코드 커밋 `55447f87f3241df76a7a110c130252b73b29c941`. 위 2026-11-07 고정 전달본에는 이 후속이 없다. 현재 검증은 macOS 모의 범위 62 PASS이며 새 Runner ZIP/EXE는 생성하지 않았다. 독립 리뷰 NOT_REVIEWED, 실제 회사 T-221 NOT_RUN이다. [실행·실패/미검증 기록](../testing/runs/20261112-runner-setup.md)을 함께 확인한다.

| 변경 파일·접점 | 회사 적용 위치와 검증 |
|---|---|
| `scripts/setup_flashing.py` · `find_fastboot`, `fastboot_devices`, `console_settings`, `board_serial`, `windows` | 기존 편집형 배포의 `src/scripts/setup_flashing.py`. 원본 SHA256 `44ec8abc2fdd20aa3191a7f66f5c7ceb60a8d912b920f670cdc6d43eb78638e4`. 회사 수정과 비교하고 선별 반영; 소스 방식은 저장소의 동일 경로 |
| `apps/gui-test/config/flashing.example.json` | 로그인 marker 예시. 예제 전체를 실제 설정에 덮어쓰지 않음 |
| `apps/gui-test/package.py` · integration `INSTALL.md` | 플러그인 패키지 안내에 편집형 Runner/소스 재시작/로그인 역할 반영. 서비스 코드·HTTP 계약은 동일 |
| `tests/test_setup_flashing_discovery.py`, `tests/test_setup_runtime.py` | 원본 탐색/선택/공통값/보존/중간 로그 시험; T-218~220. 기존 플러그인 pipeline/service/package 회귀도 재사용 |
| `dist/windows-runner/BSP-Windows-Runner.zip` 및 `.zip.sha256` | 기존 EXE 배포물 삭제. 새 EXE 생성 없음. 과거 Git 이력·회사 사용자 runtime은 보존 |

선행 조건은 편집형 Runner의 기존 `setup_runtime`·bundle 외부 프로세스 격리 helper와 기존 인증/설정 저장 경계다. 새 Python 의존성·DB/API 이전은 없다. fastboot·드라이버는 Windows에 기존 설치되어 있어야 하며 자동 설치하지 않는다. 유효 저장 경로, PATH, 표준 SDK 경로 순으로 찾는다. 설정 중 `fastboot devices`만 실행하고 `-w`·콘솔·BAT·TC는 실행하지 않는다. 등록 보드 1개/조회 serial 1개/기존 대상 충돌 없음이면 자동 선택한다. 복수 보드나 대상 변경은 목록에서 명시 매핑하며 COM↔USB를 추정하지 않는다.

공통 콘솔 입력은 `console_defaults`와 기존 보드별 실행 필드로 저장한다. 새 115200/`cr`은 변경 가능한 권장값이고 실제 통신 검증값이 아니다. 기존 보드별 차이·추가 필드·`login_steps`·observer는 보존 또는 명시 편집한다. 공통 명령은 `reboot lkshell`과 `fast`로 고정되어 있다. `fastboot init success`는 fast 이후 출력이므로 fast 이전 `lkshell_prompt`로 쓰지 않는다. 해당 프롬프트는 실제 출력 확인이 아직 필요하다. BAT 후 `**** login : `는 `login :` 부분을 새 부팅/로그인 기본값으로 사용하며 로그 마지막 줄일 필요는 없다. `root` 로그인은 기존 TC가 담당하고 Runner는 새 프롬프트 확인 후 COM을 넘긴다. 플러그인 observer `login_markers`와 `login_prompt`도 일치시켜야 하며 해당 필드는 자동 덮어쓰지 않는다.

적용 전 회사 필수 정책과 COMPANY_MAP/APPLIED, 기존 파일·외부 설정을 보존한다. 진행 중 작업을 정상 종료하고 위 소스를 갱신한 뒤 같은 `--home`으로 재시작한다. 기존 프로파일 revision과 진행 중 snapshot은 유지하므로 변경 후에는 새 미리 보기를 사용한다. **대시보드 웹 재빌드만으로 Runner를 재설치하지 않는다.** 소스 변경 시에도 runtime/deps 재설치·토큰 재입력은 불필요하다. 문제 시 보존한 소스/설정을 정상 종료 후 복원하고 UNKNOWN/DB를 삭제하지 않는다.

회사 플러그인의 HTTP payload/capability 변경은 이번에 필요하지 않다. 실제 회사 플러그인 코드와 배포 pin은 이 저장소에 없으므로 [PORT-007 후속](PORT-007.md)과 [플러그인 적용 요청](../agents/BSP_UPGRADE_PLUGIN_REQUEST.md)에 따라 실제 구조를 확인한다. 새 검증 배포물 없이 다운로드 버전/체크섬 pin을 임의로 변경하지 않는다. 회사 Windows에서 자동 탐색·serial 대응·개행·구간별 실제 출력·TC root 로그인·정상 재시작을 확인해 T-221/APPLIED에 기록한다.
