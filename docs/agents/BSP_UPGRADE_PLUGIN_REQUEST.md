# 회사 bsp-upgrade 플러그인 연동 요청서

후속 편집 Runner 인계는 [PORT-008](../porting/PORT-008.md), [실행 안내](../gui_test/WINDOWS_RUNNER_EDITABLE.md)를 따른다. 회사 고유 경로·플러그인 등록·UI hook은 회사에서 연결하며 재사용 백엔드 기능과 계약은 유지한다. 실제 회사 인수는 별도다.

RQ-60 / D-64 · 2026-11-07 · **원본 로컬 구현·모의 검증 / 회사 적용 별도**

재사용 backend·Runner·참조 client·headless/선택 UI 패키징의 고정 소스 커밋은 `1a18ea6fab8b1caead3935ce70cb1e30153d631b`이다. 현재 공개 진입점과 CLI·브라우저 인증·연결 실패 로그는 [설계 §13~14](../design/BSP_UPGRADE_PLUGIN_INTEGRATION.md#13-후속-구현의-공개-진입점과-선택-화면)를 따른다. 로컬 모의 검증과 회사 인수 상태는 PORT-007과 실행 기록을 따른다. 회사 private 플러그인 적용과 실제 장비 인수 T-209는 별도이며 NOT_RUN이다.

회사 plugin 코드는 새 실행 엔진을 작성하지 않고 `standalone.plugin_client.PluginClient`를 기존 HTTP/설치 adapter에 매핑한다. 연결 버튼/시작 준비에서는 `connect()`, 모듈 기본값은 `PatternDefaults.suggest` 또는 회사 설정 저장소와 동일한 `resolve_patterns`, 실행에는 stable key를 보관한 `start`, 상태에는 `run(id)`, 선택 상세 화면에는 `browser_access()`를 사용한다. 소스 import는 `backend.gui_test`, wheel import는 `gui_test`다. `diagnostic_callback`과 `last_diagnostic`을 상태 UI에 표시하고 `log_dir`를 회사 로컬 로그 정책 경로로 지정한다. 연결 실패의 correlation ID·원인·조치·로그 경로가 API 수락 전에도 보이도록 유지한다. 실제 private plugin 파일 위치는 COMPANY_MAP에 기록한다.

아래 요청문은 회사 플러그인 담당자에게 범위와 연결 책임을 전달하기 위한 것이다. API·데이터·흐름의 원문은 [연동 설계](../design/BSP_UPGRADE_PLUGIN_INTEGRATION.md), 전달 상태는 [PORT-007](../porting/PORT-007.md)을 따른다. 요청문에 API 스키마나 결과 형식을 따로 복제하지 않는다.

## 담당별 읽기와 구현 순서

| 담당 | 읽을 문서·절 | 구현/적용할 범위 |
|---|---|---|
| 회사 플러그인 개발자 | 이 요청서 → 연동 설계 §1 확정 경계, §3 서비스 수명, §4 요청/조회, §5 패턴/준비 token, §11 책임, §12 예외 | 모듈 기본값 저장, 미리보기/편집, 서비스 health/start adapter, 멱등 키·준비 token·Run ID 저장, 기존 결과 링크. 새 퓨징/TC 엔진은 만들지 않는다. |
| 회사 대시보드/백엔드 담당 | PORT-007 → 회사 COMPANY_MAP/APPLIED → 연동 설계 §2 현재 소스, §6~10 실행/안전/저장, §11 패키징 | 검증된 원본 API/core/Windows adapter를 재사용하고 회사 인증·서비스·DB/runtime·선택 UI mount를 연결한다. |
| 회사 배포/장비 담당 | 연동 설계 §3, §6~7, §9~10, §12와 PORT-007 인수 조건 | 기본 보드/COM·TC 명령/소스, BAT 등록·타깃/실패 전파, 터널·Runner·splitter·권한 설정. T-209 실제 환경 인수. |

회사 플러그인 코드는 현재 이 저장소에서 확인할 수 없으므로 설치 hook·사내 구조는 회사 adapter에서 연결한다. 사용 순서는 [PORT-007의 절차](../porting/PORT-007.md#회사-적용과-사용-순서)와 [회사 안내서](../gui_test/BSP_UPGRADE_COMPANY_GUIDE.md)를 따른다.

## 전달할 요청문

```text
회사 Linux에서 사용하는 bsp-upgrade 플러그인에 GUI Test 연동을 준비해 주세요.
원본 구현과 로컬 모의 검증을 수행했으며 회사 적용과 실제 인수는 별도입니다.
고정 소스와 검증된 최종 전달물의 상태를 PORT-007에서 확인해 주세요.
회사의 필수 지침을 먼저 확인하고 원본 문서의 확정 요구,
제안 기본값, 현재 구현된 동작을 구분해 주세요.

기준 문서:
- docs/design/BSP_UPGRADE_PLUGIN_INTEGRATION.md
- docs/porting/PORT-007.md

플러그인 설치물에는 이 저장소에서 구현·검증할 GUI Test 백엔드와
선택적 GUI 화면을 포함합니다. 실행 엔진은 기존 GUI Test를 재사용하고,
플러그인은 서비스 확인·기동과 HTTP 요청/조회에 집중해 주세요.
백엔드/worker·SSH 터널·Windows Runner는 플러그인 호출이나 브라우저가
끝나도 유지되어야 합니다. 같은 runtime에 worker를 중복 기동하지 마세요.

플러그인에서는 Linux installer BAT 경로와 최종 TC 패턴을 전달합니다.
모듈별 기본 TC 패턴과 전역 기본값을 저장하고 안정적인 모듈 키로 추천해 주세요.
사용자는 실행 전 패턴·일치 TC·순서를 미리 보고 변경할 수 있어야 하며,
실행마다 별도 승인 창을 강제하지 마세요. 이번 실행의 변경과 기본값 저장을
구분하고, 재조회로 사용자 편집을 덮어쓰지 마세요. 미리 본 파일과 설정은
준비 token으로 시작 요청에 연결하고, 미리보기 없는 요청도 같은 준비를
자동 수행하도록 해 주세요. token 오류 때 다른 파일로 조용히 바꾸지 마세요.

실제 COM·보드·TC 실행 명령·TC 소스 루트·Runner 주소는 서비스 설정을
재사용합니다. 플러그인에서 임의 셸 명령·COM·비밀정보를 요청 본문으로
전달하지 마세요. 플러그인 모듈 정보는 추천용이며 내부 BSP의 운영
module_context나 장비 시험 완료 권한으로 사용하지 마세요.

시작은 비동기 HTTP 요청으로 하고 반환된 기존 Run 식별자를 저장합니다.
응답 유실·재접속에는 같은 멱등 키를 사용하고, 기존 Run 조회와 보고서를
재사용해 주세요. 콜백·별도 결과 포맷·플러그인의 PASS 등록 API는 필요 없습니다.

installer 폴더 전체 복사, TC 루트 전체 의존성 전달, 사전 검사와 장비 예약,
reboot lkshell → fast → BAT → 새 로그인 프롬프트 → TC 로그인,
최대3회/PASS2 정책과 panic/부팅 실패 중단은 백엔드 구현 책임입니다.
플러그인에 이를 중복 구현하지 마세요. 자세한 판정·예약·로그 계약은
연동 설계 원문을 사용해 주세요.

GUI 전용 연동 호스트와 Windows adapter를 고정 원본에서 재사용하고,
수정된 퓨징 감독 경로와 전체 batch 예약 계약을 함께 반입해 주세요.
실제 공개 진입점과 제한은 연동 설계 §13~14를 확인해 주세요.

회사에서는 설치 hook·서비스 관리자·인증·허용 경로·기본 보드·COM,
저장된 TC 명령·TC 루트·실제 모듈 매핑·터널과 Runner의 지속 실행,
승인된 RX-only COM splitter 및 실제 BAT/TC의 준비 조건을 확인해 주세요.
BAT는 처음과 변경 시에 타깃 serial 준수·실패 전파를 등록하고 이후 동일
스크립트는 자동 hash 검증합니다. 매 TC마다 사람 승인을 반복하지 마세요.
비밀정보는 회사의 로컬 보안 설정으로 관리하고 공유 문서에 쓰지 마세요.

회사 구조 차이는 COMPANY_MAP.md에, 적용 범위·커밋·검증·미완료는
APPLIED.md에 기록합니다. 기존 회사 기능과 설정을 보존하세요.
회사 적용과 실제 장비 인수는 각각의 검증 증거가 생길 때 기록해 주세요.
```

## 담당자 간 전달물

| 원본 저장소 담당 | 회사 플러그인/호스트 담당 |
|---|---|
| 기존 엔진에 연동 API·headless 호스트·준비/퓨징/정책·로그를 구현하고 계약 시험 제공 | 설치·서비스 조립 차이와 플러그인 설정/화면/HTTP 호출 구현 |
| Linux 백엔드와 선택 UI, 별도 Windows Runner의 검증된 패키지·manifest·고정 커밋 제공 | 회사 의존성/인증/보드/COM/소스/실제 명령·splitter 조건 확인 |
| T-200~208 로컬·모의 결과와 미검증 범위 기록 | 영향 회귀와 T-209 실제 회사 인수 기록 |
| 계약 원문·PORT 갱신 | COMPANY_MAP/APPLIED의 회사 대응·적용 이력 갱신 |

원본의 로컬·모의 검증 결과와 최종 산출물 상태는 PORT-007을 따른다. 실제 회사 인수 T-209는 NOT_RUN이다. 첫 배포 설정과 실제 UNKNOWN 장비 복구는 필요하지만 정상 실행·같은 BAT·각 TC마다 반복 승인을 요구하지 않는다. 회사 전달물 `dist/BSP-GUI-Test-Company-20261107.zip` 안의 `bsp-upgrade-integration-20261107/` 폴더에는 `repository-source.zip`, `bsp-gui-test-integration.zip`, wheel, `BSP-Windows-Runner.zip`, `feature-code.patch`, `START_HERE.md`, `SHA256SUMS.json`, `source-provenance.json`과 선택 검증 로그가 포함된다. 압축 해제 후 `repository-source.zip`의 `docs/gui_test/BSP_UPGRADE_COMPANY_GUIDE.md`부터 읽는다. 회사 대시보드 담당자는 전체 소스를 참고하고 기존 회사 기능과 비교한 뒤 patch의 선택적 반영 여부를 결정한다. 세 설치물의 checksum은 PORT에 있으며 전체 전달물 검증은 동봉 checksum과 출처 기록을 따른다.
## 2026-11-12 · Runner 설정 편의 후속 적용

[PORT-008 후속](../porting/PORT-008.md)의 RQ-62 소스·해시·시험을 확인한다. 플러그인의 HTTP 요청 형식은 유지한다. 전달하는 편집 Runner의 `src/scripts/setup_flashing.py`를 선별 갱신하고, 회사의 다운로드 버전/체크섬 pin이 있는 경우 검증된 새 전달물 기준으로만 바꾼다. 원본 후속 코드는 `55447f87f3241df76a7a110c130252b73b29c941`로 고정했고 새 배포 ZIP은 생성하지 않았으므로 기존 릴리스 pin을 임의로 변경하지 않는다.

회사 설정은 `fastboot init success`를 fast 이후 로그로 구분하고, BAT 자동 리부팅 후 `**** login : `의 `login :`를 `login_prompt`와 observer `login_markers`에 일치시킨다. TC는 해당 프롬프트에서 `root` 로그인을 담당한다. Runner가 TC 전에 로그인하지 않는다. 실제 lkshell 프롬프트·TC 로그인 처리·observer boot/panic 값은 회사에서 확인하며, 사용자 제공 문구만으로 실장비 인수 PASS를 기록하지 않는다. 프로파일을 바꾸면 Runner 정상 재시작과 새 미리 보기가 필요하다. 웹 재빌드만으로 Runner를 교체하지 않는다.

## 2026-11-13 연결 토큰 제거 후속

현재 참조 PluginClient는 연결 토큰 없이 loopback 서버를 호출한다. 회사 적용 시 서버·Windows 커넥터·플러그인 클라이언트를 함께 갱신한다. 경로·identity·멱등 키·Run 소유권은 유지한다. 변경 파일·적용 조건·검증 범위는 [PORT-009](../porting/PORT-009.md)를 따른다. 회사 플러그인 UI의 실제 적용 여부는 별도로 확인한다.
