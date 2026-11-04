# Windows Runner 포터블 배포 검증

- run_id: 20261104-portable-runner
- scope: unit / contract / package / local integration (실장비 없음)
- base_revision: `485963c5f5e4153c5ed6c358c4ce66c45d998f95`
- 후속 고정 코드·시험 커밋: `2467b326f83a8be6669988c60bc2eeac76a5a988`; [회사 전달 안내 PORT-003](../../porting/PORT-003.md). 빌드 당시 dirty 파일별 해시와 위 커밋의 제품 코드 사이에 변경은 없다.
- requirements: RQ-51 / D-53 / T-156~160
- environment: Windows x64, CPython 3.12.10, 전용 `gui_test/.build/runner-venv`
- source/test criterion: 변경 파일 manifest와 최종 고정 커밋을 후속 기록한다. 이전 UI 시험 결과는 재사용하지 않는다.

## 역할과 범위

요구사항·구조·상세 설계는 각각 Astra의 지정 역할 에이전트로 분리했다. 구현은 GPT-6.1 Sol High, 시험 작성은 GPT-6.1 Sol Medium, 독립 리뷰는 별도 GPT-6.1 Sol High가 담당한다. 시험 실행·보고는 GPT-6 Luna Low의 별도 세션으로 수행한다. 실제 Claude 검토나 실제 회사 연결을 수행했다고 표시하지 않는다.

빌드 의존성 설치는 coordinator가 수행했다. `gui_test/requirements.lock`과 PyInstaller 6.22.3 설치 종료 코드 0. 실제 설치 버전은 PyInstaller 6.22.3, hooks-contrib 2026.9, altgraph 0.17.5, pefile 2024.8.26, pywin32-ctypes 0.2.3, setuptools 80.9.0이다.

## 실행 결과

최종: Windows 지원 회귀 **258 PASS / 4 SKIP**, 실제 frozen ZIP smoke **7 PASS**, 독립 코드 리뷰 **APPROVED**. 아래 실패·재시험 이력은 보존한다. 전체 Linux 대상 시험을 Windows에서 실행한 결과와 지원 Windows 범위의 최종 결과를 구분한다.

초기 전체 Python 실행: pytest 요약 71 PASS / 2 FAIL / 3 SKIP / 425 ERROR. 기본 `%TEMP%/pytest-of-grayc` 접근 거부가 425개 fixture setup을 막았고, CP949 기본 인코딩 오류와 설정 시험 실패도 있었다. `.local-reports/20261104-portable-runner/source-suite.log` 및 XML을 보존한다. 시스템 Temp 권한을 바꾸지 않고 고유한 시험 폴더와 UTF-8 모드로 재시험한다. 초기 실패를 삭제하거나 이전 PASS로 대체하지 않는다.

전체 소스 재시험은 전용 임시 폴더와 UTF-8 모드에서 415 PASS / 45 FAIL / 37 ERROR / 4 SKIP였다. Windows에서 `/fixture/nonexistent` 같은 POSIX 절대 경로를 사용하는 backend fixture가 거부되는 등 전체 Linux 대상 시험까지 포함한 결과다. 이번 변경과 관련된 Windows 지원 회귀(`tests/test_setup_runtime.py`, `tests/test_build_entrypoint.py`, 신규 bundle 시험, `gui_test/tests`)를 별도로 실행해 판정한다. 전체 실행 로그 `source-suite-retest.log`/XML도 보존한다.

초기 실제 ZIP smoke 7개는 같은 기본 임시 폴더 접근 거부로 모두 setup ERROR였다. `portable-smoke.log`/XML을 보존하고 저장소 밖의 고유한 임시 폴더에서 재실행한다.

원본 stdout/stderr와 상세 JSON/XML은 `.local-reports/20261104-portable-runner/`에 로컬 전용으로 보관하며 Git에 포함하지 않는다. 실패 시도와 재시험은 별도 파일로 보존한다.

## 미실행 인수

T-160 회사 PC/회사 공유 폴더/실제 SSH/기존 회사 TC/보드 인수는 NOT_RUN이다. 기존 T-130/T-136/T-141도 이 로컬 배포 검증으로 완료 처리하지 않는다. 배포본은 Runner 의존성을 포함하며 회사 TC Python·패키지, OpenSSH, 보드 드라이버·fastboot는 별도다. 운영 baseline NONE을 유지한다.

실제 ZIP 재시험은 6 PASS / 1 FAIL이었다. 기본 Wizard의 리디렉션 출력 CP949 오류(REG-0042)를 확인해 진입점의 frozen 출력만 UTF-8로 수정했다. `portable-smoke-retest.log`/XML에 실패를 보존하고 최종 ZIP을 다시 빌드·재시험한다. 방지 시험은 출력의 엄격한 UTF-8 디코딩과 실제 한국어 메뉴 표시까지 확인한다.

Windows 설정·빌드·bundle 집중 시험의 중간 결과는 72 PASS / 4 FAIL / 4 SKIP였다. 네 실패 모두 `setup.ps1`을 호출하는 기존 wrapper fixture에서 Restricted 실행 정책에 막힌 경우다. 영구 정책을 변경하지 않고 시험 프로세스의 `PSExecutionPolicyPreference=Bypass` 범위에서 기존 CI Windows 대상(`gui_test/tests` 포함)으로 재시험한다. 기존 Restricted 거부/자식 정책 적용 시험은 그대로 유지한다.

