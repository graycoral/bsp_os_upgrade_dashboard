# 연결 직후 Windows에 Linux TC 경로 표시

RQ-81 · T-302 · REG-0130. 기준 `48987bf2388157262e396a5b0e80f196bc886791`, 코드와 시험 `a46947859a52a9cb1eaccf0779ea9a0458ca4603`. macOS Python 3.11, 로컬 OpenSSH 서버, Chrome, Qt 6.8 offscreen을 사용했다.

| 조건 | 관측 결과 |
|---|---|
| 수정 전, Linux 공통 저장소에 TC 경로를 저장하고 실제 루프백 Host에 접속 | Manager가 CONNECTED를 반환했지만 설정의 TC 경로는 비어 있어 실패했다. |
| 수정 전, 브라우저가 첫 경로를 받은 뒤 같은 서버의 설정 버전과 경로 변경 | 새 버전을 받아도 이전 경로가 남아 회귀시험이 실패했다. |
| 8771만 사용하고 대시보드 포워딩·watch 없이 Linux 플러그인 1회 연결 | 서버 경로 자동 수신. 이전 SSH 세션의 보고 거부. 새 경로에 해당하는 목록 수신 대기. |
| 플러그인 보고와 대시보드 포워딩이 모두 없는 경우 | 임시 OpenSSH 서버에서 주 연결을 유지하며 별도 SSH 명령으로 설정 API를 읽었다. |
| 대시보드 포워딩 사용 | 실제 할당 포트로 설정 요청. 재사용된 대시보드 SSH PID를 거부했다. |
| 웹 및 Qt 설정 화면 | 최초 자동 표시, 같은 서버에서 편집값 보존, 서버 변경 시 이전 경로 제거, 설정 재수신을 확인했다. |

고정 코드의 Python 회귀는 367건 통과했다. Qt offscreen에서는 최초 수신, 초안 보존, 서버 변경 시 초기화와 읽기 전용 경로 재수신을 확인했다.

개발 중 브라우저 전체 시험은 22건 중 19건 통과했다. 콘솔 오류 표시와 연결 안내의 폴링 지연은 상태 응답 순서 처리 후 재시험에서 통과했다. 최종 집중 실행은 두 시험과 서버 경로 탐색·자동 수신을 포함해 4건 모두 통과했다. 나머지 신호등 시험은 기준 커밋에서도 동일하게 실패했다. 모의 Agent Monitor가 선택 미연결인 화면에서 정상 표시 4개를 기대하지만 실제 값은 3개다.

Python 회귀 실행 명령은 다음과 같다.

```bash
QT_QPA_PLATFORM=offscreen python -m pytest -q tests/test_direct_connector_unit*.py tests/test_ssh_bind_probe.py tests/test_connector_mirror*.py tests/test_connector_test_status.py backend/gui_test/tests/test_{shared_control,shared_connector_control,board_connector,connector_bootstrap,connector_server_port,connector_freshness,connector_web}.py
```

브라우저 실행은 `python scripts/test_connector_browser.py`, 경로 전환 시험 이름은 `connected Linux TC root refreshes automatically and follows the selected server`다. 이전 T-302의 DB 복구·양방향 동기화 근거는 [기존 실행 기록](20261119-direct-connector-implementation.md)에 있다.

회사 Windows·Linux·실보드 인수 T-305는 NOT_RUN이다. 양쪽 설치를 갱신한 뒤 회사 Linux에서 저장한 TC 경로와 Windows 환경설정의 표시값을 비교하고, 실제 회사 계정의 SSH 원격 명령 허용 여부 또는 플러그인 보고 수신을 확인한다. [이식 위치와 복구](../../porting/PORT-013.md)

## 수동 불러오기

RQ-81 · T-302 · REG-0131. 수정 전 `7f21176`, 수정·시험 `cc671797ce1fb11b7c5bc1e1825f194a9ebf6370`.

| 재현 조건 | 수정 전 | 수정 후 |
|---|---|---|
| 유효한 기존 대시보드 연결과 설정 대기 중인 직결 SSH Manager가 함께 있음 | “서버에 연결한 뒤 공통 설정을 불러오세요.” | 소유권을 확인한 기존 연결의 Linux 설정을 조회 |
| 8771 연결 및 Linux 플러그인 정상 보고 후 수동 조회 | Linux 경로 대신 로컬 편집 응답 | 현재 세션의 Linux 경로·버전·제한시간을 읽기 전용으로 반환 |
| 대시보드 포워딩만 사용할 수 없음 | API 또는 설정 조회 실패 | 플러그인 보고 또는 독립 SSH 읽기로 조회. 인증·식별 오류는 그대로 반환 |
| Linux 설정을 아직 받지 못함 | 연결 요구 또는 로컬 설정 표시 | 웹·Qt 수동 조회 API 모두 HTTP 503, 보드 연결 상태와 확인할 설정 포트 안내 |

재현 시험은 `tests/test_direct_connector_unit4.py`, `backend/gui_test/tests/test_shared_connector_control.py`에 있다. `backend/gui_test/tests/test_connector_web.py`는 실제 브라우저 세션 쿠키와 Qt용 Manager API 토큰으로 수동 조회에 같은 결과가 전달되는지 검사한다. 수정 커밋에서 직결·공통 설정·웹·커넥터 회귀 133건 및 설정 조회용 SSH 시험 2건이 통과했다. 회사 설치본의 버전과 당시 터널·포트는 미확인이다.
