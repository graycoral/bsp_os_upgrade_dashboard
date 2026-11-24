# PORT-018 · 회사 CLI 인자, 읽기 전용 감시와 퓨징 확인

회사 검토 기준은 `9f91123`, 직전 회사 전달본은 `6e65521`이다. PORT-017을 적용한 환경에서 Linux 플러그인과 Windows Host를 같은 릴리스로 갱신한다. 원본 커밋은 패키지 안 `agent-monitor/AGENT_MONITOR_SOURCE.json`의 `source_head`에서 확인한다. 회사의 실제 적용 커밋과 시험 결과는 현지 `APPLIED.md`에 기록한다.

### 실행 전 확인

1. 전역 옵션은 명령 앞에 전체 이름으로 쓴다. 약어나 명령 뒤의 전역 옵션은 환경을 준비하기 전에 종료 코드 2로 거부한다.
2. 사내 역방향 커넥터 상태만 읽을 때는 다음 첫 번째 명령을 사용한다. `--read-only`는 Windows에 보내는 HTTP 요청을 GET으로 제한하며, `--no-provision`은 준비된 Python 가상환경만 사용한다. 가상환경을 찾지 못하면 stdout은 비우고 stderr에 `NOT_PROVISIONED`를 출력한 뒤 코드 6으로 종료한다. 일반 감시가 이미 실행 중이면 그 프로세스의 옵션은 유지되므로 회사 supervisor에는 첫 번째 명령 전체를 자식 프로세스로 등록한다. 기본 예제 훅은 일반 감시용이다.
3. 미리 이번 빌드의 Linux 설치 BAT와 플래시 프로파일을 설정하거나 prepare에 `--installer`와 `--flash-profile`을 전달한다. 두 번째 명령의 출력과 생성 파일에서 `flash_confirmation`을 읽는다. `installer_bat`에는 스냅샷 안의 BAT 상대 경로·바이트 크기·SHA-256이 있다. `images`는 동일한 스냅샷의 BAT 이외 모든 파일을 상대 경로별 크기·SHA-256에 매핑한다. 보조 파일도 포함한다. `target_boards`에는 실행에 고정한 A/B 보드의 Host·보드 ID·COM 정보가 있다. 회사 빌드 manifest 및 대상 보드와 대조한 뒤에만 세 번째 명령을 호출한다. prepare는 소스와 이미지를 전송할 수 있고 send는 실제 퓨징을 접수한다. send 응답에도 같은 확인 정보가 있다.

```bash
python3 plugin.py --home "$MONITOR_HOME" --project "$PROJECT" connect --watch --read-only --no-provision --json
python3 plugin.py --project "$PROJECT" test prepare --file "$OUT/prepared.json" --build "$BUILD" --flash
python3 plugin.py --project "$PROJECT" test send --file "$OUT/prepared.json" --flash
python3 plugin.py --project "$PROJECT" test runs
```

### 프로젝트와 호환성

새 Run은 기존 `request_json`의 `origin.project`에 프로젝트를 저장한다. `GET /v1/connector-runs?project=LABEL&limit=20`은 정확히 일치하는 Run만 골라 최신순 개수 제한을 적용한다. 레이블은 URL 인코딩한다. 프로젝트를 생략한 HTTP 조회에는 과거 무라벨 Run도 포함된다. 명시적으로 `--project`를 전달한 CLI는 다른 프로젝트나 무라벨 Run을 해당 프로젝트의 결과로 표시하지 않는다. 필터는 조회 범위를 정한다. 접근 권한·장비 점유는 기존 Host 정책을 따른다. DB 스키마 이전은 필요하지 않다. 구형 Windows Host는 새 Run 본문의 프로젝트 필드를 거부할 수 있으므로 실행 전 Host 버전을 확인한다.

기존에 준비한 퓨징 파일은 원래 요청 본문·키를 보존한다. 새 클라이언트는 확인 정보가 빠진 경우 원래 Windows Host의 설치 스냅샷 manifest를 조회하고 ID와 대조한다. 스냅샷 또는 manifest 지원이 없어 확인하지 못하면 전송을 중단한다. 이미 접수되었을 수 있는 Run은 저장한 Run ID로 조회한다.

### 기계용 계약과 전달 검증

- [CLI 계약 JSON](../../contracts/plugin-cli-v1.json)은 전역·명령 옵션, 종료 코드, 읽기·Windows 쓰기·하드웨어·네트워크 등 가능한 부작용을 제공한다. [동작 변경 이력](../../contracts/plugin-behavior-changes.json)은 릴리스별 의미 변경을 기록한다. 릴리스 생성자는 각 버전의 변경을 추가한다. `release-evidence`는 이전·현재 release ID와 변경 내역을 `BEHAVIOR_CHANGES.json`에 기록한다. 알려진 비교 기준이 없으면 `baseline_matched=false`와 전체 기록을 제공한다.
- `python3 plugin.py export --output "$NEW_PACKAGE" --without-agent-instructions`로 회사용 패키지를 만든다. 기본 export에는 기존 지침이 포함된다. 제외 옵션은 대소문자를 구분하지 않고 AGENTS.md·CLAUDE.md와 .claude/agents/ 트리를 manifest 생성 전에 제외한다. 복구에는 이전 패키지와 동일한 runtime을 사용한다.
- 배포 담당자는 아래처럼 릴리스 증거에 서명한다. 회사 수신자는 독립적으로 신뢰한 원본 체크아웃의 검증 스크립트와 회사가 별도 배포한 allowed_signers 파일을 사용한다. allowed_signers의 한 줄 형식은 `회사릴리스ID ssh-ed25519 공개키`다. 검증 시 비밀키는 필요하지 않다. 서명·서명자·릴리스 해시·패키지 바이트·변경표 중 하나라도 다르면 실패한다.

```bash
python3 plugin.py release-evidence "$PRIOR_PACKAGE" "$NEW_PACKAGE" --output "$NEW_EVIDENCE_DIR"
ssh-keygen -Y sign -f "$RELEASE_SIGNING_KEY" -n bsp-plugin-release-v1 "$NEW_EVIDENCE_DIR/RELEASE_EVIDENCE.json"
python3 -I "$TRUSTED_CHECKOUT/scripts/verify_signed_plugin.py" "$PRIOR_PACKAGE" "$NEW_PACKAGE" "$NEW_EVIDENCE_DIR" --signature "$SIGNATURE_FROM_RELEASE_OWNER" --allowed-signers "$COMPANY_ALLOWED_SIGNERS" --identity "$RELEASE_IDENTITY"
```

### 변경 위치와 검증

Linux 진입점은 `apps/agent-monitor/plugin.py`, 인자·명령·감시는 `backend/gui_test/standalone/{plugin_parser,plugin_commands,module_commands,direct_connector_client}.py`와 `backend/gui_test/core/connector_diagnostics.py`다. Host의 모델·목록·manifest 조회는 `backend/gui_test/execution/{connector_runs,host}.py`에 있다. 전달 파일 선택과 증거 생성은 `apps/agent-monitor/{delivery,plugin_delivery}.py`에 있다. 회사 코드가 이 접점을 자체 구현했다면 해당 필드와 판정 규칙을 이식한다.

```bash
python -m pytest -q tests/test_connector_observation.py tests/test_connector_run_replay.py tests/test_company_connector_delivery.py
```

Windows 실장비 퓨징과 회사 운영 서명키 인수는 회사 환경에서 별도로 수행한다.
