# PORT-001 · 다이어그램 탭

**현재 최신 기능·시험 고정 커밋: `e475eb8ac267e29cdeb7501c5c39eddac10d982e`**. 작은 서브 단계·그룹 접기/펼치기·화이트 테마까지 포함한다. 37개 시험·두 빌드 PASS, 독립 리뷰 APPROVED. 이미 `8702037`을 적용한 회사는 이 커밋의 전용 화면/CSS/시험과 문서만 갱신한다. 최초 도입의 호스트 연결 안내는 아래를 따른다. 아래 게시 예정·이전 커밋 표시는 당시 이력이며 최신 이식은 이 커밋을 기준으로 한다. 실제 회사/ACON 인수는 별도다.

최신 후속(2026-11-04): 작은 단계 카드·그룹 접기/펼치기·화이트 테마. 기존 기능 위에 `web/DiagramTab.tsx`, `web/diagram.css`, `tests/browser.spec.ts`와 관련 문서를 갱신한다. 호스트/API/의존성 추가 변경 없음. [37개 시험·두 빌드·독립 리뷰 및 소스 해시](../testing/runs/20261104-workflow-diagram-light-groups.md). 아래 `8702037`은 그룹 접기·화이트 변경 전 버전이며 후속 고정 커밋은 게시 시 이 문서에 기록한다.

## 최신 전달 기준 · 2026-11-04

**기능·시험 고정 커밋: `8702037dff276c3dd930e851cf7649ccb6ec46db`**. 회사에서 최신 UI를 이식할 때 이 커밋의 `workflow_diagram/`와 시험을 사용한다. 오른쪽 펼침·컴팩트 배치·배율·선택 영역 집중을 모두 포함하며 36개 로컬 시험·두 빌드와 독립 리뷰를 통과했다. 최초 기능 호스트 접점은 아래 `199b04b`의 안내를 재사용한다. 이미 초기 기능을 이식했다면 이 후속 변경은 전용 폴더/시험/문서만 갱신하며 호스트 연결부에 추가 변경은 없다.

아래 미커밋·게시 예정 표현은 검증 당시 이력이다. `199b04b`은 최초 아래 펼침 버전, `8702037`은 현재 후속 UI 버전으로 구분한다. 실제 회사/ACON 인수는 계속 별도다. 시험 manifest는 당시 working tree의 raw SHA256이며 Git 줄바꿈 정규화 차이를 제외한 내용이 고정 커밋과 일치한다.

최신 UI 후속 범위(2026-11-04): 오른쪽 펼침에 더해 컴팩트 배치·확대/축소·선택 영역 집중을 제공한다. 신규 `workflow_diagram/web/viewport.ts`를 포함해 전용 폴더를 함께 가져온다. 호스트/API/공개 타입/의존성 추가 변경은 없으며 CSS zoom·ResizeObserver·scrollTo의 회사 대상 브라우저 호환성을 확인한다. [최신 36개 시험·두 빌드·독립 리뷰 증거](../testing/runs/20261104-workflow-diagram-zoom.md), [소스 manifest](../testing/runs/20261104-workflow-diagram-zoom-evidence/source-manifest.json). 후속 고정 커밋은 게시 단계에서 아래에 추가한다. 기존 `199b04b`은 초기 아래 펼침 버전이다.

상태: **IMPLEMENTED_LOCAL / MOCK_TESTED / 원본 전달 기준 고정**. 2026-11-03 사용자 구현 승인 후 독립 리뷰·32개 로컬 시험·두 기존 빌드·격리 빌드를 통과했다. 구현 커밋 `199b04b5c080e41ec9794326828fbc4874cef633`으로 소스·시험을 고정했다. 실제 회사 적용과 ACON 인수는 미수행이다.

## 목적과 기준

2026-11-04 후속 UI 변경: 오른쪽 단계 펼침·참고 HTML 기반 dark 스타일·이동 화살촉을 추가했다. 아래 `199b04b` 고정 커밋은 **기존 아래 펼침 버전**이며 이 후속 변경을 포함하지 않는다. 후속 이식 대상은 `workflow_diagram/web/DiagramTab.tsx`, `web/diagram.css`, `tests/browser.spec.ts`, 기능 README 및 관련 문서다. 호스트 접점·adapter·공개 타입·의존성·DB 변경은 없다. [후속 검증 기록](../testing/runs/20261104-workflow-diagram-rightward.md)의 파일 해시로 로컬 변경을 구분하며, 회사 전달용 후속 커밋은 아직 고정하지 않았다. 참고 HTML 자체를 회사에 복사할 필요는 없다.

