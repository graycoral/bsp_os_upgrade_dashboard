# PORT-016 회사 전달 · 웹 퓨징 설정

**복사할 폴더**는 [bsp-plugin-copy-ready-20261123-14634ed](bsp-plugin-copy-ready-20261123-14634ed/README.md) 전체다. 회사 플러그인 저장소의 기존 패키지 위치는 회사 담당자가 확인한다. 복사 후 최상위에 `plugin.py`, `README.md`, `PLUGIN_PACKAGE.json`, `agent-monitor/`가 있어야 한다.

| 확인 항목 | 값 |
|---|---|
| 기능 커밋 | `ac79a5643dd77c45b7f2c035c716970c6564a2d1` |
| 패키지 원본 커밋 | `14634ed2b1a8514f4d19d0a62e3e239f987155d2` · `source_dirty=false` · 두 UI 포함 |
| release | `ebb37dab272f14cf0277fc5bd264b4cc1577a96e22728b99eef5c63cf774a60e` |
| 루트 `PLUGIN_PACKAGE.json` SHA-256 | `2f2d4481d18058a9e259cfe9e116b34d9a569d67463510c7e837ad87f2659406` |
| 내부 `agent-monitor/AGENT_MONITOR_SOURCE.json` SHA-256 | `387cf38a9d5df192614e53b93a5441faea014ccc2d616dca555aba57addd2f83` |

1. 복사할 폴더에서 `python3 -IB plugin.py verify . --pristine`을 실행해 위 release를 확인한다. 이전 `8abe926` 전달본 대비 변경·추가·삭제된 37개 파일과 SHA-256은 [manifest 비교표](MANIFEST_DELTA.tsv)에 있다. 퓨징 기능별 적용 위치와 복구 절차는 [PORT-016](bsp-plugin-copy-ready-20261123-14634ed/agent-monitor/docs/porting/PORT-016.md)을 따른다.
2. 회사 담당자는 [04 사전 분석](bsp-plugin-copy-ready-20261123-14634ed/agent-monitor/docs/porting/company/04_CLAUDE_OPUS_COMPANY_ASSESSMENT.md)에서 기존 home/runtime·작업·어댑터와 회사 `config/upgrade.yaml` 매핑을 확인한다. [05 승인 범위 이식](bsp-plugin-copy-ready-20261123-14634ed/agent-monitor/docs/porting/company/05_CLAUDE_SONNET_COMPANY_PORT.md)과 [06 독립 리뷰](bsp-plugin-copy-ready-20261123-14634ed/agent-monitor/docs/porting/company/06_CLAUDE_OPUS_FINAL_REVIEW.md)에서 이번 PORT의 대상 커밋과 위 manifest를 사용한다.
3. Windows 기본 폴더는 패키지 안의 `agent-monitor/`이며 실행기는 `board-connector.bat`다. 저장된 접속 정보를 포함하는 배포는 기존 `connect export --output NEW_DIR`로 생성한다. 모의 접속 정보로 별도 Windows 폴더를 생성해 원본 내부 manifest 511개 파일의 SHA-256을 대조했다.
4. 회사 플러그인이 빌드 결과의 BAT와 프로파일을 지정하거나 사용자가 **보드 커넥터 → 이미지 퓨징 설정**에서 보완한다. 회사 인수는 `test preview --flash`로 시작하며 실제 장비 작업은 별도 승인 범위다. 회사 설치와 USB 인수는 NOT_RUN이다.

**회사 담당자에게 전달할 요청문**

> 현재 회사 설치본과 PORT-016을 대조하고 대시보드·Windows 커넥터의 퓨징 설정, 회사 빌드 완료 훅의 BAT·프로파일 매핑, 같은 runtime에서의 설정 보존을 확인해 주세요. 승인 범위에서 적용한 뒤 회사 커밋과 시험 결과를 APPLIED.md에 기록해 주세요.
