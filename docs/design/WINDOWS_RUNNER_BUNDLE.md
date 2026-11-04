# Windows Runner 포터블 배포

RQ-51/D-53. Runner용 Python과 의존성을 포함한 Windows x64 폴더형 ZIP을 제공한다. 기존 Linux Dashboard와 Windows 실행 계약은 [Windows Runner](../gui_test/WINDOWS_RUNNER.md), 자동 퓨징은 [자동 퓨징 계약](AUTOMATIC_FLASH_TEST.md)을 따른다. 회사 TC용 Python·패키지, OpenSSH, 드라이버, fastboot는 별도로 준비한다.

## 실행 경계

`BSP-Windows-Runner.exe`의 기본 진입점은 기존 설정 마법사다. `--runner`는 인증된 loopback HTTP Host, `--contained-child -- <argv>`는 격리된 자식 실행을 담당한다. 임의 Python 코드나 모듈을 실행하는 `-c`/`-m` 인터페이스는 제공하지 않는다.

Wizard → Runner → gated helper → 외부 TC Python/장비 도구 순으로 실행한다. helper는 stdin의 승인 바이트를 기다리며 부모가 Windows Job Object에 배정한 후에만 명령을 시작한다. gate EOF/오류나 Job Object 실패 시 TC를 실행하지 않는다. 기존 전체 자식 종료 확인과 UNKNOWN·중복 방지 계약을 유지한다.

외부 명령을 실행하는 helper에서 DLL 검색 경로를 복원하고 번들 내부 PATH 및 PyInstaller 내부 환경변수, Runner 토큰을 제거한다. 다중 스레드 Runner의 전역 DLL 검색 상태는 변경하지 않는다. 단일 스레드 Wizard는 SSH 생성 구간에서만 DLL 경로를 임시 복원하고 원래 상태로 되돌린다. SSH와 TC에 토큰을 전달하지 않는다.

## 설정과 데이터

기본 `%USERPROFILE%\.bsp-dashboard\windows`와 기존 `--home`을 재사용한다. JSON 추가 필드·저장 전 확인·백업·DPAPI 토큰·runtime·DB·runner identity와 UNKNOWN 기록을 보존한다. 설치 위치나 번들 `_internal`에 사용자 데이터를 저장하지 않는다. 기존 실행 중/UNKNOWN 상태를 새 runtime으로 우회하지 않는다.

포터블 모드의 설치 메뉴는 내장 의존성을 안내하며 venv/pip를 호출하지 않는다. TC Python은 기존 설정 또는 사용자가 명시한 외부 파일이어야 한다. EXE 자신이나 번들 내부 Python을 TC Python으로 저장하거나 실행하지 않는다. 소스 기반 Windows/Linux 설치 경로는 유지한다. API/DB schema 변경과 데이터 이전은 없다.

## 빌드와 전달

Windows CPython 3.12.10 x64와 고정된 PyInstaller/build 의존성으로 console/onedir 배포본을 만든다. 출력은 `dist/windows-runner/BSP-Windows-Runner/`, 해당 폴더 ZIP 및 SHA256 sidecar다. README, 소스 기준·파일 해시·빌드 도구·의존성 버전과 파일 체크섬을 포함한다. 사용자 설정·토큰·TC·runtime·개발 로그·소스 저장소를 포함하지 않는다.

## 검증

T-156~159은 실제 ZIP을 저장소 밖 공백/한글 경로에 풀어 Python/pip 없는 PATH에서 실행하고, 인증 API·설정 호환·외부 Python·gate/Job Object·중복/취소/복구와 기존 모의 회귀를 검사한다. 실제 회사 PC/공유 폴더/SSH/보드 인수 T-160 및 기존 T-130/136/141은 별도다. 빌드 성공과 모의 시험으로 실장비 인수를 완료 처리하지 않는다.
