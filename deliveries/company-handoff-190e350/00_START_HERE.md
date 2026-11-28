# Windows 찾아보기와 TC 목록 갱신 전달본

복사 대상은 [bsp-plugin-copy-ready-20261129-190e350](bsp-plugin-copy-ready-20261129-190e350/README.md) 폴더 전체다. 회사 플러그인 Git의 새 버전 디렉터리에 `plugin.py`, `PLUGIN_PACKAGE.json`, `README.md`, `agent-monitor/`를 함께 둔다. Linux Monitor와 Windows 보드 커넥터에 같은 버전을 적용한다. Windows 연결 프로필을 포함한 반입은 패키지의 [PORT-011](bsp-plugin-copy-ready-20261129-190e350/agent-monitor/docs/porting/PORT-011.md)을 따른다.

1. 복사 전후에 패키지 루트에서 `python3 -IB plugin.py verify . --pristine`을 실행한다. 배포 담당자는 아래 증거 해시를 독립 채널로 대조한다.
2. [PORT-009](bsp-plugin-copy-ready-20261129-190e350/agent-monitor/docs/porting/PORT-009.md)와 [PORT-013](bsp-plugin-copy-ready-20261129-190e350/agent-monitor/docs/porting/PORT-013.md)에 따라 세 찾아보기 버튼의 선택·취소·실패, Linux TC 경로 교체·해제, SSH 재연결 후 목록을 확인한다. 기존 작업의 런타임·설정·SSH 키는 각 설치 위치에 유지한다.
3. 직전 패키지는 `7691c0e`다. 이 버전에서 처음 갱신하면 [PORT-019](bsp-plugin-copy-ready-20261129-190e350/agent-monitor/docs/porting/PORT-019.md)의 TC·ADB 실행과 실패 로그도 포함되므로 Host를 유휴 상태에서 정지하고 기존 패키지·프로필·SQLite DB를 백업한다. **Host DB v4** 이전과 롤백은 PORT-019 순서를 따른다. 이번 찾아보기·목록 변경 자체에는 추가 DB 이전이 없다.

| 검증 항목 | 값 |
|---|---|
| 소스 커밋 | `190e3505a007e060cbfcf984d1f376ecede4a3c1` |
| 이전 공식본 | `7691c0e679b4afdd5cb25e91a6e6824b0b7631b7` |
| 패키지 manifest SHA-256 | `f01d3054135f561440cf90fde95307ae346d73a8755e140496fee28e054617e5` |
| RELEASE_EVIDENCE.json SHA-256 | `7307f2b3ada566a2ffec37f63f21a091f25ef2268a545328011c9319db72d74b` |

[변경 파일 72개의 전후 해시](MANIFEST_DELTA.tsv) · [동작 변경 목록](BEHAVIOR_CHANGES.json) · [릴리스 검증 근거](RELEASE_EVIDENCE.json)

원본 검증기에서 `python3 -IB apps/agent-monitor/plugin.py verify-evidence "$PRIOR_PACKAGE" "$NEW_PACKAGE" "$HANDOFF_DIR" --sha256 "$EXPECTED_SHA256"`로 두 고정본을 비교한다. 실제 회사 Windows 표준 대화상자·SSH·장비 확인은 현지 인수 항목이다. 회사 적용 커밋과 결과는 회사 저장소의 APPLIED.md에 기록한다.

원본 Python 회귀 195건, 찾아보기 브라우저 시험 5건, 수신용 복사본 Python 시험 140건이 통과했다. 전체 커넥터 브라우저 회귀는 28건 통과했고 기존 신호등 개수 시험 1건이 실패했다. 변경 전 버전에서도 같은 실패를 확인했다.
