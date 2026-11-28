# 다중 플러그인과 작업별 Agent Monitor 검증

RQ-87 · T-324 · PORT-021. 기준 소스 `377832f`. 회사 Linux 계정 두 개, 실제 Windows SSH, 보드 인수는 NOT_RUN이다.

## 설계 독립 리뷰

새 Codex 리뷰 세션은 [설계](../../design/MULTI_PLUGIN_OWNERSHIP.md)를 Host, Monitor와 PORT-017·020에 대조해 CHANGES_REQUESTED로 판정했다. 작업별 멱등키와 충돌 정보 제한, 승인 목적지와 터널 세대, 작업용 Monitor의 서버 권한과 두 탭, Run 단위 인계와 기존 분석 lease 회수, 서비스 전용 principal 및 장비 경합을 보완한 뒤 같은 검토자가 APPROVED로 판정했다. Claude 실행 파일은 이 환경에서 찾지 못했다.
