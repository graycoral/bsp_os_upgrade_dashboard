# 02 원본 이식 문서 정리 결과

| 필드 | 내용 |
|---|---|
| source_repo/source_commit | graycoral/bsp_os_upgrade_dashboard · 정리 전 `cf78af80fe5be775bb093d0d757fdc8d2a82a74a` · 01 감사 제품 기준 `457587d3b4b5ecb2526db39b3c420803d85d8874` |
| source_commit_before / source_commit_after | `cf78af80fe5be775bb093d0d757fdc8d2a82a74a` / `UNCOMMITTED` · 별도 브랜치 `porting/copy-ready-20261122`, 시작 당시 변경 없음 |
| target_repo/target_commit | N/A |
| scope | 원본 문서의 진입 순서, PORT-007/009/011~013, 관련 플러그인 요청·API·Windows 사용자 안내. PORT-014의 포트/소스 pin 참조 |
| changes | 아래 13개 Markdown. 제품 코드/API/DB/시험 변경 NONE |
| package_release | NONE |
| evidence | 2026-11-22 Darwin arm64 · Python 3.11.7 · 문서 검사·앵커·보존 검사·diff PASS. 명령, 결과, 로컬 로그는 아래 참조 |
| open_questions | A01~A05와 사전 빌드 자산의 수신 환경은 03 담당자가 전달본에서 확인. 회사 슬래시 연결 방식·운영 경로·콜백·서비스 소유권은 TARGET_UNKNOWN으로 04에서 현지 확인. 해당 회사 인수 T-281/T-286/T-290/T-305 NOT_RUN |
| next_task | `03_CODEX_COPY_READY_PACKAGE.md` · [폴더 전달·모드별 주의](../PORT-011.md#현재-유효-기준), [이식 진입점](../README.md), [감사 인수인계 A01~A05](IMPLEMENTATION_HANDOFF.md#03-원본에서-고칠-항목)를 사용한다. 아래 전달 조건 참조 |

## 변경 파일과 처리

| 분류 | 변경 파일 | 변경 이유와 보존 |
|---|---|---|
| MERGE | `AGENTS.md`, `CLAUDE.md` | 공통 운영 정책·원본 검토 역할·회사 Bedrock 지침의 적용 범위를 구분하고 공통 회사 절차는 이식 진입점에서 안내한다. 운영 예외, 런타임 역할, 리뷰·로그 절차는 기존 경로를 유지한다. |
| MERGE / 문단 ARCHIVE | `docs/README.md`, `docs/porting/README.md` | 첫 화면에 작업별 지도와 회사 준비·검증 링크를 둔다. PORT 목록은 001~014를 모두 연결하고 날짜별 고정 버전·이전 게시 상태는 같은 파일 아래에 남긴다. |
| MERGE / 문단 ARCHIVE | `docs/porting/PORT-011.md` | 현재 export·verify·Windows 전달을 폴더 절차로 명시한다. 구형 HTTP 세션과 기본/연결 ZIP, 파일 동기화 계약, 명령 예제·고정 bytes·초기 설계·원 실행 증거는 날짜별 절에 보존한다. 과거 개인 계정이 포함됐던 로컬 전달 폴더는 상대 표기로 바꿨다. |
| KEEP / 설명 수정 | `docs/porting/PORT-007.md`, `PORT-009.md` | 당시 HTTP/ZIP 배포와 현재 폴더 절차의 링크를 구분한다. 읽기 전용 HTTP 조회와 원래 전달 hash·커밋은 유지한다. |
| KEEP / 설명 수정 | `docs/porting/PORT-012.md`, `PORT-013.md` | 11/18 미커밋은 당시 시험 상태로 표시한다. 직결 본체 시험과 후속 리뷰 적용 범위, 공급자 빌드와 회사 자체 빌드 조건을 구분한다. 기존 pin을 유지한다. |
| MERGE | `docs/agents/BSP_UPGRADE_PLUGIN_REQUEST.md`, `docs/agents/PLUGIN_CONTROL_API.md`, `docs/gui_test/TEST_BOARD_CONNECTOR_GUI.md` | 현재 폴더 안내를 PORT-011에 연결한다. 모드별 명령 차이, 과거 HTTP/ZIP 근거와 일반 GitHub 소스 ZIP 안내를 보존한다. |
| 추가 | `docs/porting/review/DOC_CLEANUP_RESULT.md` | 02의 변경·검증·복구 및 03 전달 조건을 기록한다. |
| KEEP | 요구사항·결정·설계 계약, 시험 목록과 결과, 실행 기록, PORT-014, 스킬·템플릿, CLI 번들·진단 가이드 | 정본과 검증 이력의 경로를 보존한다. 파일 단위 ARCHIVE/DELETE 0건. |

## 검증 근거

로그는 `.local-reports/stage02-doc-cleanup.K2zQT8uT/`에 있으며 저장소에 포함되지 않는다. 비교 기준에는 01 감사 문서가 포함돼 있다.

| 명령 또는 검사 | 결과 |
|---|---|
| `python3 docs/testing/validate_docs.py` | 기준선 2,129링크·81요구·304시험·90 NOT_RUN, 오류 0. 최종 PASS · exit 0 · `validate-final.log`. |
| `python3 .local-reports/stage02-doc-cleanup.K2zQT8uT/audit.py` | 기준 Git tree와 최종 Markdown을 비교했다. 수정 파일의 RQ/D/T/PORT/REG, Git pin·해시, 기록의 FAIL/NOT_RUN 등 상태 어휘, 기존 제목 앵커 보존. 수정 경로에 들어오거나 나가는 fragment와 Codex/Claude 스킬 상대 링크 검사. 원본 계약·시험 기록의 변경 및 파일 삭제 0건. 최종 PASS · exit 0 · `audit-final.log`. |
| `git diff --check`, 전체 diff 및 새 결과 파일 확인 | PASS · exit 0 · `diff-check-final.log`. Markdown 변경 범위와 기존 증거 보존 확인. |
| 코드·CI 소비자 대조 | `delivery.py`는 변경된 문서 트리를 포함한다. Windows CI는 `docs/gui_test/**`를 감시하며, 휴대용 실행기 시험에서 해시를 읽는 `RUN_AND_DIAGNOSE.md`는 수정하지 않았다. |
| 제품·패키지·Windows/회사 시험 | 02는 문서 검증 범위다. 새 전달본, 운영 서비스, 장비, 회사 연동 결과는 NOT_RUN. |

최종 문서 검사 출력은 아래와 같다. 중간 문서 검사에서는 결과 문서를 작성하기 전 해당 신규 링크 1개가 깨져 exit 1이었다. `validate-pre-result.log`에 보존했다.

```json
{
  "status": "PASS",
  "relative_links_checked": 2160,
  "requirements": 81,
  "test_cases": 304,
  "not_run": 90,
  "errors": []
}
```

변경된 기존 Markdown에서 ID 110개와 pin·해시 91개의 누락이 없었다. 범위 내 앵커 참조 115개 및 스킬 진입점 두 곳이 유효했다. `docs/` Markdown은 221개에서 222개로 늘었다. 두 진입부의 줄 수는 문서 지도 45 → 22, 이식 안내 41 → 6으로 줄었다.

## 회복과 03 전달 조건

작업 트리 변경을 먼저 patch 또는 별도 커밋으로 보관한다. 회복이 필요하면 위 변경 파일 중 해당 추적 Markdown만 정리 전 커밋의 내용으로 복원한다. 새 결과 문서는 증거 보관용으로 따로 옮길 수 있다. 전체 브랜치 reset과 runtime·DB 복구는 필요하지 않다.

03에서 최종 소스와 수정된 문서를 사용해 전달본을 다시 만들면 문서 bytes 변경도 manifest와 release에 반영된다. 양 UI와 참조 자산을 빌드·검증한 뒤 원본 밖의 새 폴더에서 export → verify → 복사본 smoke를 수행한다. 생성 README/help의 직결 `settings file sync/push` 표기는 [A04](IMPLEMENTATION_HANDOFF.md#03-원본에서-고칠-항목)와 맞춘다. 11/18 ZIP·체크섬과 회사 NOT_RUN은 해당 이력에 남긴다.
