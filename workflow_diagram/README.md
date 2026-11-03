# Workflow Diagram

읽기 전용 BSP 작업 다이어그램이다. FrontEnd(ACON) → BackEnd(bsp-os-upgrade) → 선행 IP 모듈 그룹 → 일반 IP 모듈 그룹 순서로 표시하며 IP별 5단계를 접고 펼친다. DB·실행 명령·별도 polling을 포함하지 않는다.

## 폴더와 의존성

- `web/`: React 화면, 전용 CSS, 공개 화면 타입(`types.ts`, contractVersion 1).
- `adapters/dashboard.ts`: 기존 서버 snapshot에서 필요한 값만 추출하는 순수 변환.
- `host/snapshot.ts`: 호스트가 선택적으로 재사용하는 요청 세대/순서/버전 보호, 조회 제한시간, 신선도 판정.
- `tests/`: 상태 fixture, 경계 단위 시험, 격리 호스트와 실제 앱의 API mock 브라우저 시험.

화면은 호스트와 같은 React/ReactDOM 인스턴스를 사용한다. 별도 폰트·아이콘·Archify 설치나 그래프 배치 라이브러리를 요구하지 않는다. 현재 도구 기준은 React/ReactDOM 19.3.0, TypeScript 5.9.3, Vite 7.3.7, Playwright 1.64.0, Node 24.21.0이다. 정확한 잠금 버전은 원본 `apps/web/package-lock.json`을 참고하고, 회사 호스트의 manifest/lockfile에 필요한 의존성을 반영한다. `node_modules` 전체를 회사에 복사하지 않는다.

## 호스트 연결

```tsx
import { DiagramTab } from './workflow_diagram/web/DiagramTab';
import { toDiagramModel } from './workflow_diagram/adapters/dashboard';
import type { SnapshotObservation } from './workflow_diagram/web/types';

// snapshot은 호스트가 기존 조회에서 수용한 현재 작업이다.
// contextKey는 대상·실행 모드·작업을 구분하며 대상 변경 때 바꾼다.
const model = toDiagramModel(snapshot, { contextKey });
const observation: SnapshotObservation = hostObservation;
return <DiagramTab model={model} observation={observation} active={tab === 'diagram'} />;
```

이 예시는 호스트 조회/상태 관리를 생략한 연결부다. 비활성 탭에서 변환을 반복하지 않도록 호스트가 최신 모델을 유지하고, 같은 작업의 탭 왕복 때 컴포넌트를 유지해 펼침/스크롤 상태를 보존한다. 실제 통합 예제는 원본 `apps/web/src/main.tsx`다. 회사에서는 이 파일을 통째로 덮어쓰지 않고 대응 접점만 적용한다.

호스트는 polling뿐 아니라 명령 충돌 복구 GET 등 모든 snapshot 유입에 동일한 세대/순서/버전 수용 규칙을 적용한다. `receivedAt`은 수용 시각, `receivedMonoMs`는 로컬 단조 시각이며 서버 `updated_at`과 다르다. 초기 확인 전·조회 실패·빈 목록·버전 역행을 구분한다. 기본 조회 주기는 1,800ms, 개별 읽기 제한시간은 5,000ms, 신선도는 5,400ms다. 이 값은 ACON 연결 만료 기준이 아니다. 조회 취소는 BSP 작업 취소가 아니다.

`acon`은 선택 입력이다. 제공자·작업/IP 매핑·관찰/만료 의미를 확인한 `AconObservation[]`만 넘긴다. 공통 연결은 공통임을 표시하고, 미제공/만료/매핑 불명은 회색 확인 불가로 둔다. API 조회 성공을 ACON 연결 성공으로 치환하지 않는다. 연결 점과 실행 상태는 독립적이다.

서버 상태/진행률을 보존하며 실행 중 %를 생성하거나 100%로 게이트를 열지 않는다. 표시 단계의 `구현`에는 code와 build를 모두 보존하고 기존 대시보드 상단 집계는 변경하지 않는다. 결과 유효성은 `SUCCEEDED + CURRENT`가 기준이다. 실제 장비 Test 완료는 해당 BSP 단계 결과로만 표시한다.

## 시험과 회사 전달

원본 루트의 실행 진입점은 `node workflow_diagram/tests/run.cjs`다. 시험 러너와 필요한 브라우저 설치는 호스트 도구 환경에서 제공하며 회사에서는 `WORKFLOW_TOOLCHAIN_DIR`로 사용할 `node_modules` 절대 경로를 지정할 수 있다. 실제 사용 옵션·명령·검증 결과는 아래 문서를 기준으로 확인한다.

- 원본 설계: `docs/design/WORKFLOW_DIAGRAM.md`
- 이식 접점·제약·기준: `docs/porting/PORT-001.md`
- 로컬 검증 기록: `docs/testing/runs/20261103-workflow-diagram-implementation.md`

이 문서는 소스 통합 안내이며 실제 회사/ACON 인수를 뜻하지 않는다. 코드 커밋과 시험 증거가 고정된 PORT 안내서를 기준으로 적용하고, 회사 구조 차이·적용 이력·실제 시험은 회사 저장소에 기록한다.
