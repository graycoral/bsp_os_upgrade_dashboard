# 2026-11-22 복사형 전달 빌드·패키지·복구 검증

최종 검증 대상은 `8abe9262716cbcfc287a535094f4fbd940601113`의 깨끗한 `porting/copy-ready-20261122`다. macOS arm64 호스트에서 Python 3.11.7 x86_64 로컬 venv를 사용했다. 패키지 요구사항의 고정 의존성은 이 환경과 일치했다. UI 생산 도구는 Node 22.23.2 arm64와 Google Chrome 157.0.8103.79다. 회사 Linux/Windows 배포는 별도다. 원본 로그 경로 `.local-reports/`는 로컬 보존용이며 Git에 포함되지 않는다.

| 검사 | 결과 및 로그 |
|---|---|
| `bash scripts/build-ui.sh all` | PASS. 각 lock 기반 npm ci, tsc 및 Vite 성공. Dashboard `apps/web/dist`, Standalone `apps/gui-test/static` 각각 index·JS·CSS 생성. `20261122-copy-ready-pinned/build-all.log`. |
| `python -B apps/agent-monitor/plugin.py export --output "$PACKAGE"`와 독립 바이트 대조 | PASS. 원본 Git 소스 499개, 사전 빌드 6개 및 outer 등록 508개 대조. `20261122-copy-ready-pinned/export.log`, `manifest-sha256.txt`, `20261122-coordinator/byte-check-8abe926.json`. |
| 원본 밖 복사 디렉터리와 Node/npm 없는 PATH에서 `python -I -S plugin.py help`, `verify "$COPY" --pristine`, `export` 및 재검증 | PASS. 반복 검증과 안전한 재-export에서 원본 pin·manifest 유지. 사용자 지정 runtime의 최초 상태 조회는 `STOPPED`/`NOT_INSTALLED`를 반환하고 home/runtime을 생성하지 않는다. 지원 설정 export 및 직결 file sync 거부를 확인했다. `20261122-copy-ready-pinned/isolated-{help,verify,reexport,no-service,settings}.log`. |
| 복사본 Dashboard/Standalone GET과 Chromium, Windows 웹 모의 미리보기 | PASS. 두 index 및 참조 자산 각 3개를 HTTP 바이트 대조. Chromium에서 대시보드/커넥터 탭, 독립 GUI Test, Windows 웹 mock TC 5줄 렌더링. Chrome 구동은 공급자 시험 harness에서 수행했다. Windows BAT/CMD·TC/웹 모듈·lock의 해시는 동일 source manifest와 일치. 로그 `20261122-copy-ready-pinned/isolated-ui-smoke.log`. |
| 두 로컬 Manager/API/Worker, 기존 포트 유지, 백업 및 롤백 | PASS. macOS에서 Linux 측 Manager와 runtime 스키마를 사용해 임시 home/runtime 두 쌍을 검증. 구 READY의 `UPDATE_REQUIRED`, 별도 서비스의 `MATCHED`, Linux 측 스키마의 SQLite 백업 SHA 및 `PRAGMA integrity_check=ok`, 동일 포트 구→신 restart, 활성 신버전 경로·receipt·health 일치, rollback 후 같은 포트 구버전 재기동 및 별도 owner/설정 보존을 확인했다. 기존 환경을 재사용했으며 현지 오프라인 설치는 미실행. 로그 `20261122-copy-ready-pinned/isolated-managed-smoke.log`. |
| 선택한 Python 회귀 | 234 PASS, 종료 코드 0. A01~A05, T-284, 설정 CAS(T-283/302) 및 설치/복구/직결 회귀. `20261122-copy-ready-pinned/pytest.log`. |
| 독립 리뷰 | Astra 초기 4건의 근거·수정 재검토 승인. 동일 포트 POSIX 보정 추가 검토에서 차단 이슈 없음. 최종 pin의 제품 코드는 직전 pin과 동일하며 lifecycle 시험용 소켓에 실제 API를 반영했다. |
| 문서 검사 | PASS. `python docs/testing/validate_docs.py`, `git diff --check` 및 `20261122-copy-ready-pinned/docs.log`. |
| 회사·실물 | NOT_RUN. 회사 Linux/Windows 신규 오프라인 환경·wheel, slash/SSO/API 권한, T-286/T-290/T-305, Bedrock·Jira·실제 BSP/장비 실행. |

