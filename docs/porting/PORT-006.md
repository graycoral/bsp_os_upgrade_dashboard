# PORT-006 · 실행·진단 및 포트 저장

RQ-59/D-63/REG-0072. 원본 기준 `037b98f5d2b275e913bbd83a1429e3220ed7c497`; 대상 코드 커밋 `792d862645a7113f86f2932b112c5222b7c4a64f`. 소스 시험 후 동일 바이트를 고정했다. 먼저 회사 필수 지침과 [공통 절차](README.md), 회사 구조·적용 이력을 확인한다. 기존 회사 기능·설정·토큰을 보존한다.

## 선행 조건과 변경 위치

기존 포터블 Runner 구성 [PORT-003](PORT-003.md)과 catalog timeout [PORT-005](PORT-005.md)을 확인한다. 새 ZIP에는 현재 RQ-56 source snapshot 코드도 함께 포함되므로 회사 구조 및 실제 배포 대상과 비교한다. 회사의 Python·OpenSSH·경로·권한과 기존 runner URL을 확인한다.

| 원본 위치 | 이식 대상 |
|---|---|
| `scripts/setup_ports.py`, `scripts/setup_runtime.py` | 프로파일·직접 명령·단계 진단; 회사 runtime 경로와 연결 검증에 대응 |
| `scripts/setup.sh`, `scripts/setup.cmd`, `scripts/setup.ps1`, `scripts/run.sh`, `scripts/doctor.sh`, `scripts/run.cmd`, `scripts/doctor.cmd` | 인자·종료 코드 전달 및 운영 진입점 |
| `scripts/build_windows_runner.py` | 새 ZIP 래퍼와 안내서 복사; 기존 패키징 정책에 대응 |
| `docs/gui_test/RUN_AND_DIAGNOSE.md` | ZIP의 `GUIDE.md`와 회사 사용자 안내 |
| `tests/test_setup_commands.py`, `tests/portable_runner_smoke.py` 및 관련 setup/포터블 회귀 | 프로파일·진단·진입점과 실제 ZIP 검증 |

[명령 계약](../design/SETUP_COMMANDS.md)을 기준으로 CLI > 프로파일 > 기존 기본값/SSH 설정 우선순위, 원자 저장, 오류 종료와 기존 runner_url 검증을 유지한다. DB나 `gui-test.json` 필드 이전은 없다. 별도 schema 1 `setup-ports.json`은 Linux `<repo>/.runtime/`, Windows 선택 home에 저장하고 명시 `ports --save`에서만 쓴다. 자동 저장하지 않는다.

## 적용·검증·복원

1. 회사 코드·기존 설정과 runtime을 보존하고 원본 대상 커밋의 관련 파일을 회사 접점에 적용한다. 새 Windows ZIP은 전체를 로컬 폴더에 풀어 사용한다.
2. T-195~197 소스 시험은 로컬 PASS, 최종 독립 리뷰는 APPROVED다. T-198 새 ZIP 실제 압축 해제 smoke **10 PASS**다. ZIP은 27,889,244 bytes, SHA-256 `4809e0cee8de08bff0d1d0211f9b59385af8905a01348e0f5f4ef06784f65f0c`, 커밋 `792d862645a7113f86f2932b112c5222b7c4a64f`에서 빌드했다. 110개 체크섬과 98개 소스 해시를 확인했다. 증거와 정확한 명령은 [실행 기록](../testing/runs/20261106-setup-commands.md)에 기록한다. T-199 실제 회사 SSH·공유 폴더 인수는 **NOT_RUN**이며 로컬 결과로 대체하지 않는다.
3. 복원할 때 해당 프로세스를 정상 종료한 후 기존 ZIP/코드를 복원하고 기존 runtime·토큰을 보존한다. 이전 ZIP은 새 포트 프로파일을 무시하므로 필요한 포트 인자를 다시 지정한다. 문제 해결을 위해 DB를 비우지 않는다.
