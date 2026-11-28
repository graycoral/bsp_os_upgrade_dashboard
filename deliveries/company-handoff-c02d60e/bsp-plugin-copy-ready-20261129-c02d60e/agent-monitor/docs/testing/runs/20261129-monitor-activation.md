# 2026-11-29 · 플러그인 활성화와 Windows 대시보드 접속

RQ-86 · T-323. 기준 커밋 `d471ce70c2635f38559f98753962f9d548fe6904`. 아래 최초 결과는 당시 로컬 작업 트리에서 검증했다. 후속 전달은 `190e350`의 파일 선택·TC 목록 수정을 포함한 `b7ebc24`에서 통합했다. 통합본의 시험 결과와 릴리스 검증값은 패키지와 함께 제공하는 `00_START_HERE.md`에서 확인한다.

변경 제품·계약 파일의 SHA-256 지문은 `41da5703cc37a34c75fa39cf590e81bd4d7707ddba44dfe67d40e1b78717e775`, 변경 시험·스크립트의 지문은 `b754840f2579ab6d1d5f1eaf2955edb3584abd6608944653b4b88984cf07227b`이다. 실행 폴더의 `t323-hashes.json`에 있는 각 그룹의 경로별 SHA-256을 키 순으로 정렬한 JSON으로 직렬화해 다시 해시했다.

## 구현 전 독립 리뷰

새 Codex 리뷰 세션이 회사 훅·원본 CLI·Windows Manager·웹·Qt 경로를 읽었다. 회사 활성화 훅과 기존 수동·선택 감시의 수명을 분리하고, 제한망에서는 도구 준비와 pip 호출을 모두 차단하도록 했다. 중복 활성화는 시작 잠금에 합류해야 한다. 직결 전용 프로필의 빈 모니터 포트를 보존하고, 끊어진 SSH 세션의 링크를 웹·Qt에서 지우는 조건을 시험 범위에 포함했다.

구현 후 독립 리뷰에서 구형 Windows OpenSSH가 성공한 리스너를 `new [port listener]`로 보고한다는 호환 차이를 발견했다. 신형의 `new port-listener [port listener]`와 함께 시험했고, 다른 포트·다른 채널·실패한 바인딩은 접속 근거로 사용하지 않는다.

Sol xhigh가 Linux·Windows 구현과 시험 스크립트를 작성했다. 반복 재시험 이후 Astra가 최종 복구 경로를 인수했다. 실제 SSH에서 Windows 로컬 포트를 점유했다가 해제해도 접속 주소가 회복되지 않는 실패를 재현했다. 이후 같은 보드 연결을 유지하며 대시보드 포워딩만 다시 시작하도록 수정했다. 최초 포트 충돌 해소와 실행 중 포워딩 프로세스 단독 종료를 포함한 동일 시험이 통과했다. 로컬 근거는 `.local-reports/20261129-dashboard-forward-recovery/{before-loopback,after-loopback}.log`에 있다.

별도 단위 회귀 10건에서 구형·신형 OpenSSH 로그와 설정 오류·중지·인증 거부의 재시도 중단을 확인했다. `.local-reports/20261129-dashboard-forward-recovery/fatal-config.log`

## 재현과 재시험

- 수정 전 Linux 활성화 명령·포트 전달 시험 7건과 Windows 링크·상태 시험 10건이 실패했다. Windows 직결 상태값은 접속 주소를 비워 두었고 화면 실패 처리에는 이전 링크가 남았다.
- 중간 시험에서 기존 비대기 잠금에 추가된 시계 조회, 이미 종료된 선택 터널의 상태 보고, 웹·Qt 시험 입력 및 포트 사용 권한을 확인했다. 잠금·상태 전이를 수정하고 같은 회귀를 다시 실행했다. 첫 복사본 시험에서는 정상 기동한 임시 서비스를 정리할 때 Python 격리 옵션 때문에 관리자 모듈을 찾지 못했다. 해당 인스턴스를 정상 종료한 후 복사본에 포함된 관리자의 실행 환경을 사용해 재시험했다.
- 로컬 전용 로그는 `.local-reports/20261129-monitor-activation-linux/`, `.local-reports/20261129-monitor-link-windows/` 및 스크립트가 출력한 실행별 디렉터리에 있다. 스크립트 실행법은 [PORT-020](../../porting/PORT-020.md)을 따른다.

## 검증 범위

| 환경 | 실행과 관찰 |
|---|---|
| 기능 스크립트 | `bash scripts/test_monitor_activation.sh python package browser-monitor` 종료 0. Linux 관리·플러그인 111 PASS, 커넥터·Qt·SSH 회귀 120 PASS, 복사본 시험 PASS, Chromium 대시보드 시나리오 1 PASS. Python 수집 후 추가된 재시도 중단 조건 4건은 위 별도 단위 시험에서 통과했다. 단계별 로그와 소스·시험 파일별 SHA-256은 `.local-reports/20261129-monitor-activation.YpTO9k/`에 보관한다. |
| 로컬 빌드 | `bash scripts/build-ui.sh all --skip-install`이 기존 Node 의존성으로 Dashboard와 GUI Test 두 UI를 빌드했다. 로그는 `.local-reports/20261129-monitor-build.fYBmG4/build.log`에 있다. |
| 복사형 패키지 | 새 임시 폴더로 전체 소스와 UI를 내보내 복사 후 무결성을 검증했다. 미설치 제한망의 종료 코드 6, 준비된 설치에서 동시 호출 두 개가 API·Worker 한 쌍을 재사용하는 것, 재호출 후 같은 인스턴스, 실제 HTTP로 내려받은 HTML·자산 일치, 빈 작업 목록, Windows 내보내기 포트, 시험 인스턴스 정상 종료를 확인했다. 의존성은 로컬에 설치된 잠금 버전을 사용했다. |
| 기존 회사 CLI·전달 회귀 | 임시 홈과 모의 보드를 사용한 `test_company_connector_delivery.py`, `test_direct_connector_unit1.py`, `test_agent_monitor_delivery.py` 합계 32 PASS. `.local-reports/20261129-monitor-contract.lE11w1/contract.log` |
| Windows 접속 경로 | macOS OpenSSH 10.3p1 클라이언트·임시 sshd와 모의 Windows Host로 양방향 터널을 연결했다. 사용자 지정 포트에서 대시보드의 늦은 준비, HTML 응답, 중단·복구 및 이전 SSH 세대의 주소 만료를 검증했다. 구형 OpenSSH 로그 형식·서비스 식별 오류와 Qt는 로컬 회귀로 확인했다. |
| 전체 브라우저 | 실제 Chromium에서 30건 중 26 PASS, 4 FAIL. 실패는 모두 기존 T-308 파일 찾아보기 안내다. `d471ce70`의 별도 소스에 동일한 네 시험을 적용해 같은 안내 누락 4건을 재현했다. 이번 대시보드 버튼 시험은 단독으로도 1 PASS. 전체 `.local-reports/20261129-monitor-activation.PctFf3/browser.log`, 기준 `.local-reports/20261129-monitor-browser-base.9QzWsP/browser.log`. |

## 회사 인수

회사 플러그인의 실제 활성화 이벤트, 회사 Linux와 Windows OpenSSH, 장비 PC 브라우저에서의 접속은 NOT_RUN이다. 회사 담당자는 [PORT-020](../../porting/PORT-020.md)의 시나리오별 결과를 현지 적용 이력에 기록한다.
