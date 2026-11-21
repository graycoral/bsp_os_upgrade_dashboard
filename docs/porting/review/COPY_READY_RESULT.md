# 03 복사형 전달 패키지 결과

| 필드 | 내용 |
|---|---|
| source_repo/source_commit | graycoral/bsp_os_upgrade_dashboard · `8abe9262716cbcfc287a535094f4fbd940601113` |
| target_repo/target_commit | N/A |
| scope | [원본 감사](PORTABILITY_AUDIT.md) A01~A05, PORT-011/013/014의 전달·버전 확인·설정 CLI. 기존 설치·복구·Windows 배치 재사용 |
| changes | 아래 변경·회귀 표 참조. DB schema·의존성 변경 없음 |
| package_release | `8279480e74f35cf91c1ddec578b096671cd5e28e91bf53abb61fe31fdeaccf18` |
| evidence | [실행 기록](../../testing/runs/20261122-copy-ready-package.md), [회사 스모크](COMPANY_SMOKE_TEST.md), [백업·롤백](ROLLBACK.md) |
| open_questions | 회사 기존 owner·runtime·API 인증/권한·wheel·Windows 실험실은 04 현지 확인 |
| next_task | `04_CLAUDE_OPUS_COMPANY_ASSESSMENT.md`의 대상 repo·현행 적용 상태 및 이 문서의 handoff 대조 |

**03 로컬 전달 게이트 PASS.** 회사 적용·실환경 인수는 `NOT_RUN`이다. 저장소 전체 회귀 결과는 [실행 기록](../../testing/runs/20261122-copy-ready-package.md)에 있다. 시작 기준은 깨끗한 `porting/copy-ready-20261122`의 02 커밋 `0061754`다. 코드와 회사 가이드를 커밋하고 깨끗한 소스로 빌드·내보냈다. 이 결과 문서는 전달물의 해시를 기록하기 위해 export 이후 별도 문서 커밋에 저장한다.

## 전달물 및 검증

- 복사할 폴더 전체 `~/dashboard/deliveries/bsp-plugin-copy-ready-20261122-8abe926`. 루트는 `plugin.py`, `README.md`, `PLUGIN_PACKAGE.json`, `agent-monitor/`로 구성한다. 검증에 사용한 중간 폴더는 이전 실행 기록에 보존한다.
- `PLUGIN_PACKAGE.json` SHA-256 `f8b131462a4d9d235d9ccf4499be828f791dabe790ef7f7bdb76d22c9f36d6d3`
- `agent-monitor/AGENT_MONITOR_SOURCE.json` SHA-256 `4ab2944e70bdd554fd3da0c763ea4369fdc819ce25c0f5ce52ef46dd4b83278d`
- inner의 `source_head`는 위 Git SHA, `source_dirty=false`, `include_ui=true`. inner 505개 등록 파일(트래킹 소스 499개 + 사전 빌드 파일 6개), outer 508개 등록 파일(`PLUGIN_PACKAGE.json` 자체 제외). 각 파일명과 SHA-256은 두 manifest에서 확인한다. Windows descriptor 및 launcher의 release가 동일하며 `agent-monitor/board-connector.bat`가 Windows 기본 진입점이다.
- runtime DB/백업, 사용자 설정, SSH 키, 토큰, venv와 npm 설치 폴더는 전달 목록에서 제외했다. 운영 중 재검증은 동봉 Python 소스에 대응하는 표준 `__pycache__`만 예외로 처리한다. 인수 시 `verify … --pristine`과 별도 채널에서 제공된 두 manifest SHA를 함께 확인한다.

## 수정과 회귀

| 감사 ID | 공통 코드와 회귀 |
|---|---|
| A01 | `delivery.py`에서 Dashboard와 Standalone GUI의 index·참조 JS/CSS를 수집 및 검증한다. 누락된 index/assets 거부, `--without-ui` 보존. `standalone/server.py`는 공급 빌드 경로를 기본 후보로 추가했다. |
| A02 | `delivery.py`가 원본 SHA 및 작업 트리 상태를 기록하고 검증된 manifest를 Git 없는 재복사, 별도 vendor Git, 설치 staging에서도 이어받는다. 빌드 파일 6개는 공급자 빌드 바이트와 비교했다. |
| A03 | `manage.py`와 `plugin.py monitor status`로 source manifest, current.json, service receipt 및 matched health를 대조한다. `backend/api/main.py`는 실제 로드 경로를 제공한다. 기존 READY가 구버전이면 `UPDATE_REQUIRED`를 표시하고, 맞는 health가 없으면 실행 release는 미관측 상태로 둔다. 새 home의 사용자 지정 runtime은 수동 조회에 쓰기 없이 허용한다. POSIX 포트 확인은 깨끗한 종료 후 TIME_WAIT를 허용하고 현재 listener는 계속 거부한다. |
| A04 | 직결 `plugin_commands.py`와 CLI에서 `settings file sync/push`를 거부한다. `settings export/import`의 기존 저장소 CAS를 사용한다. stale revision·편집 파일과 기존 일시정지/예약·UNKNOWN 보존을 시험했다. 기존 HTTP 세션의 `SettingsFileBridge`는 회사 Host Adapter에서 연결할 수 있다. |
| A05 | `plugin_delivery.py`가 manifest상의 전체 파일 집합, SHA, 루트·내부 진입점, Windows descriptor 및 GUI/assets/lock을 검증한다. 잘못된 추가·누락·다른 launcher·다른 Windows release가 거부된다. 일반 Python 실행 후 기존 라이브러리 import로 생긴 캐시와 pristine 모드 차이를 시험했다. |

Astra 독립 리뷰에서 사용자 지정 runtime의 최초 시작, 정상 사용 뒤 재검증, receipt와 health 관측의 구분, 구버전 롤백 확인의 네 건을 수정했고 재검토는 승인됐다. 이후 실제 동일 포트 재기동에서 발견된 TIME_WAIT 문제를 별도로 수정·검증했다.

## 04 회사 검토에 넘길 정보

1. 위 폴더·두 SHA-256·release를 하나의 인수 단위로 사용한다. 회사 기존 부분 이식 및 pin을 확인하고 [스모크의 회사 접점 표](COMPANY_SMOKE_TEST.md#회사-host-adapter-위치)를 실제 파일·함수에 매핑한다.
2. 회사 전용 수정 위치는 slash 명령/활성화·알림의 direct/HTTP 선택, 모듈 게시 callback과 version/권한, 기존 UI 탭·API prefix/권한·스타일, 설치 경로/포트/동일 owner, Windows 현지 도구·SSH-R·보드/TC 경로다. 공통 설정 DB와 실행 데이터는 기존 배포 소유자에서 유지한다.
3. 미충족 조건은 회사 Linux의 실제 Python/ABI wheel 공급·오프라인 설치, Windows Python 3.11~3.13 x64 및 OpenSSH/COM/PuTTY/fastboot, 기존 회사 DB/프로세스·권한 및 하드웨어 확인이다. 회사 T-286/T-290/T-305, Bedrock 실제 모델/Jira는 현지 증거 전까지 `NOT_RUN`이다.
