# 2026-11-18 웹 커넥터 좌우 패널 게시

RQ-63/73 · D-81 · T-287 · REG-0114/0115. 사용자 지시로 완료한 웹 커넥터 변경을 커밋·푸시·main에 머지한다. 기존 root 작업 트리의 timeout/Mock·미러 문구·플러그인 모듈 작업은 포함하지 않고 보존한다. 별도 worktree는 `/Users/younghokim/dashboard/.worktrees/connector-split-20261118`, 기준 main은 `74b348c8af8645c10b622c311f2e75522aeaf6f6`이다.

제품 자산2개와 브라우저 시험1개는 [구현 검증](20261118-connector-split.md)의 최종 bytes를 그대로 복사했다. API·DB·실행 정책 변경 없음. 최신 원격 TC projection/전달 기능을 선행 기준으로 유지하며 전달 pin·검증·원격 확인은 게시 완료 후 이 기록에 남긴다. 원본 로그는 root의 `.local-reports/20261118-connector-split-publication/` 로컬 전용이다.

사용자 후속으로 게시 완료 후 로컬 보드 커넥터를 재실행한다. 현재 macOS에서는 원본/전달 폴더의 모의 preview 두 프로세스가 실행 중이며 실제 Windows 장비 작업과 구분한다. 설정/실행 기록 삭제나 실제 TC 실행은 포함하지 않는다.


## 코드 게시와 최소 재확인

고정 코드·시험 커밋은 `2609d394660f7cab9acee49baa8e3c844a4318b1`이다. 일반 HTTPS push는 인증 정보 부재로 거부돼 인증된 GitHub API로 같은 tree `f6aac76b64030485fde7c1b84973e7b594e9b9a9`를 게시했다. 로컬 임시 커밋17fe99f와 API 코드 커밋의 tree 일치를 확인했으며 복구 ref/번들을 보존한다.

제품 자산/시험3개와 모의 host/fixture7개의 bytes가 최초8개 검증과 같은 것을 확인했다(`runtime-comparison.json`). 같은 시험의 과거 PASS를 다른 bytes에 재사용하지 않았다. 최신 main 분리 작업본에서는 대량 목록·조절 경계·비율 보존·좁은 창을 묶은 기존 시험1개만 추가 실행해 PASS(1.4분/종료0)했다. 원본 로그는 `browser-integration-1.log`, fixture/캡처는 분리 작업본의 `.local-reports/20261118-connector-split-publication/`에 있다. 새 의존성 설치·광역 회귀는 수행하지 않았다.

T-287의 원래7+1개와 이번 통합1개 PASS는 로컬 모의 근거이며 실제 회사·Windows·SSH/UART 인수와 독립 Claude 리뷰는 미실행이다. 이식 안내는 [PORT-009](../../porting/PORT-009.md#2026-11-18--웹-커넥터-tc로그-좌우-패널)와 문서 지도에 같은 코드 pin으로 추가했다.

사용자 후속 지시에 따라 머지 완료 후 반영된 로컬/원격 브랜치를 정리한다. 삭제 전 모든 현재 refs를 root 로컬 `branches-before-cleanup.bundle`에 보관하고 `git bundle verify` 종료0을 확인했다. 원격의 병합 완료 여부와 로컬의 patch 동등성/최신 구현에 의한 대체 여부를 분리 확인하며 미반영 작업과 root 미커밋 변경은 보존한다. 실제 삭제/재실행 결과는 완료 보고에 남긴다.
