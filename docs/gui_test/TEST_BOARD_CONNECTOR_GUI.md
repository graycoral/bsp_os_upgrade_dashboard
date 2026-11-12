# 보드 커넥터 사용 안내

현재 이름은 **보드 커넥터**다. 내부 실행 명령과 기존 설정 경로는 호환 유지한다. [계약](../design/BOARD_CONNECTOR_CONTRACT.md), [PORT-009](../porting/PORT-009.md)을 함께 확인한다.

## Mac에서 같은 창 미리보기

저장소에서 한 번 준비한 `.venv`와 고정 Qt 의존성 `apps/board-connector/requirements.lock`을 사용한다.

```bash
.venv/bin/python -m pip install -r apps/board-connector/requirements.lock
.venv/bin/python -B -m backend.gui_test.connector --preview
```

실행할 때마다 설치하지 않는다. 미리보기는 첫 진입부터 임시 home과 금지 호출 guard를 사용한다. 실제 설정·토큰·DPAPI·COM·SSH·TC·네트워크·자식 프로세스를 사용하지 않는다. 실제 제품과 같은 Qt widget/controller에 MockConnector를 주입한다. 연결 뒤 상태 선택에서 시험 중/오류/미연결/확인 필요와 보드 콘솔·공통 오류를 볼 수 있다. 미리보기의 파일 선택은 선택값만 모의 저장하고 실제 TC를 읽거나 실행하지 않는다.

연결/환경설정 두 탭, 환경설정의 보드 수 1~32와 보드별 탭, 연결 탭의 작은 상태등과 요약을 제공한다. 보드 수를 줄여도 저장 전에는 draft이고 변경 취소로 되돌린다. 로그는 기본 접힘이며 펼치면 보드 콘솔/TC 실행/연결/플러그인 오류 탭과 오류 필터·검색·복사·로그 열기가 있다. 창 닫기는 실제 연결 종료와 다르다.

## Windows 소스 실행

**현재 기존 editable 배포 ZIP에는 Qt wheel이 포함되어 있지 않다. 기존 ZIP의 launch.cmd를 GUI가 된 것으로 취급하지 않는다.** 이번 변경은 소스 GUI·참조 호스트 어댑터와 로컬 모의 검증이며 새 EXE/배포 ZIP은 만들지 않았다. 기존 CLI는 그대로 사용 가능하다. 새 소스 GUI를 사용하는 PC는 설치 담당자가 기존 Python 의존성과 Qt 6.8.3(Windows x64 호환 wheel/라이선스 포함)을 한 번 준비해야 한다. 일반 사용자의 매 실행 pip 설치는 없다. Windows wheel/오프라인 조립/실제 GUI 인수는 T-228 NOT_RUN이다.

소스 checkout의 준비된 `.venv\Scripts\pythonw.exe -B -m backend.gui_test.connector` 또는 `apps\board-connector\launch.cmd`로 시작한다. 새 프로파일이면 환경설정에서 서버/계정·회사 Dashboard 포트(예:8765), 외부 TC Python, 보드별 제어 COM/RX를 한 번 지정하고 저장한다. 기존 windows-runner.json은 자동으로 불러온다. SSH 포트/키는 고급 설정이다. key/agent와 사전 host key 인증을 사용하며 필요한 OpenSSH 대화형 인증은 표준 콘솔에서 먼저 끝낸다.

기존 Windows runner token과 Linux의 GUI_TEST_RUNNER_TOKEN은 그대로 사용한다. 설치 담당자는 별도의 GUI_TEST_CONNECTOR_REGISTRATION_TOKEN과 같은 값을 Windows `TokenStore(home/'registration', True)`로 DPAPI 저장한다. GUI IPC 토큰은 관리자가 별도로 생성한다. 비밀번호/토큰을 일반 JSON·명령행·화면·회사 전달 문서에 넣지 않는다.

연결은 기존 회사 대시보드 서비스를 재사용한다. GUI가 Linux API/Worker를 새로 설치하거나 중복 실행하지 않는다. 보드는 공통 registry를 통해 Dashboard와 plugin에 나타난다. TC 소스는 공통 서버에서 선택하며 Windows에 같은 TC 폴더를 다시 입력하지 않는다. 현재 실행은 고정 snapshot이며 Z:/UNC 직접 원본 실행과 새 자동 정리는 지원하지 않는다.

보드 콘솔은 검증된 RX 전용 splitter 포트가 필요하다. 프로그램이 virtual COM 드라이버를 설치하거나 포트를 자동 생성하지 않는다. 제어 COM과 RX를 같은 포트로 지정하면 거부한다. TC stdout/stderr는 별도 TC 실행 탭이며 보드 콘솔 수집의 대체물이 아니다. 미설정/끊김/오래된 상태는 문구로 표시한다. 오류는 공통 서버의 증분 오류 조회에 저장되며 회사 plugin의 실제 수신은 별도 인수한다.

안전한 연결 종료는 진행/일시정지/예약/UNKNOWN/삭제 중 작업이 없을 때만 가능하다. 종료 불명은 실제 상태를 확인하고 기존 복구 절차를 사용한다. TC 제한시간·세션 영구 삭제는 기존 대시보드 기능으로 관리한다. GUI에 별도 삭제/정리 정책을 저장하지 않는다.
