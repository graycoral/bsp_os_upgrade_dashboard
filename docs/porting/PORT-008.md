# PORT-008 · 편집 가능한 Windows Runner

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
