# PORT-007 · BSP 업그레이드 플러그인과 GUI Test 연동

2026-11-12 표시명 후속: Windows Runner의 사용자 표시명을 **TEST BOARD CONNECTOR**로 바꾼다. 참조 PluginClient의 진단 메시지와 서비스 패키지 안내만 변경하며 연결 URL·요청/응답 필드·capability·runner identity·설정 경로는 유지한다. 회사 플러그인의 메뉴/설정에 이전 표시명이 있으면 회사 구조를 확인해 같은 이름으로 맞춘다. 명칭 후속 적용 기준은 [PORT-008](PORT-008.md)과 [명칭 검증 기록](../testing/runs/20261112-board-connector-name.md)이다.

## 2026-11-12 후속 · Runner 설정/배포 안내

[PORT-008 후속](PORT-008.md)의 대상 `55447f87f3241df76a7a110c130252b73b29c941`에서 Windows 설정 탐색/공통 입력 및 integration 패키지의 `INSTALL.md` 안내를 갱신했다. HTTP payload·capability·DB·참조 `PluginClient` 코드는 변경하지 않는다. 원본의 plugin pipeline/service/package 모의 회귀를 포함해 62 PASS다. 실제 회사 플러그인 저장소·다운로드 manifest는 현재 작업 범위에서 접근/검증하지 않았다.

회사 적용 담당자는 전달 Runner의 `src/scripts/setup_flashing.py`, 서비스 패키지 안내와 실제 프로파일을 확인한다. fastboot 모드의 `fastboot init success`를 fast 이전 lkshell 준비 문구로 쓰지 않는다. BAT 후 `**** login : `의 `login :`를 `login_prompt`와 observer `login_markers`에 일치시키고 `root` 로그인은 TC에 둔다. 기존 퓨징 전 `login_steps`·RX splitter/boot/panic 설정은 회사 값으로 유지한다. 실제 lkshell 준비 프롬프트와 TC root 로그인 동작은 미확인이다. 프로파일 변경 후 Runner 정상 재시작과 새 미리 보기가 필요하다. 웹 재빌드만으로 Runner를 재설치하지 않는다.

새 EXE는 생성하지 않고 원본 Git의 기존 EXE ZIP·체크섬을 제거했다. 새 편집형 ZIP도 이번에 생성하지 않았으므로 회사 다운로드 버전/해시 pin을 임의로 바꾸지 않는다. 검증된 후속 배포물을 별도로 만들 때만 실제 pin을 맞춘다. 독립 리뷰 NOT_REVIEWED, 회사 T-209/221 NOT_RUN이며 기존 본문의 고정 전달 이력은 보존한다.

후속 편집 가능한 Runner 배포는 [PORT-008](PORT-008.md)을 참조한다. 아래 고정 커밋과 산출물은 당시 PORT-007 이력으로 유지한다.

2026-11-07 기준 **원본 로컬 구현과 모의 검증을 수행했다. 회사 코드 적용과 실제 환경 인수는 별도이며 T-209는 NOT_RUN이다.** 회사 플러그인의 실제 UI, 설치 hook과 저장소는 이 저장소에서 확인되지 않았고 여기서 구현했다고 주장하지 않는다. 실제 장비·모델 실행 승인은 포함되지 않는다.

## 기준과 전달 상태

- 추적: RQ-60 / D-64 / T-200~209. [연동 설계 §13–14](../design/BSP_UPGRADE_PLUGIN_INTEGRATION.md)에 실제 공개 진입점과 연결 진단을 정리한다. [회사 역할별 안내](../gui_test/BSP_UPGRADE_COMPANY_GUIDE.md)와 [플러그인 요청서](../agents/BSP_UPGRADE_PLUGIN_REQUEST.md)를 함께 전달한다.
- 설계 조사 기준 커밋: `476d95f08169d4a4fbb4a999a94d417d9e59cef3`. 대상 구현 소스·시험 고정 커밋: `1a18ea6fab8b1caead3935ce70cb1e30153d631b` (`feature/bsp-upgrade-gui-test`).
- 이전 로컬 검증 이력: `.local-reports/pvt2/integration/bsp-gui-test-integration.zip` SHA-256 `3fead3852d4e08218a4addbd282d68135fe65332094015f19e036af61beaba11`; `.local-reports/pvt2/wheels/bsp_gui_test-0.1.0-py3-none-any.whl` SHA-256 `6ced451a921c7608da311a9d937ea3bf98a06e13d868f76bbcb2827fed80fd57`. 이 ZIP은 기존 사용자 설정 변경을 포함하므로 최종 전달에서 제외한다. 최종 설치물은 고정 커밋의 깨끗한 작업 트리에서 생성했다. 단일 회사 전달 묶음의 전체 파일과 출처는 동봉 `SHA256SUMS.json`, `source-provenance.json`을 확인한다.
- 선행 기능과 회사 차이는 [PORT-003](PORT-003.md), [PORT-004](PORT-004.md), [PORT-005](PORT-005.md), [PORT-006](PORT-006.md) 및 회사 `COMPANY_MAP.md`·`APPLIED.md`로 확인한다. 과거 PASS를 이번 구현의 PASS로 재사용하지 않는다.

| 최종 설치물 | 크기 (bytes) | SHA-256 |
|---|---:|---|
| `bsp-gui-test-integration.zip` | 403885 | `d0ecdadd76afaba7a73d85a50916e399ea77cfa8984adc97b8761b1611e2ff10` |
| `bsp_gui_test-0.1.0-py3-none-any.whl` | 128055 | `576e349cbbd54d67838e97c55d0ad2e293cc8fad778696cdcf853c60de2bd847` |
| `BSP-Windows-Runner.zip` | 27976854 | `e66fc3b20d379f2cb3f2463a9d23b66a447956ac2de03e621c11de23d253ca4c` |

