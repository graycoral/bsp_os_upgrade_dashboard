# 2026-11-06 Windows Runner 실행별 포트 인자

RQ-48/51, D-49 후속. 회사 Windows Runner가 포트 문제로 연결되지 않았다는 사용자 보고 후 EXE CLI 인자 구현을 승인받았다. 회사 오류 원인은 정확한 로그 전 미확인이다. 기존 구조 분리·화면 변경 커밋은 보존하며 제품 실행이나 SSH/장비 시험을 대신 수행하지 않는다.

## 변경 계약

`--port`와 `--runner-port`는 Windows Runner listener이며 생략하면8771이다. `--dashboard-port`는 Windows 브라우저 포트8766, `--remote-runner-port`는 Linux 역방향 listener8771, `--remote-dashboard-port`는 Linux API8766을 기본으로 사용한다. `--ssh-port`는 저장된 SSH 포트(없으면22)의 이번 실행용 override다. 모두1~65535의 정수이며 같은 PC에서 Dashboard와 Runner의 포트가 같으면 거부한다.

CLI 인자는 자동 저장하지 않는다. Linux가 사용자 지정 역방향 포트를 쓰려면 메뉴1에서 연결 URL을 확인·저장한 뒤 같은 인자로 메뉴3을 실행한다. Windows의 `--port`만 바꾸면 Linux 역방향 listener는8771을 유지해 Linux 설정 변경이 필요 없다. SSH 매핑·free 검사·Runner 실행·인증 준비 조회·메뉴4와 이미지 설정의 읽기 전용 조회·URL 안내에 유효 포트를 사용한다. 기존 토큰·loopback·소유 프로세스 종료·이력 계약은 유지한다.

## 검증 상태

- 구현: `scripts/setup_runtime.py`, `scripts/setup_flashing.py`; 사용 안내와 추적 문서 갱신.
- 별도 Sol Medium 시험 작성, fresh Sol High 독립 리뷰 APPROVED. 제품 스크립트와 외부 임시 경로 fixture 보완을 각각 검토했다.
- 실제 배포 EXE 재빌드·패키지 인자 인수: NOT_RUN. 기존 ZIP은 새 옵션을 자동 지원하지 않는다.
- 회사 SSH·공유 폴더·COM·TC·퓨징: NOT_RUN. 운영 baseline NONE 유지.

검증 명령·종료 코드·건수는 별도 실행 결과를 받은 뒤 추가한다. 원본 로그는 고유한 `.local-reports/20261106-runner-ports/` 하위에 보존하고 Git에는 올리지 않는다.

## 초기 시도와 회귀

Luna Low 실행의 초기 시도는 기존 임시 폴더 접근 권한으로 실패했다. 두 번째 시도는 115 PASS/7 FAIL/4 SKIP이었다. 신규 CLI 시험 3건은 저장소 내부 임시 `--home`이 제품의 의도된 보호 규칙에 거부된 시험 fixture 문제였고, 기존 wrapper 4건은 호스트 PowerShell 실행 정책으로 차단됐다. CLI fixture를 저장소 밖 `TemporaryDirectory`로 고쳤으며 제품 보호 규칙은 유지했다. wrapper 시험에는 자식 프로세스 환경의 `PSExecutionPolicyPreference=Bypass`만 사용하고 시스템/사용자 정책은 바꾸지 않았다.

fixture 보완 전 저장소 밖 basetemp로 전체 122 PASS/4 SKIP, 종료 코드0을 확인했다(`ports-regression-4`). 보완 후 최종 재실행과 패키징 결과는 아래에 추가한다. 초기 실패 로그를 덮어쓰거나 삭제하지 않았다.

최종 fixture 반영 후 별도 Luna Low가 `.venv/Scripts/python.exe -m pytest tests/test_runner_ports.py tests/test_setup_runtime.py tests/test_windows_runner_bundle.py -q -p no:cacheprovider --basetemp <저장소 밖 고유 경로>`를 재실행해 **122 PASS/4 SKIP, 종료 코드0**을 확인했다. 로그: `.local-reports/20261106-runner-ports/ports-regression-final-5/`. 실제 SSH·장비 시험은 포함하지 않는다.
