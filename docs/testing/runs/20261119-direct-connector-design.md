# 2026-11-19 · 직결 보드 커넥터 · 자율 실행 · 양방향 진단 상세 설계 기록

- 구분: **설계 문서 작성 전용 (`DESIGN_ONLY` / `IMPLEMENTATION_NOT_STARTED` / `NOT_REVIEWED`)**
- 제품 코드 변경: 없음 (후속 Hydrogen 구현 세션에서 Unit 1~6 진행, 별도 Hydrogen 세션에서 독립 리뷰 진행 예정)
- 대상 설계 문서: [직결 보드 커넥터 상세 설계](../../design/DIRECT_CONNECTOR_ARCHITECTURE.md)

## 반영된 설계 문서 변경

1. [직결 보드 커넥터 상세 설계](../../design/DIRECT_CONNECTOR_ARCHITECTURE.md) 신규 작성 (기준선 `main` `14e6402`)
   - Q1 직결: Windows `Host` 준비 + `SSH -R`(기본 `127.0.0.1:8771`) `LogLevel=VERBOSE` 실제 바인드 확인 시 즉시 `CONNECTED` 판정 (`0.1s` sleep 오판 제거, `launch.py`/`emergency.py` `Host`·`SSH` 수명 분리, 선택 `-L` 비차단 격리, `^[a-f0-9]{32}$` 기반 `bootstrap-v2` 및 `shared_control.py` 호환)
   - Q2 자율 실행: 기존 `source_snapshots`/`installer_snapshots` 보안 검증기 기반 청크 재개 동기화 → `POST /v1/connector-runs`(Single/Dual `Connection`, `CommandTemplate`·`FlashProfile`, `D-48` 배타 공유) → `ConnectorRunExecutor` 순차 실행(10초 폴링 리스 제거, `parse_result`·`ConsoleHub` 감시, `FLASHING` 안전 경계 정지) → `fail-stop-analysis-v1` 단일 SQLite 원자적 래치 및 재연결 분석 핸드오프(`claim`/`HOLD`/`RETRY` 동일 Run·`REPREPARE` 자식 Run) → `UNKNOWN` 크래시 복구·`retention.py` 보호·바이트 오프셋 증분 로그 및 `executions.db` DDL 정의
   - Q3 Agent Monitor: `127.0.0.1:8771` 직접 조회 프록시 + `connector-registry.db` 주기/조회 오프라인 캐시, CSRF/스코프 미들웨어, 설정/`pause`/`cancel`/`reconcile`/`putty`/`restart` 허용 및 `analysis_latched` 중 임의 `resume` 차단
   - 양방향 연결 진단: 양측 확인 트리거(`diagnose` & Windows `verify-connection`), Windows 사전점검(키 ACL 포함)+`stderr` 분류 + Linux `/proc/net/tcp`/`tcp6`·`uid=0` `sshd` 구분·타 포트 `sshd`·`.ssh` 읽기 전용 감사 + `POST /v1/peer/hello`·`GET /v1/diagnostics/connection` 상호 불일치 통지
   - 공통 저장소·브리지·CLI 디커플링: Linux `<runtime>/shared-settings.db`(`DELETE`+`flock`+CAS) 및 `recovery.py`(`reset`/`doctor`/`adopt`) 호환, TC 카탈로그 투영(`PUT /v1/tc-catalog-projection`), DPAPI `manager-bridge` 토큰 기반 재부착 가능 `Host↔Manager` 브리지, `manage.py prepare-env` 및 `--connector-port`/`--port` 충돌 차단
2. 문서 지도·계획·상호참조 갱신:
   - [문서 지도](../../README.md)
   - [구현 계획](../../implementation/IMPLEMENTATION_PLAN.md)
   - [작업 진행 기록](../../implementation/WORK_STATUS.md)
   - [보드 커넥터 계약](../../design/BOARD_CONNECTOR_CONTRACT.md)
   - [보드 커넥터 미러](../../design/BOARD_CONNECTOR_MIRROR.md)
   - [플러그인 연동 안내](../../agents/PLUGIN_CONTROL_API.md)

## 검증 결과

- 문서 정합성 검사: `.venv/bin/python docs/testing/validate_docs.py` — **`PASS`** (`relative_links_checked: 2076`, `requirements: 76`, `test_cases: 289`, `not_run: 89`, `errors: []`)
- 공백/포맷 검사: `git diff --check` — **`PASS`** (exit code `0`)
- 제품 코드 변경 검사: 제품 소스(`.py`/`.ts`/`.tsx`/`.mjs`/`.sh`) 미변경 (설계·문서 전용)
- 설계 수용 시험(`DCA-01` ~ `DCA-15`): **`NOT_RUN`** (구현 착수 전)
- 독립 리뷰: **`NOT_REVIEWED`** (구현 후 별도 세션 예정)
