# PORT-021 회사 전달 · 여러 작업이 사용하는 보드 커넥터

[복사할 폴더](bsp-plugin-copy-ready-20261129-c02d60e/README.md) 전체를 회사 플러그인 저장소의 **새 버전 디렉터리**에 복사한다. 패키지 루트에 `plugin.py`, `PLUGIN_PACKAGE.json`, `README.md`, `agent-monitor/`가 함께 있어야 한다. 운영 DB와 자격 파일은 각 설치에 둔다.

1. 복사 전후 패키지 루트에서 `python3 -IB plugin.py verify . --pristine`을 실행한다. [기능별 적용 안내](bsp-plugin-copy-ready-20261129-c02d60e/agent-monitor/docs/porting/PORT-021.md)에 Windows 프로비저닝, Linux 계정과 작업 등록, 공유 Monitor 설치 명령이 있다.
2. 회사 플러그인 담당자는 작업을 생성할 때 반환한 작업 ID를 영속 보관하고 기존 작업을 재개할 때 같은 ID를 전달한다. 작업 창의 **Monitor 열기**는 해당 작업을 연다. Windows 커넥터에서는 현재 Run 소유 작업을 열고, 유휴 상태에서 작업이 여럿이면 선택한다.
3. 공유 모드 적용 전 운영자는 실행 자료와 Host·Monitor 전송 경로의 승인 범위를 확인하고 [현지 인수 항목](bsp-plugin-copy-ready-20261129-c02d60e/agent-monitor/docs/porting/PORT-021.md)을 수행한다. Windows SSH, 회사 플러그인, 실제 계정·보드 인수 기록은 회사 APPLIED.md에 남긴다.

| 확인 항목 | 값 |
|---|---|
| 고정 소스 | `c02d60e8bc6738d924e4740d0352cb4303df7e40` |
| 직전 전달본 | `d47286a` |
| 릴리스 ID | `1e20d60799a1dc3c5816e7f26928236a07e44fa43bc45b56846978eb5a4fbae4` |
| PLUGIN_PACKAGE.json SHA-256 | `7f26a128a8bcd39e23479ed10a9b622be62cf8bcbd9dcd503ad724cdf700c54d` |
| RELEASE_EVIDENCE.json SHA-256 | `198ff8ea0ba1a5a2260f52a68b015668bf085b0b3d9cc3536ebccd856ce5b5a8` |

[실제 변경 경로 63개와 전후 해시](MANIFEST_DELTA.tsv) · [동작 변경](BEHAVIOR_CHANGES.json) · [릴리스 근거](RELEASE_EVIDENCE.json) · [시험 및 독립 리뷰](bsp-plugin-copy-ready-20261129-c02d60e/agent-monitor/docs/testing/runs/20261129-multi-plugin-ownership.md)

최종 전달 폴더 자체에서 `verify . --pristine`을 통과했다. 개인 및 공유 Monitor 준비·재사용·정상 종료 스크립트가 통과했고, 실제 복사본으로 실행한 소유권·작업 선택 시험은 23개 모두 통과했다. 원본에 모은 결과는 `.local-reports/20261129-multi-plugin.ebNADi/`에 있다. 이 로그는 회사 전달 폴더에 포함하지 않는다.

원본 검사기는 `python3 -IB apps/agent-monitor/plugin.py verify-evidence "$PRIOR_PACKAGE" "$NEW_PACKAGE" "$HANDOFF_DIR" --sha256 "$EXPECTED_SHA256"`로 전달 전후 패키지와 위 독립 해시를 비교한다. 복구 시 [직전 전달 폴더](../company-handoff-d47286a/00_START_HERE.md)를 사용하고 유휴 상태에서 전환 전 프로필·DB를 함께 복원한다.
