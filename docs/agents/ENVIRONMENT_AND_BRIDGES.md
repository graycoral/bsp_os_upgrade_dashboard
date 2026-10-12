# 작업 폴더 기반 도구 연결과 환경 설정

2026-10-12 · D-42 / ADR-09. **기본은 내장 CLI 연결이다. 사용자가 bridges 폴더나 JSON wrapper를 만들 필요가 없다.** 기존 사용자 브리지는 고급 호환 설정으로 남긴다. 아래 기능은 로컬 모의 CLI 시험 대상이며 실제 Linux 모델 호출·BSP 빌드 인수는 별도로 수행한다.

## 실행 위치

Linux의 평소 작업 계정으로 API와 worker를 실행하고 Windows/Mac에서는 브라우저와 SSH 터널로 접속한다. worker는 설정한 작업 폴더를 cwd로 삼고 같은 계정의 PATH에서 도구를 찾는다. 서비스 관리자를 쓰면 HOME·PATH·도구 로그인이 터미널과 같은지 확인한다. 호스트/계정 입력은 접속 참고 정보이며 자동 SSH 실행 기능이 아니다.

실행 관리는 worker 하나가 담당한다. Claude 조정 역할은 분석·질문/제안을 맡으며 다른 실행 관리자를 시작하지 않는다. 이벤트 기반 orchestrate·보고 v2·자동 Jira 판단 접수는 여전히 후속 범위다.

## 최초 설정 순서

1. 환경 설정에서 **프로젝트 작업 폴더**, 기존 원본/벤더 수정본/신규 OS 원본 경로를 입력한다. 읽기 전용 원본과 수정 작업 폴더를 분리한다.
2. **도구 연결 방식 → 내장 연결**을 선택한다. Claude는 분석·설계·조정에 필요하다. OpenCode/Codex가 미설치이면 기존 정책에 따라 Claude를 사용한다.
3. 다른 곳에서 만든 에이전트가 있으면 **에이전트 지침 폴더**를 지정한다. 빈칸은 작업 폴더다. 기존 파일을 생성하거나 덮어쓰지 않는다.
4. 프로젝트의 **빌드 명령**, **산출물 파일 경로**, **검증 명령**, **최종 통합·회귀 명령**을 입력한다. 필요한 경우 빌드 환경 초기화 파일의 절대 경로를 등록한다. 명령을 추측해 기본값으로 넣지 않는다.
5. 저장 후 환경 점검을 실행한다. 도구·버전·필수 옵션 및 로컬 로그인 설정을 확인한다. 모델/빌드/로그인 명령은 점검에서 실행하지 않는다.
6. 실제 작업할 때만 실행 방식을 **실제 Linux 도구 실행**으로 바꾸고 새 업그레이드를 시작한다. 현재 설정은 기존 job에 소급되지 않는다.

## 설정 항목

| 필드 | 기본/의미 |
|---|---|
| `execution` | `demo` 기본. 실제 실행 값은 기존 API 호환을 위해 `bridge` 유지 |
| `runner` | `native` 기본. 기존 JSON wrapper 사용자는 `bridge` |
| `workspace` | 실제 Linux 작업 폴더의 절대 경로 |
| `tool_paths` | 도구별 빈 문자열은 PATH 자동 탐지. 고급 설정에서 실행 파일 절대 경로만 지정 가능 |
| `disabled_tools` | 선택 도구 `opencode`, `codex`의 사용 해제 목록. Claude 대체 정책 적용 |
| `models` | 도구별 선택 모델. 빈 값이면 CLI 기본 설정. 반복 수정 실패 전환 시 Claude `opus`가 우선 |
| `agent_instructions` | 기존 에이전트 지침 루트. 빈 값은 workspace |
| `role_instructions` | 역할별 상대 Markdown 경로. 루트 밖·외부 symlink·누락된 명시 파일 거부 |
| `build_command` | 등록된 빌드 셸 명령. 예: `./build.sh` |
| `build_env_script` | 선택 환경 초기화 파일. 명령과 같은 Bash 프로세스에서 source |
| `artifact_path` | 작업 폴더 내부 산출물 파일. 예: `out/firmware.img` 또는 `out/{attempt_id}.img` |
| `verification_command` | 실제 소프트웨어 검증 명령. 예: `./verify.sh`. 장비 시험을 대신하지 않음 |
| `integration_command` | 전체 통합 빌드와 회귀를 수행하는 명령. 예: `./integration-test.sh` |
| `source_revision` | 빈 값이면 신규 원본의 깨끗한 Git HEAD를 새 job에 고정. 직접 고정 해시는 40/64 hex |

