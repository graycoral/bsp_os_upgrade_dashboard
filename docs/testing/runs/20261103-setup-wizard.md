# 20261103 설정 마법사 구현·검증

- 요구사항: RQ-48 / D-49 / T-137~141. 기준 main76e2519, feature/setup-wizard. DB/API/기존 하드웨어 계약 변경 없음.
- 사용자 요청: 단계별 입력을 받는 설치/실행 스크립트, 설정 저장·다음 실행 재사용·별도 변경, 완료 후 머지·푸시.
- 구현: scripts/setup_runtime.py/setup_flashing.py와 Bash/PowerShell/CMD 진입점. 토큰 DPAPI/Linux600, 원자 JSON 저장/백업, 실제 연결만 실행, 소유 자식 정상 종료, 선택적 이미지/manifest 설정.
- 실제 SSH/TC/COM/fastboot/모델/BSP 작업은 실행하지 않았다. T-141/T-130/T-136 NOT_RUN. 운영 baseline NONE 유지.

## 독립 리뷰

새 gpt-6-astra 세션 `/root/setup_astra_review`의 초기 CHANGES_REQUESTED와 최종 APPROVED. REG-0029의 일곱 지적을 수정했다. [최종 리뷰 및 해시](20261103-setup-wizard-evidence/astra-review.txt). 이는 실제 Claude 검토나 실장비 인수가 아니다.

## 독립 시험

별도 gpt-6-sol 세션 `/root/setup_sol_tests`가 tests/test_setup_runtime.py를 작성하고 실행했다. 주 작업자가 결과와 Linux 이식성을 검토하여 재시험을 요청했다. 최초 시험 자체의 SSH argv 기대 슬라이스 오류(35 PASS/1 FAIL/2 SKIP)는 보존하고 수정했다. 중간 Windows44 PASS/4 SKIP, 연관 회귀74 PASS/경고1. 이후 메뉴 기본값 변경 및 Linux mock 상수 보강 후 최종 결과를 아래 추가한다. 미실행을 PASS로 기록하지 않는다.

원본 출력/JUnit/해시: `.local-reports/setup-sol-20261103/`. 게시 증거는 [증거 폴더](20261103-setup-wizard-evidence/README.md)에 기록한다.

최종 로컬 v2: Windows Python3.13.5 신규45 PASS/4 SKIP, 관련 회귀74 PASS/기존 수집 경고1. SKIP은 POSIX 권한·실제 작은 POSIX 자식 정상 종료·Bash 진입점 및 Windows symlink 권한 부재다. Windows mock 상수를 별도 fixture로 제공해 Linux에서도 계약 시험을 수행하며 메뉴3 재사용 시험에는 설치된 venv 조건을 명시했다. 제품 코드/Astra 해시와 sol manifest-v2가 일치함을 주 작업자가 확인했다.