## 재사용 코드와 회사 연결

원본의 `backend/gui_test/` 코어·API·worker·Windows adapter와 계약 시험을 재사용한다. `standalone/integration.py`는 GUI 전용 상주 호스트이고 `standalone/plugin_client.py`는 서비스 기동·진단, 패턴 기본값, 미리보기·시작·Run 조회용 참조 클라이언트다. 원본 import는 `backend.gui_test`, 설치 wheel은 `gui_test`다. `apps/gui-test/package.py`는 integration 소스 묶음과 headless wheel staging, 선택 UI 포함을 제공한다. Windows Runner는 호환 capability를 가진 별도 설치물로 운영한다. 상세 공개 API와 구성은 연동 설계 §13–14가 원문이다.

회사 담당자는 기존 구조를 비교하고 인증·서비스 계정·설치 hook·API mount·설정 저장소·플러그인 UI를 회사 adapter에서 연결한다. 모듈 패턴 추천 및 편집, 안정적인 멱등 키, Run ID 조회와 진단 표시를 회사 플러그인에서 연결한다. 공통 실행 엔진과 예약·전송·퓨징·재시도·결과 집계를 복제하지 않는다. 회사의 실제 대상 파일과 기존 기능 보존 조건을 `COMPANY_MAP.md`에 기록하고 전체 파일 덮어쓰기를 기본 적용 방법으로 삼지 않는다. 부모 batch 예약 등 연관 변경은 기존 Windows GUI 실행·D-48 경로와 함께 적용하며 endpoint만 부분 반입해 준비 완료로 판단하지 않는다.

회사 환경에서는 허용 installer/TC 루트, 기본 보드·COM, 저장된 TC 명령, Runner identity와 SSH, 승인된 RX 전용 splitter, 보드 fastboot 매핑과 등록 BAT 조건을 확인한다. 비밀정보는 회사 보안 설정으로 관리한다. runtime DB·설정·source-storage/integration-inputs 및 보안 자격 증명 참조의 백업과 동일 버전의 별도 runtime 복원 절차를 회사 환경에 맞게 준비한다. 실제 회사 데이터 이전·복원 검증은 **NOT_RUN**이며 구버전 worker로 새 정책 Run을 재개하지 않는다.

## 검증 근거와 제한

독립 실행 기록은 [2026-11-07 실행 기록](../testing/runs/20261107-bsp-upgrade-integration.md)을 참조한다. 현재 전달받은 로컬 결과는 다음과 같다.

- 집중 검증 169 PASS, 전체 backend 494 PASS. 집중 검증은 전체 실행과 중복되는 부분집합이므로 합산하지 않는다.
- Runner/setup 기본 정책 실행은 131 PASS, 7 SKIP, 5 FAIL로 정책 제한이 있었다. process-only Bypass 재실행은 136 PASS, 7 SKIP이다. 원래 실패를 삭제하거나 기본 정책 PASS로 바꾸지 않는다.
- integration ZIP과 wheel 생성, 설치 import 및 UI build PASS. 전체 Dashboard build도 1,612 modules PASS다. 이는 회사 Linux·Windows 실환경 설치나 장비 인수의 증거가 아니다.
- 고정 커밋의 깨끗한 작업 트리에서 Windows Runner를 빌드했고 portable smoke는 10 PASS (`.local-reports/pvt2/portable-runner-smoke.log`)다. T-208의 실제 Linux 설치·복원은 NOT_RUN이다.
- Sol High 독립 코드 리뷰 APPROVED: `.local-reports/rq60-code-review`. 실제 시험 명령과 환경, 개별 ID 판정 및 미검증 범위는 실행 기록에서 확인한다. T-209 회사 Linux/SSH/Windows/장비/TC/splitter 인수는 NOT_RUN이다.

## 회사 적용과 사용 순서

1. 회사 필수 지침, 이 PORT, `COMPANY_MAP.md`·`APPLIED.md`, 관련 코드와 시험 및 필요한 상세 설계를 순서대로 확인한다. 고정 구현 커밋과 최종 설치물·체크섬을 전달받아 검증한다.
2. 회사 백엔드 담당자는 공통 코드·계약을 재사용하고 회사 서비스·인증 접점을 연결한다. 플러그인 담당자는 회사 UI·설정·설치 hook과 참조 클라이언트를 연결한다. 별도 상주 Windows Runner와 Linux 서비스의 수명을 플러그인 요청에 종속시키지 않는다.
3. 회사 환경 사실과 비밀 저장소를 설정하고 플러그인 연결 진단을 확인한 다음 모의 인수와 영향 회귀를 수행한다. 상세 절차는 [회사 역할별 안내](../gui_test/BSP_UPGRADE_COMPANY_GUIDE.md)를 따른다. 실제 장비 시험은 별도 승인 범위에서 실행한다.
4. 일상 사용자는 플러그인에서 완료된 BAT 경로와 모듈을 선택하고 제안 패턴을 필요에 따라 미리보고 수정한다. 같은 실행 의도의 재접속에는 같은 키와 Run ID를 사용한다. UNKNOWN 장비 상태는 물리 확인과 정해진 조정 절차를 따른다.
5. 회사 적용 커밋·범위·시험 결과·잔여 제약을 `APPLIED.md`에 기록한다. 회사 인수, 데이터 복원 및 최종 전달물의 상태는 실제 증거가 생겼을 때 각각 갱신한다.
