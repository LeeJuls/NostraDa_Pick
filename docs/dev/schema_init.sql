-- =========================================================
-- NostraDa_Pick (노다픽) - DB 스키마 초기화 스크립트 (Task 1-1)
-- =========================================================
-- 📌 실행 방법: Supabase 대시보드 -> SQL Editor -> 복사 후 "RUN" 클릭

-- 1. 사용자(Users) 테이블
CREATE TABLE IF NOT EXISTS public.users (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    email VARCHAR(255) UNIQUE NOT NULL,
    nickname VARCHAR(255),
    last_nickname_changed_at TIMESTAMP WITH TIME ZONE,
    points INTEGER DEFAULT 1000 NOT NULL CHECK (points >= 0),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- 2. 이슈/문제(Issues) 테이블
-- 외래키(correct_option_id)는 options 테이블 생성 후 아래에서 추가(ALTER)합니다.
CREATE TABLE IF NOT EXISTS public.issues (
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
CREATE TABLE IF NOT EXISTS public.options (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    issue_id UUID NOT NULL REFERENCES public.issues(id) ON DELETE CASCADE,
    title VARCHAR(255) NOT NULL,
    pool_amount INTEGER DEFAULT 0 NOT NULL CHECK (pool_amount >= 0),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- 이제 issues 테이블의 정답 옵션 컬럼에 fk_correct_option 외래키 조약 추가
ALTER TABLE public.issues
    ADD CONSTRAINT fk_correct_option 
    FOREIGN KEY (correct_option_id) 
    REFERENCES public.options(id) 
    ON DELETE SET NULL;

-- 4. 베팅 내역(Bets) 테이블
CREATE TABLE IF NOT EXISTS public.bets (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
    issue_id UUID NOT NULL REFERENCES public.issues(id) ON DELETE CASCADE,
    option_id UUID NOT NULL REFERENCES public.options(id) ON DELETE CASCADE,
    amount INTEGER NOT NULL CHECK (amount > 0),
    status VARCHAR(20) DEFAULT 'PENDING' CHECK (status IN ('PENDING', 'WON', 'LOST', 'REFUNDED')),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    CONSTRAINT unique_user_issue_bet UNIQUE (user_id, issue_id) -- 1인 1표 제약
);

-- 🚨조회 성능 고도화를 위한 INDEX 추가 
CREATE INDEX IF NOT EXISTS idx_issues_status ON public.issues(status);
CREATE INDEX IF NOT EXISTS idx_options_issue_id ON public.options(issue_id);
CREATE INDEX IF NOT EXISTS idx_bets_user_id ON public.bets(user_id);
CREATE INDEX IF NOT EXISTS idx_bets_issue_id ON public.bets(issue_id);

-- [QA 코멘트]: 각 제약조건(CHECK)이 올바르게 설계되어, 마이너스(-) 베팅이나 상태값 오타 등을 원천 차단했습니다.
-- [GA] 중복 투표 방지를 위해 UNIQUE 제약조건 추가.
