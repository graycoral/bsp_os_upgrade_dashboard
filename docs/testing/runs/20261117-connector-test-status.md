# 2026-11-17 보드 커넥터 TC 목록·상태 조회

RQ-73 / D-79 / T-280~281. 로컬 소스 구현과 모의 검증이며 실제 Linux·Windows·회사 장비 인수와 구분한다. 독립 Claude 리뷰는 **NOT_REVIEWED**다. 이번 세션은 커밋·푸시·운영 서비스 재시작·실제 TC/장비 실행을 수행하지 않았다.

## 기준과 범위

시작 당시 HEAD는 `f0fd97c88548de4896aac350444336293a768e8f`, 검증 중 공유 작업 공간의 별도 세션에서 기존 포트/클릭 실행 작업이 main에 반영되었다. 이번 TC 목록 변경은 working tree다. 기존 timeout/Mock/설치·강제 종료 등의 다른 변경을 보존한다. 검증 시 HEAD: `62d6b52da93c3bc64f694fd89e66033bc173914e`.

코드 식별: `workingtree:sha256:626f5682b42ef00fb987402f4748e60aa2a828ad805f5e0352acac511d8957f9`.
시험 식별: `workingtree:sha256:f6ba894cae4efa02f95c12697539526dd1fcadc7b8c7ffc9dbfe4941f5854aad`.
해시는 로컬 `verified-files.json`의 backend GUI Test 코드와 해당 UI/시험 파일 집합 기준이며 저장소 전체 릴리스 hash가 아니다.

## 구현

- `connector/test_status.py`: 공통 TC 경로 우선·적용된 frozen source fallback, 안전한 파일 읽기/공통 discovery, 소스별 캐시, 서버 Run/runner/전체 snapshot identity 대조, 보드별 최신 상태 조회.
- `connector/api.py`, `supervisor.py`: 읽기 전용 GET과 기존 Windows polling, 실패한 상태 수신의 stale 보존. 미러는 Windows 판정을 신뢰하지 않고 서버에서 직접 조회한다.
- 웹 공통 view/CSS, Qt GUI, Agent Monitor `ConnectorMirror`: 전체 스크립트와 선택 보드 상태. TC 선택·시작·중지·재실행·제어권 취득 UI 없음. preview는 격리된 모의 상태다.
- `core/discovery.py`는 목록 생성 부분만 `discover_contents`로 재사용한다. 기존 제한시간 WIP를 유지하고 CRLF의 텍스트 hash와 원본 bytes의 snapshot hash를 구분한다.
- DB 이전·새 제품 의존성 없음. 폴더 내용 재확인은10초 캐시, source/metadata 변경은 다음 조회에서 갱신한다. 판정은 기존 `Run.results`이며 반복·재시도 결과를 자체 계산하지 않는다.

## 검증

원본 로그·상세 결과·스크린샷·도구는 `.local-reports/20261117-connector-test-status/` 아래 로컬 전용이며 Git에 포함하지 않는다.

| 실행 | 결과 | 근거 |
|---|---|---|
| Python13개 파일, 기존 커넥터/API/미러·discovery/source·전송·플러그인 snapshot/pipeline·패키지 | PASS · 325개, 종료0 | `PATH=/usr/bin:$PATH .venv/bin/python -m pytest <verified-files.json의 Python 시험13개> -q`; `python-final-2.log` |
| 커넥터 웹 화면(macOS 모의) · 조회 전용 TC 목록 포함 | PASS · 18개, 종료0 | `scripts/test_connector_browser.py`; `browser-web-1.log` |
| Agent Monitor 미러 브라우저 | PASS · 16개, 종료0 | `npx playwright test connector-mirror.spec.ts --reporter=line`; `browser-mirror-1.log` |
| 양쪽 UI TypeScript/Vite build | PASS · 종료0 | `bash scripts/build-ui.sh all --skip-install`; `build-2.log` |
| 문서·링크/ID 및 diff 공백 | PASS · 종료0 | `docs/testing/validate_docs.py`, `git diff --check`; `docs-2.log`, `docs-final.log` |
| T-281 실제 회사·Windows Python3.13·SSH·TC·장비 상태 전달 | NOT_RUN | 로컬 모의 시험으로 대체하지 않음 |

모의 시험은 제어/예약/DB 쓰기 없음, 전체 스크립트·보드 전환, source/runner/Mock 격리, 경로 교체·빈 폴더, CRLF, 의존 파일 변경, 반복 판정·UNKNOWN/취소, source 전환 중 조회·단절, GET polling과 쓰기 거부, Qt 읽기 전용, 텍스트 삽입 안전성을 포함한다. 모의 화면 스크린샷도 직접 확인했다.

## 초기 실패 보존

- 최초 API 시험의 쓰기 거부 예상값405에 대해 실제 인증 경계가403을 반환했다(100 PASS/1 FAIL). 제품 보안을 유지하고 기존403 계약을 검증하도록 시험을 수정했다. `python-1.log` 보존.
- 확장 시험 최초 Git2.15.1의 `git init -b` 미지원으로 기존 Git discovery 시험1개 실패(254 PASS). `/usr/bin/git` 2.54.0을 시험 PATH에 적용한 후 동일 회귀를 통과했다. `python-3.log`, `python-4.log` 보존.
- 최초 build는 PATH의 Node 부재로 실패했고, 번들 Node24.22.1에서는 macOS Team ID native module 서명 경계로 실패했다. 공식 Node22.23.5 darwin-arm64를 SHASUMS256와 대조해 로컬 도구 폴더에 준비한 후 기존 설치 의존성으로 양 UI build를 통과했다. lock/dependency 파일은 변경하지 않았다. `build.log`, `dashboard-build.log`, `build-2.log` 보존.
- 문서 초안 검사 중 미작성 실행 기록 링크와 T-280~281 결과 행 부재가 확인되었다. 최종 문서·결과 기록 후 재검사했다. `docs-1.log` 보존.

## 남은 범위

실제 회사 경로의 대규모 목록 성능·SSH 지연/끊김·Windows3.13·보드별 실제 TC 상태·회사 인수 및 독립 Claude 리뷰는 미실행이다. 새 배포 pin·ZIP/EXE 생성·게시·회사 설정 변경은 수행하지 않았다.
