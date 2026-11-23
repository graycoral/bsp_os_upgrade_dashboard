# BSP OS Upgrade Dashboard → 사내 `bsp-os--upgrade` 플러그인 이식 실행 가이드

> **이 파일의 역할:** 실행 순서 및 작업 간 인수인계 규칙. 모든 세션의 공통 시작 문서.
> **지정 모델:** 원본 작업 시작 시 **Codex Astra/High**가 계획 검토; 사내 작업 시작 시 **Claude Opus (Bedrock)**가 회사 적용 계획 검토. 파일 자체는 실행 작업이 아님.
> **기준:** `https://github.com/graycoral/bsp_os_upgrade_dashboard` (`main` 기준으로 매번 실제 HEAD 재확인)
> **사내 기본 환경:** Claude Code + Amazon Bedrock. 사내 LLM/OpenCode는 필수 의존성이 아님.
> **핵심 목표:** 구현된 기능을 재작성하지 않고, 검증된 소스·사전 빌드 UI·Windows 커넥터를 가능한 한 **폴더 복사 + 최소한의 호스트 어댑터 수정**으로 사내 플러그인에서 사용한다.

## 1. 역할 및 모델 라우팅

| 순서 | 지침 파일 | 실행 장소/하네스 | 지정 모델 | 추론 강도 | 결과물 |
|---|---|---|---|---|---|
| 1 | `01_CODEX_SOURCE_AUDIT.md` | 공개/로컬 원본 저장소 · Codex | **Astra 계열** (가능하면 GPT-6 High) | High | 이식성 감사·의존성·검토 인수인계 |
| 2 | `02_CODEX_DOC_CLEANUP.md` | 공개/로컬 원본 저장소 · Codex | **Sol 계열** (가능하면 GPT-6 Medium) | Medium | 중복 문서 정리·보존 증거·리디렉션 |
| 3 | `03_CODEX_COPY_READY_PACKAGE.md` | 공개/로컬 원본 저장소 · Codex | **Sol 계열** (가능하면 GPT-6 Medium) | Medium | 복사 가능한 패키지·검증·Smoke Test |
| 4 | `04_CLAUDE_OPUS_COMPANY_ASSESSMENT.md` | 사내 대상 저장소 · Claude Code (Bedrock) | **Claude Opus** | 깊은 추론 | 사내 적용 현황·변경 계획·차단 이슈 |
| 5 | `05_CLAUDE_SONNET_COMPANY_PORT.md` | 사내 대상 저장소 · Claude Code (Bedrock) | **Claude Sonnet** | 보통~높음 | 승인 범위 이식·스모크/회귀 시험·APPLIED |
| 6 | `06_CLAUDE_OPUS_FINAL_REVIEW.md` | **새 Claude Code 세션** · Bedrock | **Claude Opus** | 깊은 추론 | 독립 코드·계약·배포 리뷰 |

**모델 이름 주의:** `Astra`, `Sol`은 사용 중인 Codex 환경의 모델 역할 구분을 가리킨다. UI에 명칭이 없으면 사용 가능한 Codex의 최신 고성능 추론 모델(High) 및 일반 코딩 모델(Medium)을 선택한다. Claude의 구체적인 Bedrock 모델 ID는 회사에서 허용된 모델 목록을 따르며 임의로 만들지 않는다. **Haiku는 원인 불명 장애·이식 설계·대량 삭제 판단에는 사용하지 않는다.** 모델 호출이 중단되는 사내 OpenCode/GLM은 필수 단계로 두지 않는다.

## 2. 세션 분리 원칙

- 한 파일 = 한 세션의 **작업 지시서**. 단계 종료 후 새로운 세션을 연다. 장문의 세션 대화보다 문서·Git diff·테스트 결과로 넘긴다.
- 매 단계에서 해당 지침과 직전 단계의 인수인계 파일만 먼저 읽고, 추가 자료는 관련 범위로 제한한다.
- **원본 공개 저장소**에서 가능한 문제(공통 코드, 전달물 누락, 빌드/검증)를 먼저 해결한다.
- **사내 대상 저장소**는 이미 적용된 코드, 내부 환경, 호스트 플러그인 연결을 대조한다. 원본으로 사내 코드·로그·경로를 역반출하지 않는다.
- 상호 다른 하네스의 세션을 직접 연결하려 하지 말고, 동일한 파일 스키마와 Git 커밋/패키지 manifest를 인수인계 계약으로 사용한다.
- 코드 적용과 실제 장비 인수는 별개이다. 로컬 모의 PASS는 회사 PASS가 아니다.

## 3. 전달물 구조

기존 제공 기능을 최우선 재사용한다.

