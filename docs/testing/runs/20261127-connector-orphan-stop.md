# 20261127-connector-orphan-stop

RQ-71/77 · D-77 · T-271/292 · REG-0128. 원본 `e9547d337b839f6ad1fe11d2ce809a725d13a34a`, 코드와 시험 `8512625cb69a867b5a8da58f11afee45cbcdfa5b`.

| 재현 조건 | 수정 전 | 수정 후 확인 |
|---|---|---|
| 이전 Manager가 남긴 주 SSH가 살아 있는 상태에서 새 Manager가 상태를 기록하고 종료 | 강제 종료 결과는 FORCE_STOPPED였지만 이전 SSH가 살아 있어 회귀시험 1건 실패 | 같은 프로필의 PID·생성 시각을 보존해 이전 SSH만 정리 |
| 시작 전 Linux 8771에서 현재 Host의 identity가 이미 응답 | 기록된 주 SSH와 수동 SSH에 동일한 안내. 두 분기 시험 모두 실패 | 기록한 서버·계정·포트·주 SSH 생성 세대가 모두 일치하면 PID와 강제 종료 절차를 안내. 수동 터널, 다른 포트, 재사용된 PID, 대시보드 전용 SSH에는 소유자 확인 안내 |
| 같은 identity를 내보내는 실제 수동 SSH가 먼저 포워딩 | 기존 연결을 진단하는 상황 | 수동 SSH 생존, Manager의 주 SSH 시작 0회, 수동 터널 사용자가 종료한 뒤 Manager가 자동으로 주 SSH 1개 연결 |
| 별도 프로세스로 실행한 터널 감독자가 강제 종료된 뒤 주 SSH가 계속 전달 | 서버 포트로 identity 응답을 직접 재확인 | 같은 프로필 강제 종료 후 포트 연결이 거부됨. 별도 수동 포트는 같은 identity로 계속 응답. 같은 포트에 다시 시작한 주 SSH는 새 프로세스 |
| 서버 포트 점유 검사 | 강제 종료 결과에 원격 포트 상태가 없음 | TCP LISTEN 행이 없으면 FREE, 있으면 BUSY와 주소·제공된 프로세스 정보, 원격 명령 실패·예상 외 출력·빈 강제 명령 결과는 UNKNOWN |
| 프로필 복사와 PID 재사용 | 기존 소유권 검사 및 분리된 기록 점검 | 다른 경로로 복사한 소유권 파일은 종료 전에 거부. 재사용된 PID는 보존. 로컬 종료가 확정돼도 다른 점유자가 있으면 BUSY를 기록 |

로컬 macOS에서 임시 계정 키·임의의 루프백 포트·별도 OpenSSH 서버와 클라이언트를 사용했다. 테스트 Host에서 발급한 identity를 두 실제 SSH 경로로 확인했다. macOS 시험은 생성 시각과 종료 핸들을 시험 어댑터로 대체했고 `ss`가 없는 서버의 UNKNOWN을 확인했다. Linux 명령의 FREE/BUSY 출력 판정은 POSIX 셸과 `ss` 응답 모의로 확인했다. 중간 실행에서는 SSH 기록 형식을 변경하는 동안 부모와 자식 시험 프로세스의 버전이 달라 통합 시험이 한 차례 실패했다. 최종 재시험은 고정된 소스로 실행했다.

재현 명령은 다음과 같다.

```bash
python -m pytest -q tests/test_force_stop.py tests/test_ssh_bind_probe.py tests/test_direct_connector_unit*.py tests/test_board_connector_launcher.py tests/test_setup_runtime.py tests/test_company_connector_delivery.py
```

최종 관련 회귀시험은 **192 PASS, 28 SKIP**(123.64초)였다. FastAPI의 기존 TestClient 사용에 대한 의존성 경고가 1건 있었다. 구버전 고아 SSH 시험 1건과 기존 안내 문구를 검사한 2건에서 수정 전 실패를 확인했다.

회사 Windows의 실제 process handle, Linux sshd 권한과 `ss` 출력, 장비가 연결된 8771 재시작 인수(T-272/T-305)는 NOT_RUN이다. [회사 적용 방법](../../porting/PORT-009.md)