선택 회귀 실행 명령은 다음과 같다. 기존 repo 이력을 별도 실패 기록으로 보존했다.

```bash
PYTHONDONTWRITEBYTECODE=1 "$TEST_PY" -m pytest -p no:cacheprovider -ra -q \
  tests/test_agent_monitor_delivery.py tests/test_plugin_delivery.py \
  tests/test_agent_monitor_manager.py tests/test_agent_monitor_recovery.py \
  tests/test_agent_monitor_lifecycle.py tests/test_plugin_runtime.py tests/test_direct_connector_unit*.py
```

## 실패·재시험

- 원본 02 archive와 기준 빌드로 수행한 기존 export/verify는 PASS다. 검증 출처가 Git 없는 archive인 이 시험용 release의 원본 SHA는 비어 있다. `20261122-copy-ready-baseline/archive.*/{export,verify}.log`.
- 초기 10건 FAIL은 설치 검증 함수 시그니처 변경을 테스트 더블에 반영하지 않아 발생했다. 다음 15건 FAIL은 자산 경로 확인이 정상 상대 URL의 `./`를 거부한 결과다. manifest 경로 검사 전에 HTML 자산 URL의 선행 `./`를 정규화하고 재시험에서 201 PASS를 확인했다. `20261122-copy-ready-dev1/pytest.log`, `20261122-copy-ready-dev2/pytest.log`, `20261122-copy-ready-dev3/pytest.log`.
- `b89d4d5`의 실제 같은 포트 전환은 종료 직후 TIME_WAIT를 live listener와 같이 처리해 실패했다. `caba8de`의 POSIX `SO_REUSEADDR` 보정은 TIME_WAIT 회복과 실 listener 거부를 실소켓 시험으로 확인했다. 해당 pin의 실제 같은 포트 restart/rollback은 PASS다. `caba8de`의 별도 동시 실행 Python 회귀에서 lifecycle 더블에 `setsockopt`가 빠진 1건 및 `IMAGE_SPACE` 조건 7건이 실패했다. 더블 보정 후 최종 pin에서 독립하여 재실행했다. `20261122-copy-ready-delivery/isolated-managed-smoke.log`, `20261122-copy-ready-accepted/{isolated-managed-smoke,pytest}.log`.
- 중간 전체 Python `tests backend/gui_test/tests`는 2,234 PASS, 29 FAIL, 37 SKIP. 실패한 29개 ID는 02 `0061754`와 제품 코드 pin `caba8de`에서 동일 환경·동일 ID로 각각 29 FAIL을 재현했다. macOS에 없는 Linux `/proc` 및 기본 경로의 Git 2.15.1 옵션 등이 영향을 줬다. Git 단일 시험은 `PATH=/usr/bin:$PATH`의 Apple Git 2.54.0에서 PASS. 전체 Python 회귀는 FAIL이다. `20261122-copy-ready-final/pytest.log`, `20261122-coordinator/{baseline-29,final-29,final-git254}.log`.
- 별도 Chromium 전체 범위는 PASS로 올리지 않았다. 중간 static settings/mirror 배치 17 PASS/14 FAIL이고, 02 archive에서도 mirror 2 PASS/같은 14 FAIL이었다. 해당 fixture는 현재 direct/status API를 예상 요청에 등록하지 않았다. 중간 Windows connector browser 배치는 14 PASS/4 FAIL/1 미실행이었으며 테스트 중 npm ci로 worker 모듈을 찾지 못한 종료도 기록됐다. 최종 복사본 Chromium 스모크는 별도 명령과 위 직접 근거에 한정한다. `20261122-copy-ready-dev3/{settings,connector}-chromium.log`, `20261122-copy-ready-baseline/archive.*/source/.local-reports/mirror-baseline.log`.
