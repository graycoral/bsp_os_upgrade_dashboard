# 보드 커넥터 · Astra 잔여 4건 코드 재검토

2026-11-12. root가 기존 독립 Astra 세션에 새 코드를 읽기 전용으로 후속 검토하도록 요청했다. Astra는 제품 편집/추가 시험을 실행하지 않았다. 판정은 **해당 4건의 로컬 코드 수정 확인 범위 APPROVED**, 추가 필수 차단 없음이다. 전체 제품/회사 Windows 인수 승인이나 Claude 리뷰 완료를 뜻하지 않는다.

| 지적 | 수정 확인 |
|---|---|
| batch RX의 다른 보드 control/normal RX 충돌 | 모든 control COM/다른 RX owner 전역 검증, subset 보드 소유 이전 |
| durable error stream의 empty ACK 이후 중복 | error_events 키의 존재로 legacy fallback 구분, producer 안정 event_id 사용 |
| 저장 console의 freshness | 등록 verified_at과 projection received_at 모두 15초 내 확인, last-known/stale 명시 |
| safe-stop의 legacy flash 우회 | Host TC·batch reserve·legacy flash·batch prepare의 같은 stopping fence |

Astra는 최종 received_at 재등록-only stale 회귀 정의도 읽고 잔여 닫힘을 확인했다. 실제 시험 결과는 Sol의 [실행 기록](20261112-board-connector-gui.md)에 귀속한다. 이후 일반적인 F2 보강(외부 TC Python 미설정에서도 bootstrap, 실행 preflight/integration만 차단)과 GUI 표시 정리는 이 좁은 승인 범위로 확대하지 않는다. 회사 T-228 NOT_RUN을 유지한다.
