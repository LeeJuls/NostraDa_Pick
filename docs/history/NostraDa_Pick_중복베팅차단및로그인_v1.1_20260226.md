# NostraDa_Pick 히스토리 - 로그인 및 1인 1표 제약 (중복 베팅 차단) 연동
- **작성일**: 2026년 2월 26일
- **버전**: v1.1

## 1. 개발 배경 (Background)
사용자의 추가 기능 요구사항("투표를 한 명이 여러 번 하면 안되고 자기 기록이 있어야 하니 로그인 기능을 추가해야 함")에 따라, **구글 OAuth 로그인 연동과 더불어 Supabase DB 상에 "1인 1표 고유 제약(UNIQUE)" 방식**을 기획하고 구현함.

## 2. 의사 결정 논의 사항
- **어뷰징(중복 투표) 방지 전략 선정**:
    - **옵션 A (앱 레벨 검증)**: Python API 단에서 DB를 SELECT하여 검증 후 없으면 `INSERT` -> 동시성 이슈(Race Condition) 시 뚫릴 우려가 있음.
    - **옵션 B (DB 레벨 제약)**: `bets` 테이블에 `UNIQUE (user_id, issue_id)` 복합키를 추가하여 DB 엔진이 원천 차단.
    - **최종 결정**: 가장 견고한 **옵션 B**를 채택함. 에러 메시지(Violation)를 Catch하여 `409 Conflict` "이미 참여한 투표입니다"로 반환.

- **유저 정보 동기화 타이밍**:
    - 구글 로그인 후 토큰에서 획득한 이메일을 기준으로 `supabase.table('users')` 조회를 들어감. 없으면 신규 가입(1000포인트 기본 지급), 있으면 ID를 가져와 세션에 엮음.
    - 유저 개인이 프로필이나 정보를 언제든 확인 가능하게 함.

## 3. 핵심 변경 내역 (Changelog)
- **`docs/dev/schema_init.sql`**: `bets` 테이블에 복합 UNIQUE (`CONSTRAINT unique_user_issue_bet UNIQUE (user_id, issue_id)`) 추가.
- **`routes/auth.py`**: 카카오/구글 로그인 콜백 시나리오를 바탕으로 Supabase DB 연동. (API 키 여부에 따라 조건부 실행)
- **`routes/api.py`**: POST `/api/bet` 엔드포인트를 신설하여 1) 세션 검증, 2) 이슈 OPEN 검증, 3) 500/409/200 에러 핸들링과 Supabase INSERT 수행 로직 완성.
- **`static/js/app.js` & `templates/index.html`**:
    - `<button>` 태그를 `onclick="alert()"` 목업에서 실제 `data-issue-id` 기반의 fetch POST로 탈바꿈.
    - 로그인 안 한 사용자는 클릭 시 `/auth/login` 유도. 성공하거나 이미 투표인 경우 버튼을 비활성화(disabled).

## 4. 리뷰 및 다음 계획
- 프론트 UI / 백엔드 Auth 뼈대 / DB 제약조건 모두 연결됨.
- 다음 스텝으로는 실제 "OPEN 상태 이슈 및 투표 진행바 비율" 등을 DB에서 가져오도록 `routes/api.py` 의 GET API들을 고도화할 예정.
