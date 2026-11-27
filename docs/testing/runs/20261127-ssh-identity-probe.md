# 2026-11-27 · Linux identity 기반 SSH 연결 확인

RQ-77 / T-292 / REG-0127. 기준 `03e4ac39d44657554c0eb966984542477b6dd9d5`, 로컬 수정·시험 커밋 `a39b0084c4c8c571b0c538da66514c8b3b4feed1`. [회사 적용 위치와 확인 절차](../../porting/PORT-013.md#2026-11-27--8771-응답과-manager-연결-상태-일치)

## 재현과 재시험

회사 관찰은 Linux 8771 identity 정상·보드 1개 조회, Windows SSH 인증 로그 17줄, Manager 확인 타임아웃 후 재연결이다. 로컬에서 확인한 원인은 성공 문구에 의존하는 Manager 판정이다. 회사 Windows의 파이프 버퍼 지연 자체는 미측정이다.

macOS OpenSSH 10.3p1과 Python 3.11.7을 사용했다. 임시 키·known_hosts·sshd·HTTP Host를 루프백으로 격리했다. macOS의 실행 기록에서 Windows 프로세스 생성 시각은 시험용 식별자로 대체했다. 원본 로그는 Git에서 제외하는 `.local-reports/ssh-identity-TMsiCc/`에 있다.

| 조건 | 관찰 |
|---|---|
| 수정 전 주 SSH에서 성공 로그 생략 | 기존 `DEBUG1` 작업 트리에서 FAIL 1건. 7초 동안 인증된 SSH가 3번 연결·종료됐다. `red.log` |
| 수정 후 인증 17줄만 출력하는 모의 SSH | Linux 확인 성공 시 CONNECTED. 성공 문구를 출력해도 identity가 미확인이면 연결 대기 |
| 루프백 SSH 서버의 설정 포트·다른 로컬 포트, 주 SSH 성공 로그 생략 | 실제 SSH 원격 명령이 HTTP 200과 현재 runner를 확인. 주 PID 1개를 이전 타임아웃 이후에도 유지 |
| 원격 명령 거절(`MaxSessions 0`, `ForceCommand /bin/false`) | 주 SSH 유지. 이전 관측은 제외. Linux 직결 진단의 실제 HTTP GET·peer/hello POST 후 해당 서버명/주소·포트·runner를 확인해 CONNECTED |
| 다른 runner 응답, Windows Host 기동 지연 | 확인 대기. 같은 SSH PID에서 올바른 Host 응답이 돌아오면 CONNECTED |
| 새 주 SSH 시작 전부터 같은 runner가 응답 | 기존 엔드포인트 점유를 표시하고 중복 주 SSH 기동을 보류 |
| 잘못된 서비스·runner·HTTP 상태·잘못된 JSON·강제 명령 출력·과대 응답 | 성공 판정 거부. 주 터널 오류 분류와 별도로 처리 |

관련 시험 명령은 `python -m pytest -q tests/test_ssh_bind_probe.py tests/test_direct_connector_unit*.py tests/test_runner_ports.py tests/test_setup_runtime.py tests/test_force_stop.py`다. 작업 트리 재시험 `final-suite.log` 및 고정 커밋 격리 재시험 `pinned.log` 모두 178 PASS, 9 SKIP, 종료 코드 0이다. 고정 커밋에서 별도 Codex 세션 코드 리뷰 APPROVED. 회사 환경과 Claude 독립 리뷰는 미실행이다. 시험용 macOS 프로세스 식별자 추가 전 실행에서 6건 실패한 기록은 `verified.log`와 `targeted.log`에 남겼다.

문서 검사 `python3 docs/testing/validate_docs.py`는 작업 트리와 이식 브랜치에서 각각 PASS, `git diff --check`도 통과했다.

## 별도 세션에서 확인한 유사 사례

아래 네 항목은 확인 요청에 따라 모의 입력 또는 실제 단기 자식 프로세스로 재현했다. 이번 제품 수정 범위는 주 SSH의 연결 판정이다.

| 경로 | 재현 결과 | 로컬 근거 |
|---|---|---|
| Manager 연결 검증 | SSH 상태가 CONNECTED이면 Host 503에서 STOPPED/CONNECTED를 함께 반환. 다른 서비스가 200 JSON을 반환해도 READY/CONNECTED | `.local-reports/ssh-audit-lfkTxI/observations.log` |
| 선택 대시보드 SSH `-L` | 150ms 생존 후 성공 표시. 자식이 0.6초 후 종료돼도 보조 터널 상태가 CONNECTED | 같은 실행의 `observations.log` |
| 자동 퓨징 UART 부팅 확인 | 마커 뒤 300바이트 입력 시 READY. 마커 뒤 70,000바이트가 들어오면 64KiB 버퍼에서 밀려 CONSOLE_TIMEOUT | `.local-reports/uart-readiness-review-venwY9/replay.log` |
| native v1 빌드 | 일부 산출물을 쓰고 1로 종료한 더미 빌드는 FAILED. 같은 명령에 `tee` 파이프를 붙이면 성공 및 산출물 해시가 기록됨 | `.local-reports/build-exit-review-3ZRmuI/replay.log` |

일반 TC는 종료·출력 EOF와 결과 계약을 확인한다. BSP bridge는 종료 후 구조화된 결과를 검증한다. 검토한 두 경로에서 SSH와 같은 디버그 성공 줄 대기는 발견되지 않았다.

제한된 SSH 계정의 권한 조합은 `.local-reports/probe-permissions-HgYH08/check.log`, 주 SSH의 개별 채널 거절 오분류는 `.local-reports/probe-review-OW8ghv/host-down.log`에서 독립 재현했다. 회사 Windows·Linux·실물 보드 인수 T-305는 NOT_RUN이다.
