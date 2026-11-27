# 보드 커넥터 자동 연결과 플러그인 수신 확인

RQ-77/81 · T-291/302 · REG-0138. 기준 `10090eb`에서 플러그인과 Agent Monitor를 각각 단독 피어로 넣어 수동 조회를 재현했다. Agent Monitor가 보낸 TC 경로 `/test/agent_monitor`에도 출처가 ‘Linux 플러그인 연결 보고’로 표시됐다. 기존 코드는 현재 세션·대상·revision을 확인한 뒤 발신자 종류에 관계없이 같은 라벨을 붙였다.

현재 작업 트리에서는 첫 탭이 현재 세션에 해당하는 플러그인의 마지막 보고와 설정을 표시한다. 공통 설정 조회는 실제 응답자의 이름을 표시한다. 서로 다른 TC 경로를 보내는 Linux 클라이언트 두 개와 로컬 HTTP Host로, 나중에 온 Agent Monitor 보고가 플러그인의 수신 내역을 바꾸지 않는 경우를 시험했다. 세션 변경, 만료, 보고 미수신도 검사했다. 플러그인이 생략한 선택 설정은 수신 내용에서 생략하며, revision이 달라 공통 폼에서 거부한 보고도 수신 내용에서 조회할 수 있다.

GUI 실행 시 서버 포트 옵션을 먼저 적용하고 기존 Manager에 한 번 자동 연결을 요청한다. 서버와 SSH 계정만으로 시작할 수 있다. 설정 미입력, 최초 저장, 실행 중 Host 재사용, 명시적 종료, 실패 후 수동 재시도 가능 상태, 구버전 Manager의 수동 연결 안내를 검사했다. 자동 연결 범위는 Host와 SSH다.

로컬 실행 로그는 Git에 포함하지 않는 `.local-reports/20261127-plugin-overview/`에 있다. 처음 추가한 시험은 수신 정보 조회 기능이 없어 2건 실패했다. 첫 Python 회귀 실행은 부분 초기화한 테스트 Manager에 자동 시작 상태가 없어 실패했다. 초기 상태 처리를 수정한 뒤 재시험했다. 최초 브라우저 실행은 PATH에 npx가 없어 중단됐고, 설치된 Playwright CLI를 Node로 실행해 재시험했다.

| 실행 | 결과 |
|---|---|
| `pytest`로 Manager 웹·포트·bootstrap, 직결 Unit 2/4, BAT/CMD launcher, 공유 설정, PuTTY, 보드 GUI, TC 상태, SSH 조회 검증 | 초기 재시험 282 PASS, 최종 코드 284 PASS, 27 SKIP. macOS의 Windows 전용 사례 등은 실행하지 않았다. `python-final.log`, `all-final.log` |
| 수정된 Unit 4의 실제 루프백 보고, 포트·Qt 공유 설정 재검증 | 75 PASS. `peer-final.log` |
| 설정 저장 대기·명시 종료·기동 실패, 구버전 호환 및 실제 Manager 폴링 루프의 자동 시작 요청 검사 | 3 PASS. `auto-final.log` |
| 보고 출처·루프백 전달 재시험 | 3 PASS. `receipt-validation.log` |
| 선택 필드가 생략된 플러그인 보고, revision이 다른 보고, 전체 Unit 4 및 포트·Qt 공유 설정 | 76 PASS. `peer-fields-final.log` |
| Chrome의 첫 탭에서 수신 대기 → 플러그인 수신 → 설정 펼치기 → 보고 만료 → 보고 없음 | 1 PASS. `focused-browser.log` |

게시 전 로컬 작업 트리의 전체 Chrome 회귀는 22 PASS, 6 FAIL이었다. 신규 첫 탭 시험과 Linux 설정 수동·자동 조회는 통과했다. 실패는 로컬 T-308 찾아보기 안내 4건, [모의 신호등 개수 1건](20261127-connector-linux-settings.md), 서버 이름 갱신 대기 1건이다. 서버 이름 대기는 이번 변경본과 기준 커밋의 웹 자산 양쪽에서 같은 기대값/관찰값으로 재현됐다. `browser2.log`, `notices-browser.log`, `baseline-notices.log`에 남겼다.

회사 Windows 프로필, 실제 SSH 연결과 회사 플러그인 송신값 확인은 T-305 NOT_RUN이다. DB 변경과 데이터 이전은 없다.
