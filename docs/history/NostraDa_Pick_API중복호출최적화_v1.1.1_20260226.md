# NostraDa_Pick 히스토리 - API 중복 호출 최적화 (Pre-fetch 방어)
- **작성일**: 2026년 2월 26일
- **버전**: v1.1.1

## 1. 개발 배경 (Background)
`v1.1`에서 1인 1표 보장을 위해 백엔드 API DB에 UNIQUE 속성을 걸었으나, **사용자가 투표 버튼을 악의적으로 광클릭할 시 벡엔드 API(`POST /api/bet`)로 트래픽이 몰려 DB Connection과 서버에 무리가 갈 소지가 큼(DDoS)**. 이를 방지하기 위한 UI/프론트엔드 레벨의 선제적 차단이 요구됨.

## 2. 의사 결정 논의 사항
- **최적화 전략 (Pre-fetch Caching)**:
    - 매번 누를 때마다 백엔드로 "나 투표했어?" 물어보는 대신, 화면 진입 시 로그인된 사용자라면 **"/api/bets/me" (내가 투표한 이슈 ID 리스트)**를 딱 1번만 GET으로 긁어옴.
    - 프론트엔드 진입 시 `[issue_uuid_1, issue_uuid_2]` 와 같은 배열을 들고 곧바로 DOM 트리를 순회하여 일치하는 투표 버튼들을 애초에 원천 비활성화(`disabled=true`) 처리해버림.

## 3. 핵심 변경 내역 (Changelog)
- **`routes/api.py`**:
    - `GET /api/bets/me` 라우터를 추가. 플라스크 세션의 `user.id` 값을 기반으로 Supabase `bets` 테이블을 단순 SELECT (`select('issue_id')`).
- **`static/js/app.js`**:
    - 로그인 여부 분기(`isLoggedIn === true`) 시 `fetchAPI('/api/bets/me')`를 가장 먼저 호출하도록 추가.
    - 리턴받은 데이터 배열 안에 있는 이슈 번호를 `data-issue-id` 속성으로 가진 모든 버튼을 `forEach`로 찾아 회색으로 덮고 "✅ 본 투표" 메시지로 치환함.
    - (추가 방어) 최초 1회 버튼 클릭 직후에도 응답이 오기 전까지 `btn.disabled = true`로 곧바로 묶어서 API 더블클릭 콜을 막음.

## 4. 리뷰
- **결과**: 서버/DB 부하 방지 및 부드러운 UI 제공 (페이지 로드 시 투표한 카드는 즉시 회색으로 잠김).
- 사용자 경험 관점에서도 자신이 참여한 이력이 명확히 구별되어 게임 직관성이 대폭 상승함.
