# 웹 보드 커넥터 퓨징 설정 검증

RQ-83 · T-309 · REG-0119. 기준 커밋 `557b7d070a195c44f17bf2eb05e0d8fd0dd7c73d` 이후 로컬 작업 트리에서 검증했다. 원본 로그는 로컬 전용 `.local-reports/fusing-settings-RQbOO6/` 아래에 있다.

| 범위 | 실행과 결과 |
|---|---|
| 공유 UI 빌드 | `apps/web`, `apps/gui-test` 각각 `npm run build` PASS. TypeScript 및 Vite 빌드 완료. |
| Linux 설정·직결 CLI | `pytest -q tests/test_direct_connector_unit4.py tests/test_bsp_plugin_client.py backend/gui_test/tests/test_shared_connector_control.py backend/gui_test/tests/test_shared_control.py` 53 PASS. 실제 임시 DB·대시보드 API를 통한 양방향 설정 확인, 명시적 퓨징의 필수값과 인자 우선순위, TC 단독 호환 및 오프라인 BAT 저장 거부를 포함한다. |
| 대시보드 브라우저 | Chromium `playwright test connector-mirror.spec.ts` 16 PASS. 탭 진입 시 필드 노출, BAT와 프로파일 수정, 읽은 revision으로 저장, 다른 설정 보존 확인. |
| Windows 웹 화면 | `scripts/test_connector_browser.py`를 macOS Chromium과 모의 Manager로 실행했다. 19 PASS, 5 FAIL. 추가한 퓨징 폼 노출·편집·저장은 PASS. |
| 기존 실패 대조 | 동일 시험을 기준 커밋의 별도 소스에서 실행해 파일 선택 미리보기 안내 3건, 파일 선택 대기 안내 1건, 연결 신호등 개수 1건의 동일 실패를 확인했다. `windows.log`, `baseline.log` 참조. |

처음 대시보드 단독 시험은 설정 저장을 확인한 뒤 fixture가 직결 상태 GET을 예상하지 않아 실패했다. 직결 연결이 없는 503 응답을 명시한 뒤 전체 16건을 재실행했다. 마지막 Python 회귀 1차에서 퓨징 프로파일 검사 코드가 TC 투영 함수에도 들어가 2건이 실패했다. 해당 코드를 퓨징 미리보기 경로에만 남기고 같은 53건을 재실행했다. 실패 로그는 `dashboard.log`, `final-python.log`, 최종 결과는 `dashboard-r2.log`, `final-python-r2.log`에 보존했다.

빈 퓨징 필드를 보내는 기존 클라이언트의 오프라인 제한시간 저장을 함께 확인한 최종 Python 재시험은 53 PASS다. 로그는 `compatibility.log`에 있다. 문서 검사와 `git diff --check`도 통과했다.

실제 회사 YAML 훅, Windows 설치본, USB 장비 퓨징·부팅·TC 인수는 NOT_RUN이다. 회사 적용은 [PORT-016](../../porting/PORT-016.md)을 따른다.

## PORT-016 전달 경로 검증

원본 체크아웃 `3f4879e21e70ada4f65845ae886e83c00e10577f`에 미커밋 변경이 있는 상태에서 두 UI를 다시 빌드하고 소스 밖의 임시 폴더로 내보냈다. 로컬 후보 release는 `075630d527cfcf8665833c5aab29faa8820bc83f1d34d20d6910771879717e26`이고 `source_dirty=true`다. 회사용 고정 전달본은 아직 게시 전이다.

- `plugin.py verify PACKAGE --pristine` PASS. 생성된 루트 README에서 PORT-016을 참조하며, 루트·내부 진입점이 바이트 단위로 일치한다.
- 가상 접속 정보로 별도 Windows 폴더를 생성했다. Windows descriptor의 release와 내부 manifest의 파일 511개 SHA-256이 패키지와 일치한다. Windows 프로세스와 장비는 실행하지 않았다.
- 게시된 `8abe926` 외부 manifest와 로컬 후보 외부 manifest의 파일 목록을 비교한 변경·추가·삭제 경로는 36개다. 다른 후속 변경을 포함한 전체 차이는 로컬 전용 `.local-reports/port016-delivery-mRuytm/manifest-delta.tsv`에 기록했다. PORT-016 표는 퓨징 기능 범위만 설명한다.
- 패키징 시험 `tests/test_plugin_delivery.py`와 `tests/test_agent_monitor_delivery.py` 합계 26 PASS. 생성·검증 결과와 시험 로그는 같은 로컬 보고 폴더에 있다.