비밀번호·API 키·토큰은 설정 파일에 넣지 않는다. 도구 자체 로그인을 Linux 계정에서 준비하며 만료되면 해당 도구에서 다시 로그인한다. 모델 이름은 설치한 도구/공급자가 지원하는 값만 사용한다. OpenCode의 provider 인증을 설치 여부로 확인했다고 표시하지 않는다.

## 기존 역할 지침을 가져오는 규칙

지침 폴더의 `AGENTS.md`, `CLAUDE.md`를 공통 자료로 읽는다. 기본 역할 파일은 `roles/analysis.md`, `roles/design.md`, `roles/code.md`, `roles/review.md`, `roles/coordinate.md`, `roles/question.md`다. 파일당 64KiB까지 읽으며 기본 파일은 없어도 내장 역할 지침을 사용한다. 다른 배치라면 고급 설정에서 각 역할의 상대 경로를 지정한다.

예를 들어 `role_instructions.analysis`를 `.claude/agents/bsp-analyst.md`로 지정할 수 있다. **파일 내용을 역할 자료로 전달하며 그 파일의 도구/모델 권한 설정을 자동 실행하지 않는다.** 원래 프로젝트가 자체 에이전트 배정기를 갖고 있어도 이중 배정하지 않는다. 모듈 목록은 대시보드의 영속 목록이며 CLI 세션/agent 목록으로 덮어쓰지 않는다.

새 job은 도구 경로·점검 결과·역할 지침 내용을 저장한다. 이후 PATH/설정/지침을 바꿔도 기존 job에 자동 적용하지 않는다. 에이전트가 반환할 데이터의 단일 기준은 [보고 계약](../design/AGENT_STATUS_CONTRACT.md)이다.

## 실행과 결과 수집

- Claude: 비대화형 JSON/schema 결과를 사용한다. 읽기 역할은 Read/Glob/Grep만, 코드 역할은 작업 폴더 Edit/Write를 추가한다. 원본 소스 쓰기와 하위 agent/MCP 실행을 기본 호출에서 허용하지 않는다. 전체 권한 우회 플래그를 쓰지 않는다.
- OpenCode: 구현 전용 `run` JSON 이벤트를 사용한다. 호출별 내부 역할/권한을 주입하고 Bash·하위 작업·외부 쓰기를 허용하지 않는다. 프로젝트의 설정/인증 파일은 수정하지 않는다.
- Codex: 별도 리뷰 세션을 `exec`의 read-only sandbox와 JSON/schema로 실행한다.
- 빌드/검증/통합: 지정한 셸 명령만 실행한다. 모델 응답에 담긴 명령을 실행하지 않는다. 검증 명령도 파일을 쓸 수 있으므로 수정/빌드와 같은 배타 잠금을 사용한다.

명령에는 `BSP_JOB_ID`, `BSP_MODULE_ID`, `BSP_MODULE_NAME`, `BSP_ATTEMPT_ID`, `BSP_SOURCE_REVISION`, `BSP_STAGE`, `BSP_OLD_BASE`, `BSP_VENDOR_TREE`, `BSP_NEW_BASE`를 환경변수로 전달한다. 모듈 빌드에는 `BSP_ARTIFACT_PATH`도 제공한다. 명령에서 값을 사용할 때는 `"$BSP_ARTIFACT_PATH"`처럼 인용한다. 산출물 경로의 템플릿은 job_id/module_id/attempt_id만 지원한다. 빌드 스크립트가 필요한 출력 디렉터리를 만들도록 한다.

성공은 exit 0만으로 agent 완료가 되지 않는다. 완료 이벤트·JSON 형식·상관관계 ID·근거를 검사한다. 코드 결과의 실제 작업 파일 내용 해시를 계산하고 별도 리뷰 후 다시 대조한다. 이 해시는 소스 사본/OS 격리를 만들지 않으며 `.git`, `.repo`, 도구 메타데이터, 선언한 이미지·원본 폴더는 제외한다. 거대한 작업 폴더에서는 해시 계산 비용이 있으므로 실행 소스와 빌드 출력을 분리한다.

