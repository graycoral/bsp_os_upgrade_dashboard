# Web Interface Guidelines UI 수정 · 2026-11-04

- 요구사항: RQ-19/20/38/39/50 및 사용자 UI 점검·수정·커밋·푸시 요청.
- 기준: `97a509d`, 별도 `ui/web-guidelines-audit` 작업 트리.
- 설계: [UI 점검 명세](../../design/WEB_GUIDELINES_AUDIT.md).
- 원 작업 폴더의 기존 motion/overview/diagram/문서 미커밋 변경은 별도 보존한다.
- 외부 연동: 합성 또는 격리 Mock만 사용. 실제 장비·BSP·Jira 인수는 NOT_RUN.

## 실행 상태

로컬 수정·검증 완료. 최종 독립 리뷰 APPROVED. 아래 최종 결과는 실제 실행이며 Linux worker/실환경 제한은 별도로 유지한다.

| 검증 | 최종 결과 | 실행자 |
|---|---|---|
| Dashboard / GUI Test 단독 production 빌드 | 둘 다 PASS | GPT-6 Luna Low |
| 전체 합성 브라우저·단위 회귀 | 44 PASS | GPT-6 Luna Low |
| 단독 GUI E2E | 18 PASS | GPT-6 Luna Low |
| 배포 패키지 pytest | 6 PASS | GPT-6 Luna Low |
| 독립 코드 리뷰·후속 모달/이동 포커스 리뷰 | APPROVED | 별도 GPT-6.1 Sol High |
| Linux worker 통합 E2E | BLOCKED: Windows fcntl 부재, WSL 미설치 | GPT-6 Luna Low / coordinator 환경 확인 |
| 실제 BSP·장비·Jira 인수 | NOT_RUN | 사용자 실환경 범위 |

T-150~152와 REG-0039를 로컬 검증했다. 최종 실행 로그는 [압축 증거 목록](20261104-web-guidelines-evidence/logs.json), 검증한 코드·시험의 LF 정규화 SHA256은 [소스 manifest](20261104-web-guidelines-evidence/source-sha256.json)에 보존한다. 수정 기준은 이 문서를 최초 포함하는 커밋이며 원 작업 폴더의 기존 미커밋 UI와 구분한다. 실제 운영 baseline은 변경하지 않는다.

## 원 작업 폴더 통합 확인

수정 커밋은 `4368530cf43a9e8c3d848e54e0ec65630f138eab`이다. 원 작업 폴더 `ui/hallmark-overview`에도 fast-forward로 반영했으며 기존 미커밋 motion/overview/diagram/문서 변경은 보존했다. 충돌한 main/TestPage는 기존 표현·모션과 새 접근성 로직을 함께 유지한 결과로 독립 리뷰 APPROVED. 원본 백업은 `.local-reports/ui-guidelines-baseline/` 및 autostash `81e6c87`에 남겼다.

기존 미추적 `motion.spec.ts`는 링크 역할과 native dialog 내부 애니메이션 요소에 맞춘 선택자만 수정했으며 기존 작업과 함께 미커밋으로 유지한다. 이 조합에서 GPT-6 Luna Low가 **두 production 빌드와 전체 50개 시험(감사 회귀 44 + 기존 overview 2 + motion 4)을 모두 통과**시켰다. [통합 소스 manifest](20261104-web-guidelines-evidence/combined-source-sha256.json)와 `combined-*` 압축 로그는 이 로컬 조합의 근거이며, 커밋에 기존 사용자 작업 전체를 포함했다는 뜻이 아니다.

## 독립 리뷰와 초기 실행

- GPT-6.1 Sol High 독립 리뷰: 파일 가져오기 재선택과 저장 중 후속 입력 보존을 확인했다. `--base` 통합 ZIP의 Dashboard 파일 allowlist 누락(P2)을 지적했고 GPT-6.1 Terra Low가 수정했다. GPT-6.1 Sol Medium이 실제 임시 Git 저장소에서 패치 내용을 검사하는 회귀 시험을 추가했다. 해당 수정 재리뷰 APPROVED.
- GPT-6 Luna Low 최초 빌드 명령은 저장소 루트에 package.json이 없어 실패했다. 올바른 `apps/web`에서 Dashboard/GUI Test 빌드는 모두 통과했다.
- 최초 전체 시험은 번들 Chromium 미설치로 20 PASS/23 FAIL. 설치된 Chrome 경로를 명시해 재실행했다.
- Chrome 재실행에서 Vite가 별도 합성 호스트 파일을 차단했다. 시험 서버의 허용 경로를 저장소와 실제 도구 설치 경로로 한정해 수정했다. 제품 서버 설정은 변경하지 않았다.
- 이후 실제 모달 시험에서 Shift+Tab 후 포커스가 대화상자 밖으로 벗어나는 실패를 발견했다. native dialog의 배경 격리는 유지하고, 가시적·활성 컨트롤 경계에서 명시적인 순환 처리를 보완한다. 동일 시험으로 재검증한다.

최초 로그는 `.local-reports/ui-guidelines/`의 `builds-20261104-011300.log`, `builds-20261104-011317.log`, `workflow-20261104-011333.log`, `workflow-chrome-20261104-011412.log`, `workflow-final-20261104-011522.log`에 보존한다. 최종 결과와 혼동하지 않는다.

- 전체 합성 시험 중간 결과 41 PASS/3 FAIL: 모달 실패 외 두 건은 이탈 경고를 취소한 `page.reload()`의 완료를 기다려 시간 초과가 발생했다. trace에서 경고 표시·취소가 확인됐고, 취소된 탐색의 load를 기다리지 않도록 시험을 수정했다. 입력 보존·실제 경고·저장 후 경고 없음 검증은 유지했다.
- 단독 화면 중간 결과 16 PASS/2 FAIL: TC 이름 비교가 새 이동 버튼의 화살표까지 포함했다. 행의 이름 span을 읽도록 기대값 대상을 수정하고 기존 순서·Preflight·완료 Run 보존 검증을 유지했다.
- 추가 키보드 점검: 첫/마지막 위치로 이동하면 사용한 버튼이 비활성 상태로 포커스를 유지했다. 이동한 TC 행의 사용 가능한 이동 버튼으로 포커스를 복원하고 회귀 시험을 추가한다.
- 패키지 pytest: 사용자 전역 임시 폴더 권한 오류를 보존하고, 작업 트리 안의 전용 임시 폴더를 지정해 6 PASS.
- Linux 통합 E2E는 Windows의 `fcntl` 모듈 부재로 worker 시작 전에 BLOCKED. `wsl --list --quiet`로 WSL 미설치를 확인했다. 잠금 동작을 가짜로 대체하지 않았다. API·worker 로그와 격리된 runtime은 `.local-reports/ui-guidelines/integrated-20261104-011821/`에 보존한다.
