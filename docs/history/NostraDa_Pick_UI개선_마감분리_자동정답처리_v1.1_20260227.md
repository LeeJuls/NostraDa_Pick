# [GA] 히스토리 기록: UI 개선, 마감 섹션 분리 및 자동 정답 처리 구현

## 1. 개요
- **일자**: 2026-02-27
- **버전**: v1.1
- **작성자**: Antigravity (GA)
- **주요 내용**: 내가 투표한 옵션 ✅ 표시, 마감 섹션 분리, 6시간 제한 및 정답 처리 자동화

## 2. 의사 결정 및 논의 사항
- **투표 옵션 식별**: 기존의 `issue_id` 목록만 반환하던 API 형식을 `{ issue_id: option_id }`로 확장하여 프론트엔드에서 특정 버튼에만 강조 효과를 줄 수 있도록 설계함.
- **섹션 분리 로직**: 별도의 API 호출 대신 기존 open_issues 데이터를 프론트엔드에서 `close_at` 기준으로 분류하여 렌더링함으로써 API 호출 횟수를 최적화함.
- **정답 처리 자동화**: `resolver_service.py`를 신설하여 Gemini로 정답을 판정하고, 이를 00:00/12:00 UTC에 맞춰 실행할 수 있는 구조를 마련함.

## 3. 변경 상세 (Code Changes)
- **Backend**:
  - `routes/api.py`: `/api/bets/me` 반환 형식 딕셔너리로 변경.
  - `services/gemini_service.py`: 퀴즈 기간 최대 6시간 제한 로직 추가.
  - `services/resolver_service.py`: [NEW] 자동 정답 처리 및 포인트 지급 핵심 로직.
  - `run_resolve.py`: [NEW] 서비스 트리거 스크립트.
- **Frontend**:
  - `static/js/app.js`: 투표한 개별 옵션에 체크 표시 및 초록 테두리 추가. 진행/마감 섹션 분리 렌더링.
  - `templates/index.html`: `issues-list-closed` 섹션 및 `refresh-info` 문구 추가.

## 4. 커밋 메시지
- `[GA] UI 개선(투표 체크표시, 마감 섹션 분리) 및 정답 자동 처리(6시간 제한) 구현`
