# 보드 커넥터 웹 기본 전환 · Astra xhigh 리뷰

검토자: 독립 subagent / `gpt-6-astra` / reasoning `xhigh`. 기준 HEAD `e4f53ca1ec288feb3eb1b9ccff8335a398ad321c`와 해당 시점 작업 트리. 다른 세션의 공통 설정·플러그인 중심 변경은 보존한다.

## 설계 검토 · APPROVED

최초 검토 입력에 웹 opt-in/Qt 기본이라는 잘못된 범위를 포함했다. 사용자는 웹 기본 전환으로 바로잡았으며, Astra가 추가 검토에서 **browser 기본·Qt 명시 옵션**을 APPROVED했다. 최초 opt-in 판정을 최종 사용자 승인으로 취급하지 않는다.

채택 조건:

- 같은 Windows Manager/Host/SSH/COM 실행 코어 재사용, 별도 Worker/실행 관리자 없음.
- 브라우저 전용 경로와 기존 비브라우저 IPC 경계 분리. 단기 일회성 fragment 티켓, instance별 쿠키/경로, 정확한 Host/Origin/port·CSRF, HttpOnly/SameSite·CSP/no-store.
- 로컬 설정 revision과 연결/저장 공통 잠금. 편집 초안·미지 설정·RTS/DTR·inactive board 보존.
- 실제 inventory 수집 시각 기준 stale 표시, 공통 설정 저장/PENDING/APPLIED/BLOCKED 구분.
- 표준 Windows 경로 선택과 직접 입력, Qt 의존성 없는 기본 실행/진단, UI 선택을 항상 자식에 전달.
- 구버전 Manager capability/자산/브라우저 실패를 구분하고 실행 중 작업을 종료하거나 두 번째 Manager를 만들지 않음.
- CMD 단계 진단은 회사 경로 오류의 원인 확정과 분리하고 AutoRun의 이미 발생한 최초 오류까지 해결했다고 주장하지 않음.

## 구현 후 독립 리뷰 · 최초 시도 NOT_RUN

실제 변경 파일을 대상으로 같은 Astra xhigh subagent에 구현 후 리뷰를 요청했다. 응답은 **usage limit으로 agent turn 실패**였으며 코드 리뷰 결과는 반환되지 않았다. 토큰/시간을 더 사용해 재요청을 반복하거나 다른 모델을 Astra 리뷰로 표시하지 않았다.

이 시점의 상태는 `DESIGN_APPROVED / IMPLEMENTATION_REVIEW_NOT_RUN_USAGE_LIMIT`였다. 구현자의 자체 점검·단위/브라우저 시험 통과를 독립 리뷰 APPROVED로 표시하지 않았다.

## 제한 해제 후 실제 코드 리뷰 · CHANGES_REQUESTED → APPROVED

안내된 제한 해제 시각 이후 같은 `gpt-6-astra` / `xhigh` agent에서 실제 구현을 검토했다. 최초 구현 후 판정은 **CHANGES_REQUESTED**였으며 비활성 보드 RTS/DTR 소실(P1), 새 탭의 기존 CSRF 무효화(P2), 지연 저장 중 초안 덮어쓰기(P2), pending 상태 요청 중 과거 fresh 표시(P2)를 지적했다. 별도 재현으로 앞 두 건을 확인했고 로그를 보존했다.

모든 지적을 수정하고 서버 폴더 선택 버튼의 입력 잠금 누락까지 보완한 뒤 같은 agent가 재검토해 **APPROVED**했다. 승인 범위는 **웹 기본 전환과 지적 네 건의 수정**이며 이 범위의 남은 차단 결함을 확인하지 못했다. 코드 변경은 구현자가 수행했으며 검토자는 제품 파일을 수정하지 않았다.

검토자가 독립 실행한 새 web 단위 시험은 34 PASS(`astra-unit-retake-1.log`)다. 최종 회귀 238 PASS/Windows 18 SKIP(`regression-1.log`)와 Chromium 10 PASS(`browser-1.log`) 로그도 확인했다. 코드/시험 manifest와 실패·수정·재시험은 [실행 기록](20261114-connector-web.md)을 따른다.

별도 public-tools 자동 설치의 실제 동작은 승인 범위가 아니다. 이 접점의 동시 추가로 생긴 launcher fixture 7 FAIL을 보존하고 외부 설치를 모의 처리한 후 238 PASS로 재시험했다. 실제 Windows/회사 인수로 확대하지 않는다. 현재 최종 상태는 `DESIGN_APPROVED / WEB_IMPLEMENTATION_REVIEW_APPROVED / COMPANY_ACCEPTANCE_NOT_RUN`이다.

실제 Windows CMD·네이티브 파일 선택·Z:/UNC·회사 SSH/COM/USB 인수는 NOT_RUN이다. 설계 리뷰는 그 인수 승인이 아니다.

## 후속 탭 delta · CHANGES_REQUESTED → APPROVED

같은 작업 폴더에서 뒤이어 보드 설정/로그 subtab과 storage/BC-29 변경이 추가되어 앞선 승인을 현재 전체 바이트로 확대하지 않고 탭 delta를 별도 검토했다. 같은 Astra xhigh가 다중 invalid 처리기 충돌과 tab↔panel ARIA 연결 누락을 P2로 지적했다. 첫 invalid 처리 하나로 통합하고 여러 보드의 빈 COM을 순서대로 수정하는 시험, 안정 id/aria-controls/aria-labelledby 및 초점/방향키 시험을 반영했다.

두 P2의 **코드·시험 변경 delta는 APPROVED**다. 검토자는 이 마지막 delta의 최신 브라우저 결과를 직접 재실행/확인한 것으로 표시하지 않았다. 구현자가 최신 통합 Chromium 12 PASS와 관련 회귀 241 PASS/Windows 20 SKIP를 실행·기록한다. storage 실제 정리와 BC-29 공개 도구 설치, 실제 Windows 인수는 이 승인 범위 밖이며 별도 작업/현지 검증을 따른다.
