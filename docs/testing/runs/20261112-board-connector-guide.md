# 보드 커넥터 가이드 정리 · 2026-11-12

RQ-63/D-67. 제품 기준 `ed3d2ac409ce586c0682637fba4c6f1989247e28`, 문서 작업 기준 `7d7e4dd3168b4be09af48c250d1d1870a8c4d4b4`.

사용자 지시로 기존 [사용 안내](../../gui_test/TEST_BOARD_CONNECTOR_GUI.md)를 개정했다. 설치 절은 명령어만 제공하고 사용 순서는 짧은 단계, 예외 조치는 표로 정리했다. Windows–Linux Mermaid 연결도, 포트 구분, 최초 인증 설정, 플러그인 연결을 추가했다. 문서 지도·GUI Test 목차·기존 CLI 안내·플러그인 회사 안내·PORT-009에서 연결한다.

확인한 코드: connector GUI/settings/supervisor/API, runtime manager, PluginClient, setup_runtime의 SSH 터널·TokenStore, 고정 의존성 파일. 통신 방향·버튼명·설정 위치·인증 이름·참조 메서드를 대조했다.

검증 원본은 `.local-reports/board-connector-guide-c88c3860/`에 보존한다. 문서 링크·ID 검사와 Git 공백 검사, 명령 내 Python 구문·참조 파일·메서드 확인을 수행한다. 게시할 문서만 별도 추출하여 미게시 초안에 대한 링크가 없는지도 확인한다. 실제 결과는 아래 실행 결과에 기록한다.

문서만 변경했다. 설치 명령 실행·토큰 저장·Windows/회사 연결·실제 보드 시험은 NOT_RUN이다. Mermaid는 소스 구문을 확인했으며 브라우저 렌더링은 NOT_RUN이다. 제품 시험의 기존 결과를 이번 문서 검증으로 대체하지 않는다.

## 실행 결과

- 전체 작업 폴더 문서 검사: PASS, 상대 링크 1,242·요구사항63·시험228·오류0 (`docs.log`).
- 게시 대상 추출본 문서 검사: PASS, 상대 링크 1,233·요구사항63·시험228·오류0 (`staged-docs.log`).
- `git diff --cached --check`: PASS (`diff-check.log`).
- 숨김 토큰 입력 명령 2개의 Python 구문, 의존성/실행 파일 3개, 플러그인 메서드 4개, 코드 펜스 짝 확인: PASS (`content-check.json`).
