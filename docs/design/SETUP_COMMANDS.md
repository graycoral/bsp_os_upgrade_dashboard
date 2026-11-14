# 실행·진단 명령 계약 · RQ-59/D-63

setup 기본 동작은 기존 메뉴이며 `run`, `doctor`, `ports`를 직접 선택할 수 있다. `--only identity|boards|catalog`은 doctor 전용, `--save`는 ports 전용이다. 잘못된 조합·포트·프로파일과 기존 Linux runner_url 오류는 실행 전에 거부하고 오류 종료한다. identity/boards 전용 진단은 catalog 설정을 읽지 않는다. 진단은 인증·보드·목록의 단계와 실패를 구분하며 실제 TC·퓨징을 실행하지 않는다. timeout은 transport 제한이며 전체 진단의 hard deadline이 아니다.

`ports`는 유효값과 출처를 표시하며 `ports --save`만 원자 저장한다. CLI > 저장 프로파일 > 기존 기본값/SSH 설정 순이다. Linux `<repo>/.runtime/setup-ports.json`, Windows `<선택 home>/setup-ports.json`; schema 1, 네 포트와 선택 SSH 포트를 담는다. 기존 연결·토큰은 보존하며 자동 저장하지 않는다. setup.ps1은 나머지 인자를 전달하고 실제 종료 코드를 반환한다. Windows `launch-run.cmd`/`diagnose.cmd`, Linux `scripts/setup.sh run`/`scripts/setup.sh doctor`는 대기 없이 종료 코드를 전달한다. [사용 안내](../gui_test/RUN_AND_DIAGNOSE.md), [검증 기록](../testing/runs/20261106-setup-commands.md).


## Agent Monitor 공통 수명주기 · RQ-67/D-71

루트 `run.sh`와 Linux 설정 마법사의 `run`은 `apps/agent-monitor/manage.py start`로 통합한다. 처음 `--runtime <절대경로>`를 `runtime-location.json`에 연결하며 이후 release 변경과 무관하게 같은 DB·설정을 재사용한다. 다른 경로로 조용히 바꾸지 않는다. `run.sh`는 지원 Python이 없을 때 Linux 공개 package-manager bootstrap을 수행한다.

관리 명령은 `install/start/status/stop`, 오프라인 `inspect-runtime/adopt`, 검증된 `rollback`, 참조 보호 `cleanup`, 공개/공급 의존성 `tools`다. `adopt --release <SHA256> --inspection-revision <SHA256>`는 실제 Worker 잠금·지원 계약·현재 revision·backup을 확인하고 설치 포인터만 연결한다. UNKNOWN·실행 중·예약·미지원 계약을 완료로 바꾸지 않는다. `rollback [--release <SHA256>]`은 설치 manifest·환경을 검증하고 미완료/소유권이 있으면 거부한다. `cleanup --keep 2`는 계획이며 `--apply`일 때만 현재·직전·runtime 참조 외의 검증된 release를 정리한다.

공개 필수 도구는 Linux apt/dnf/pacman과 Windows winget/OpenSSH capability로 누락 시 준비한다. 정상 도구가 있으면 설치하지 않는다. Windows `board-connector.cmd --diagnose`는 Python 미설치 상태에서도 자동 설치로 넘어가지 않는다. 장비 드라이버·회사 TC 패키지 이름은 추정하지 않으며 서명/해시가 있는 공급 파일·명시 offline wheelhouse만 사용한다. 설치 성공을 회사 장비/TC 인수로 표시하지 않는다. 상세 입력과 복구 순서는 [PLUGIN_CONTROL_API](../agents/PLUGIN_CONTROL_API.md)를 따른다.
