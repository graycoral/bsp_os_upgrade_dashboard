# 실행·진단 명령 계약 · RQ-59/D-63

setup 기본 동작은 기존 메뉴이며 `run`, `doctor`, `ports`를 직접 선택할 수 있다. `--only identity|boards|catalog`은 doctor 전용, `--save`는 ports 전용이다. 잘못된 조합·포트·프로파일과 기존 Linux runner_url 오류는 실행 전에 거부하고 오류 종료한다. identity/boards 전용 진단은 catalog 설정을 읽지 않는다. 진단은 인증·보드·목록의 단계와 실패를 구분하며 실제 TC·퓨징을 실행하지 않는다. timeout은 transport 제한이며 전체 진단의 hard deadline이 아니다.

`ports`는 유효값과 출처를 표시하며 `ports --save`만 원자 저장한다. CLI > 저장 프로파일 > 기존 기본값/SSH 설정 순이다. Linux `<repo>/.runtime/setup-ports.json`, Windows `<선택 home>/setup-ports.json`; schema 1, 네 포트와 선택 SSH 포트를 담는다. 기존 연결·토큰은 보존하며 자동 저장하지 않는다. setup.ps1은 나머지 인자를 전달하고 실제 종료 코드를 반환한다. Windows `launch-run.cmd`/`diagnose.cmd`, Linux `scripts/run.sh`/`doctor.sh`는 대기 없이 종료 코드를 전달한다. [사용 안내](../gui_test/RUN_AND_DIAGNOSE.md), [검증 기록](../testing/runs/20261106-setup-commands.md).
