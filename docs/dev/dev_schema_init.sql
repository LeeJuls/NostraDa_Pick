-- =========================================================
-- NostraDa_Pick (노다픽) - 개발(Local) 전용 DB 스키마 초기화
-- =========================================================
-- 📌 설명: 라이브 서비스와 로컬 개발 데이터 격리를 위해 'dev_' 접두사를 추가한 테이블입니다.
-- 📌 실행 방법: Supabase 대시보드 -> SQL Editor -> 복사 후 "RUN" 클릭

-- 1. 사용자(Users) 테이블
CREATE TABLE IF NOT EXISTS public.dev_users (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    email VARCHAR(255) UNIQUE NOT NULL,
    nickname VARCHAR(255),
    last_nickname_changed_at TIMESTAMP WITH TIME ZONE,
    points INTEGER DEFAULT 1000 NOT NULL CHECK (points >= 0),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- 2. 이슈/문제(Issues) 테이블
-- 외래키(correct_option_id)는 options 테이블 생성 후 아래에서 추가(ALTER)합니다.
CREATE TABLE IF NOT EXISTS public.dev_issues (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    title VARCHAR(500) NOT NULL,
    category VARCHAR(50) NOT NULL,
    status VARCHAR(20) DEFAULT 'OPEN' CHECK (status IN ('OPEN', 'RESOLVING', 'RESOLVED', 'CANCELLED')),
    close_at TIMESTAMP WITH TIME ZONE NOT NULL,
    resolved_at TIMESTAMP WITH TIME ZONE NULL,
    correct_option_id UUID NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- 3. 선택지(Options) 테이블
CREATE TABLE IF NOT EXISTS public.dev_options (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    issue_id UUID NOT NULL REFERENCES public.dev_issues(id) ON DELETE CASCADE,
    title VARCHAR(255) NOT NULL,
    pool_amount INTEGER DEFAULT 0 NOT NULL CHECK (pool_amount >= 0),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- 이제 issues 테이블의 정답 옵션 컬럼에 fk_dev_correct_option 외래키 조약 추가
ALTER TABLE public.dev_issues
    ADD CONSTRAINT fk_dev_correct_option 
    FOREIGN KEY (correct_option_id) 
    REFERENCES public.dev_options(id) 
    ON DELETE SET NULL;

-- 4. 베팅 내역(Bets) 테이블
CREATE TABLE IF NOT EXISTS public.dev_bets (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES public.dev_users(id) ON DELETE CASCADE,
    issue_id UUID NOT NULL REFERENCES public.dev_issues(id) ON DELETE CASCADE,
    option_id UUID NOT NULL REFERENCES public.dev_options(id) ON DELETE CASCADE,
    amount INTEGER NOT NULL CHECK (amount > 0),
    status VARCHAR(20) DEFAULT 'PENDING' CHECK (status IN ('PENDING', 'WON', 'LOST', 'REFUNDED')),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    CONSTRAINT unique_dev_user_issue_bet UNIQUE (user_id, issue_id) -- 1인 1표 제약
);

-- 🚨조회 성능 고도화를 위한 INDEX 추가 
CREATE INDEX IF NOT EXISTS idx_dev_issues_status ON public.dev_issues(status);
CREATE INDEX IF NOT EXISTS idx_dev_options_issue_id ON public.dev_options(issue_id);
CREATE INDEX IF NOT EXISTS idx_dev_bets_user_id ON public.dev_bets(user_id);
CREATE INDEX IF NOT EXISTS idx_dev_bets_issue_id ON public.dev_bets(issue_id);