빌드 성공은 이번 실행에서 생성/갱신된 파일과 SHA-256이 있어야 한다. 작업 폴더 밖·symlink 이탈·이전 그대로인 산출물은 거부한다. 검증/통합 명령은 **실패 시 nonzero를 반환하는 프로젝트 시험 스크립트**여야 한다. 현재 사례별 자동 시험 보고 해석은 없으며 종료 코드/수행 근거를 기록한다. 원문 stdout/stderr는 비밀정보 노출을 피하기 위해 화면/DB에 저장하지 않는다. 상세 빌드 로그는 등록한 스크립트에서 관리한다.

## 점검·실패·재시작

`MISSING / DISABLED / INVALID / PROBE_FAILED / UNSUPPORTED / LOGIN_REQUIRED / CLI_READY`를 구분한다. `CLI_READY`는 실행 파일·옵션 확인이며 실제 서비스 접속/모델 추론 성공이 아니다. 인증은 `UNVERIFIED / CONFIGURED / LOGIN_REQUIRED`로 표시한다. OpenCode는 공급자별 인증 인수가 필요하다.

선택 도구가 없거나 명시적으로 해제된 경우에만 시작 시 Claude 대체를 정한다. 설치된 도구의 옵션 오류/로그인 필요는 조용히 다른 도구로 바꾸지 않고 알린다. 실행 중 인증·환경 오류는 ENVIRONMENT/CONTRACT 실패로 남기며 같은 코드 FIX 실패 횟수에 넣지 않는다. 무한 자동 재시도는 하지 않는다.

종료가 확인된 조정 연결 실패는 화면의 **로그인 확인 후 연결 재시도**로 다시 연결하며 실패 이력을 보존한다. 기존 실행 프로세스를 잃으면 UNKNOWN/NEEDS_RECONCILIATION을 유지한다. timeout/출력 초과 시 프로세스 그룹 종료 권한이 없으면 UNKNOWN으로 기록하고 writer 잠금을 유지한다. 정상 전경 프로세스 종료 후 이미 회수한 PID에 종료 신호를 보내지 않는다. 도구/스크립트는 분리된 백그라운드 작업을 남기면 안 된다. 실제 프로세스 재접속·종료 확인 후 재개 자동화는 아직 없다. `--last`/`--continue`로 다른 모듈의 최신 세션을 임의 재사용하지 않는다. 브라우저 종료와 Linux worker 종료는 별개다.

## 기존 JSON 브리지 호환

고급 연결 방식 `runner: bridge`는 기존 `agents`/`build_argv` 배열과 stdin/stdout v1을 유지한다. 이 모드에서만 `.bsp-dashboard/bridges/...` 경로 채우기를 제공한다. 사용자가 실제 설치한 wrapper나 사용자 지정 배열은 자동 변환하지 않는다.

runner가 없는 이전 JSON의 명시 실행 배열은 기존 브리지로 해석한다. 저장 DB의 정확한 자동 기본 경로 네 개가 모두 미설치인 경우에는 설정 조회에서 내장 모드를 제안한다. 기존 job snapshot은 변환하지 않는다. 조회된 정규화 설정은 새 작업에 적용하며 다음 설정 저장 시 영속한다. 과거 job은 기존 모드를 유지한다.

## 실제 환경 인수와 공식 호출 근거

로컬 모의 CLI 시험은 실제 인증·모델 품질·Linux 정책·프로젝트 hook/확장·BSP 빌드·사내 Jira·보드 인수를 대신하지 않는다. 사용자 도구 설정/확장과 운영체제 권한까지 격리하는 컨테이너/불변 소스 snapshot은 후속 범위다. 실제 Claude/BSP 실행은 사용자가 수행한다.

호출 기능은 [Claude CLI](https://code.claude.com/docs/en/cli-reference), [Claude 구조화 출력](https://code.claude.com/docs/en/headless), [OpenCode CLI](https://opencode.ai/docs/cli/), [OpenCode 권한](https://opencode.ai/docs/permissions/), [Codex 비대화형 실행](https://learn.chatgpt.com/docs/non-interactive-mode)에 근거한다. 설치 버전에서 필요한 옵션이 없으면 시작을 거부한다. 로컬 Codex 0.162.1의 도움말도 대조했으며 모델은 호출하지 않았다.
