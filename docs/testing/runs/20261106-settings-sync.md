# 전체·탭별 설정 동기화 · 2026-11-06

상태: **IMPLEMENTING / PARTIAL_TESTED / RQ55_STATIC_REVIEW_APPROVED**. RQ-55/D-59 및 후속 RQ-56/D-60. 환경 설정에서 기존 화면 편집 가능 설정을 모두 제공하고 대시보드·사람 검토/Jira·Test 현황에서도 관련 항목을 같은 편집 상태로 수정한다. 그룹별·전체 접기/펼치기와 서버 폴더/Git URL 소스 등록·실제 브랜치 조회·불변 소스 전달을 추가한다. 사용자가 완료 후 재빌드·재실행·머지·푸시를 명시적으로 요청했다. 실제 장비·모델·Jira·외부 저장소 인증 인수 및 운영 baseline 변경은 범위 밖이다.

## 기준과 역할

- 시작 기준: `main`, `cd124ae` 및 이번 미커밋 변경. 기존 사용자 변경 `apps/gui-test/config/device-test.example.json`, `.vscode/`는 보존한다.
- 요구 분석: 지정 Requirements Analysis / GPT-6 Astra XHigh.
- 상세 설계: 지정 Detailed Design / GPT-6 Astra High.
- 구현: 지정 Implementation / GPT-6.1 Sol High.
- 시험 작성: 지정 Unit Test Development / GPT-6.1 Sol Medium. 상태 보존·검증 경계를 브라우저 행동 시험으로 확인한다.
- 독립 코드 검토·시험 실행 결과는 실제 수행 후 아래에 기록한다.

## 검증할 동작

단일 BSP 폼과 단일 TestPage를 유지해 양쪽 위치에서 같은 초안·JSON 오류·명령 템플릿·연결·반복·Suite 입력을 편집한다. 실행 기록·다이어그램에 새 설정을 만들지 않는다. 보기 모드는 명시적 적용·재로드와 모드별 데이터 분리를 유지한다. BSP 설정 저장, GUI 프로파일/명령/Suite 저장, 브라우저 보기 모드 적용은 각각 기존 저장 범위를 유지한다.

접기·펼치기는 키보드와 보조기술로 조작 가능해야 하며 접힌 잘못된 입력을 저장하면 해당 영역을 열고 입력 위치를 안내한다. Test 현황과 전체 설정에서만 해당 화면의 조회/heartbeat를 활성화하고 중복 타이머를 만들지 않는다. 설정 편집·화면 이동은 실행을 시작·중단하거나 기존 작업 snapshot을 변경하지 않는다.

## 실행·검토 기록

### RQ-55 초기 실행과 정적 리뷰

별도 Luna Low 실행의 `.local-reports/settings-sync-20261106/104929770/`에서 `npm.cmd run build --prefix apps/web`와 `npm.cmd run build --prefix apps/gui-test`는 각각 exit0이다. 새 `settings-sync.spec.ts` 최초 실행은 Playwright 기본 브라우저 캐시가 없어 7개 모두 페이지 실행 전 실패(exit1)했다. 설치된 Chrome을 `BSP_BROWSER_EXECUTABLE`로 지정한 재실행은 **4 PASS / 3 FAIL, exit1**이다. T-169/173은 잘못된 JSON의 검증 문구가 label 이름에 추가되는 선택자 오류, T-175는 option의 암시적 value를 명시적 HTML 속성으로 찾은 시험 오류였다. 별도 시험 작성자가 기존 검증을 유지하며 선택자를 수정했고 비활성 조회·접기 저장소 실패·중복 ID 검증을 보강해 9개 시험으로 확장했다. 수정 후 재시험은 아직 NOT_RUN이다.

새 독립 Sol High의 RQ-55 정적 코드 리뷰는 **APPROVED**다. 시험 실행·시각 검증을 대신하지 않으며 RQ-56의 후속 소스 변경은 별도 최종 리뷰 대상이다. 전체 로그·스크린샷·manifest는 `.local-reports/`의 고유 실행 폴더에 로컬 전용으로 보존하며 Git에 포함하지 않는다. 실패와 재시험은 별도 실행으로 추가한다.

### RQ-56 설계와 구현 범위

추가 요구 분석 Astra XHigh, 구조 Astra XHigh, 상세 Astra High를 수행했다. Manager 소유 소스 서비스가 서버 폴더/관리 Git 저장소에서 불변 snapshot을 준비하고 적용 버전·실제 ref/commit을 영속화한다. Windows 실행기에는 선택적 snapshot capability와 인증된 전송 경로를 추가하며 기존 공유 소스·자동 퓨징의 Host.root는 유지한다. 같은 목록을 보여주고 다른 파일을 실행하는 fallback을 금지한다. 실제 원격 저장소 대신 임시 로컬 Git·모의 전송으로 검증할 예정이다.

### 소스 통합 중간 실행·독립 검토

별도 Luna의 `.local-reports/settings-sync-20261106/110151656-source/`에서 두 UI 빌드는 exit0이다. Python 최초 기본 TEMP는 접근 거부로 중단됐고, 저장소 내부 TEMP로 바꾼 실행은 **26 PASS/14 FAIL**이었다. 일반 폴더 fixture가 저장소 안의 Git 하위 폴더가 된 것이 12건의 원인이었다. 저장소 밖의 별도 TEMP에서 실행한 **43 PASS/2 FAIL**은 이 원인을 확인했다. 남은 두 건은 실제 HTTPS를 로컬 Git으로 치환한 mock이 production의 file protocol 금지에 걸린 시험 경계 문제였으며 시험 mock에서만 로컬 전송을 허용했다. production의 경로 판별·protocol 제한은 유지한다.

브라우저 중간 실행은 **12 PASS/3 FAIL**이다. 새 소스 시험 6개는 모두 통과했고, 기존 설정 시험의 오류 도움말 label 결합과 취소한 초기 요청의 재시도 횟수 기대값을 수정했다. 입력 보존·포커스·한 번의 성공 초기화·비활성 polling 금지 검증은 유지한다. 이 실패들은 최종 성공으로 덮지 않고 각 실행 로그에 보존한다.

새 독립 Sol High의 전체 RQ-56 및 RQ-55 통합 정적 리뷰는 **APPROVED**다. 리뷰 중 REG-0062의 Windows 디렉터리 접두어 대소문자 충돌, REG-0063의 legacy 복귀 API 종류 누락을 수정하고 독립 재확인 exit0을 받았다. 원래 재현은 `.local-reports/source-review-20261106-casing/full.log`, 재확인은 `.local-reports/source-review-20261106-final/full.log`에 로컬 전용 보존한다. 별도 시험 작성자가 manifest 생성/수신 양쪽의 접두어 충돌 방지 시험을 추가했다. 수정 후 최종 전체 실행 결과는 아래에 추가한다.
