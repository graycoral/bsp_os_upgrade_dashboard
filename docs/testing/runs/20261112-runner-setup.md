# Windows Runner 설정 편의·EXE 배포 종료

RQ-62/D-66/REG-0078, T-218~221. 원본 기준 `5c6310f4a2fce255149801a4fc6403a5037bba51`, 코드/시험 대상 `55447f87f3241df76a7a110c130252b73b29c941`. 환경 macOS arm64/Python 3.11.7, 임시 파일/DB와 모의 프로세스·USB 목록. 실제 Windows·SSH·콘솔·BAT·TC·보드 호출은 하지 않았다. 독립 리뷰 NOT_REVIEWED, 실제 회사 T-221 NOT_RUN.

## 변경과 경계

`scripts/setup_flashing.py`는 유효 저장 경로/PATH/표준 SDK 탐색, 읽기 전용 `fastboot devices`, 단일 대상 자동 선택과 다중/변경 대상 명시 매핑, 공통 콘솔 입력을 제공한다. 새 115200/`cr`은 추천값이며 실장비 검증값은 아니다. 명령 `reboot lkshell`/`fast`와 fast 이후 로그 `fastboot init success`를 fast 이전 프롬프트로 입력하는 혼동을 거부한다. 사용자가 확인한 BAT 자동 리부팅 후 `**** login : `에서 `login :`를 새 기본 부팅/로그인 marker로 사용한다. 수신 버퍼 중간의 marker도 확인한다. root 로그인은 기존 TC 역할로 유지한다.

프로파일 `console_defaults`는 기존 보드별 필드로 펼친다. 기존 보드별 예외/추가 필드·토큰·runtime·UNKNOWN·진행 중 snapshot을 보존한다. DB/API/실행 코드/의존성 변경은 없다. 실제 lkshell 프롬프트는 아직 미확인으로 자동 생성하지 않는다. `apps/gui-test/package.py`는 플러그인 `INSTALL.md` 안내만 갱신했고 참조 PluginClient HTTP payload/capability는 유지한다. 실제 회사 플러그인 코드는 이 저장소에 없다.

사용자 지시로 기존 추적 EXE 배포물 `dist/windows-runner/BSP-Windows-Runner.zip`(27,889,244 bytes)과 `.zip.sha256`을 삭제했다. 별도 단독 Runner EXE는 없었다. 새 EXE/편집형 ZIP 생성이나 회사 PC 파일 삭제는 하지 않았다. 과거 Git·시험 이력/호환 소스는 보존한다. 일반 회귀의 임시 합성 소스 ZIP은 로컬 시험 파일이며 EXE 배포가 아니다. 웹 재빌드만으로 Runner 재설치는 필요하지 않고 편집 소스 갱신은 해당 파일 백업·선별 적용·정상 재시작으로 반영한다.

## 실행 결과

아래 `.local-reports`는 전체 stdout/stderr와 manifest를 보관한 **로컬 전용 경로이며 Git에 넣지 않는다**. 실패한 최초 시도를 보존했다.

| 명령/조건 | 실제 결과 | 로그 |
|---|---|---|
| `.venv/bin/python -m pytest tests/test_setup_flashing_discovery.py tests/test_setup_runtime.py tests/test_runner_ports.py -q` 최초 | exit 1; 102 PASS / 8 FAIL / 8 SKIP. 3개는 샌드박스 loopback EPERM | `.local-reports/runner-setup-0f7130acba/pytest.log` |
| 같은 시험을 loopback 허용 환경에서 재실행 | exit 1; 105 PASS / 5 FAIL / 8 SKIP | `.local-reports/runner-setup-permitted-7ff6069ddf/pytest.log` |
| HEAD의 변경 전 setup_flashing 소스를 메모리에 로드해 runner_ports의 해당 5개 재현 | exit 1; 같은 5 FAIL / 43 deselected. 3개는 macOS 미지원 CLI 가드, 2개는 기존 SSH which mock의 `path` 키워드 미지원 | `.local-reports/runner-baseline-c7a59fa617/pytest.log` |
| 설정·편집 빌드·bundle·기존 flashing/hardware 회귀 6개 파일 | exit 1; 163 PASS / 6 FAIL / 10 SKIP. 변경하지 않은 build의 POSIX flock 중복 잠금 3개와 로컬 pyserial 미설치 3개 | `.local-reports/runner-regression-94023c7288/pytest.log` |
| 출력 문구 반영 후 설정 집중 시험 `pytest tests/test_setup_flashing_discovery.py tests/test_setup_runtime.py -k 'flash or readiness_marker' -q` | exit 0; 33 PASS / 39 deselected | `.local-reports/runner-final-44253b2aa8/pytest.log` |
| 최종 설정 + plugin pipeline/service/package 회귀, 아래 명령 | exit 0; 62 PASS / 39 deselected / 1 기존 의존성 warning | `.local-reports/runner-publish-3f32450dfb/pytest.log` |

최종 명령:

```sh
.venv/bin/python -m pytest tests/test_setup_flashing_discovery.py tests/test_setup_runtime.py backend/gui_test/tests/test_plugin_integration_pipeline.py backend/gui_test/tests/test_plugin_integration_service.py backend/gui_test/tests/test_plugin_integration_package.py -k 'flash or readiness_marker or integration' -q
```

최종 manifest `.local-reports/runner-publish-3f32450dfb/manifest.json`은 변경한 소스 3개/시험 2개의 raw SHA256을 담는다. 결합 SHA256 `2184070b2c7283c725a081a445dee86d922173aabb8c047763102ab4ac26652b`; setup_flashing SHA256 `44ec8abc2fdd20aa3191a7f66f5c7ceb60a8d912b920f670cdc6d43eb78638e4`. 코드 커밋의 blob과 업로드 소스 일치를 확인했다. 과거/광역 회귀의 실패를 통과로 바꾸지 않으며 최종 62 PASS는 명시된 집중 범위에 한한다. 문서/링크·Git diff 검사는 별도로 수행하고 제품/회사 인수로 승격하지 않는다.

T-218~220은 위 모의 범위 PASS, T-221 실제 Windows PATH/SDK·드라이버·장치/COM 대응·개행·실제 구간별 출력·TC root 로그인·소스 갱신/정상 재시작은 NOT_RUN이다. 운영 baseline NONE을 유지한다. [PORT-008](../../porting/PORT-008.md), [PORT-007](../../porting/PORT-007.md)에 회사 적용·복원·다운로드 pin 확인사항을 기록했다.

작업 공간 문서 검사 `python3 docs/testing/validate_docs.py`는 exit 0, 상대 링크 1,187·요구사항 62·시험 221·오류 0이다. 로컬 로그 `.local-reports/runner-docs-321d3b85cf/validation.log`를 보존한다. `git diff --check`의 문서 EOF 빈 줄 2개는 정리 후 PASS를 확인했다. 이 검사는 제품/실장비 PASS가 아니다.

게시 대상만 별도로 구성한 문서 검사도 exit 0(상대 링크 1,178·요구사항 62·시험 221·오류 0)이다. 기존 미커밋 `docs/README.md`/모니터 설계는 제외하고, WORK_STATUS는 원본 HEAD에 이번 절만 추가해 확인했다. 로컬 근거는 `.local-reports/runner-publish-3f32450dfb/publication-docs-validation.log`다. GitHub 연결 도구에서 소스 blob SHA를 원본 bytes와 대조하고 코드 커밋을 만든 뒤 같은 커밋을 PORT·결과에 고정했다. 최종 main 이동은 기존 head를 조건으로 하며 원격 결과를 별도로 확인한다.
