# Windows 파일 선택과 TC 경로 갱신

RQ-63/81 · T-308/302 · REG-0117/0118. 기준 커밋은 `f15b31ae03c00e3b4fa5522ef94ab96db9369673`이다. macOS arm64, Python 3.11, Playwright, 임시 Linux 설정 DB와 루프백 Host를 사용했다.

| 시험 | 결과 |
|---|---|
| 수정 전 `BSP_REPRO_T308=1 python scripts/test_connector_browser.py --grep T-308` | 4 FAIL. 세 필드에서 미리보기 안내가 비었고 지연된 선택 요청에도 대기 메시지가 없었다. |
| 수정 전 Windows `ManagerActions.shared`로 폴더 저장 후 Host 상태 조회 | FAIL. Linux에 저장됐으나 Host 경로가 비었다. 이전 경로가 남는 사례의 [원래 재현 기록](20261122-connector-file-picker.md)도 보존했다. |
| 수정 후 `python scripts/test_connector_browser.py --grep 'T-308\|cancelling a picker'` | 5 PASS. 세 필드의 미지원 안내, 지연·실패와 초안 유지, 취소·선택을 확인했다. T-308은 기본 회귀에 포함된다. |
| 직접 연결 unit 2·3·4, connector run replay·observation, connector web·shared connector control·shared control의 pytest 8개 파일 | 195 PASS. Windows 저장 → Linux 설정 API → 루프백 Host 조회로 경로 교체·해제, 접근 불가 폴더 재시도, Runner 및 리비전 불일치 거부를 확인했다. |
| 대시보드·독립 GUI Test UI | 두 UI의 프로덕션 빌드 PASS. |
| 실제 회사 Windows 파일 선택창·SSH 터널·회사 장비 | NOT_RUN. [PORT-009 확인 항목](../../porting/PORT-009.md#브라우저-파일-선택과-tc-경로-확인). |

전체 로그는 로컬 전용 `.local-reports/t308-fix/`에 있다. `browser-red.log`와 `catalog-red2.log`가 수정 전 실패, `web-final-focused.log`와 `python-final.log`가 수정 후 결과다.

## 고정 소스와 브라우저 전체 회귀

제품 커밋은 `190e3505a007e060cbfcf984d1f376ecede4a3c1`이다. 기본 커넥터 웹 모음은 Playwright 고정 Chromium에서 28 PASS, 1 FAIL이었다. 유일한 실패는 별도 신호등 시험에서 초록 4개를 기대했으나 3개가 표시된 경우다. 변경 전 `f15b31a`의 격리 체크아웃에서 같은 시험을 실행해 같은 4/3 실패를 확인했다. 최종 취소·선택을 포함한 관련 시험 5건은 모두 통과했다. 전체 모음과 기준 버전 결과는 `web-final-full.log`와 `base-lights.log`에 있다. 시스템 Chrome의 중복 전체 실행은 고정 Chromium으로 전체 결과를 확보한 뒤 중단했다.

고정 소스의 두 UI 빌드 자산으로 회사 패키지를 내보냈다. 깨끗한 패키지의 사본 안에서 direct connector unit 4, 회사 전달 계약, Run replay, connector observation, connector web을 실행해 140 PASS였다. 가상 프로젝트 안으로 Windows 연결 폴더를 내보낸 첫 시도는 출력 경로 보호로 거부됐고, 프로젝트 밖에 다시 생성한 폴더에는 수정한 파일과 실행 BAT가 들어 있었다. 두 수정 파일의 바이트를 대조했다. 전체 로그는 `receiver.log`, `windows-export.log`, `windows-export-scoped.log`에 있다. 패키지 무결성과 직전 `7691c0e` 대비 전달 증거 검증도 통과했다.