- 동작: FrontEnd(ACON) → BackEnd(bsp-os-upgrade) → 선행 IP 모듈 그룹 → 일반 IP 모듈 그룹의 가로 다이어그램, IP별 단계 접기/펼치기, 현재 단계·진행률·상태 점·진행 화살표 효과.
- 근거: RQ-50 / D-51 / [다이어그램 설계](../design/WORKFLOW_DIAGRAM.md) / T-144~149.
- 원본: 이 BSP OS 업그레이드 대시보드 저장소.
- 변경 전 원본 기준: `e86c5cbbf53cd360a1b90eafcc1c37b050e3659e`.
- 원본 구현·시험 커밋: `199b04b5c080e41ec9794326828fbc4874cef633`. 회사 대상 커밋은 회사 적용 후 APPLIED.md에 기록한다.
- 선행 PORT: 없음. 호스트 patch는 위 변경 전 원본을 기준으로 하며 회사가 같은 구조라고 가정하지 않는다. GUI Test 전체를 이 기능의 선행 조건으로 요구하지 않는다.
- 의존성: 현재 앱의 React/ReactDOM 19.3.0, TypeScript 5.9.3, Vite 7.3.7, Playwright 1.64.0, Node 24.21.0. 원본 `apps/web/package-lock.json`을 기준으로 회사 manifest/lockfile에 필요한 항목을 반영한다. 제품 런타임 신규 의존성은 없다.
- 실제 시험 코드·명령·증거: [구현·검증 기록](../testing/runs/20261103-workflow-diagram-implementation.md). 이전 [문서 작성 기록](../testing/runs/20261103-workflow-diagram-docs.md)은 제품 시험 증거가 아니다.
- 후속 문서 리뷰: [동작·효율성·연동 검토](../testing/runs/20261103-workflow-diagram-review.md). 코드 대조에 따른 설계 보완이며 제품 시험·독립 Claude 검토가 아니다.
- 전달 방식: 위 고정 구현 커밋의 전용 폴더·시험과 호스트 접점을 재사용한다. 회사 대응 파일에 필요한 차이만 적용한다. 기존 manifest의 미커밋 표시는 시험 당시 이력이며 현재 구현 커밋과 코드 내용이 동일하다. Git의 CRLF/LF 정규화로 raw 파일 SHA256이 달라질 수 있으므로 커밋 blob과 시험 manifest의 용도를 구분한다.
- 현재 파일 기준: [소스·시험 manifest](../testing/runs/20261103-workflow-diagram-evidence/source-manifest.json), [호스트 연결부 patch](../testing/runs/20261103-workflow-diagram-evidence/host-integration.patch). patch는 위 기준 HEAD 대비 `main.tsx`와 `tsconfig.json`만 포함하며 전용 폴더는 별도로 함께 가져온다. 회사 구조에 무조건 적용하지 않는다. 작업 중 별도로 바뀐 `scripts/build.cmd`는 이 기능의 전달 범위에 포함하지 않는다.

## 재사용 코드와 회사 연결 계획

다음 경로가 실제 구현·시험 파일이다. 회사에서는 전용 폴더를 재사용하고 호스트 연결부만 조정한다.

| 원본 위치 | 유지할 동작 / 목적 | 이식 방식 | 관련 시험 |
|---|---|---|---|
| workflow_diagram/web/ | 독립 화면·노드·연결선·전용 스타일·화면 데이터 형식 | 신규 폴더 재사용 | T-144~147 |
| workflow_diagram/adapters/dashboard.ts | 기존 상태를 화면 모델로 변환 | 회사의 상태 조회/데이터 구조에 맞춰 조정 | T-145~146 |
| workflow_diagram/host/snapshot.ts | 요청 세대/순서/버전 수용·timeout·신선도 | 호스트의 동등 보호가 있으면 재사용하거나 이 helper 연결 | T-146 |
| workflow_diagram/tests/ | 표시·누락·단절·역순 응답·접기/펼치기 fixture 및 시험 | 시험과 fixture 함께 재사용 | T-144~148 |
| workflow_diagram/README.md | 사용 예·의존성·통합 방법 | 코드와 함께 전달 | T-148 |
| apps/web/src/main.tsx | 새 탭·화면 호출·snapshot 관찰 시각/조회 상태 전달·모든 snapshot 유입의 수용 보호·조회 timeout | 회사 대응 파일에 필요한 변경만 반영; 기존 보호가 충분하면 재사용 | T-146, T-148 |
| apps/web/tsconfig.json 및 vite.config.ts | 외부 기능 폴더의 빌드 포함/React 호환 | 필요 여부 확인 후 최소 조정 | T-148 |

