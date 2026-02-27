# 닉네임 변경 및 랭킹 표시 개선 기능 명세서

## 1. 개요
사용자가 기본 구글 이름(혹은 이메일) 대신 고유한 닉네임을 설정할 수 있도록 기능을 추가합니다.
랭킹보드에서는 이메일 대신 닉네임이 표시되도록 개선하며, 닉네임 변경은 1일 1회로 제한합니다.

## 2. 데이터베이스 (Supabase `users` 테이블)
- `nickname` (VARCHAR) 컬럼 추가: 사용자의 표시 이름
- `last_nickname_changed_at` (TIMESTAMP) 컬럼 추가: 마지막 닉네임 변경 시각 기록 (1일 제한 검증용)

## 3. 백엔드 (Flask API & Auth)
- **`auth.py` 로그인 로직 개선**:
  - `users` 테이블에 처음 추가될 때 구글 `name`을 `nickname`에 기본 저장.
  - 기존 유저도 `nickname`이 없으면 업데이트.
  - 세션 정보에 DB의 `nickname`과 `last_nickname_changed_at` 여부 추가.
- **`api.py` 라우터 추가/수정**:
  - `POST /api/users/nickname`: 닉네임 변경 API (1일 1회 제한 검증, 중복 체크 혹은 단순 업데이트)
  - `GET /api/leaderboard`: 기존 `email` 반환을 `nickname` 반환으로 변경.
  - `GET /api/users/me`: `nickname`, `last_nickname_changed_at` 정보 추가.

## 4. 프론트엔드 (UI & JS)
- **초기 진입 안내 팝업**:
  - 로그인 후 `last_nickname_changed_at`가 null 인 경우 (즉 첫 가입/첫 방문) "닉네임을 설정해주세요 (1일 1회 변경 가능)" 모달 표시.
- **내 정보 섹션**:
  - 내 정보에 '이메일' 대신 '닉네임' 우선 표시.
  - [닉네임 변경하기] 버튼 추가.
- **랭킹보드 (명예의 전당)**:
  - 렌더링 시 이메일 대신 닉네임 출력.

## 5. 실시간 반영 정책
- Supabase 업데이트이므로 변경 즉시 DB에 적용하고 세션을 업데이트하여 실시간으로 반영.
- 부하가 거의 없는 단순 UPDATE 문 1회이므로 실시간 처리.
