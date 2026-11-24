# Test 현황 모듈 TC 수정본 · 회사 복사 안내

회사 플러그인 저장소에서 현재 `plugin.py`와 `agent-monitor/`를 함께 보관하는 위치에 [bsp-plugin-copy-ready-20261124-6e65521 폴더](bsp-plugin-copy-ready-20261124-6e65521/README.md)의 내용 전체를 복사한다. 최초 설치라면 두 항목을 함께 둘 회사 경로를 먼저 정한다. 운영 DB와 설정은 기존 runtime을 사용한다.

이번 수정 대상은 **Linux 대시보드의 Test 현황 탭**이다. 회사가 모듈 조회 서비스를 자체 관리한다면 [PORT-014의 변경 위치와 시험](bsp-plugin-copy-ready-20261124-6e65521/agent-monitor/docs/porting/PORT-014.md#등록된-windows-실행기의-모듈-tc-목록-수정-reg-0122)을 따른다. Windows 보드 커넥터는 기존 설치를 계속 사용할 수 있다.

1. 복사한 패키지 루트에서 `python3 -IB plugin.py verify . --pristine`으로 무결성을 확인한다.
2. 기존 회사 릴리스 갱신 절차로 대시보드에 반영한 뒤 `python3 plugin.py monitor status`에서 패키지와 실행 중인 Monitor의 릴리스를 대조한다. 모듈 시험 대기 중인 작업에서 Windows 연결 후 모듈에 속하는 TC가 나타나는지 확인한다.
3. 복구 시 [직전 전달본 9f91123](../company-handoff-9f91123/00_START_HERE.md)을 선택한다. 두 패키지 간 변경 파일 7개와 전후 지문은 [변경표](MANIFEST_DELTA.tsv)에서 확인할 수 있다.

| 검증 항목 | 값 |
|---|---|
| 원본 커밋 | `6e65521219d8437d97df006f5e5366f823b23937` |
| release ID | `3d219ab569e622fc564b6497b3d2d9b700b55882df61346028991b44f2c85816` |
| PLUGIN_PACKAGE.json SHA-256 | `dcad5acdf73a916211657ab80eb707863994b665253ce62e11b1503c7132a0f7` |
| RELEASE_EVIDENCE.json SHA-256 | `e8b6d75d90863a17712a2d3ae5773186a96e5e794b186e03c880a4b8c2d040bd` |

[릴리스 증거](RELEASE_EVIDENCE.json)는 이전 PORT-017 패키지의 `plugin.py verify-evidence PRIOR CURRENT EVIDENCE_DIR --sha256 HASH`로 검증할 수 있다. 회사 인수 시에는 독립 채널로 확인한 해시를 사용한다. UI 입력 파일은 이전 릴리스와 동일하여 검증된 두 UI 빌드 파일을 재사용했다. 깨끗한 원본에서 관련 시험 147건, 패키지 안에서 T-319 세 사례가 통과했다. 회사 Windows·SSH·장비 인수는 NOT_RUN이다.
