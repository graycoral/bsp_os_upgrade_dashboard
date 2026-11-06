# PORT-005 · TC 목록 읽기 제한시간

RQ-58/D-62/REG-0071. 느린 Windows TC 공유 폴더의 목록 조회 대기시간과 웹 설정·진행 표시를 회사 대시보드로 이식한다. 먼저 [회사 공통 절차](README.md)와 회사 저장소의 COMPANY_MAP/APPLIED, 필수 운영 정책을 확인한다.

## 기준과 선행 조건

원본 기준 커밋은 `0a378cda23262cafaa8f962c3c7eae5765a18755`이다. **대상 코드 커밋은 `7cad856f65798e3891e200d60e1301057161e3b8`다.** 로컬 검증 후 동일 코드·시험 바이트를 고정했으며 회사 인수는 별도다. 기준 커밋의 RQ-55/56 소스 설정 및 PORT-004 공통 GUI 구조가 선행한다. 원본 커밋을 회사의 마지막 적용 커밋으로 가정하지 말고 이미 이식한 기능과 비교한다.

기존 Python/httpx/FastAPI/UI 도구 버전을 사용하며 새 의존성이나 DB 이전은 없다. API와 worker가 같은 runtime을 사용해야 한다. 회사 인증·API prefix·TestError 응답·서비스 계정의 runtime 파일 권한을 확인한다. 기존 승인 Runner EXE의 카탈로그 서버를 그대로 사용한다.

## 재사용 파일과 조정 위치

| 파일 | 역할·회사 조정 |
|---|---|
| `backend/gui_test/catalog_settings.py` | stdlib-only 설정 저장·검증·원자 교체; runtime의 전용 JSON 경로를 주입 |
| `backend/gui_test/runtime.py`, `core/manager.py` | 정상/Mock/live·API/worker에 같은 설정 객체 또는 파일 연결; 직접 Manager는 DB 옆 기본 파일 |
| `backend/gui_test/adapters/windows_remote.py` | catalog별 callable 유효값을 한 번 읽고 `/v1/catalog` 요청에만 timeout 주입; 다른 요청5초 유지 |
| `backend/gui_test/api/router.py` | 두 prefix의 독립 설정 GET/PUT; 회사의 기존 인증·오류 매핑 유지 |
| `packages/gui-test-ui/src/SourceRequestSettings.tsx`, `SourceSettings.tsx`, `TestPage.tsx`, 관련 공통 스타일 | 같은 UI/CSS 버전으로 목록 로딩 상태·설정 편집/저장·오래된 응답 거부 재사용 |
| `scripts/setup_runtime.py` | 선택 사항: 소스 마법사 단계별 flush·메뉴8·점검 전용 CLI override; helper도 함께 반입 |
| `backend/gui_test/tests/test_catalog_settings.py`, `tests/test_catalog_timeout.py`, `tests/e2e/catalog-loading.spec.ts` | 설정·요청 제한·진행·브라우저 회귀; 기존 fixture 변경도 함께 확인 |

필드·범위·오류·적용 규칙의 원본은 [GUI Test 계약 RQ-58](../design/GUI_TEST_CONTRACT.md)이다. 회사에서 기존 연결 `gui-test.json`이나 DB를 교체하지 않는다. source-storage·기존 Run·선택·Suite·TC 실행 timeout·lease·제어 정책을 보존한다. 전용 파일 부재는 기본100초이며 저장값은 다음 요청부터 적용한다. 저장을 위해 소스를 다시 적용하거나 재시작할 필요가 없다.

## 적용·검증·복원

1. 회사 코드·기존 설정·DB를 백업하고 원본 기준과 대상 코드의 관련 파일 diff를 회사 접점에 대응한다. 사용자/회사 파일 전체를 자동 교체하지 않는다.
2. Linux API/worker와 공유 UI를 같은 버전으로 배포하고 서비스의 실제 runtime에 전용 설정 경로를 맞춘다. 코드 배포 후 서비스 재시작은 기존 운영 절차를 따른다. 이후 제한시간 설정만 바꿀 때는 재시작하지 않는다.
3. `python -m pytest -q backend/gui_test/tests/test_catalog_settings.py tests/test_catalog_timeout.py`와 관련 기존 setup/runtime/WindowsRemote/GUI 회귀를 실행한다. 브라우저는 저장·재조회·지연 목록·실패·미연결·모드 변경·오래된 응답과375px을 확인한다. 실제 명령·로그·코드 기준은 [실행 기록](../testing/runs/20261106-catalog-timeout.md)에 기록한다.
4. T-191~193 로컬 시험 PASS와 최종 독립 리뷰 APPROVED다. T-194 회사 공유 폴더/기존 EXE/SSH 인수는 별도 NOT_RUN이다. fixture 성공을 실제 회사 인수로 올리지 않는다.
5. 복원은 검토한 이전 코드/UI와 백업 설정을 정상 절차로 되돌린다. 전용 JSON은 이전 코드가 사용하지 않으므로 보존할 수 있다. runtime DB·UNKNOWN·실패 이력을 삭제하지 않는다.

**승인된 기존 `dist` ZIP/EXE를 재빌드하거나 교체하지 않는다.** 대시보드 호출자 수정은 기존 서버와 호환되지만 이전 EXE 자체 메뉴4의5초 동작·진행 표시는 그대로다. 새 마법사 기능을 쓰려면 갱신된 소스 마법사를 사용한다. 향후 새 EXE는 별도 빌드·검증·승인 대상이며 `source_snapshot_v1` 지원이나 새 binary 검증을 이 변경으로 주장하지 않는다.
