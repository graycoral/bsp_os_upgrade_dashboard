# PORT-017 회사 플러그인 전달

[bsp-plugin-copy-ready-20261124-9f91123](bsp-plugin-copy-ready-20261124-9f91123/README.md) 폴더 전체를 회사 플러그인에 복사한다. [인수 명령·안전 기본값·Mock 시험](bsp-plugin-copy-ready-20261124-9f91123/agent-monitor/docs/porting/PORT-017.md)과 [설계](bsp-plugin-copy-ready-20261124-9f91123/agent-monitor/docs/design/COMPANY_CONNECTOR_DELIVERY_CONTRACT.md)를 함께 제공한다. owner의 수동 감시와 선택적 시작 훅을 지원한다.

| 기준 | 고정값 |
|---|---|
| 원본 커밋 | `9f911235d98df0120593d3028a27fcfdee5cead3`, 깨끗한 체크아웃 |
| release ID | `646e59bb3a8be1630193ef9de750bb5429776910b8a46ac8958f1485b1c00eb4` |
| 루트 PLUGIN_PACKAGE.json SHA-256 | `20cefe010f85ba22e36d0e359bd529fed8931b9c89f3e72c471781d89236023f` |
| RELEASE_EVIDENCE.json SHA-256 | `9fa475295275cb1052c2194a273c84397b7f554732ec3bc2210d8336d5766b99` |

[이전 14634ed 대비 변경 35개 파일과 전후 해시](MANIFEST_DELTA.tsv) · [두 릴리스의 manifest·변경표 SHA-256](RELEASE_EVIDENCE.json). 이전 고정본과 UI 입력 파일이 같아 이전 검증본의 대시보드·독립 GUI 빌드 파일을 바이트 그대로 사용했다.

패키지 루트에서 `python3 -IB plugin.py verify . --pristine`을 실행한다. 회사의 독립 채널에서 받은 RELEASE_EVIDENCE.json 해시를 `EXPECTED`에 넣고, 신뢰하는 PORT-017 설치본에서 `python3 -IB plugin.py verify-evidence "$PRIOR_PACKAGE" "$CURRENT_PACKAGE" "$EVIDENCE_DIR" --sha256 "$EXPECTED"`를 실행한다. 이전 패키지와 새 패키지의 루트에는 각각 PLUGIN_PACKAGE.json이 있다. 증거 디렉터리에는 위 두 파일을 둔다.

코드 커밋의 회귀 169건과 패키지 안의 신규 인수 시험 33건은 중복을 포함한다. 회사 훅·Windows·실장비·독립 채널 인수는 NOT_RUN이다. 실제 장비 작업은 회사 승인을 거친다.
