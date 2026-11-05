# 2026-11-06 Windows Runner 실행별 포트 인자

RQ-48/51, D-49 후속. 회사 Windows Runner가 포트 문제로 연결되지 않았다는 사용자 보고 후 EXE CLI 인자 구현을 승인받았다. 회사 오류 원인은 정확한 로그 전 미확인이다. 기존 구조 분리·화면 변경 커밋은 보존하며 제품 실행이나 SSH/장비 시험을 대신 수행하지 않는다.

## 변경 계약

`--port`와 `--runner-port`는 Windows Runner listener이며 생략하면8771이다. `--dashboard-port`는 Windows 브라우저 포트8766, `--remote-runner-port`는 Linux 역방향 listener8771, `--remote-dashboard-port`는 Linux API8766을 기본으로 사용한다. `--ssh-port`는 저장된 SSH 포트(없으면22)의 이번 실행용 override다. 모두1~65535의 정수이며 같은 PC에서 Dashboard와 Runner의 포트가 같으면 거부한다.

CLI 인자는 자동 저장하지 않는다. Linux가 사용자 지정 역방향 포트를 쓰려면 메뉴1에서 연결 URL을 확인·저장한 뒤 같은 인자로 메뉴3을 실행한다. Windows의 `--port`만 바꾸면 Linux 역방향 listener는8771을 유지해 Linux 설정 변경이 필요 없다. SSH 매핑·free 검사·Runner 실행·인증 준비 조회·메뉴4와 이미지 설정의 읽기 전용 조회·URL 안내에 유효 포트를 사용한다. 기존 토큰·loopback·소유 프로세스 종료·이력 계약은 유지한다.

## 검증 상태

- 구현: `scripts/setup_runtime.py`, `scripts/setup_flashing.py`; 사용 안내와 추적 문서 갱신.
- 별도 Sol Medium 시험 작성, fresh Sol High 독립 리뷰 APPROVED. 제품 스크립트와 외부 임시 경로 fixture 보완을 각각 검토했다.
- 실제 배포 EXE 재빌드: PASS. 소스 커밋 `1d9a6a260bb25b4b5835173965834a1995104800`, CPython3.12.10 x64 고정 환경, `scoped_dirty=false`로 새 ZIP을 생성했다.
- 회사 SSH·공유 폴더·COM·TC·퓨징: NOT_RUN. 운영 baseline NONE 유지.

검증 명령·종료 코드·건수는 별도 실행 결과를 받은 뒤 추가한다. 원본 로그는 고유한 `.local-reports/20261106-runner-ports/` 하위에 보존하고 Git에는 올리지 않는다.

## 초기 시도와 회귀

Luna Low 실행의 초기 시도는 기존 임시 폴더 접근 권한으로 실패했다. 두 번째 시도는 115 PASS/7 FAIL/4 SKIP이었다. 신규 CLI 시험 3건은 저장소 내부 임시 `--home`이 제품의 의도된 보호 규칙에 거부된 시험 fixture 문제였고, 기존 wrapper 4건은 호스트 PowerShell 실행 정책으로 차단됐다. CLI fixture를 저장소 밖 `TemporaryDirectory`로 고쳤으며 제품 보호 규칙은 유지했다. wrapper 시험에는 자식 프로세스 환경의 `PSExecutionPolicyPreference=Bypass`만 사용하고 시스템/사용자 정책은 바꾸지 않았다.

fixture 보완 전 저장소 밖 basetemp로 전체 122 PASS/4 SKIP, 종료 코드0을 확인했다(`ports-regression-4`). 보완 후 최종 재실행과 패키징 결과는 아래에 추가한다. 초기 실패 로그를 덮어쓰거나 삭제하지 않았다.

최종 fixture 반영 후 별도 Luna Low가 `.venv/Scripts/python.exe -m pytest tests/test_runner_ports.py tests/test_setup_runtime.py tests/test_windows_runner_bundle.py -q -p no:cacheprovider --basetemp <저장소 밖 고유 경로>`를 재실행해 **122 PASS/4 SKIP, 종료 코드0**을 확인했다. 로그: `.local-reports/20261106-runner-ports/ports-regression-final-5/`. 실제 SSH·장비 시험은 포함하지 않는다.

## 배포 빌드와 실제 ZIP 시험

별도 Luna Low가 `apps/gui-test/.build/runner-venv/Scripts/python.exe scripts/build_windows_runner.py --log-dir .local-reports/20261106-runner-ports`로 빌드했다. 빌드 로그는 `build-20261105T154742704500Z/`에 보존한다. 최종 `dist/windows-runner/BSP-Windows-Runner.zip`은 27,935,932 bytes이며 SHA256은 `ead6f4afd437012a2e18810de43e4685e37a3e7c005dd94bb043c32dcaecdc81`다. ZIP·sidecar는 전달 대상으로 커밋하며 원본 로그·임시 EXE 폴더는 로컬 전용이다.

