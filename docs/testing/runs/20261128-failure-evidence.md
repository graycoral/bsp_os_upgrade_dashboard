# 실패 TC 증거 조회 · Windows Host 및 플러그인 참조 CLI

RQ-79 · T-322. 최초 시험은 ba31de7 위의 작업본에서 실행했다. 원격 `main`에 게시한 구현은 [`1616809`](https://github.com/graycoral/bsp_os_upgrade_dashboard/commit/161680977a2e7d7a581550d7acb5c6bcbb6a84ed)이다. macOS 로컬 SQLite·HTTP Host와 복사형 플러그인 CLI, 모의 ADB, 로컬 POSIX 셸에서 확인했다. 회사 Windows, 보드 USB·UART, 실제 회사 플러그인의 수신·표시, 현장 지연은 NOT_RUN이다.

- Dual Python TC 실패 시 한 보드의 수집을 보류하고 다른 보드에 권한 오류를 주입했다. 수집 중 Run은 PAUSED였고 TC 로그 끝부분을 바로 읽을 수 있었다. 수집 후 보드별 결과와 같은 시도의 실패 사유·종료 코드를 재접속한 클라이언트에서 확인했다. 누락·오프라인·권한 오류·3초 제한의 모의 진단을 확인했다.
- 모의 장치 셸에서 실제 수집 명령을 실행했다. 최근 50줄, 비밀 값 마스킹, 65 KiB를 넘는 한 줄의 잘린 자격 증명 제거, 커널 명령 실패 보존을 확인했다. 기존 PASS 경로는 진단 호출 없이 종료했다.
- 재접수·이전 DB에서의 업그레이드와 백업 복구, 중단된 수집의 재시작 표시, 바뀐 시리얼의 수집 차단, 삭제 후 조회 410과 증거 삭제를 시험했다.
- 별도 Codex 세션이 실패 상태 커밋 시점, 보드 매핑, 구형 Host와 분석 호환, 보존·마스킹·삭제, 회사 CLI에서 시도별 조회 가능 여부를 검토했다. 수정 후 로컬 증거 범위 APPROVED. 독립 세션에서 관련 시험 3 PASS.
- 복사한 `plugin.py test analyze`를 기본 분석기로 실행하자 기존 호출에서 필수 `run` 데이터가 빠져 종료 1로 실패했다. 참조 클라이언트가 실패 시도와 원인·근거 버전을 넘기도록 수정했다. 분석기 미설정 상태에서는 HOLD로 기록하며 저장한 증거와 Run을 유지한다.
- 로컬 전용 원본은 `.local-reports/20261128-failure-evidence/`와 `.local-reports/20261128-failure-independent-review/`에 있다. `builtin-red.log`에 기본 분석기 실패를 보존했다.

[응답 구조와 상태](../../design/DIRECT_CONNECTOR_ARCHITECTURE.md#실패-증거-전달) · [회사 실행 명령](../../agents/BOARD_CONNECTOR_PLUGIN_WORKFLOW.md#실패한-시도의-로그-받기) · [원본 변경과 DB 적용](../../porting/PORT-013.md)

실행 결과는 다음과 같다.

| 실행 | 결과 | 로그 |
|---|---|---|
| `pytest -q`로 connector run replay, direct connector unit 3·4·5, 회사 전달, 플러그인 runtime 등 6개 시험 파일 실행 | 105 PASS | `verified.log` |
| 기본 분석기 수정 후 복사형 CLI와 direct connector unit 4 재시험 | 25 PASS | `builtin-fixed.log` |
| 최종 CLI 계약과 복사형 패키지 전달 전체 재시험 | 8 PASS | `export-final.log` |

위 시험 수에는 중복이 있다. 실제 Windows·회사 인수와 분리한 로컬 결과다. 기본 분석기 수정은 별도 세션에서 코드 재검토 후 APPROVED다.
