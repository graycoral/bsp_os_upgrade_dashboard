# 보드 커넥터 Python 3.13 · 2026-11-13

RQ-65/D-69/T-235/REG-0083. 기준 `91d658f1461ec017952dad37bcabb3f149703da8`.

Python 3.13 64비트를 우선 선택하며 3.11/3.12 호환을 유지한다. 기존 환경은 실행 Python minor까지 일치해야 재사용한다. 누락된 `scripts/board_connector.py`를 명시하고 전체 소스 갱신을 안내한다. Qt와 서버 의존성 핀·DB·저장 설정·TC Python은 바꾸지 않았다. [PySide6-Essentials 6.8.3 공식 메타데이터](https://pypi.org/project/PySide6-Essentials/6.8.3/)의 Python 범위는 >=3.9,<3.14다.

| 검증 | 결과 | 범위 |
|---|---|---|
| focused.log | 64 PASS / 5 SKIP | Mac Python 3.11, Qt offscreen 및 모의 connector/토큰 없는 연결. Windows CMD 5개 미실행 |
| wheels.log | PASS, exit 0 | 두 lockfile의 Windows CPython 3.13 wheel 해석·다운로드. 실제 Windows 실행 근거는 아님 |
| Windows Python 3.13 CI | NOT_RUN | 게시 후 최초 설치·오프라인 재사용·CMD 버전 선택·실제 회귀 결과 추가 |

```bash
QT_QPA_PLATFORM=offscreen PATH=/usr/bin:/bin:/usr/sbin:/sbin .venv/bin/python -m pytest -q -rs tests/test_board_connector_launcher.py backend/gui_test/tests/test_board_connector.py backend/gui_test/tests/test_tokenless_connections.py
.venv/bin/python -m pip download --only-binary=:all: --platform win_amd64 --python-version 313 --implementation cp --abi cp313 --dest .local-reports/connector-python313-20261113/wheels -r apps/gui-test/requirements.lock -r apps/board-connector/requirements.lock
```

원본 로그·wheel·SHA manifest는 `.local-reports/connector-python313-20261113/`에만 보관하며 Git에 포함하지 않는다. Windows CI는 3.13을 설치하고 CMD가 선택한 버전과 신규 환경 버전을 각각 확인한다. 기존 독립 패키징 3.12 기준은 유지한다. 회사 Z:·GUI·SSH·COM·TC/장비 T-234 NOT_RUN, 독립 리뷰 NOT_REVIEWED다. Python 버전 제한 수정만으로 회사의 파일 누락 원인이 해결됐다고 주장하지 않는다.