독립 Sol High 리뷰는 최초 production, 추가 frozen Wizard 생명주기 시험, REG-0042 수정 delta에 모두 APPROVED였다. 리뷰어는 빌드·시험을 대신 실행하지 않았으며, 최종 시험은 별도 Luna 실행 증거로 판정한다.

## 최종 실행과 배포본

별도 GPT-6 Luna Low 실행:

| 항목 | 명령·조건 | 결과·로컬 증거 |
|---|---|---|
| 실제 EXE 재빌드 | `gui_test/.build/runner-venv/Scripts/python.exe scripts/build_windows_runner.py` | ZIP 생성 성공; `build-fixed.log`, `build-20261104T145234501003Z/` |
| 지원 Windows 회귀 | 위 Python의 `-X utf8 -m pytest -q tests/test_windows_runner_bundle.py tests/test_setup_runtime.py tests/test_build_entrypoint.py gui_test/tests --basetemp=C:/Users/grayc/prun-20261104 --junitxml=.local-reports/20261104-portable-runner/windows-regression-short.xml` | 종료 0; 258 PASS / 4 SKIP; `windows-regression-short.log`/XML |
| 실제 EXE smoke | `BSP_RUNNER_EXE`에 최종 EXE 지정 후 위 Python의 `-X utf8 -m pytest -q tests/portable_runner_smoke.py`와 고유한 저장소 밖 basetemp/XML 지정 | 종료 0; 7 PASS; `portable-smoke-final.log`/XML |
| ZIP 무결성 | sidecar·내부 SHA256SUMS·현재 소스 해시 비교 및 금지 파일 검사 | 108개 파일, 69개 소스 해시 일치, mismatch/개인 설정·runtime·토큰 파일 없음; `artifact-integrity-final.log` |

source 시험 프로세스에만 UTF-8 환경과 `PSExecutionPolicyPreference=Bypass`를 전달했다. 시스템/사용자 영구 실행 정책은 변경하지 않았다. 긴 Windows 임시 경로에서 mock artifact 생성이 실패한 중간 실행(`windows-regression.log`: 241 PASS / 5 FAIL / 12 ERROR / 4 SKIP, `windows-regression-final.log`: 245 PASS / 1 FAIL / 12 ERROR / 4 SKIP)을 보존하고 짧은 고유한 basetemp에서 동일 시험을 통과했다. Windows SKIP 4개는 symlink 생성 권한 1개, Linux 전용 소유자/모드·세션 정리·Bash 진입점 3개다.

실제 smoke는 시스템 Python/pip 없는 PATH의 저장소 밖 공백/한글 경로에서 Wizard 메뉴·한국어 출력, 인증 API·catalog·runner identity 재사용·중복 Host 거부, helper gate/환경 비전달, 실제 Job Object 자손 취소를 확인했다. COM이 없는 환경이므로 frozen API를 통한 실제 보드 TC 실행이나 실제 SSH 서버 접속을 수행하지 않았다. 일반 API TC·timeout/취소/중복/복구는 기존 가짜 COM 소스 회귀와 frozen helper 시험으로 나누어 검증했다.

- ZIP: `dist/windows-runner/BSP-Windows-Runner.zip` (27,919,944 bytes)
- SHA256: `5bf944ba9214b00d8f0b52692f462669be3bbd9c3d23deac8ebe249a33daef21`
- expanded: EXE와 `_internal`, README, build-info, SHA256SUMS를 함께 전달한다.
- source digest: `d5f98fca7f3005dba7ed001ee9f300cda7a661475bf4c516de00ad7ed65994de`
- test digest: `a44b843c7f46385c6ca7b2a6009507ed746fdea03ce96d271e30a930db5abb4d`
- 로컬 `verified-source-manifest.json`과 배포본 `build-info.json`에 파일별 SHA256을 보존한다. 빌드 당시 base commit+dirty scoped hash와 후속 고정 코드 커밋을 구분한다.

T-156~159 로컬 PASS, REG-0042 로컬 VERIFIED. T-160과 운영 baseline NONE은 유지한다. [사용 안내](../../gui_test/WINDOWS_RUNNER_PORTABLE.md).

실제 전달 ZIP을 직접 지정한 최종 압축 해제 시험도 종료 0, 7 PASS였다. `BSP_RUNNER_EXE=<최종 ZIP 절대 경로>`와 `--basetemp=C:/Users/grayc/smz-20261104`, `--junitxml=.local-reports/20261104-portable-runner/portable-zip-final.xml`을 사용했다. `portable-zip-final.log`/XML이 ZIP 기준 증거이며, 앞의 `portable-smoke-final.log`/XML은 같은 빌드의 EXE 폴더 복사 기준 증거다. 두 결과를 혼동하지 않는다.

전체 저장소 시험을 짧은 임시 경로에서도 추가 확인한 결과는 종료 1, 419 PASS / 41 FAIL / 37 ERROR / 4 SKIP였다(`source-suite-final.log`/XML). native/Claude 패키지 등 POSIX 경로·프로세스 가정을 포함하는 Windows 미지원 범위와 기존 문서/hash 계약 실패가 남는다. 이 작업은 해당 범위를 통과했다고 보고하지 않으며, 필수 Windows 회귀 258 PASS와 실제 EXE 7 PASS를 배포본의 로컬 검증 근거로 사용한다. Linux 전체 회귀와 회사 실제 환경 인수는 별도다.
