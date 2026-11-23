# 원본 감사 인수인계

| 필드 | 내용 |
|---|---|
| source_repo/source_commit | graycoral/bsp_os_upgrade_dashboard · `457587d3b4b5ecb2526db39b3c420803d85d8874` |
| source_commit | `457587d3b4b5ecb2526db39b3c420803d85d8874` · `git rev-parse HEAD origin/main` 결과 일치, 최초 `git status --short --branch`는 깨끗한 `porting/copy-ready-20261122` |
| target_repo/target_commit | N/A |
| scope | 00 계획 검토, 01 감사 게이트 및 02/03 원본 조치와 04 회사 조사 입력 |
| changes | 이 감사 문서 신규 작성. 제품·DB 변경 NONE |
| package_release | 제품 전달용 NONE. UI 제외 시험용 `ce29893244d4a68c90d6f47efb734ce08dd447938290b759042bcb20b2e04ae5` |
| evidence / execution_evidence | 2026-11-22 Darwin arm64 · Python 3.11.7 · pytest 9.1.1. 선정 시험 18 PASS, 1 SKIPPED. 원본 문서 검사 2,122링크·81요구·304시험·90 NOT_RUN, 오류 0. 명령·로그는 [실행 근거](IMPLEMENTATION_HANDOFF.md#실행-근거) 참조 |
| open_questions / unknowns | 회사 적용 기준·서비스 소유자·인증·wheel 공급원·Windows 장비는 TARGET_UNKNOWN. 회사 적용 담당자가 04에서 확인. 실장비 T-305 NOT_RUN |
| next_task | 02_CODEX_DOC_CLEANUP.md → 03_CODEX_COPY_READY_PACKAGE.md → 회사 내부 04 평가 순서 |

## 계획 검토와 게이트

**00 원본 계획 채택, 01 감사 PASS.** 소유 파일·분류·재현 가능한 누락 및 미검증 범위를 식별했다. 폴더 복사와 최소 host adapter를 유지하고 기존 export/verify를 확장할 수 있다. 01은 코드·설정 또는 이력을 수정하지 않았다. 회사 repo/운영 로그·키를 수집하지 않았다.

| 다음 단계 | 소유와 입력 | 완료 조건 |
|---|---|---|
| 02 원본 문서 정리 (Sol) | [문서 계획](DOC_CLEANUP_PLAN.md), PORT-011/013/014 및 진입점. 제목/anchor·과거 SHA·실패·NOT_RUN 보존 | 변경 목록·사유·고정 상태·상대 링크/앵커 검사·git diff --check를 DOC_CLEANUP_RESULT에 기록. 코드·DB 수정 없음 |
| 03 원본 패키지 (Sol) | [원본 감사](PORTABILITY_AUDIT.md) A01~05, [의존성](DEPENDENCY_MATRIX.md). `delivery.py`, `plugin_delivery.py`, `plugin.py`, 기존 관리/시험 진입점 | 실제 빌드한 두 UI·Windows closure를 포함해 새 디렉터리 export/verify, 복사본 import·HTTP 자산·release/프로세스 검증, 회귀/롤백. 산출물과 결과/회사 smoke/rollback 문서. 차단된 항목과 실제 가용 수준 기록 |
| 04 회사 현황 검토 (Opus/Bedrock) | 03에서 확인한 파일 manifest·release·source pin과 회사 현지 지침/COMPANY_MAP/APPLIED | 회사 현재 commit/부분 이식·단일 owner·기존 설정·역할/ACL·실행 데이터와 호환/복구·충돌을 현지에서 대조. 실험실 장비 T-305 별도 |
| 05·06 회사 적용/독립 리뷰 | 회사 계획 승인 범위로 Sonnet 이식, 새 Opus 세션 리뷰 | 같은 소스에 대한 실제 회사 smoke·회귀·복구·별도 리뷰가 있을 때 현지 상태 갱신 |

## 실행 근거

최초 `git rev-parse HEAD origin/main`은 양쪽 모두 문서 머리의 SHA였고 `git status --short --branch`는 브랜치명만 출력했다. `git symbolic-ref --short HEAD`로 브랜치를 확인했다. 기준 자료는 pinned tree와 `docs/testing/runs/20261119-direct-connector-implementation.md`이며, 이 문서의 과거 452+212 PASS를 현재 시험 횟수에 더하지 않았다.

원본 pin에서 테스트 의존성이 준비된 Python 3.11.7 venv를 선택했다. 아래 `$TEST_PY`는 해당 venv의 Python, `$AUDIT_TMP`는 저장소 밖에 만든 고유 임시 폴더다. 실행 식별자 `bsp-stage01.gppZYQq0`, 로그 `$AUDIT_TMP/pytest.log`. bytecode와 pytest 저장소 캐시는 생성하지 않았다.

```bash
PYTHONDONTWRITEBYTECODE=1 "$TEST_PY" -m pytest -p no:cacheprovider \
  --basetemp="$AUDIT_TMP/tests" -q \
  tests/test_agent_monitor_delivery.py tests/test_plugin_delivery.py \
  tests/test_direct_connector_unit1.py::test_shared_settings_store_migration_and_cas_and_tofu \
  tests/test_agent_monitor_recovery.py::test_sqlite_backup_copies_committed_wal_without_checkpointing_source \
  tests/test_agent_monitor_recovery.py::test_rollback_checks_environment_and_preserves_runtime_and_previous
python3 docs/testing/validate_docs.py
```

| 검사 | 관측 결과 | 경계 |
|---|---|---|
| 위 pytest | exit 0 · 18 passed, 1 skipped in 3.43s | `test_agent_monitor_delivery.py:99`는 이 워크트리에 사전 빌드 UI가 없어 skip. full release 검사 03 필요 |
| 실제 테스트용 한글 경로에서 헤드리스 export·복사본 help/verify·import/MockConnector TC·재-export | `tests/test_plugin_delivery.py:22`~71 PASS. 첫 소스 manifest 492파일·pin 일치, 두 번째 492파일·동일 release·`source_head=null`, 모두 `include_ui=false` | CLI 기능 closure의 일부. A02에 SHA 계승 필요 |
| 기본 UI 수집의 누락 확인 | 임시 폴더에 `apps/web/dist/index.html`과 그 안에 없는 JS를 가리키는 script만 생성 → `delivery.source_files(temp,include_ui=True)`의 반환 목록이 해당 index 1개. 별도 GUI Test static도 없는 상태 | A01 확인, full 전달본 생성 없음 |
| 정적 비교 | `git ls-files`·`rg -n`·`nl -ba`, PORT pin·설정 DB/실행권·관리 API·UI·Windows lock 및 문서 소비자 확인 | 회사 상대 import·API/SSO/port·Windows config는 TARGET_UNKNOWN |
| 원본 문서 검사 | PASS · 2,122 링크·81 RQ·304 시험·90 NOT_RUN, errors=[] | 이 수치는 감사 전 기준. 실장비 T-305 및 회사 재검증 미실행 |

## 03 원본에서 고칠 항목

1. **A01/A05를 기존 전달 코드에서 처리한다.** full 모드는 두 앱의 실제 빌드 output·index 참조 JS/CSS·Windows launcher/필요한 모듈/GUI/lock을 manifest에 포함해야 한다. 정상 복사본에서 `-I` import·static GET을 실행하고 의도적으로 하나가 빠진 테스트용 사본은 거부해야 한다. 소스 backend 기본 static과 전달 트리의 경로가 다른 standalone에는 명시적인 static_dir를 사용한다. headless 옵션과 기존 locked install을 보존한다.
2. **A02는 같은 파일들의 출처를 지킨다.** 검증된 source manifest의 원본 SHA를 재-export·설치 staging까지 계승하고 내용 digest를 별도로 검사한다. 원본 새 export는 clean/pinned source로 만들고 작업 트리 변경이 있으면 SHA와 함께 명시한다. 서로 다른 Git의 vendor 사본과 Git 없는 디렉터리에서 각각 확인한다.
3. **A03은 실행 중 상태 조회로 판정한다.** 새 package release·설치 current.json·service receipt·health managed_release와 실제 설치 경로를 한 번에 대조할 수 있도록 한다. 구 서비스가 READY여도 새 release와의 차이가 드러나야 한다. 두 home/runtime과 paused 예약을 둔 회귀로 기존 서비스의 자동 종료·데이터 교차 사용이 없는지 확인한다.
4. **A04를 잘못된 자동 갱신으로 배포하지 않는다.** 현재 direct dispatcher가 `settings file sync/push`의 방향을 구분하지 않는다. 현행 명령표·생성 README·help에서 미지원 의미를 바로잡고, 지원 복원이 범위라면 기존 bridge를 재사용해 모드별 동작·일방/양방 변경·conflict·사용자 draft 보존 시험을 추가한다. 회사 slash callback이 레거시 session인지 direct인지 현지 확인한다.
5. 포트/데이터/오프라인 조건은 새 패키징 시스템 대신 smoke·rollback 체크로 전달한다. Linux Manager/Worker와 Windows Host가 각각 소유한 DB의 백업·복구 검증, 신규 버전과 보존된 이전 버전 상태, 예약·UNKNOWN 동작을 독립 시험한다.

03 재실행의 기본 명령은 새 외부 경로를 사용한다. `$PACKAGE`는 존재하지 않는 새 경로, `$TEST_PY`는 lock을 설치한 Python이다.

```bash
bash scripts/build-ui.sh all
"$TEST_PY" apps/agent-monitor/plugin.py export --output "$PACKAGE"
"$TEST_PY" -I "$PACKAGE/plugin.py" verify "$PACKAGE"
"$TEST_PY" -I "$PACKAGE/plugin.py" help
"$TEST_PY" -m pytest -q tests/test_agent_monitor_delivery.py tests/test_plugin_delivery.py \
  tests/test_agent_monitor_manager.py tests/test_agent_monitor_recovery.py \
  tests/test_direct_connector_unit1.py tests/test_direct_connector_unit4.py
```

Node/npm을 찾을 수 없는 별도 PATH·원본을 import할 수 없는 cwd에서 양 UI index와 참조 파일, Windows BAT/CMD·connector 웹 모듈을 확인한다. 브라우저/HTTP의 내용과 설치·실행 release까지 증거에 기록한다. Linux·Windows 신규 오프라인 venv는 해당 ABI wheel을 공급자가 확보한 뒤 시험한다.

## 회사 인수인계

회사 플러그인은 vendor 출처/sha와 실제 OS 프로세스의 파일 경로, `--project`, `--home`, `--runtime`, 모니터 포트·direct 포트를 매핑한다. 대시보드가 자체 API/worker를 소유하면 별도 관리자 시작 여부부터 확인한다. 새 source 삭제·기존 파일 덮어쓰기는 회사 변경 이력과 각 소비자의 import/route를 비교한 뒤 판단한다. 회사에 맞출 곳은 slash/activation·모듈 게시 callback·UI host/API 권한·설치 경로 및 환경 값이다. 소스/상태를 원본에 반출하지 않는다.

실제 04~06 작업과 T-290/T-305는 NOT_RUN이다. 원본 계획의 02/03은 위 감사·의존성·문서 계획과 각 지시서의 지정 경로에서 이어간다.
