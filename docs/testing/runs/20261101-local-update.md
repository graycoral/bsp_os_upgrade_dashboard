# 2026-11-01 로컬 main 업데이트

상태: SOURCE_UPDATED / OFFLINE_TESTED / SERVER_AND_BROWSER_BLOCKED.

## 변경과 데이터

- 대상: graycoral/bsp_os_upgrade_dashboard main `2e2d24b74d8464d432e118fd4a80646d6d7a6c9a`. Git 이력 없는 소스 사본이다. 원격 파일 238개 중 234개를 Git blob SHA-1·크기로 검증했다. 실행 코드와 텍스트 문서는 모두 포함한다.
- 과거 GUI UX 스크린샷 4개는 GitHub 도구가 UTF-8만 지원하고 브라우저 ZIP 다운로드도 차단되어 미포함이다. 해당 과거 기록의 링크는 고정 커밋의 원본으로 연결했다. 완전한 파일 동기화로 표현하지 않는다.
- 로컬 변경: `run.sh`를 최신 시작 스크립트에 연결, 기본 포트 8766을 시작·serve·Windows 터널과 README에 반영, `.local-update/`를 Git 제외. API와 DB 스키마는 최신 원본 그대로다. 사용자 요청대로 로그인 없이 사용한다.
- 기존 코드·설정·DB·시험 이력·산출물은 `.local-update/20261101T052210Z/backup`과 `original`에 보존했다. SQLite backup API로 `legacy-consistent.sqlite3`를 생성했다. 기존 worker 잠금이 비어 있음을 확인했다.
- 기존 작업 1개, 모듈 5개, 시도·결과·산출물 각각 5개를 복원 사본에서 확인하고 무결성 검사와 151개 백업 파일 해시를 검증했다. 새 앱은 `.runtime`에 새 DB를 만들며 구 DB를 연결하지 않는다.

## 시험과 환경

| 검증 | 결과 | 근거 |
|---|---|---|
| Python 전체 | PASS, 284개 | [최종 로그](20261101-local-update-evidence/pytest-final.log), [JUnit](20261101-local-update-evidence/pytest-final.xml.gz) |
| 최초 Python | FAIL, 281 PASS / 3 FAIL | [최초 로그](20261101-local-update-evidence/pytest-initial.log) |
| 실패 3개 재시험 | PASS | [재시험 로그](20261101-local-update-evidence/pytest-targeted.log) |
| Dashboard 빌드 | PASS | [빌드 로그](20261101-local-update-evidence/build-dashboard.log) |
| GUI Test 단독 빌드 | PASS | [빌드 로그](20261101-local-update-evidence/build-gui.log) |
| 백업·복원 | PASS | [복원 검증](20261101-local-update-evidence/restore-verification.json) |
| 새 DB·내부 API smoke | PASS | [기록](20261101-local-update-evidence/local-api-smoke.json): 빈 작업 목록, UI·health·jobs·GUI capabilities HTTP 200. TestClient 내부 호출이며 실제 서버 접속 아님 |
| 문서 검사 | PASS | [기록](20261101-local-update-evidence/docs-check.json). 미동기화 스크린샷은 원본 커밋 링크로 표시 |
| 브라우저 E2E | BLOCKED | [실행 로그](20261101-local-update-evidence/browser-initial.log): localhost:18766 bind PermissionError |
| 서비스 시작·8766 실접속 | BLOCKED | 셸의 포트 바인딩 제한. 승인된 실행 명령도 자동 승인 정책에서 sandbox_approval=false로 거부됨 |
| 실제 Linux·모델·BSP·보드·Jira | NOT_RUN | 이번 업데이트 범위에 실제 운영 실행 없음 |

Python 3.11.7. 최초 Git 2.15.1은 `git init -b` 미지원이므로 Apple Git 2.54.0을 PATH로 선택해 원 시험을 수정 없이 통과했다. ReportLab 누락으로 실패한 PDF 시험은 PyPI 공식 ReportLab 4.4.3·Pillow 13.0.0 wheel 설치 후 통과했다. PySerial 3.5는 로컬 설치본을 재사용했다. 코드 결함으로 확인되지 않은 환경 문제이며 시험 기대값·실패 이력을 변경하지 않았다.

Node 22.23.2. 네트워크 설치 제한 때문에 기존 설치본을 복사하고 잠금 파일과 설치 패키지 버전을 대조했다(Python 루트 의존성 전부 일치, npm 설치 패키지 73개 일치). GUI 패키징용 전체 lock 설치는 완료하지 못했다. `pip check`에는 아직 `charset-normalizer` 누락이 남아 있으며, 공식 3.5.2 wheel 다운로드가 시간 초과되었다. PDF를 포함한 현재 자동 시험 통과가 전체 설치 검증 완료를 뜻하지 않는다.

전체 시험 명령: `PATH=/usr/bin:/bin:/usr/local/bin .venv/bin/python -m pytest -q`. 브라우저는 `BSP_E2E_PORT=18766 .venv/bin/python scripts/test_e2e.py`, 별도 단독 GUI 시험은 `.venv/bin/python -m gui_test.demo.browser_e2e`다. 단독 runner는 빈 임시 포트를 자동 선택한다. Node PATH·Playwright 브라우저 준비가 필요하다.

## 후속 실행과 복원

일반 터미널에서 프로젝트 폴더로 이동하여 `.venv/bin/python -m pip install -r gui_test/requirements.lock`으로 누락 의존성을 설치하고 `.venv/bin/python -m pip check`를 확인한다. 이후 `bash run.sh`를 실행하고 `http://127.0.0.1:8766`에서 확인한다. 브라우저 시험과 서비스 접속이 확인되기 전 운영 baseline은 NONE이다.

복원 시 해당 프로젝트의 새 API·worker를 먼저 종료한다. 새 코드와 `.runtime`을 별도로 보존하고 `original`의 파일을 원래 위치로 복원한다. `legacy-consistent.sqlite3`를 기존 `runtime/dashboard.sqlite3`로 사용하고 과거 WAL/SHM은 별도 보관한다. 백업 manifest 및 산출물 해시를 확인한 뒤 구 `run.sh`를 사용한다. 자동 역 migration이나 원본 삭제는 하지 않는다.

GitHub 게시·커밋·PR·실제 Claude 독립 검토는 수행하지 않았다. 과거 PASS는 원 기록에 보존하며 현재 전체 인수로 재사용하지 않는다.

## 후속 재실행 확인

사용자 재실행 요청으로 `bash run.sh`를 다시 실행했다. Uvicorn이 127.0.0.1:8766에서 시작했고 Chrome 실접속에서 OS 업그레이드 대시보드·API 연결됨·빈 작업 목록·무로그인을 확인했다. 서비스 시작과 기본 브라우저 접속의 이전 BLOCKED는 해소됐다. 셸 curl은 별도 접근 제한으로 실패했으며 성공 근거는 실제 Chrome 화면이다. 전체 E2E·누락 의존성·과거 스크린샷의 제약은 그대로다. 서버와 사용자 확인용 탭은 유지했다.

게시 준비(2026-11-02): 대용량 JUnit 원본은 내용 변경 없이 gzip으로 공개한다. 로컬 원본과 실패 이력은 유지한다.