회사 경로·기술 스택은 미확인이다. 회사 `COMPANY_MAP.md`에 대응 관계를 먼저 기록하고 원본 main.tsx 전체를 덮어쓰지 않는다. 폴더 복사에 더해 탭 등록·adapter·필요한 빌드 설정 연결이 필요하다.

### 회사 연결부에서 먼저 확인할 항목

| 확인 항목 | 필요한 판단 / 미지원 시 처리 |
|---|---|
| UI와 의존성 | React 소스/TS/CSS를 빌드할 수 있는지, React 단일 인스턴스·타입 경로·asset 포함·오프라인 빌드를 확인. 현재 package.json의 버전 범위는 검증된 회사 버전이 아니며 구현 후 lockfile 기준으로 고정 |
| 조회 경로와 기준 | 호스트의 snapshot 조회를 재사용하고 polling/명령 충돌 복구 등 모든 유입의 작업·대상·실행 모드 구분 및 역순/이전 세대 차단을 확인. 영구 pending은 유한 timeout/무효화 뒤 재조회. 별도 polling을 만들지 않음 |
| 관찰 상태 | 최초 확인 전/조회 실패/성공 시각/지연을 전달. RQ-50 원본은 events 실패와 snapshot 실패를 분리한다. 회사도 같은 보호가 필요한지 확인하고 저장 시각 updated_at을 관찰 시각으로 대신하지 않음 |
| 데이터 의미 | 서버 현재 단계·실행 상태·결과 유효성·대기 사유·진행률을 [설계 4절](../design/WORKFLOW_DIAGRAM.md#4-현재-데이터와-표시-변환-경계)과 대조. 모르는 상태나 그룹은 진단·미확인으로 남김 |
| ACON 근거 | 제공자와 작업/IP 적용 범위·관찰/만료 의미 확인. 공통 연결과 모듈별 연결을 구분하고 미제공이면 해당 표시만 확인 불가 |
| 규모·표시 | 모듈 상한/이름 길이/대표 이력 bytes/회사 전역 CSS/탭 수명·키보드/좁은 화면 확인. 원본 시험 규모 100개를 초과하면 회사 기준으로 추가 측정. 전송/파싱과 화면 변환/렌더 비용을 구분 |

화면 입력 타입·반환 진단의 단일 기준은 `workflow_diagram/web/types.ts`(contractVersion 1)다. 회사 adapter는 그 타입으로 변환하며 원본 API 타입·전역 store를 화면 내부로 끌어오지 않는다. 실행 명령/인증정보/전체 로그·이력은 화면에 전달하지 않는다. 사용 예는 [기능 README](../../workflow_diagram/README.md)를 따른다.

## 데이터·운영·호환성

- 읽기 전용 화면이며 DB schema/worker/실행 정책 변경은 없다. 모듈 목록과 그룹은 영속 데이터에서 가져온다.
- 기존 조회·인증·갱신 처리는 호스트 앱이 담당한다. 별도 polling·실행 관리자·직접 DB 접근을 추가하지 않는다.
- 회사 API 연결과 실제 ACON 연결 근거를 구분한다. ACON 상태 제공 위치/만료 기준 미확정은 해당 표시만 미설정/확인 불가로 처리한다.
- 서버 6단계와 화면 5단계의 대응은 [설계 4절](../design/WORKFLOW_DIAGRAM.md#4-현재-데이터와-표시-변환-경계)대로 구현했다. code/build를 구현 내부에 함께 표시하고 빌드 실패/유효성·진행률 근거를 숨기거나 새로 계산하지 않는다.
- 병렬 분석, 최초 계획 확인, 선행 그룹 전체 완료 게이트, 수정/빌드 배타, 기본 수동시험·자동 프로파일 예외, 최종 검토와 기존 회사 추가 기능을 보존한다.
- CSS 선택자·변수·keyframes·SVG id를 격리하고 회사 전역 CSS가 화면 내부에 미치는 영향도 확인한다. 라이브러리·아이콘·폰트·시험 도구의 암묵적 의존성을 검사한다. Archify 설치를 회사 런타임 필수 조건으로 요구하지 않는다.
- 저장 데이터 이전은 해당 없음. 펼침/스크롤은 현재 작업의 세션 메모리만 사용하고 작업/대상 세대 변경 시 초기화한다. 일반 탭 왕복은 유지한다.
- 복원 계획: 도입 전 회사 변경을 보존하고 새 탭/화면 연결과 해당 기능 전용 설정만 역변경한다. 다른 기능에서 사용 중인 파일·의존성은 삭제하지 않으며 실행 DB·모듈 이력을 초기화하지 않는다. 정확한 역변경 범위는 실제 커밋 확정 후 기록한다.

## 검증과 인수 계획

| 시험 | 실행 위치·명령 | 기대 결과 | 현재 결과 |
|---|---|---|---|
| T-144 | `node workflow_diagram/tests/run.cjs browser.spec.ts host-integration.spec.ts` | 상위 가로 순서·소속 IP·독립 접기/펼치기 | 실행 기록 참조 |
| T-145 | `node workflow_diagram/tests/run.cjs adapter.spec.ts` | 실제 실행/대기·유효성·빌드·취소 중·자동 Test·진행률/게이트 표시 | 실행 기록 참조 |
| T-146 | `node workflow_diagram/tests/run.cjs snapshot.spec.ts presentation.spec.ts host-integration.spec.ts` | ACON/API 구분·최초 확인·같은 version 관찰·역순 성공/실패·A→B→A 작업 변경·이벤트 단독 실패 | 실행 기록 참조 |
| T-147 | `node workflow_diagram/tests/run.cjs browser.spec.ts presentation.spec.ts` | 연결 점과 실행 표시 분리·분석 예외 화살표·모션 정지·접근성·100개/좁은 화면 | 실행 기록 참조 |
| T-148 | 전체 `run.cjs` 및 아래 두 빌드 | 역방향 앱 의존 없음·CSS 양방향 영향·추가 조회 0·탭 비활성 비용·기존 탭/데이터 보존 | 실행 기록 참조 |
| T-149 | 회사 환경; 실제 ACON 상태 제공 방식 확인 후 실행 절차 고정 | 실제 연결/단절 근거와 서버 모듈 상태가 화면과 일치 | NOT_RUN |

두 빌드 명령은 `npm.cmd run build --prefix apps/web`, `npm.cmd run build:gui-test --prefix apps/web`이며 로컬 재실행 PASS다. 독립 GPT-6.1 Sol High 코드 리뷰도 APPROVED다. 실제 모의 시험의 실패/환경 제약/재시험과 검토 해시는 [실행 기록](../testing/runs/20261103-workflow-diagram-implementation.md)을 따른다. 실제 회사 적용·ACON 인수와 Python 전체 백엔드 회귀는 이 로컬 검증을 대신하지 않는다. 원본 PASS를 회사 PASS로 복사하지 않는다.

시험 toolchain은 기존 `apps/web/node_modules`를 기본으로 사용한다. 다른 호스트는 `WORKFLOW_TOOLCHAIN_DIR`에 node_modules 절대 경로, `BSP_BROWSER_EXECUTABLE`에 설치된 Chromium 계열 브라우저 경로를 지정한다. 설치 없이 이미 준비된 도구만 쓰며 회사에서 [시험 README](../../workflow_diagram/tests/README.md)의 명시 의존성을 함께 준비한다.

격리 호스트 시험은 원본 apps/web·gui_test·전역 CSS 없이 전용 폴더와 명시된 의존성/fixture만으로 빌드·표시하는 방식으로 수행한다. 실제 repo 빌드도 별도 검증한다. 전달 목록에는 전용 폴더, 호스트 접점 diff, 실제 필요한 manifest/lockfile 변경, 실행 가능한 시험 진입점/fixture/명령, 고정 해시를 포함한다. tests 폴더만 복사하고 시험 러너나 브라우저 환경을 빠뜨리지 않는다.

## 다음 갱신 조건

구현 지시 → 구현/로컬 시험 → 코드 커밋 확정 → 이식 기준과 대상 전체 해시·의존성·증거 기록 → 전달 가능한 안내서로 상태 변경 순서다. 회사 담당자는 [공통 절차](README.md)에 따라 `COMPANY_MAP.md`와 `APPLIED.md`에 실제 적용 범위·회사 커밋·시험·미완료를 남긴다. 회사 적용이나 실제 장비 실행은 이 초안으로 승인되지 않는다.


## 미고정 후속 · 전체 탭 모션

2026-11-04 사용자 요청에 따른 화살촉 1200ms·즉시 카메라·키보드 강조 예외는 `workflow_diagram/web/DiagramTab.tsx`, `diagram.css`, `viewport.ts`의 후속 변경이다. 기존 고정 커밋은 이 모션 변경을 포함하지 않는다. 호스트/API/공개 타입·신규 의존성 변경은 없다. 공통 모달/GUI 버튼 변경은 별도 호스트 파일이며 독립 다이어그램 이식에 필수가 아니다. [점검표·검증 기록](../testing/runs/20261104-ui-motion.md).
