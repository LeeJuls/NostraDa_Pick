# 프로젝트_실시간데이터마이그레이션_v1.0_20260226

## 1. 개요
현재 로컬 개발 환경에서 사용 중인 모든 하드코딩(더미) 데이터를 실시간 **Gemini AI 추천 문제**와 **Supabase DB 데이터**로 치환하여 서비스 실효성을 확보함.

## 2. 주요 개발 항목
- **로그인 환경 정비**: 구글 OAuth 로컬 테스트를 위한 Redirect URI 가이드 제공.
- **Gemini 이슈 생성 자동화**: 매일 최신 뉴스 기반의 예측 주제를 생성하는 `gemini_service` 구축.
- **DB 연동 고도화**: 
  - `issues`, `options`, `users`(랭킹) 데이터를 API를 통해 동적으로 서빙.
  - 프론트엔드(`app.js`)의 하드코딩 UI를 API 연동 기반 동적 생성(`fetch & render`) 방식으로 전환.

## 3. 세부 작업 리스트 (To-do)
- [ ] `services/gemini_service.py` 생성 및 프롬프트 최적화
- [ ] Supabase `issues` 테이블 초기 데이터 샘플 삽입
- [ ] `api.py` 내 모든 `dummy_data` 제거 및 `supabase.table()` 조회 로직으로 변경
- [ ] `index.html` 의 정적 카드 마크업을 JS 템플릿으로 이전
- [ ] 랭킹 보드(`Leaderboard`) DB 연동 API 추가 및 반영

## 4. 일정 및 세이브 포인트
- **SP 1**: Gemini API 연동 테스트 및 이슈 생성 확인
- **SP 2**: 벡엔드 API 전체 DB 연동 완료
- **SP 3**: 프론트엔드 동적 렌더링 전환 완료

---
**작성자**: NostraDa_Pick Agent (PM/Backend)
**날짜**: 2026-02-26
