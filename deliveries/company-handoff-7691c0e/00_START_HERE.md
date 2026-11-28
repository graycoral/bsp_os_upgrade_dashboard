# 회사 플러그인 제한망 운영 · PORT-018

[복사할 패키지](bsp-plugin-copy-ready-20261124-7691c0e/README.md) 폴더 전체를 회사 플러그인 저장소의 새 버전 디렉터리에 둔다. `plugin.py`, `PLUGIN_PACKAGE.json`, `README.md`, `agent-monitor/`가 같은 위치에 있어야 한다. Linux 플러그인과 Windows Host를 이 버전으로 함께 갱신한다. 기존 runtime·SSH 설정·회사 지침은 원래 위치에 유지한다. 이전 버전은 [6e65521 복구 안내](../company-handoff-6e65521/00_START_HERE.md)에서 찾을 수 있다.

### 설치 전 확인

1. 신뢰하는 원본 체크아웃의 검증기로 릴리스 증거를 검사한다. 아래 `TRUSTED_PLUGIN`은 해당 체크아웃의 `apps/agent-monitor/plugin.py` 경로다. `PRIOR`와 `CURRENT`는 두 패키지 루트, `EVIDENCE`는 이 안내서가 있는 폴더다. 기대 SHA-256은 회사의 독립 채널에서 확인한다.
2. 회사 서명 절차를 사용할 때는 [PORT-018의 서명·검증 명령](bsp-plugin-copy-ready-20261124-7691c0e/agent-monitor/docs/porting/PORT-018.md)을 따른다. 회사 배포 담당자의 서명 파일과 별도로 배포한 신뢰 공개키 목록이 필요하다. 이 전달본에 운영키 서명은 포함되어 있지 않다.
3. 사내 SSH/루프백 통신은 허용하며 외부 설치를 금지하는 현장에서는 아래 감시 명령을 supervisor에 등록한다. 종료 코드 6은 현장 승인 경로로 Python 환경을 먼저 준비해야 한다는 뜻이다. 퓨징은 `test prepare --flash`로 만든 파일의 `flash_confirmation`을 회사 빌드 manifest와 대조한 뒤에만 `test send --flash`를 실행한다.

```bash
python3 -IB "$TRUSTED_PLUGIN" verify-evidence "$PRIOR" "$CURRENT" "$EVIDENCE" --sha256 "$EXPECTED_SHA256"
python3 -IB "$CURRENT/plugin.py" verify "$CURRENT" --pristine
python3 -B "$CURRENT/plugin.py" --home "$MONITOR_HOME" --project "$PROJECT" connect --watch --read-only --no-provision --json
```

### 릴리스 식별

| 항목 | 값 |
|---|---|
| 원본 커밋 | `7691c0e679b4afdd5cb25e91a6e6824b0b7631b7` |
| release ID | `126a68c2234b2853377cbc63c23e7dff1c699261ffaad42d49d325a00941a1a3` |
| PLUGIN_PACKAGE.json SHA-256 | `e0a7b76225c8ff239e6fdcf38239a41b577ba22670ab59a879132f133e375b14` |
| RELEASE_EVIDENCE.json SHA-256 | `41317d2509638191c48e3aeaf9455f2c681c4f68426d6b56720984ab025529ea` |

직전 패키지와 비교한 [동작 변경 목록](BEHAVIOR_CHANGES.json), [변경 파일 30개의 전후 해시](MANIFEST_DELTA.tsv), [검증 증거](RELEASE_EVIDENCE.json), [기계용 명령·종료코드·부작용 계약](bsp-plugin-copy-ready-20261124-7691c0e/agent-monitor/contracts/plugin-cli-v1.json)을 제공한다. 패키지에는 AGENTS.md·CLAUDE.md와 .claude/agents/를 제외했다. 두 UI의 소스와 빌드 입력이 이전 릴리스와 같아 검증한 UI 산출물을 재사용했다. 실제 회사 Linux·Windows·장비 퓨징 인수는 현장에서 수행한다.

고정 원본의 회귀 시험 131건과 복사된 패키지의 인수 시험 48건이 통과했다. 동일 릴리스 증거의 SSH 서명 검증은 임시 Ed25519 키로 확인했다. [로컬 검증 기록](../../docs/testing/runs/20261124-plugin-company-cli.md)

### 보드 커넥터 추가 인수 항목

실제 Windows의 **찾아보기** 동작과 Linux 공통 TC 경로가 Windows 목록에 반영되는 시점을 확인한다. 아래 항목은 원본 저장소에서 추가한 현지 확인 절차다. 위 릴리스 식별값은 복사할 고정 패키지에 적용된다. [파일 선택과 TC 경로 확인](../../docs/porting/PORT-009.md#브라우저-파일-선택과-tc-경로-확인)
