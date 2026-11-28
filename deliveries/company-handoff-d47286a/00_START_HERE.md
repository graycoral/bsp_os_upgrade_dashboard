# 회사 전달본 · 찾아보기와 TC 목록 갱신, 플러그인 활성화, 버전별 패키지 검증

[복사할 패키지 폴더](bsp-plugin-copy-ready-20261129-d47286a/README.md) 전체를 회사 플러그인 저장소의 새 버전 디렉터리에 둔다. 패키지 루트에 `plugin.py`, `PLUGIN_PACKAGE.json`, `README.md`, `agent-monitor/`가 함께 있어야 한다. 직전 공식본 `bf1f7d2`은 복구용으로 보관한다.

1. 복사 전후 패키지 루트에서 `python3 -IB plugin.py verify . --pristine`을 실행한다. 기존 설정·DB·장비 프로필은 운영 위치에 유지한다. 이번 릴리스의 DB 스키마 변경은 없다.
2. 회사 플러그인 담당자는 활성화 훅에서 아래 명령을 비동기로 한 번 호출한다. Windows가 꺼져 있어도 실행한다. 성공하면 JSON의 `state=READY`와 `reused`를 표시하고 여러 창에서 같은 서비스를 재사용한다. 제한망에서 종료 코드 6과 `NOT_PROVISIONED`가 반환되면 준비된 릴리스의 설치를 안내한다. 창을 닫아도 공용 서비스를 유지하며 보드 직결 명령은 계속 사용할 수 있다. [회사 플러그인 요청서](bsp-plugin-copy-ready-20261129-d47286a/agent-monitor/docs/agents/BSP_UPGRADE_PLUGIN_REQUEST.md#회사-플러그인-활성화-시-agent-monitor-준비)
3. 같은 설치 설정으로 `connect export`를 실행해 만든 Windows 폴더 전체를 장비 PC에 복사한다. Windows에서 `start-board-connector.bat`로 프로필을 적용한다. 커넥터가 SSH 포워딩과 모니터 응답을 확인하면 웹·Qt의 **대시보드 열기**에서 접속할 수 있다. [포트 지정·현지 인수·복구 절차](bsp-plugin-copy-ready-20261129-d47286a/agent-monitor/docs/porting/PORT-020.md)

```sh
python3 "$PACKAGE/plugin.py" --home "$MONITOR_HOME" --runtime "$MONITOR_RUNTIME" \
  --monitor-port "$MONITOR_PORT" monitor ensure --no-provision

python3 "$PACKAGE/plugin.py" --home "$MONITOR_HOME" --runtime "$MONITOR_RUNTIME" \
  --monitor-port "$MONITOR_PORT" connect export --output "$WINDOWS_PACKAGE"
```

| 검증 항목 | 값 |
|---|---|
| 고정 소스 | `d47286a3b96cc7eae885ff88b1599abdd5f6b56a` |
| 직전 공식본 | `bf1f7d289b64baefd03bea98f3799838cea73123` |
| 릴리스 ID | `1f51b20bca6bcccdba91c2dd4bef55cd48b0d524899bc99ada2304045e4d6f0d` |
| PLUGIN_PACKAGE.json SHA-256 | `649d31d2e06dcacba3c1674127d5cdb8db6ebb42dc0d926a5019968adb9b03c6` |
| RELEASE_EVIDENCE.json SHA-256 | `535e7e0fed776323867beb1d888d6cea60fcd97af47f050c48fe62afdb096dbe` |

[변경 경로 8개의 전후 해시](MANIFEST_DELTA.tsv) · [동작 변경](BEHAVIOR_CHANGES.json) · [릴리스 검증 근거](RELEASE_EVIDENCE.json) · [원본 통합 시험 기록](../../docs/testing/runs/20261129-port020-release.md)

원본 검증기에서 `python3 -IB apps/agent-monitor/plugin.py verify-evidence "$PRIOR_PACKAGE" "$NEW_PACKAGE" "$HANDOFF_DIR" --sha256 "$EXPECTED_SHA256"`를 실행한다. 회사 훅과 실제 Windows–Linux SSH·장비 인수는 현지에서 수행하고 적용 커밋과 결과를 회사 `APPLIED.md`에 기록한다. 복구 시 활성화 훅을 해제하고 기존 운영 절차로 유휴 서비스와 커넥터를 중지한 뒤 [직전 복사본](../company-handoff-bf1f7d2/00_START_HERE.md)과 보관한 프로필을 같은 home·runtime에 적용한다.

Windows에서는 세 찾아보기의 선택·취소와 저장 후 TC 폴더 교체·해제, SSH 재연결 후 목록을 확인한다. [PORT-009](bsp-plugin-copy-ready-20261129-d47286a/agent-monitor/docs/porting/PORT-009.md) · [PORT-013](bsp-plugin-copy-ready-20261129-d47286a/agent-monitor/docs/porting/PORT-013.md)

`bf1f7d2`에서 바뀐 제품 동작은 패키지 의존 파일 검사다. 인수 담당자는 전달 증거의 SHA-256을 별도 경로로 대조한다. `7691c0e`에서 처음 갱신하면 [PORT-019의 Host DB v4 이전·복구](bsp-plugin-copy-ready-20261129-d47286a/agent-monitor/docs/porting/PORT-019.md)도 적용한다.
