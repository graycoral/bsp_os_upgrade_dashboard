# Agent Monitor 플러그인 중심 설계 · 2026-11-14

기준 `e4f53ca1ec288feb3eb1b9ccff8335a398ad321c`. 사용자 요청은 기능별 절차·인터페이스를 순서대로 확인하고 문서를 갱신하는 것이다. 제품명 Agent Monitor, 설명 bsp-os-upgrade를 확인했다.

새 [협의 문서](../../design/PLUGIN_CENTRIC_INTERFACE_PLAN.md)에 확정된 방향, 기능 확인 순서, F01 서비스 준비 절차 제안과 기존 인터페이스 접점을 기록했다. 관련 문서에 현재 계약/목표 변경 구분과 링크를 추가했다. 최초 설치 범위 및 상세 API는 사용자 확인 대기다.

제품 코드·DB·사용자 설정 변경 없음. 외부 서비스 시작·장비 실행·회사 적용·커밋·푸시는 수행하지 않았다. 제품시험 NOT_RUN, 독립 리뷰 NOT_REVIEWED. 문서 검증 결과는 아래에 추가한다.

문서 검사 PASS: 상대 링크 1,312개, 기존 요구사항 66개·시험 239개 정합성, 오류 0. `git diff --check` PASS. 실행 원문은 `.local-reports/plugin-centric-design-20261114/docs.json`에 보관한다. 이 결과는 문서 참조 검사이며 새 기능의 제품시험 PASS가 아니다.

F01-Q1 후속: 사용자 최소 개입·필요 구성 요소 자동 설치 결정을 반영했다. 초기 문서의 설치 범위 확인 대기는 이 답변으로 해소했다. 설치/서비스 준비/조회 인터페이스를 제안했고 작업 수명 F01-Q2는 확인 대기다. 제품 코드 변경·실제 설치 없음.

F01 후속 문서 검사 PASS: 상대 링크 1,314개, 오류 0; git diff --check PASS. 원문 `.local-reports/plugin-centric-design-20261114/docs-f01.json`. 제품시험은 계속 NOT_RUN이다.

F01-Q2/F04/F07 후속: 창 종료 후 TC 지속·기본 600초·세 편집 경로를 사용자 확정으로 반영했다. 현재 timeout DB/실행 감독 코드와 비교하고 장애 후 후속 TC 보류는 제안으로 구분했다. 제품 코드·설정 값은 아직 변경하지 않았고 제품시험 NOT_RUN이다.

제한시간 후속 문서 검사 PASS: 상대 링크 1,321개, 오류 0; git diff --check PASS. 원문 `.local-reports/plugin-centric-design-20261114/docs-timeout.json`. 제품시험 결과와 구분한다.

F07-Q1 후속: 첫 TC 실패 시 후속 TC 수행 중단·플러그인 분석을 사용자 확정으로 반영했다. 이전 보드 상태 확인 후 사용자 재실행 제안은 대체됐다. 후속 배정 차단·근거 보존·분석 요청 보관은 처리 절차 제안이며, 분석 후 재실행/재개 조건과 병렬 실행 영향은 확인 대기다. 제품 코드·DB 변경 없음, 제품시험 NOT_RUN, 독립 리뷰 NOT_REVIEWED.

실패 분석 후속 문서 검사 PASS: 상대 링크 1,323개, 오류 0; git diff --check PASS. 원문 `.local-reports/plugin-centric-design-20261114/docs-failure-analysis.json`. 제품 동작 검증과 구분한다.

F03/F04/F06 후속: 자동 플래싱 전체 흐름·사람 개입 없는 진행과 Agent Monitor/ACON/보드 커넥터 상호 연동·커넥터 설정 변경을 사용자 확정으로 반영했다. Windows 어댑터/FlashService의 기존 실행 절차와 ACON 문서의 미확정 접점을 대조했다. 공통 설정·상태 전달 상세와 분석 후 재실행은 제안/확인 대기로 유지한다. 제품 코드·DB 변경 없음, 제품시험 NOT_RUN, 실제 회사/ACON/장비 인수 NOT_RUN, 독립 리뷰 NOT_REVIEWED.

플래싱·상호 연동 후속 문서 검사 PASS: 상대 링크 1,330개, 오류 0; git diff --check PASS. 원문 `.local-reports/plugin-centric-design-20261114/docs-flash-interop.json`. 제품/회사 연동 검증을 뜻하지 않는다.

2026-11-14 전달 안내 후속: PORT-007/009에 플러그인 중심 변경 범위·기존 고정 코드와의 차이·새 코드 커밋 미정·시험 NOT_RUN을 반영했다. 플러그인 담당자의 진입 문서는 BSP_UPGRADE_PLUGIN_REQUEST이며 최신 읽기 순서와 설계 검토 요청문을 추가했다. 사용자 추가 지시로 전체 요구사항 완성 후 별도 세션에서 effort를 한 단계 높인 독립 리뷰와 지적 반영을 예정했다. 전체 리뷰는 아직 NOT_RUN / NOT_REVIEWED이며 제품 코드·DB·설정·게시 변경 없음.

포팅/플러그인 전달 문서 검사 PASS: 상대 링크 1,350개, 오류 0; git diff --check PASS. 원문 `.local-reports/plugin-centric-design-20261114/docs-porting.json`. 전체 요구사항 독립 리뷰는 아직 수행하지 않았다.

코드 재사용 전달 후속: 사용자는 플러그인에서 코드를 그대로 복사해 사용할 수 있도록 요구했다. 기존 PluginClient의 core/httpx 의존성과 소스 내보내기/headless staging을 확인하고, 의존 소스·설치 진입점·시험 동봉 및 원본 저장소 없는 폴더에서의 독립 검증을 설계·PORT-007·플러그인 요청서에 완료 조건으로 추가했다. Agent Monitor의 플러그인 설치/관리 관계와 상주 서비스·Windows 커넥터의 별도 수명을 구분했다. 새 전달 검증 NOT_RUN, 제품 코드·배포물 변경 없음.

코드 재사용 전달 문서 검사 PASS: 상대 링크 1,353개, 오류 0; git diff --check PASS. 원문 `.local-reports/plugin-centric-design-20261114/docs-source-reuse.json`. 복사본 실행·새 기능 제품시험은 수행하지 않았다.
