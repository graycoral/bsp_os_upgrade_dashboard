# Linux UI 빌드 진행 표시

RQ-44 / T-126 / REG-0095. 기준 `455a5011f9a63e95023861e699d7364aa0628957`에 Linux/macOS Bash 빌드 진입점과 회귀 시험을 수정했다.

## 보고와 재현

사용자는 Linux 빌드 명령 실행 후 출력이 없다고 보고했다. 기존 Bash 스크립트는 바로 `npm ci`를 실행한다. 설치 중 npm 출력이 없으면 시작·설치·컴파일 단계를 알 수 없다. 조용한 설치 fixture를 사용한 신규 시험을 기존 스크립트에 실행해 1 FAIL을 확인했다. 회사 registry/proxy/DNS/인증서 중 어느 원인으로 대기했는지는 미확정이다.

## 변경

시작·Node/npm 버전·설치·컴파일·완료를 표시하고 Node/npm 누락을 안내한다. 설치에 `--loglevel=info --foreground-scripts`를 전달해 npm 진행과 설치 스크립트 출력을 보여준다. 실패한 단계와 실제 종료 코드를 표시한다. 기존 all/dashboard/gui-test, --skip-install, lockfile 기반 설치를 유지한다.

Agent Monitor 담당자는 `scripts/build-ui.sh`와 `tests/test_build_entrypoint.py`를 적용한다. 소스 빌드를 호출하는 플러그인도 같은 스크립트의 출력·종료 코드를 전달한다. DB 변경은 없다. 빌드 명령은 [scripts 안내](../../../scripts/README.md)를 따른다.

## 검증

전체 로그는 `.local-reports/20261116-build-progress/`에 로컬 전용으로 보관한다.

| 실행 | 결과 | 로그 |
|---|---|---|
| 수정 전 `test_t126_bash_reports_stage_before_quiet_install` | 예상 1 FAIL | `before-fix-test.log` |
| `python -m pytest tests/test_build_entrypoint.py -q` | 11 PASS / Windows 4 SKIP | `entrypoint-tests.log`, 시험 ID 접두사 정정 전 동일 시험 |
| `python -m pytest tests/test_build_entrypoint.py tests/test_setup_runtime.py -q` | 59 PASS / Windows 11 SKIP | `regression-tests.log` |
| 기존 스크립트 두 UI 빌드 | PASS | `baseline-build.log` |
| 수정한 `bash scripts/build-ui.sh` 설치·두 UI 빌드 | PASS | `fixed-build.log` |
| `bash -n scripts/build-ui.sh`, `git diff --check` | PASS | 로컬 명령 exit 0 |

실제 빌드는 main의 격리 checkout에 수정 스크립트만 적용해 macOS Node 22.23.4/npm 10.9.9로 실행했다. 작업 중인 GUI Test 변경 7개는 포함하지 않았다. 최초 격리 파일 복사 명령은 잘못된 상대경로로 실패했고 이어 실행된 기존 스크립트 결과를 baseline으로 보존했다. 복사 위치를 수정한 뒤 새 스크립트로 설치·두 빌드를 다시 실행했다.

스크립트 SHA-256 `1f2e5ec68c60e3d01e19e5bf24a3400c4cb21fd4c3ffa7f7c715b3dd25506992`. 시험 SHA-256 `94ea584b9810205b508cc4c1b48d6e4635f959f57801f6932cad2e6b0f9658c9`. 회사 Linux 네트워크 및 Windows 재검증은 NOT_RUN이다. 회사 대기를 해결했다고 판정하려면 해당 서버에서 재실행한 단계·npm 출력이 필요하다.

npm 설치 스크립트 출력 옵션은 공식 문서를 확인했다. [npm ci](https://docs.npmjs.com/cli/v11/commands/npm-ci/)

수정 코드·시험 고정 커밋은 `7ef37a36226a593de4227687b91ed17039fc124a`다. 문서 검사 1683개 링크 PASS를 확인했다.
