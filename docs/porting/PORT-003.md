# PORT-003 · Windows Runner 포터블 실행파일

회사 노트북의 Runner용 패키지 설치를 생략하고, Python 런타임·의존성이 포함된 EXE로 설정과 실행을 관리한다. RQ-51/D-53, [설계](../design/WINDOWS_RUNNER_BUNDLE.md), [사용 안내](../gui_test/WINDOWS_RUNNER_PORTABLE.md)를 따른다.

## 고정 기준과 전달

2026-11-06 포트 인자 배포 갱신: 대상 소스는 `1d9a6a260bb25b4b5835173965834a1995104800`이며 현재 전달 ZIP은 **27,935,932 bytes**, SHA256 `ead6f4afd437012a2e18810de43e4685e37a3e7c005dd94bb043c32dcaecdc81`다. `BSP-Windows-Runner.exe --port 18771`을 지원하고 생략 시8771이다. Linux8771에서 Windows 지정 포트로 SSH 터널을 연결하므로 Windows 포트만 바꿀 때 Linux 설정은 유지한다. [이번 검증 기록](../testing/runs/20261106-runner-ports.md), [포트별 사용 안내](../gui_test/WINDOWS_RUNNER_PORTABLE.md). 아래 크기·해시·커밋은 최초 배포 이력이며 현재 ZIP과 구분한다.

- 원본: `graycoral/bsp_os_upgrade_dashboard`
- 선행 기준: `485963c5f5e4153c5ed6c358c4ce66c45d998f95`
- 대상 코드·시험 커밋: `2467b326f83a8be6669988c60bc2eeac76a5a988`
- 전달 ZIP: [BSP-Windows-Runner.zip](../../dist/windows-runner/BSP-Windows-Runner.zip), 27,919,944 bytes
- ZIP SHA256: `5bf944ba9214b00d8f0b52692f462669be3bbd9c3d23deac8ebe249a33daef21` ([체크섬 파일](../../dist/windows-runner/BSP-Windows-Runner.zip.sha256))
- 빌드 당시에는 선행 기준 위의 미커밋 코드였다. ZIP `build-info.json`의 69개 소스 해시는 최종 검증 파일과 일치한다. 이후 위 커밋으로 코드·시험을 고정했으며 ZIP을 다른 커밋에서 빌드한 것처럼 표시하지 않는다.

회사 저장소에 이식할 때는 필수 정책과 `COMPANY_MAP.md`·`APPLIED.md`를 먼저 확인한다. 바이너리 배포는 회사에서 허용하는 파일 반입·실행 경로를 사용한다. 2026-11-05 사용자 승인에 따라 전달 ZIP과 SHA256 파일을 Git에서 관리한다. raw 개발 로그·개인 설정·runtime 데이터는 Git에 넣지 않는다. 원격 업로드·게시 위치는 이 안내서가 정하지 않는다.

## 선행 조건과 변경 위치

Linux는 기존 RQ-46 Windows Runner 연결과 필요한 경우 RQ-47 자동 퓨징 계약을 지원해야 한다. UI PORT-001/002는 이 배포본 자체의 선행 조건이 아니다. Runner API/DB schema 변경은 없다. 회사 TC Python·TC 전용 패키지, OpenSSH 클라이언트, 보드 드라이버·fastboot는 별도로 준비한다.

| 파일 | 재사용·회사 조정 지점 |
|---|---|
| `scripts/windows_runner_entry.py` | EXE의 설정·Runner·gated helper 진입점 |
| `backend/gui_test/execution/bundle.py` | 외부 Python 검증·토큰/PATH/DLL 경계 |
| `backend/gui_test/execution/process.py`, `host.py` | frozen Job Object gate와 명시적 외부 TC Python; 기존 실행 계약 보존 |
| `scripts/setup_runtime.py` | 기존 home/DPAPI/runtime 재사용; frozen 모드에서 pip 생략과 EXE 자식 실행 |
| `scripts/build_windows_runner.py`, `packaging/windows-runner.spec`, `windows-runner-build.lock` | Windows CPython3.12.10 x64·PyInstaller6.22.3 빌드·해시·ZIP; 버전은 lock 원문 확인 |
| `tests/test_windows_runner_bundle.py`, `tests/portable_runner_smoke.py` | 경계·생명주기와 실제 EXE/ZIP 모의 회귀 |

회사 코드가 달라졌다면 기존 배정·중복 방지·UNKNOWN·정상 종료 대기 계약을 유지하며 연결부만 조정한다. 계약 필드 전체는 복제하지 않고 [Runner](../gui_test/WINDOWS_RUNNER.md)와 [자동 퓨징](../design/AUTOMATIC_FLASH_TEST.md)을 참조한다.

## 설정·복원

ZIP 전체를 로컬 폴더에 풀고 EXE를 실행한다. 기존 `%USERPROFILE%/.bsp-dashboard/windows` 또는 동일한 `--home`의 JSON·DPAPI 토큰·runtime·DB·runner identity를 사용한다. EXE와 `_internal`을 함께 유지한다. 새 runtime으로 UNKNOWN을 우회하지 않는다. 데이터 이전은 없으며 복원할 때 실행 중 작업을 정상 종료한 뒤 배포본만 이전 버전으로 바꾼다. 사용자 데이터와 회사 전용 설정은 회사에 남긴다.

## 검증과 남은 인수

독립 Sol High 코드 리뷰 APPROVED. 별도 Luna 실행으로 Windows 지원 회귀258 PASS/4 SKIP, 실제 EXE7 PASS, 최종 ZIP 압축 해제7 PASS를 확인했다. 108개 배포 파일의 내부 체크섬·ZIP sidecar·69개 소스 해시가 일치한다. REG-0042 출력 인코딩 결함을 실제 EXE에서 재현·수정·재시험했다. 명령·초기 실패·재시험·제약은 [실행 기록](../testing/runs/20261104-portable-runner.md)을 따른다.

T-156~159는 이 로컬/모의 범위의 PASS다. 전체 Linux 대상 시험을 Windows에서 실행한 실패를 통과로 바꾸지 않는다. 회사 공유 폴더·SSH·TC Python·COM·실제 퓨징/보드 T-160과 기존 T-130/136/141은 별도 인수이며 운영 baseline NONE을 유지한다. 회사 적용 범위·추가 수정·실제 시험은 회사 `APPLIED.md`에 기록한다.
