# Windows 직접 실행 진입점 검증

RQ-48 / T-139 / REG-0030. 기준 d0b187d. 사용자 보고: 회사 PC의 Z: 파일 조회와 CMD dir은 성공하며 직접 Python 마법사 실행은 정상. 최초 CMD 오류 원인은 아직 확정하지 않았다. 이전45 PASS로 회사 공유 경로 문제가 해결됐다고 보고한 것은 검증 범위를 넘었다.

변경: setup.cmd/setup.ps1의 Python 절대 경로 직접 실행, py -3 기본 선택, build.cmd의 PowerShell 절대 경로 직접 실행. 추정 UNC 연결/캐시 의존 제거. 기존 사용자 설정/토큰/DB는 변경하지 않는다.

새 Astra 읽기 전용 리뷰와 별도 GPT-6-sol 실제 wrapper 모의 시험을 수행한다. 실제 공유 폴더·회사 빌드·장비·SSH는 시험하지 않는다. 최종 결과를 아래 기록한다.


최종 결과: 새 Astra 리뷰 APPROVED, 별도 GPT-6-sol Windows Python3.13.5 시험49 PASS/4 SKIP. 새4개 시험은 LF/CRLF × 정상/오류 종료 조합에서 실제 CMD/PowerShell을 실행하고 공백 경로·다른 cwd·인자·대상 파일·종료 코드를 확인했다. 대상은 임시 가짜 Python/PowerShell이며 실제 빌드/보드는 실행하지 않았다. 초기 기본TEMP 권한 실패 후 저장소 내 임시 경로로 재시험했다.

[원본 시험 출력](20261103-direct-windows-launch-evidence/pytest-output.txt), [명령·파일 해시](20261103-direct-windows-launch-evidence/verification.txt), [독립 리뷰](20261103-direct-windows-launch-evidence/astra-review.txt). 주 작업자가 실제 시험 코드와 출력/해시를 대조했다. 회사 공유 경로를 통과했다고 확대하지 않는다. T-141/T-130/T-136은 NOT_RUN 유지.

수정/검증 기준 커밋: `4ae2ddc8df959da29405f83c69a1213d64b477a7`. 실제 회사 CMD 재시험은 사용자 확인 전 미완료다.
