-- =========================================================
-- NostraDa_Pick - 이슈 사전 번역 컬럼 추가 (API 호출 최적화)
-- =========================================================
-- 📌 실행 방법: Supabase 대시보드 -> SQL Editor -> 복사 후 "RUN"
-- 📌 효과: 이슈 생성 시 1회만 번역 → DB 저장 → 사용자에게 즉시 제공
-- =========================================================

-- [라이브] issues 테이블 번역 컬럼 추가
ALTER TABLE public.issues ADD COLUMN IF NOT EXISTS title_ko TEXT;
ALTER TABLE public.issues ADD COLUMN IF NOT EXISTS title_ja TEXT;
ALTER TABLE public.issues ADD COLUMN IF NOT EXISTS title_de TEXT;
ALTER TABLE public.issues ADD COLUMN IF NOT EXISTS title_fr TEXT;
ALTER TABLE public.issues ADD COLUMN IF NOT EXISTS title_es TEXT;
ALTER TABLE public.issues ADD COLUMN IF NOT EXISTS title_pt TEXT;
ALTER TABLE public.issues ADD COLUMN IF NOT EXISTS title_zh TEXT;

-- [개발] dev_issues 테이블 번역 컬럼 추가
ALTER TABLE public.dev_issues ADD COLUMN IF NOT EXISTS title_ko TEXT;
ALTER TABLE public.dev_issues ADD COLUMN IF NOT EXISTS title_ja TEXT;
ALTER TABLE public.dev_issues ADD COLUMN IF NOT EXISTS title_de TEXT;
ALTER TABLE public.dev_issues ADD COLUMN IF NOT EXISTS title_fr TEXT;
ALTER TABLE public.dev_issues ADD COLUMN IF NOT EXISTS title_es TEXT;
ALTER TABLE public.dev_issues ADD COLUMN IF NOT EXISTS title_pt TEXT;
ALTER TABLE public.dev_issues ADD COLUMN IF NOT EXISTS title_zh TEXT;
