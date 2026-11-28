# 플러그인 모듈 후보 목록

RQ-75 / D-82. 플러그인이 게시한 모듈 후보 목록과 사용자가 저장한 모듈·선행 그룹, 기존 작업의 고정 모듈은 서로 다른 데이터다. 후보 수신으로 저장된 선택이나 작업 snapshot을 덮어쓰지 않는다. 세션·모델 응답을 모듈 원본으로 사용하지 않는다.

## 공개 접점

full Agent Monitor의 `GET /api/v1/config/modules`는 `{version, modules}`를 반환한다. 최초값은 `{version:0, modules:[]}`다. `PUT`은 `{expected_version, modules}`를 받으며 각 모듈은 기존 `ModuleSpec`의 `name`, `group`, `target_paths`와 필수 `stable_key`를 사용한다. `group`은 `boot` 또는 `main`이다. 이름과 key는 비어 있지 않고 목록 내 고유해야 하며 최대100개다. 대상 경로는 기존 Profile의 상대 경로 검증을 적용한다.

게시 권한은 `X-Bsp-Service: plugin`, `X-Bsp-Scope: bsp-control-v1`과 기존 runtime/package pin을 가진 비브라우저 클라이언트다. 일반 Dashboard 브라우저와 GUI-only PluginClient는 게시할 수 없다. loopback·origin·identity 제한은 유지한다. GUI-only standalone은 이 API를 제공하지 않는다.

서버는 `dashboard.db`의 기존 `meta` 테이블에 `plugin_module_catalog` JSON을 원자 저장한다. DB schema 이전은 없다. 현재 버전과 `expected_version`이 다르면409 `VERSION_CONFLICT`다. 같은 버전에서 같은 목록을 게시하면 버전을 증가시키지 않는다. 응답을 잃었으면 최신 목록과 버전을 읽고 같은 값인지 확인한다. CAS 충돌을 무조건 덮어쓰지 않는다.

참조 `BspPluginClient.module_catalog()`와 `publish_modules(modules, expected_version=...)`를 사용한다. 회사 플러그인은 자신의 영속 모듈 목록을 `ModuleSpec`으로 매핑해 연결·목록 변경 시 게시해야 한다. 현재 저장소에는 실제 회사 플러그인 저장소나 등록 callback이 없으므로 그 연결은 현지 adapter 작업이다.

## 화면과 저장

- 환경 설정의 모듈 이름과 추가 항목은 플러그인 후보를 선택하는 콤보박스다. 선택 시 이름·stable key·대상 경로와 기본 그룹을 함께 가져오고 그룹은 별도로 선택할 수 있다.
- 3초 single-flight 조회·비활성 중단·복귀 시 조회를 사용한다. 새 목록은 선택지를 갱신하며 편집 중 값은 바꾸지 않는다. 저장은 기존 `/config` version CAS를 사용하고 새 작업부터 적용한다.
- 후보가 삭제되거나 수신되지 않아도 기존 선택을 표시·보존한다. 추가/교체 선택은 목록 조회 성공 시에만 가능하다. 중복 이름/key 선택은 UI와 기존 서버 설정 검증으로 거부한다.
- 기존 작업의 최초 계획 확인·선행 그룹 전체 완료·분석 병렬·수정/빌드 배타 조건은 유지한다. 후보 게시와 설정 저장은 BSP 실행을 시작하지 않는다.

검증·회사 적용은 [이번 기록](../testing/runs/20261118-dashboard-workflow.md), [PORT-012](../porting/PORT-012.md)을 따른다. 외부 모듈 에이전트의 상태·결과 보고 형식은 기존 [보고 계약](AGENT_STATUS_CONTRACT.md)이며 이번 후보 API와 별개다.