- `apps/agent-monitor/delivery.py` — 소스 + 사전 빌드 UI의 byte manifest
- `apps/agent-monitor/plugin_delivery.py` — 플러그인 소유 복사형 전달 패키지 + 검증
- `apps/agent-monitor/plugin.py` — 플러그인 진입점/`export`/`verify`
- `docs/porting/README.md`, `PORT-001`~`PORT-014.md` — 기존 적용 계약
- `.agents/skills/portable-feature/SKILL.md` — 기존 Codex용 이식 스킬
- 사내 `docs/porting/COMPANY_MAP.md`, `APPLIED.md` — 회사 전용 구조/적용 기록 (없으면 템플릿에서 생성)

사내에 복사하는 패키지에는 제품 코드, 실행에 필요한 잠긴 의존성 설명, 사전 빌드 UI, 각 파일 hash와 버전/검증 결과가 있어야 한다. **SSH 키·토큰·비밀번호·DB 스냅샷·사내 설정을 소스와 함께 복사하지 않는다.**

## 4. 단계별 통과 게이트

1. **원본 감사 PASS:** 누락 의존성·복사 범위·회사 맞춤 부분을 구분했고, 실행하지 않은 시험은 `NOT_RUN`으로 남긴다.
2. **문서 정리 PASS:** 요구사항 원본·결정 이력·PORT pin·실패 근거를 삭제하지 않고 링크·검증 스크립트가 통과한다.
3. **전달 패키지 PASS:** export → `verify` → 완전 새 디렉터리에서 진입점/import/배포 자산 시험 → release/manifest 확인. 미지원 환경은 `BLOCKED/NOT_RUN`.
4. **사내 준비 PASS:** 회사 기존 코드/기능·runtime·포트·DB/마이그레이션 상태와 사전 백업 및 롤백 방식 확인.
5. **사내 적용 PASS:** 복사 중심 적용 + 필수 Adapter 변경만 수행, 원본/대상 diff 및 회사 smoke/regression 기록.
6. **독립 리뷰 PASS:** 구현 세션이 아닌 새 Claude Opus 세션에서 소스·시험·배포 경계 검토. 주요 P0/P1 결함이 해결되지 않으면 인수 보류.

## 5. 알려진 점검 포인트 (2026-11-21 원본 구조 확인 기준)

- 회사 대시보드 포트 예시는 `8765`, 원본 Agent Monitor 기본 `8766`, 직접 커넥터 기본 `8771`이다. 실제 운영 값은 사내에서 확인한다.
- `PORT-013`은 직결 커넥터·Windows SSH-R·공통 설정/DB 복구·자율 실행을, `PORT-014`는 작업 삭제/재실행·TC 전체 보기·회사 포트 격리를 다룬다.
- `PORT-011`의 **과거 ZIP 이력**과 최신 **폴더 전체 복사** 설명이 섞여 있으므로 코드와 현행 전달물을 기준으로 해석한다.
- 새 전달물은 기존 실행 중 프로세스와 다를 수 있다. 복사 후 `managed_release`, 설치 소스, 실행 서비스 version을 함께 검증한다.
- Node.js 22.12+는 원본 UI 빌드 요구사항으로 보이며, prebuilt 전달물 수신자에게도 Node가 필요한지 별도로 시험한다.
- Windows connector는 실행 환경 준비가 필요하다. Python/의존성/공개 도구의 사내 폐쇄망 사용 가능성을 따로 확인한다.
- 회사 소스와 오류 로그에 아직 접근하지 않았으므로 **실제 사내 오류 원인은 미확정**이다.

## 6. 공통 결과 상태·인수인계 형식

모든 세션의 최종 문서 첫 부분에 다음 표를 기입한다.

| 필드 | 내용 |
|---|---|
| source_repo/source_commit | 원본 경로·정확한 Git SHA |
| target_repo/target_commit | 회사 경로·Git SHA (원본 단계에서는 `N/A`) |
| scope | 이번 작업 기능·PORT·파일 범위 |
| changes | 변경 파일과 이유; 코드 변경 없으면 `NONE` |
| package_release | `PLUGIN_PACKAGE.json`/`AGENT_MONITOR_SOURCE.json`에 적힌 release (없으면 `NONE`) |
| evidence | 실행 명령·환경·로그 경로·PASS/FAIL/BLOCKED/NOT_RUN |
| open_questions | 정책/호스트/환경 미결정, 영향, 권장안, 담당 |
| next_task | 다음 파일에서 바로 수행할 항목 |

**금지:** 공개 저장소로 사내 경로·자격 증명·서비스 정보 반출, 근거 없는 상태 PASS, 승인 없는 destructive migration/reset/장비 flashing, 대량 자동 덮어쓰기.
