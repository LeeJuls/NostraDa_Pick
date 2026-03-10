# NostraDa Pick - AI 출제 방향성(타겟팅) 제어 명세서
**버전:** v1.0
**작성일자:** 2026-03-06

## 1. 개요
운영자가 원하는 특정 키워드나 주제(예: "미국-이란 피격", "비트코인", "손흥민 골")를 지정하면, 4시간마다 동작하는 Gemini AI 기반 문제 출제 봇(Scheduler)이 해당 주제를 우선적으로 분석하여 퀴즈(이슈)로 만들어내는 **"타겟 맞춤형 출제 시스템"**의 구축 명세입니다.

## 2. 목표 및 요구사항
1. **유연한 주제 제어:** 웹 어드민 패널에서 손쉽게 출제 타겟 주제(텍스트 배열)를 입력하고 수정할 수 있어야 합니다.
2. **다중 키워드 지원:** 여러 개의 키워드를 쉼표(,)로 구분하여 입력 가능해야 합니다.
3. **가중치 부여 (프롬프트 조정):** 제공된 타겟 키워드 중 최소 1개 이상이 실제 출제 문제에 포함될 수 있도록 AI 프롬프트를 고도화해야 합니다.
4. **폴백(Fallback) 모드:** 어드민 설정값이 공백(랜덤)일 경우, 기존처럼 AI가 자유롭게 실시간 트렌드(경제, 정치 등)로 문제를 출제하도록 유지해야 합니다.

## 3. 세부 설계 내역

### 3.1 DB 구조 (Supabase)
새로운 테이블 `admin_settings` 또는 기존 키값 관리 테이블 신설:
- **Table Name:** `app_settings` (단일 Row(싱글톤) 형태로 운영 설정값 중앙 제어)
- **Columns:**
  - `id` (UUID, 기본 키)
  - `key` (TEXT, 식별 키 - 예: `"target_topics"`)
  - `value` (JSONB 또는 TEXT - 키워드들을 저장)
  - `updated_at` (TIMESTAMP)

### 3.2 Backend API (Flask)
- **GET `/api/admin/settings/target_topics`:** 현재 저장된 타겟 키워드 반환
- **POST `/api/admin/settings/target_topics`:** 새로운 타겟 키워드 배열 저장 (운영자/어드민 권한 체크)
- **Gemini Service 연동 (`services/gemini_service.py`):**
  - 문제 출제 직전 (`generate_trending_issues()` 내부) `app_settings` 테이블에서 설정값을 Read.
  - 키워드가 있을 경우 프롬프트의 지시문 격상: 
    > *"Focus heavily on the following specific trending topics or keywords: {topics}. Ensure at least 1-2 generated prediction issues are directly related to these topics."*

### 3.3 Frontend (Admin UI)
- 현재 로컬 전용으로 노출 중인 `div#admin-panel`에 요소를 추가합니다.
- **UI 컴포넌트:**
  - `🎯 AI 타겟 주제 설정` (Label)
  - `input type="text"` (예: "미국, 이란 전쟁, 비트코인 10만달러, 애플 AI")
  - `[저장]` (Button)
- 변경 시 곧바로 다음 강제 문제 생성(또는 스케줄링)부터 변경된 주제가 AI 출제에 반영됩니다.

## 4. 작업 단계 (Phase)
1. DB(Supabase) `app_settings` 테이블 기획 및 SQL 스크립트 작성/적용.
2. Flask 컨트롤러에 DB 읽기/쓰기 용 API 생성.
3. `gemini_service.py` 내부 프롬프트와 연결.
4. 프론트엔드 `app.js` 및 `base.html`에 관리자용 설정 UI 추가.
5. 로컬 테스트(원하는 키워드로 "강제 문제 생성") 후 Github 푸시 대기.
