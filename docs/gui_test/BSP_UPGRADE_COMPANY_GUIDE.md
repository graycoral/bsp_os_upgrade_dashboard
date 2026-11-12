# 회사 BSP 업그레이드 플러그인 GUI Test 적용 및 사용 안내

전체 대시보드와 보드 커넥터 GUI를 함께 쓰는 구성은 [연동 절차와 연결도](TEST_BOARD_CONNECTOR_GUI.md#플러그인대시보드-연동)를 따른다. 아래 standalone 서비스 설치 절차는 별도 서비스 구성을 사용할 때 적용한다.

후속 편집 가능한 Runner 전달은 [PORT-008](../porting/PORT-008.md)과 [실행 안내](WINDOWS_RUNNER_EDITABLE.md)를 따른다. 회사 담당자는 실제 경로, 플러그인 등록 및 UI hook을 연결하고 재사용 백엔드는 원본 계약을 유지한다. 수정한 Runner 소스는 재시작으로 반영하고 필요하면 재포장한다. 회사 PC에서 Runner pip 설치는 필요 없다. 로컬 검증을 완료했으며 실제 회사 인수는 별도다.

플러그인 개발자는 [연동 요청서](../agents/BSP_UPGRADE_PLUGIN_REQUEST.md)와 [연동 설계 §13–14](../design/BSP_UPGRADE_PLUGIN_INTEGRATION.md)를, 대시보드 이식 담당자는 [PORT-007](../porting/PORT-007.md)과 새 Runner의 [PORT-008](../porting/PORT-008.md)을 확인한다. Linux 백엔드는 별도 프로세스로 실행하며 기존 API는 유지한다. 최초 `setup.cmd`, 일상 `launch.cmd`, 장애 시 `diagnose.cmd`를 사용하고 `src/`의 `.py` 수정 후 재시작한다. 재배포에는 `repack.cmd`를 사용한다. 전체 재빌드에 필요한 입력 ZIP은 폴더 구조를 유지해 풀고 그 루트를 `-Offline -CachePath`에 지정한다.

이 안내는 회사 환경에 적용할 담당자를 위한 작업 안내다. 원본 로컬 구현과 모의 검증을 수행했으며 공개 인터페이스는 [연동 설계 §13–14](../design/BSP_UPGRADE_PLUGIN_INTEGRATION.md), 검증 결과와 고정 소스 커밋은 [PORT-007](../porting/PORT-007.md)이 기준이다. 회사 플러그인 적용과 실제 장비 인수 T-209는 별도다. 기존 회사 전달 묶음의 `repository-source.zip`은 이 안내서와 전체 추적 소스를 제공한다. 기존 묶음의 패치는 `feature-code.patch`이며 최신 편집 Runner 전달 묶음은 PORT-007 차이 `bsp-integration-code.patch`와 기준 0178부터 Runner 코드까지의 `editable-runner-code.patch`를 제공한다. 회사 기존 기능과 비교해 선택적으로 적용한다. 내부 `SHA256SUMS.json`과 `source-provenance.json`으로 구성물과 구성별 커밋을 확인하고 외부 전달 ZIP은 별도 `.zip.sha256`과 `.zip.provenance.json`으로 확인한다.

## 담당자별 읽기 순서

| 담당 | 먼저 읽을 문서와 할 일 |
|---|---|
| 사용자·운영자 | 이 문서의 최초 준비, 일상 사용, 장애 대응과 [연동 설계 §7·9·10·12](../design/BSP_UPGRADE_PLUGIN_INTEGRATION.md)를 읽고 회사 환경과 승인 범위를 확인한다. |
| 회사 플러그인 개발자 | [플러그인 요청서](../agents/BSP_UPGRADE_PLUGIN_REQUEST.md)의 담당별 안내, [연동 설계 §3–5·11·13–14](../design/BSP_UPGRADE_PLUGIN_INTEGRATION.md), 아래 클라이언트 연결을 읽는다. |
| 대시보드·백엔드 이식 담당자 | 회사 필수 지침, [PORT-007](../porting/PORT-007.md), 회사 `COMPANY_MAP.md`와 `APPLIED.md`, [연동 설계 §2·6–11·13–14](../design/BSP_UPGRADE_PLUGIN_INTEGRATION.md), 관련 코드와 시험 순으로 확인한다. |
| Windows Runner 담당자 | [PORT-007](../porting/PORT-007.md), [연동 설계 §7–10·13–14](../design/BSP_UPGRADE_PLUGIN_INTEGRATION.md), [자동 퓨징 계약](../design/AUTOMATIC_FLASH_TEST.md)과 회사 장비 정책을 확인한다. |

## 전달과 최초 환경 준비

1. 원본 담당자는 고정 구현 커밋, 검증된 Linux GUI 전용 백엔드 소스 또는 설치 패키지, 선택 UI, 별도 Windows Runner 설치물과 체크섬·시험 근거를 전달한다. 회사 플러그인 코드와 회사 설정은 이 저장소에서 확인되지 않는다. 회사 기존 코드와 차이를 비교하고 `COMPANY_MAP.md`에 대상 위치와 보존할 기능을 적는다. 파일 전체 덮어쓰기를 기본 적용 방법으로 사용하지 않는다.
2. Linux 플러그인 설치에 백엔드를 포함하고 회사 서비스 관리자로 별도 상주 프로세스를 구성한다. 설치된 서비스가 이미 같은 runtime으로 동작하면 재사용하며 플러그인 호출 종료나 브라우저 종료로 중지하지 않는다. Windows Runner는 별도 Windows 호스트에서 상시 실행하고 SSH 연결을 준비한다. 대시보드 UI는 선택 사항이다.
3. 최초 배포 시 회사의 installer 허용 루트, 전체 TC 소스 루트, 기본 보드와 COM, 저장된 TC 명령 프로파일과 revision, runtime·패키지·설정·Runner identity, SSH 및 서비스 계정을 설정한다. `config/integration.example.json`과 설치물의 `INSTALL.md`를 기준으로 `gui-test.json`의 `runner=windows-http` 및 `integration`을 구성한다. 서비스와 Runner 토큰은 각 서비스 계정의 보호된 환경 설정에 별도로 제공하고 코드·공유 문서·로그에 넣지 않는다.
4. Windows 담당자는 회사의 승인된 COM splitter에서 제어 포트와 RX 전용 관찰 포트를 분리하고, 보드별 fastboot 장치 매핑 및 준비 상태를 확인한다. BAT는 이미지 묶음과 함께 등록하고 최초 등록 또는 변경 시 등록 hash, 대상 serial 선택, 실패 시 0이 아닌 종료 코드와 성공·실패 marker를 확인한다. 실제 보드, BAT, TC와 splitter 호환성은 회사 환경에서 확인해야 한다.
5. 플러그인의 연결/진단 동작으로 서비스 identity, worker와 Runner 연결을 확인한다. 이 동작은 장비를 점유하지 않지만 필요하면 설치된 서비스를 기동한다. Runner 연결 준비는 보드 부팅이나 TC 준비 성공을 뜻하지 않는다. 이후 모의 인수와 영향 회귀를 실행해 결과를 기록하고, 실제 장비 인수는 별도 승인 범위에서 진행한다. 회사 적용 커밋·범위·결과·남은 제약은 `APPLIED.md`에 기록한다.

소스 내 패키징 옵션은 아래와 같다. 이는 **재생성 명령 템플릿**이며 실제 전달 설치물 이름과 체크섬은 PORT를 따른다. UI 포함은 사전에 UI 빌드가 필요하다. Windows Runner 설치물은 별도로 제공한다.

```sh
python apps/gui-test/package.py --integration --output <확인된-출력경로>
python apps/gui-test/package.py --integration --include-ui --output <확인된-UI포함-출력경로>
python apps/gui-test/package.py --stage-headless-wheel <비어있는-스테이징-경로>
```

설치된 wheel의 import 경로는 `gui_test`, 원본 소스에서 직접 연결할 때는 `backend.gui_test`다. 서비스 실행 인자는 `python -m gui_test.standalone.integration --runtime <영속-runtime-경로> --port <포트>`이며 선택적으로 `--principal`과 `--static-dir`을 사용한다. 회사 서비스 계정·경로·기동 명령은 실제 설치물에서 검증한다.

## 회사 플러그인 연결

원본 `standalone/plugin_client.py`의 `PluginClient`, `PatternDefaults`, `SystemdService`를 재사용한다. 회사 플러그인은 설치 hook, 서비스 시작 연결, 설정 저장소, 버튼과 결과 표시를 회사 구조에 맞게 구현한다. 공통 GUI Test 엔진, 예약·전송·퓨징·재시도·결과 집계를 복제하지 않는다. 대시보드 이식 담당자는 공통 코어와 Windows 계약을 함께 반영하고 인증·서비스·API mount 등 회사 접점만 조정한다. 부분 반입 조건은 PORT-007을 따른다.

- 모듈별 기본 TC 패턴과 전역 기본값을 저장하고 `PatternDefaults.suggest(module_key, override=None)`로 제안한다. 이번 실행의 편집과 기본값 저장을 구분한다. 동시 설정 작성자가 있으면 회사의 트랜잭션 저장소를 사용한다.
- `PluginClient(url, token, expected_identity, starter=..., log_dir=..., diagnostic_callback=...)`에 loopback 주소, 보안 저장소에서 읽은 토큰과 고정 identity를 제공한다. identity에는 `runtime_id`, `package_version`, `config_revision`, `runner_id`가 필요하다. `SystemdService`는 설치된 고정 unit을 시작하며 요청 수명에 서비스 중지를 연결하지 않는다.
- 최초 설치 시 회사 설치 담당자는 신뢰할 수 있는 loopback 서비스와 서비스 계정의 소유권을 확인해 기동한 뒤, 보호된 토큰으로 인증된 `GET /api/v1/health` 응답을 읽는다. 응답의 네 identity가 배포하려는 runtime·패키지·설정·Runner와 일치하는지 확인하고 비밀이 아닌 네 값만 회사 설정 저장소에 고정한다. 이는 최초 신뢰 설정이며 별도 registry 파일을 전제하지 않는다. 이후 연결에서 불일치가 발생하면 값을 자동으로 덮어쓰지 말고 설치 및 구성 차이를 조사한다. 토큰은 문서나 identity 저장소에 기록하지 않는다.
- `connect()`로 연결 상태를 표시한다. `preview(installer_path, patterns)`와 `preparation(preparation_id)`로 선택적 미리보기와 준비 상태를 표시하고 일치 TC 및 순서를 사용자가 확인·수정할 수 있게 한다. 준비 토큰은 선택 사항이다.
- `start(key, installer_path, patterns, prepared_token=None)`에 Linux의 완료된 installer BAT 경로, 최종 TC 패턴과 실행 의도별 안정적인 멱등 키를 전달한다. 응답의 `id`를 저장하고 `run(run_id)`로 조회한다. 응답 유실이나 재접속 시 같은 키와 Run ID를 유지한다. 202 접수는 시험 성공이 아니다. 기존 보고서에서 결과와 시도 이력을 확인한다.
- 상세 화면이 설치된 경우 `browser_access()`가 반환하는 `url`로 선택적 읽기 전용 화면을 연다. 서비스 bearer token을 브라우저 주소나 저장소에 넣지 않는다. 브라우저 화면은 실행 제어 수단이 아니다.

## 일상 사용과 장애 대응

환경 준비 후 사용자는 플러그인에서 완료된 이미지 폴더의 BAT 경로와 작업 모듈을 지정한다. 저장된 패턴이 제안되며 필요할 때 미리보고 이번 실행에서 수정할 수 있다. 시작 후 플러그인에서 Run 진행과 보고서를 확인한다. 매 TC나 동일 BAT마다 재승인을 요구하지 않는다. 완료된 이미지 묶음은 준비 중 수정하지 않는다. 실제 장비 실행은 별도 승인된 범위에서만 수행하며 최종 사람 검토는 유지한다.

연결 실패는 Run 생성 전에도 표시한다. `diagnostic_callback`, `last_diagnostic` 또는 오류의 `diagnostic`에서 correlation ID, 단계, 오류 코드, 원인, 조치와 로그 경로를 표시한다. 기본 파일은 실행 계정의 `~/.bsp-upgrade/gui-test-logs/connections.jsonl`이며 `log_dir`로 변경할 수 있다. 플러그인과 백엔드 계정이 다르면 각각의 경로와 correlation ID를 연결한다. 백엔드가 내려가도 플러그인 측 진단을 남기며 로그 기록 실패도 원래 연결 오류와 함께 표시한다. 토큰·비밀번호·환경 전체·원시 예외를 기록하지 않는다.

연결이 복구되면 기존 키와 Run ID로 상태를 확인한다. 장비 실행 종료를 증명할 수 없는 `UNKNOWN`은 물리 상태 확인과 정해진 조정 절차가 필요한 예외다. 데이터 삭제나 강제 예약 해제를 자동 복구로 취급하지 않는다.
