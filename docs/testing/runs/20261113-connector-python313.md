# 보드 커넥터 Python 3.13 · 2026-11-13

RQ-65/D-69/T-235/REG-0083. 기준 `91d658f1461ec017952dad37bcabb3f149703da8`.

Python 3.13 64비트를 우선 선택하며 3.11/3.12 호환을 유지한다. 기존 환경은 실행 Python minor까지 일치해야 재사용한다. 누락된 `scripts/board_connector.py`를 명시하고 전체 소스 갱신을 안내한다. Qt와 서버 의존성 핀·DB·저장 설정·TC Python은 바꾸지 않았다. [PySide6-Essentials 6.8.3 공식 메타데이터](https://pypi.org/project/PySide6-Essentials/6.8.3/)의 Python 범위는 >=3.9,<3.14다.

| 검증 | 결과 | 범위 |
|---|---|---|
| focused.log | 64 PASS / 5 SKIP | Mac Python 3.11, Qt offscreen 및 모의 connector/토큰 없는 연결. Windows CMD 5개 미실행 |
| wheels.log | PASS, exit 0 | 두 lockfile의 Windows CPython 3.13 wheel 해석·다운로드. 실제 Windows 실행 근거는 아님 |
| Windows Python 3.13.17 CI | PASS | 644 PASS/4 SKIP, CMD 3.13 선택·누락 파일 진단, 최초 설치·오프라인 재실행·패키지 smoke |

```bash
QT_QPA_PLATFORM=offscreen PATH=/usr/bin:/bin:/usr/sbin:/sbin .venv/bin/python -m pytest -q -rs tests/test_board_connector_launcher.py backend/gui_test/tests/test_board_connector.py backend/gui_test/tests/test_tokenless_connections.py
.venv/bin/python -m pip download --only-binary=:all: --platform win_amd64 --python-version 313 --implementation cp --abi cp313 --dest .local-reports/connector-python313-20261113/wheels -r apps/gui-test/requirements.lock -r apps/board-connector/requirements.lock
```

원본 로그·wheel·SHA manifest는 `.local-reports/connector-python313-20261113/`에만 보관하며 Git에 포함하지 않는다. Windows CI는 3.13을 설치하고 CMD가 선택한 버전과 신규 환경 버전을 각각 확인한다. 기존 독립 패키징 3.12 기준은 유지한다. 회사 Z:·GUI·SSH·COM·TC/장비 T-234 NOT_RUN, 독립 리뷰 NOT_REVIEWED다. Python 버전 제한 수정만으로 회사의 파일 누락 원인이 해결됐다고 주장하지 않는다.

## 게시·CI 결과

제품·시험 고정 커밋 `1447c207515f828dcf925075625b6f0f7c3a6d60`, [PR #21](https://github.com/graycoral/bsp_os_upgrade_dashboard/pull/21), main 병합 `4c7b18ae6f21dcfb9981b4ce61e338a25d48b1f6`.

- [회귀 CI](https://github.com/graycoral/bsp_os_upgrade_dashboard/actions/runs/43366823782): 전체 SUCCESS. Windows Python 3.13.17 x64에서 644 PASS/4 SKIP. 신규 가상환경도 3.13인지 확인했고 최초 설치와 PIP_NO_INDEX 재실행 모두 PASS. Linux Python 3.12 회귀 1451 PASS/21 SKIP, Dashboard 브라우저 60 PASS, 단독 GUI 브라우저 18 PASS.
- [독립 Windows 빌드](https://github.com/graycoral/bsp_os_upgrade_dashboard/actions/runs/43366823961): 기존 Python 3.12 기준 PowerShell/pwsh 모두 SUCCESS.
- 원본 windows-ci.log/linux-ci.log는 위 로컬 보고 폴더에 보관한다. 회사 Z:·GUI·SSH·COM·장비 T-234 NOT_RUN은 유지한다.