`BSP_RUNNER_EXE`에 최종 ZIP 경로를 지정해 `pytest tests/portable_runner_smoke.py -q`로 압축 해제본을 검증했다. **7 PASS, 종료 코드0**, 로그 `zip-smoke-1/`. 격리된 모의 Python 자식·읽기 전용 API와 패키지 경계를 확인하며 실제 SSH·COM·TC·퓨징은 실행하지 않았다.

실제 packaged EXE의 `--help`는 종료 코드0으로 `--port`/`--runner-port`와 기본8771을 표시했다. `--port 0`은 종료 코드2로 거부했고, 별도 임시 `--home`에서 `--port 18771`과 메뉴0 입력은 종료 코드0이었다. 실제 SSH나 TC를 시작하지 않았다. 관련 로그는 같은 로컬 실행 폴더의 `exe-help`, `exe-invalid-port`, `exe-port-18771` 접두사 파일에 보존한다.

최종 ZIP 내부 `SHA256SUMS`의107개 파일과 build-info의73개 소스 해시를 현재 소스와 대조해 일치함을 확인했다. source_revision은 위 소스 커밋이며 scoped_dirty=false, scoped_status=[]다. ZIP 자체의 해시도 sidecar와 일치한다.


## Canonical result index correction (2026-11-06)

TEST_RESULTS.csv is the current one-row-per-catalog-ID index. Base commit `2c6bf29` contained duplicate T-138/T-139/T-140/T-158 rows from the port follow-up. The latest proven `20261106-runner-ports` rows remain canonical; the four superseded rows are preserved verbatim below and in that fixed commit. Their original run documents remain authoritative history. This index correction does not change any past result or remove failure evidence.

```csv
test_id,status,run_id,code_revision,test_revision,environment,executed_at,executor,evidence,defect_id,notes
T-138,PASS,20261103-setup-wizard,96e3a0296e55dca67c5d7bfeaca0c5cf657ffb75,96e3a0296e55dca67c5d7bfeaca0c5cf657ffb75,GitHub Actions Linux/Windows Python3.12 Node22; fake services and dummy child processes,2026-11-03T08:54:04.848791+00:00,GPT-6-sol independent test and CI verification; root reviewed,runs/20261103-setup-wizard.md,REG-0029,Linux459 and Windows221 PASS; platform-only3 SKIP each covered on other OS; browser24+18; PS5.1/7 package PASS. Live T-141 NOT_RUN
T-139,PASS,20261103-direct-windows-launch,4ae2ddc8df959da29405f83c69a1213d64b477a7,4ae2ddc8df959da29405f83c69a1213d64b477a7,Windows Python3.13.5; actual CMD/PowerShell with dummy targets,2026-11-03T10:31:25.153326+00:00,GPT-6-sol independent tests; root reviewed,runs/20261103-direct-windows-launch.md,REG-0030,49 PASS/4 platform SKIP; spaced paths and unrelated cwd; LF/CRLF; actual company SMB wrapper retest pending
T-140,PASS,20261103-setup-wizard,96e3a0296e55dca67c5d7bfeaca0c5cf657ffb75,96e3a0296e55dca67c5d7bfeaca0c5cf657ffb75,GitHub Actions Linux/Windows Python3.12 Node22; fake services and dummy child processes,2026-11-03T08:54:04.848796+00:00,GPT-6-sol independent test and CI verification; root reviewed,runs/20261103-setup-wizard.md,REG-0029,Linux459 and Windows221 PASS; platform-only3 SKIP each covered on other OS; browser24+18; PS5.1/7 package PASS. Live T-141 NOT_RUN
T-158,PASS,20261104-portable-runner,workingtree:sha256:d5f98fca7f3005dba7ed001ee9f300cda7a661475bf4c516de00ad7ed65994de,workingtree:sha256:a44b843c7f46385c6ca7b2a6009507ed746fdea03ce96d271e30a930db5abb4d,Windows x64 CPython3.12.10 PyInstaller6.22.3; fake TC COM SSH and actual frozen ZIP,2026-11-04T14:54:31.173702+00:00,GPT-6 Luna Low execution; independent GPT-6.1 Sol High review APPROVED,runs/20261104-portable-runner.md,REG-0042,Frozen Wizard Runner+mock SSH lifecycle; authenticated packaged API and identity/duplicate lock;258 PASS4 SKIP Windows regression and7 PASS frozen smoke; company live NOT_RUN
```
