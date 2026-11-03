# Windows 웹 빌드 실행 정책 오류 수정

- 범위: RQ-44/T-126, REG-0036. 기준 main `e86c5cbbf53cd360a1b90eafcc1c37b050e3659e`.
- 사용자 증거: 로컬 저장소에서 `scripts/build.cmd` 실행 시 `build.ps1`을 로드하지 못하고 `PSSecurityException/UnauthorizedAccess` 출력. 빌드 본문 진입 전 PowerShell 실행 정책 차단이다. 이전 공유 드라이브 오류 REG-0030의 원인을 확정하는 증거는 아니다.
- 수정: `build.cmd`의 자식 PowerShell 호출에만 `-ExecutionPolicy Bypass`를 추가. 절대 스크립트 경로·인자 전달·실패 pause·원래 종료 코드 유지. 사용자/컴퓨터 정책 저장과 관리자 권한은 필요하지 않다. 그룹 정책은 여전히 우선한다.
- 변경 파일: `scripts/build.cmd`, 사용 안내, 요구사항/시험/진행/회귀 기록, `tests/test_build_entrypoint.py`. DB·설정 데이터 변경 없음, 실제 장비/서버 실행 없음.
- 방지 시험: Restricted 환경을 상속한 실제 PowerShell에서 기존 직접 호출 실패를 재현하고 CMD 경유 성공을 확인한다. LF/CRLF, 공백 포함 경로, 다른 cwd, 인자 전달, 종료 코드0/7, 호출 전후 실행 정책 목록 일치를 확인한다.
- 독립 GPT-6-astra 코드·시험·안내 리뷰 APPROVED. reviewer도 신규 시험4 PASS를 확인했다. 최초 기본 pytest 임시 디렉터리 권한 때문에 fixture4 ERROR가 발생했고 고유 basetemp로 재실행했다. 최종 실행 기록 문서 전체에 대한 리뷰를 의미하지 않는다.
- 독립 GPT-6-sol 신규4 PASS, 기존 setup 회귀49 PASS/4 플랫폼 SKIP, 실제 CMD 양쪽 UI 빌드 PASS. [정확한 명령·환경·결과](20261103-build-execution-policy-sol.md). 주 작업자가 시험 코드와 보고 결과를 검토했다. 영구 실행 정책 전후 동일을 확인했다.
- 회사 그룹 정책/SMB/장비 인수는 NOT_RUN, 운영 baseline NONE 유지.
