# 보드명 옆 PuTTY 아이콘과 목록 대수 요약

2026-11-15 · RQ-63/T-266. 기준 b120932 위 로컬 배치 시안이며 커밋/게시하지 않았다.

PuTTY 열기는 선택 보드 이름 옆 30px 터미널 아이콘으로 옮겼다. 상태별 접근 이름·보드명 tooltip·기존 입력 제어/작업 중/stale/반환 재시도 차단을 유지한다. 등록·감지·시험 중 대수는 보드 리스트 제목 오른쪽에 작은 세 열로 표시한다. 기존 상단 요약과 별도 PuTTY 버튼 행을 제거했으며 API/DB/의존성 변경은 없다.

기존 Chromium 회귀 15개에서 아이콘 크기/위치/접근 이름과 목록 요약 위치를 추가 확인한다. 1360/390px 가로 넘침·키보드, 연결·편집·다중 탭/CSRF·stale·반환 중 표시 회귀를 함께 실행한다.

최초 `browser.log`는 14 PASS/1 FAIL이었다. 편집 중 스타일 파일에 잘못된 내용을 저장해 크기 검증이 실패했다. 처음 확인한 clean 기준의 원래 스타일을 정확히 복구하고 이번 배치 규칙만 적용했다. 실패 로그를 보존하고 같은 시험을 `browser-retest.log`로 재실행했다. 원본 로그와 manifest는 `.local-reports/20261115-connector-header/`에 둔다.

실제 Windows/PuTTY/장비 시험과 새 독립 리뷰는 수행하지 않았다. 이 로컬 시안은 기존 공개 전달 커밋에 포함되지 않는다. 시험 결과와 코드/시험 해시는 아래 기록을 따른다.

최종 재시험 `browser-retest.log` **15 PASS**, 26.5초. 명령은 고정 Node/Chromium 환경의 `.venv/bin/python scripts/test_connector_browser.py`다. 제품 SHA256 `a3b915a02bfae5de63bea2f4d39f042ece8f0f6f40f401e1b4c2e628da8ccdda`, 시험 SHA256 `33ec9b07d52528d88eb2486a0f5e8443d6c46b7f5d139d372671aa3e351346eb`. native Chrome 제어 도구는 pipe 시작 오류로 갱신할 수 없어 실제 열린 탭과 fixture 검증을 구분한다.
