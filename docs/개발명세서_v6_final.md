# [개발 명세서 v6] 노스트라 다 찍기 (Nostradamus Pick-all)

> **작성 기준:** v5 작업 명세서 + 4인(기획/프론트/백엔드/QA) 크로스 리뷰 반영
> **핵심 원칙:** 최소 비용으로 재미 검증 우선. 확장은 검증 후.

---

## 1. 4인 리뷰 반영 사항 요약

| # | 원본(v5) 문제점 | 결정 | 담당 |
|:--|:---|:---|:---|
| 1 | 결과 발표(Reveal) UX 없음 | 메인 상단에 "최근 결과" 섹션 추가 | 기획+프론트 |
| 2 | Supabase Free Tier 50K 요청 초과 예상 | Flask 메모리 캐싱으로 요청 최소화 | 백엔드 |
| 3 | `resolve_issue` RPC N+1 문제 | 벌크 UPDATE로 개선 | 백엔드 |
| 4 | cascade 삭제 트랜잭션 없음 | Supabase RPC 함수로 원자적 처리 | 백엔드 |
| 5 | 동시 베팅 레이스 컨디션 | `place_bet` RPC 내 row-level lock | 백엔드+QA |
| 6 | auto_engine 동시 실행 가능 | System_Config에 lock 플래그 추가 | 백엔드 |
| 7 | 이슈 카드 상태별 UI 구분 부족 | 5가지 상태별 명확한 비주얼 정의 | 프론트 |
| 8 | 0표일 때 50%/50% 오해 | 0표면 비율바 숨기고 "첫 투표를 해보세요" | 기획+프론트 |
| 9 | OPEN 문제 0개일 때 빈 화면 | "곧 새로운 예측이 등장합니다" 안내 | 기획+프론트 |
| 10 | Gemini 부적절 문제 필터링 없음 | 프롬프트에 제한 조건 명시 + DRAFT 검수 | 백엔드+QA |
| 11 | 바이럴 요소 | MVP 생략, Phase 2에서 추가 | 기획 |
| 12 | 알림/리텐션 | MVP 생략, Phase 2에서 추가 | 기획 |

---

## 2. 기술 스택 (확정)

| 구분 | 기술 | 비고 |
|:---|:---|:---|
| Backend | Flask (Python 3.11+) | 라우팅, 세션, API |
| Frontend | Jinja2 + HTML/CSS/JS | 반응형, 바닐라 JS |
| DB/Auth | Supabase (PostgreSQL) | Google OAuth |
| AI | Gemini API (gemini-2.0-flash) | 출제, 번역, 결과 판정 보조 |
| 캐싱 | Flask 메모리 캐시 (cachetools) | Supabase 요청 절감 |
| 광고 | Google AdSense | 네이티브 HTML |
| 배포 | Render.com | Web($7) + Cron(~$1) |

---

## 3. 프로젝트 구조

```
nostradamus-pick/
├── app.py                  # Flask 엔트리포인트
├── config.py               # 환경 변수
├── requirements.txt
├── .env                    # gitignore
├── .gitignore
│
├── routes/
│   ├── __init__.py
│   ├── auth.py             # 로그인/로그아웃/OAuth
│   ├── main.py             # 메인 페이지 (OPEN + 최근 결과)
│   ├── admin.py            # 관리자 대시보드
│   └── api.py              # AJAX (베팅, 언어)
│
├── services/
│   ├── __init__.py
│   ├── supabase_client.py  # Supabase 연결 + 캐싱 래퍼
│   ├── gemini_client.py    # Gemini API (출제, 번역, 결과 판정)
│   ├── cache.py            # 캐시 매니저 (TTLCache)
│   ├── i18n.py             # 다국어
│   └── auto_engine.py      # 풀오토 엔진
│
├── templates/
│   ├── base.html
│   ├── index.html
│   ├── login.html
│   ├── admin/
│   │   └── dashboard.html
│   └── components/
│       ├── issue_card.html
│       ├── result_card.html    # 결과 발표 카드
│       ├── vote_stats.html
│       ├── ranking.html
│       ├── empty_state.html    # 빈 상태 안내
│       └── ad_banner.html
│
├── static/
│   ├── css/style.css
│   └── js/app.js
│
└── render.yaml
```

---

## 4. 데이터베이스 설계

### 4.1 Users 테이블

```sql
CREATE TABLE Users (
    uid UUID PRIMARY KEY,
    nickname VARCHAR(50) NOT NULL,
    email VARCHAR(255),
    role VARCHAR(10) DEFAULT 'user' CHECK (role IN ('user', 'admin')),
    preferred_lang VARCHAR(10) DEFAULT 'en',
    current_streak INTEGER DEFAULT 0,
    max_streak INTEGER DEFAULT 0,
    total_wins INTEGER DEFAULT 0,
    total_played INTEGER DEFAULT 0,
    last_played_date TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX idx_users_ranking ON Users (current_streak DESC, total_wins DESC);
```

> **v5 대비 추가:** `total_played` (총 참여 수) — 승률 계산 가능, `email` — 향후 알림용

### 4.2 Issues 테이블

```sql
CREATE TABLE Issues (
    issue_id SERIAL PRIMARY KEY,
    category VARCHAR(20) NOT NULL,
    question_title TEXT NOT NULL,
    resolution_criteria TEXT NOT NULL,
    status VARCHAR(10) DEFAULT 'DRAFT'
        CHECK (status IN ('DRAFT', 'OPEN', 'CLOSED', 'RESOLVED')),
    correct_answer VARCHAR(3) CHECK (correct_answer IN ('Yes', 'No', NULL)),
    betting_deadline TIMESTAMPTZ,
    total_yes INTEGER DEFAULT 0,
    total_no INTEGER DEFAULT 0,
    source VARCHAR(10) DEFAULT 'manual' CHECK (source IN ('manual', 'auto')),
    resolved_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX idx_issues_status ON Issues (status);
CREATE INDEX idx_issues_deadline ON Issues (betting_deadline) WHERE status = 'OPEN';
```

> **v5 대비 추가:** `resolved_at` — 결과 발표 시점 기록 (최근 결과 섹션 정렬용)

### 4.3 Issue_Translations 테이블

```sql
CREATE TABLE Issue_Translations (
    translation_id SERIAL PRIMARY KEY,
    issue_id INTEGER REFERENCES Issues(issue_id) ON DELETE CASCADE,
    lang_code VARCHAR(10) NOT NULL,
    translated_title TEXT NOT NULL,
    translated_criteria TEXT NOT NULL,
    created_at TIMESTAMPTZ DEFAULT now(),
    CONSTRAINT unique_issue_lang UNIQUE (issue_id, lang_code)
);
```

> **v5 대비 변경:** `ON DELETE CASCADE` 추가 — Issue 삭제 시 번역도 자동 삭제

### 4.4 Bets 테이블

```sql
CREATE TABLE Bets (
    bet_id SERIAL PRIMARY KEY,
    uid UUID REFERENCES Users(uid),
    issue_id INTEGER REFERENCES Issues(issue_id) ON DELETE CASCADE,
    choice VARCHAR(3) NOT NULL CHECK (choice IN ('Yes', 'No')),
    is_correct BOOLEAN,
    created_at TIMESTAMPTZ DEFAULT now(),
    CONSTRAINT unique_user_issue UNIQUE (uid, issue_id)
);

CREATE INDEX idx_bets_issue ON Bets (issue_id);
CREATE INDEX idx_bets_user ON Bets (uid);
```

> **v5 대비 추가:** `is_correct` — 결과 확정 시 기록. 히스토리/결과 카드에서 바로 조회 가능
> **ON DELETE CASCADE** — Issue 삭제 시 베팅도 자동 삭제 (별도 삭제 로직 불필요)

### 4.5 System_Config 테이블

```sql
CREATE TABLE System_Config (
    key VARCHAR(50) PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at TIMESTAMPTZ DEFAULT now()
);

INSERT INTO System_Config (key, value) VALUES
('auto_mode', 'off'),
('auto_issue_count', '3'),
('auto_deadline_hours', '24'),
('auto_engine_lock', 'false');
```

> **v5 대비 추가:** `auto_engine_lock` — cron 동시 실행 방지

### 4.6 RPC 함수 (개선)

**place_bet (레이스 컨디션 해결):**
```sql
CREATE OR REPLACE FUNCTION place_bet(
    p_uid UUID, p_issue_id INTEGER, p_choice VARCHAR(3)
) RETURNS JSONB AS $$
DECLARE
    v_deadline TIMESTAMPTZ;
    v_status VARCHAR(10);
BEGIN
    -- row-level lock으로 동시 업데이트 방지
    SELECT betting_deadline, status INTO v_deadline, v_status
    FROM Issues WHERE issue_id = p_issue_id
    FOR UPDATE;

    IF v_status IS NULL THEN
        RETURN jsonb_build_object('success', false, 'error', 'issue_not_found');
    END IF;
    IF v_status != 'OPEN' THEN
        RETURN jsonb_build_object('success', false, 'error', 'issue_not_open');
    END IF;
    IF now() > v_deadline THEN
        RETURN jsonb_build_object('success', false, 'error', 'deadline_passed');
    END IF;

    -- UNIQUE 제약으로 중복 베팅 자동 방지 (에러 캐치)
    BEGIN
        INSERT INTO Bets (uid, issue_id, choice) VALUES (p_uid, p_issue_id, p_choice);
    EXCEPTION WHEN unique_violation THEN
        RETURN jsonb_build_object('success', false, 'error', 'already_voted');
    END;

    IF p_choice = 'Yes' THEN
        UPDATE Issues SET total_yes = total_yes + 1 WHERE issue_id = p_issue_id;
    ELSE
        UPDATE Issues SET total_no = total_no + 1 WHERE issue_id = p_issue_id;
    END IF;

    UPDATE Users SET
        last_played_date = now(),
        total_played = total_played + 1
    WHERE uid = p_uid;

    RETURN jsonb_build_object('success', true);
END;
$$ LANGUAGE plpgsql;
```

> **v5 대비 개선:**
> - `FOR UPDATE` — row-level lock으로 동시 베팅 레이스 컨디션 해결
> - `EXCEPTION WHEN unique_violation` — 중복 베팅을 DB 레벨에서 깔끔하게 처리
> - `total_played` 증가 추가

**resolve_issue (벌크 업데이트로 N+1 해결):**
```sql
CREATE OR REPLACE FUNCTION resolve_issue(
    p_issue_id INTEGER, p_correct_answer VARCHAR(3)
) RETURNS JSONB AS $$
DECLARE
    v_affected INTEGER;
BEGIN
    -- Issue 상태 변경
    UPDATE Issues SET
        correct_answer = p_correct_answer,
        status = 'RESOLVED',
        resolved_at = now()
    WHERE issue_id = p_issue_id AND status = 'CLOSED';

    IF NOT FOUND THEN
        RETURN jsonb_build_object('success', false, 'error', 'issue_not_closable');
    END IF;

    -- Bets에 is_correct 기록 (벌크)
    UPDATE Bets SET is_correct = (choice = p_correct_answer)
    WHERE issue_id = p_issue_id;

    -- 정답 유저: streak +1, wins +1 (벌크)
    UPDATE Users SET
        current_streak = current_streak + 1,
        total_wins = total_wins + 1,
        max_streak = GREATEST(max_streak, current_streak + 1)
    WHERE uid IN (
        SELECT uid FROM Bets
        WHERE issue_id = p_issue_id AND choice = p_correct_answer
    );

    -- 오답 유저: streak = 0 (벌크)
    UPDATE Users SET current_streak = 0
    WHERE uid IN (
        SELECT uid FROM Bets
        WHERE issue_id = p_issue_id AND choice != p_correct_answer
    );

    GET DIAGNOSTICS v_affected = ROW_COUNT;
    RETURN jsonb_build_object('success', true, 'resolved_issue', p_issue_id, 'affected_users', v_affected);
END;
$$ LANGUAGE plpgsql;
```

> **v5 대비 개선:**
> - FOR LOOP 제거 → 벌크 UPDATE 2개로 처리 (N+1 → 2 쿼리)
> - `is_correct` 기록 — 결과 카드에서 바로 사용
> - `resolved_at` 기록 — 최근 결과 정렬용

**delete_issue_cascade (트랜잭션 보장):**
```sql
CREATE OR REPLACE FUNCTION delete_issue_cascade(
    p_issue_id INTEGER
) RETURNS JSONB AS $$
DECLARE
    v_status VARCHAR(10);
    v_bet_count INTEGER;
BEGIN
    SELECT status INTO v_status FROM Issues WHERE issue_id = p_issue_id;

    IF v_status IS NULL THEN
        RETURN jsonb_build_object('success', false, 'error', 'not_found');
    END IF;
    IF v_status = 'RESOLVED' THEN
        RETURN jsonb_build_object('success', false, 'error', 'cannot_delete_resolved');
    END IF;

    -- 베팅 수 카운트 (응답용)
    SELECT COUNT(*) INTO v_bet_count FROM Bets WHERE issue_id = p_issue_id;

    -- CASCADE로 Bets, Translations 자동 삭제
    DELETE FROM Issues WHERE issue_id = p_issue_id;

    RETURN jsonb_build_object(
        'success', true,
        'deleted_bets', v_bet_count
    );
END;
$$ LANGUAGE plpgsql;
```

> **v5 대비 개선:** 별도 DELETE 3개 → CASCADE + RPC 1개로 원자적 처리

---

## 5. 캐싱 전략 (Supabase 요청 절감)

> **목표:** Free Tier 50K/월 이내 유지. DAU 200명 기준.

### 5.1 캐시 설계

```python
# services/cache.py
from cachetools import TTLCache
import threading

class CacheManager:
    def __init__(self):
        self._lock = threading.Lock()
        # 캐시별 TTL과 최대 항목 수
        self.open_issues = TTLCache(maxsize=1, ttl=30)      # 30초
        self.rankings = TTLCache(maxsize=1, ttl=60)          # 60초
        self.recent_results = TTLCache(maxsize=1, ttl=30)    # 30초
        self.translations = TTLCache(maxsize=500, ttl=3600)  # 1시간
        self.issue_detail = TTLCache(maxsize=100, ttl=30)    # 30초

    def get_or_fetch(self, cache, key, fetch_fn):
        """캐시에 있으면 반환, 없으면 fetch_fn 실행 후 캐싱"""
        with self._lock:
            if key in cache:
                return cache[key]
        result = fetch_fn()
        with self._lock:
            cache[key] = result
        return result

cache = CacheManager()
```

### 5.2 요청량 예상 (캐싱 적용 후)

| 동작 | 캐싱 전 (1유저/방문) | 캐싱 후 | 비고 |
|:---|:---|:---|:---|
| OPEN 이슈 목록 | 1 요청 | ~0.03 요청 | 30초 TTL, 다수 유저 공유 |
| 랭킹 | 1 요청 | ~0.02 요청 | 60초 TTL |
| 최근 결과 | 1 요청 | ~0.03 요청 | 30초 TTL |
| 유저 베팅 조회 | 1 요청 | 1 요청 | 유저별 다름, 캐싱 안 함 |
| 베팅 실행 | 1 요청 | 1 요청 | 실시간 필수 |
| **합계 (1방문)** | **~5 요청** | **~2.1 요청** | **58% 절감** |

**DAU 200명 x 일 3회 방문 x 2.1 요청 x 30일 = 37,800 요청/월** → Free Tier 이내

---

## 6. 화면 설계 (기획자 + 프론트 협업)

### 6.1 메인 화면 레이아웃

```
┌──────────────────────────────────┬──────────────────┐
│  Nostradamus Pick-all            │  [언어 선택]      │
│                                  │  [Google Login]   │
├──────────────────────────────────┼──────────────────┤
│                                  │                  │
│  === 최근 결과 (New!) ===        │  Leaderboard     │
│  ┌────────────────────────────┐  │                  │
│  │ [RESOLVED] BTC hit 100K?  │  │  1. UserA  12W  │
│  │ 정답: No  |  62% vs 38%   │  │  2. UserB   9W  │
│  │ 내 선택: Yes (오답)        │  │  3. UserC   7W  │
│  │ [빨간색 테두리]             │  │  ...             │
│  └────────────────────────────┘  │                  │
│  ┌────────────────────────────┐  │                  │
│  │ [RESOLVED] Team A win?    │  │                  │
│  │ 정답: Yes  |  55% vs 45%  │  │                  │
│  │ 내 선택: Yes (정답!)       │  │                  │
│  │ [초록색 테두리]             │  │                  │
│  └────────────────────────────┘  │                  │
│                                  │                  │
│  === 진행 중인 예측 ===          │                  │
│  ┌────────────────────────────┐  │                  │
│  │ [Sports] Will Team B win? │  │                  │
│  │ 마감: 2026-02-25 18:00    │  │                  │
│  │ [Yes] [No]                │  │                  │
│  │ Yes 62% ████████░░ 38% No│  │                  │
│  │ 142 votes                 │  │                  │
│  └────────────────────────────┘  │                  │
│                                  │                  │
│  ┌────────────────────────────┐  │                  │
│  │  Ad Banner                │  │                  │
│  └────────────────────────────┘  │                  │
│                                  │                  │
│  ┌────────────────────────────┐  │                  │
│  │ [Economy] Fed rate cut?   │  │                  │
│  │ 마감: 2026-02-26 09:00    │  │                  │
│  │ [Yes] [No]                │  │                  │
│  │ 첫 투표를 해보세요!        │  │  ← 0표일 때     │
│  └────────────────────────────┘  │                  │
│                                  │                  │
├──────────────────────────────────┴──────────────────┤
│  This is a simulation game. Users are solely        │
│  responsible for their predictions and outcomes.    │
└─────────────────────────────────────────────────────┘
```

### 6.2 이슈 카드 5가지 상태 (프론트 개발자 정의)

| 상태 | 조건 | UI | 색상/스타일 |
|:---|:---|:---|:---|
| **투표 가능** | OPEN + 미투표 + 로그인 | Yes/No 버튼 활성 + 비율바 | 기본 흰색 카드 |
| **투표 완료** | OPEN + 이미 투표 | 버튼 비활성 + "You chose: X" | 선택한 버튼 하이라이트 |
| **비로그인** | OPEN + 비로그인 | "Sign in to vote" 링크 | 버튼 대신 링크 |
| **마감됨** | CLOSED (결과 대기) | "Betting Closed" + 비율바 | 회색 오버레이 |
| **결과 확정** | RESOLVED | 정답 표시 + 내 결과 | 정답=초록 테두리, 오답=빨강 |

### 6.3 빈 상태 (Empty State)

| 상황 | 표시 내용 |
|:---|:---|
| OPEN 문제 0개 | "새로운 예측이 곧 등장합니다. 잠시만 기다려주세요!" |
| 최근 결과 0개 | 최근 결과 섹션 자체를 숨김 |
| 랭킹 0명 | "아직 참여자가 없습니다. 첫 예언자가 되어보세요!" |

### 6.4 반응형 CSS 핵심

```css
/* 데스크탑: 2컬럼 (7:3) */
.main-layout {
    display: grid;
    grid-template-columns: 7fr 3fr;
    gap: 24px;
    max-width: 1200px;
    margin: 0 auto;
    padding: 16px;
}

/* 모바일: 1컬럼. 랭킹은 하단으로 */
@media (max-width: 768px) {
    .main-layout {
        grid-template-columns: 1fr;
        padding: 8px;
    }
}

/* 이슈 카드 기본 */
.issue-card {
    background: #fff;
    border: 1px solid #e0e0e0;
    border-radius: 12px;
    padding: 20px;
    margin-bottom: 16px;
    transition: border-color 0.3s ease;
}

/* 결과 카드 — 정답 */
.issue-card.result-correct {
    border: 2px solid #4CAF50;
    background: #f8fff8;
}

/* 결과 카드 — 오답 */
.issue-card.result-wrong {
    border: 2px solid #F44336;
    background: #fff8f8;
}

/* 결과 카드 — 미참여 */
.issue-card.result-missed {
    border: 1px solid #e0e0e0;
    opacity: 0.8;
}

/* 마감된 카드 */
.issue-card.closed {
    opacity: 0.7;
}

/* 비율 바 */
.progress-bar {
    display: flex;
    height: 32px;
    border-radius: 16px;
    overflow: hidden;
    font-size: 13px;
    font-weight: bold;
    margin: 12px 0 4px;
}
.progress-yes {
    background: #4CAF50;
    color: white;
    display: flex;
    align-items: center;
    justify-content: center;
    min-width: 40px;
    transition: width 0.5s ease;  /* 애니메이션 */
}
.progress-no {
    background: #F44336;
    color: white;
    display: flex;
    align-items: center;
    justify-content: center;
    min-width: 40px;
    transition: width 0.5s ease;
}

/* Yes/No 버튼 */
.bet-btn {
    padding: 12px 32px;
    border: 2px solid;
    border-radius: 8px;
    font-size: 16px;
    font-weight: bold;
    cursor: pointer;
    transition: all 0.2s;
    min-width: 100px;    /* 모바일 터치 영역 확보 */
    min-height: 44px;    /* iOS 권장 최소 터치 높이 */
}
.bet-btn-yes { border-color: #4CAF50; color: #4CAF50; }
.bet-btn-yes:hover { background: #4CAF50; color: white; }
.bet-btn-no { border-color: #F44336; color: #F44336; }
.bet-btn-no:hover { background: #F44336; color: white; }

.bet-btn:disabled {
    opacity: 0.5;
    cursor: not-allowed;
}
.bet-btn.selected {
    color: white;
}
.bet-btn-yes.selected { background: #4CAF50; }
.bet-btn-no.selected { background: #F44336; }

/* 카테고리 태그 */
.category-tag {
    display: inline-block;
    padding: 2px 10px;
    border-radius: 12px;
    font-size: 12px;
    font-weight: 600;
    margin-bottom: 8px;
}

/* 광고 배너 */
.ad-banner {
    text-align: center;
    margin: 16px 0;
    padding: 8px;
    background: #f9f9f9;
    border-radius: 8px;
    min-height: 90px;
}

/* 랭킹 */
.ranking-list { list-style: none; padding: 0; }
.ranking-item {
    display: flex;
    justify-content: space-between;
    padding: 8px 12px;
    border-bottom: 1px solid #f0f0f0;
}
.ranking-item.me {
    background: #fffde7;
    font-weight: bold;
    border-radius: 6px;
}
```

### 6.5 마감 카운트다운 표시

```
마감까지: 23시간 42분   ← 24시간 이상 남음
마감까지: 2시간 15분    ← 24시간 이내
마감까지: 45분          ← 1시간 이내 (빨간색)
[Betting Closed]        ← 마감됨
```

> 프론트: JS setInterval로 1분마다 갱신. 서버 시간 기준.

---

## 7. API 엔드포인트 명세

### 7.1 라우트 목록

| Method | Path | 설명 | 인증 | 캐싱 |
|:---|:---|:---|:---|:---|
| GET | `/` | 메인 페이지 | X | 이슈: 30s, 랭킹: 60s |
| GET | `/auth/login` | 로그인 페이지 | X | - |
| GET | `/auth/callback` | OAuth 콜백 | X | - |
| POST | `/auth/set-session` | 세션 설정 | X | - |
| POST | `/auth/logout` | 로그아웃 | O | - |
| POST | `/api/bet` | 베팅 실행 | O | - |
| POST | `/api/set-language` | 언어 변경 | X | - |
| GET | `/admin/` | 관리자 대시보드 | Admin | - |
| POST | `/admin/toggle-mode` | 수동/풀오토 전환 | Admin | - |
| POST | `/admin/generate` | Gemini 문제 출제 (수동) | Admin | - |
| POST | `/admin/approve/<id>` | DRAFT → OPEN 승인 | Admin | - |
| POST | `/admin/resolve/<id>` | 결과 확정 (수동) | Admin | - |
| POST | `/admin/delete/<id>` | 문제 즉시 삭제 | Admin | - |
| POST | `/admin/update-config` | 풀오토 설정 변경 | Admin | - |

### 7.2 API 상세

**POST `/api/bet`**
```
Request:
{
    "issue_id": 12,
    "choice": "Yes"     // "Yes" 또는 "No"
}

Response (성공):
{
    "success": true,
    "updated_stats": {
        "total_yes": 85,
        "total_no": 57,
        "yes_pct": 60,
        "no_pct": 40
    }
}

Response (실패):
{
    "success": false,
    "error": "already_voted" | "deadline_passed" | "issue_not_open" | "not_logged_in"
}
```

**POST `/api/set-language`**
```
Request:  { "lang": "ko" }
Response: { "success": true }
```

---

## 8. 서비스 로직 상세

### 8.1 인증 플로우

```
1. 유저 → "Google Login" 클릭
2. Supabase Auth → Google OAuth 팝업
3. Google → 인증 → Supabase callback URL
4. Frontend → access_token을 /auth/set-session으로 POST
5. Flask → Supabase에서 유저 정보 조회 → session에 저장
6. ensure_user_exists() → Users 테이블에 없으면 INSERT
7. check_streak_reset() → 72시간 초과면 current_streak = 0
8. 메인 페이지로 리다이렉트
```

**ensure_user_exists:**
```python
def ensure_user_exists(uid, email, nickname):
    """유저가 없으면 생성, 있으면 스킵"""
    result = supabase.table('Users').select('uid').eq('uid', uid).execute()
    if not result.data:
        supabase.table('Users').insert({
            'uid': uid,
            'email': email,
            'nickname': nickname,
            'role': 'user'
        }).execute()
```

**check_streak_reset:**
```python
def check_streak_reset(uid):
    """72시간(3일) 미참여 시 current_streak 리셋. UTC 기준."""
    user = supabase.table('Users').select('last_played_date, current_streak') \
        .eq('uid', uid).single().execute()

    if user.data and user.data['last_played_date']:
        last = datetime.fromisoformat(user.data['last_played_date'])
        if datetime.now(timezone.utc) - last > timedelta(hours=72):
            if user.data['current_streak'] > 0:
                supabase.table('Users').update({'current_streak': 0}) \
                    .eq('uid', uid).execute()
```

### 8.2 메인 페이지 데이터 로딩

```python
# routes/main.py
@main_bp.route('/')
def index():
    uid = session.get('uid')

    # 캐싱된 공통 데이터
    open_issues = cache.get_or_fetch(
        cache.open_issues, 'all',
        lambda: supabase.table('Issues')
            .select('*')
            .eq('status', 'OPEN')
            .order('betting_deadline')
            .execute().data
    )

    recent_results = cache.get_or_fetch(
        cache.recent_results, 'all',
        lambda: supabase.table('Issues')
            .select('*')
            .eq('status', 'RESOLVED')
            .order('resolved_at', desc=True)
            .limit(5)
            .execute().data
    )

    rankings = cache.get_or_fetch(
        cache.rankings, 'top100',
        lambda: supabase.table('Users')
            .select('nickname, current_streak, total_wins')
            .order('current_streak', desc=True)
            .order('total_wins', desc=True)
            .limit(100)
            .execute().data
    )

    # 유저별 데이터 (캐싱 안 함)
    user_bets = {}
    if uid:
        check_streak_reset(uid)
        issue_ids = [i['issue_id'] for i in open_issues + recent_results]
        if issue_ids:
            bets = supabase.table('Bets') \
                .select('issue_id, choice, is_correct') \
                .eq('uid', uid) \
                .in_('issue_id', issue_ids) \
                .execute().data
            user_bets = {b['issue_id']: b for b in bets}

    # 번역 처리
    lang = session.get('lang', 'en')
    if lang != 'en':
        all_issues = open_issues + recent_results
        translate_issues(all_issues, lang)

    return render_template('index.html',
        open_issues=open_issues,
        recent_results=recent_results,
        rankings=rankings,
        user_bets=user_bets
    )
```

### 8.3 다국어 (i18n)

**지원 언어:** en, ko, ja, zh, es, fr, de, pt (8개)

```python
# services/i18n.py

UI_TEXTS = {
    'en': {
        'site_title': 'Nostradamus Pick-all',
        'login': 'Sign in with Google',
        'logout': 'Sign out',
        'votes': 'votes',
        'you_chose': 'You chose',
        'betting_closed': 'Betting Closed',
        'sign_in_to_vote': 'Sign in to vote',
        'correct': 'Correct!',
        'wrong': 'Wrong',
        'missed': 'You didn\'t participate',
        'answer_was': 'Answer',
        'recent_results': 'Recent Results',
        'open_predictions': 'Open Predictions',
        'leaderboard': 'Leaderboard',
        'no_issues': 'New predictions coming soon!',
        'no_rankings': 'Be the first prophet!',
        'disclaimer': 'This is a simulation game. Users are solely responsible for their predictions and outcomes.',
        'first_vote': 'Be the first to predict!',
        'deadline': 'Deadline',
        'already_voted': 'Already voted',
        'deadline_passed': 'Betting is closed',
        'not_logged_in': 'Please sign in',
        'delete_confirm': 'users have bet on this. Delete?',
        'wins': 'W',
    },
    'ko': {
        'site_title': '노스트라 다 찍기',
        'login': 'Google로 로그인',
        'logout': '로그아웃',
        'votes': '투표',
        'you_chose': '내 선택',
        'betting_closed': '베팅 마감',
        'sign_in_to_vote': '로그인하고 투표하기',
        'correct': '정답!',
        'wrong': '오답',
        'missed': '미참여',
        'answer_was': '정답',
        'recent_results': '최근 결과',
        'open_predictions': '진행 중인 예측',
        'leaderboard': '랭킹',
        'no_issues': '새로운 예측이 곧 등장합니다!',
        'no_rankings': '첫 예언자가 되어보세요!',
        'disclaimer': '본 서비스는 시뮬레이션 게임이며, 예측 결과에 대한 책임은 전적으로 사용자 본인에게 있습니다.',
        'first_vote': '첫 투표를 해보세요!',
        'deadline': '마감',
        'already_voted': '이미 투표했습니다',
        'deadline_passed': '베팅이 마감되었습니다',
        'not_logged_in': '로그인이 필요합니다',
        'delete_confirm': '명이 베팅했습니다. 삭제하시겠습니까?',
        'wins': '승',
    },
    'ja': {
        'site_title': 'ノストラダ当て',
        'login': 'Googleでログイン',
        'logout': 'ログアウト',
        'votes': '票',
        'you_chose': 'あなたの選択',
        'betting_closed': '受付終了',
        'sign_in_to_vote': 'ログインして投票',
        'correct': '正解!',
        'wrong': '不正解',
        'missed': '不参加',
        'answer_was': '正解',
        'recent_results': '最近の結果',
        'open_predictions': '予測受付中',
        'leaderboard': 'ランキング',
        'no_issues': '新しい予測がまもなく登場します!',
        'no_rankings': '最初の預言者になろう!',
        'disclaimer': 'これはシミュレーションゲームです。予測結果に対する責任はすべてユーザー本人にあります。',
        'first_vote': '最初の投票をしてみよう!',
        'deadline': '締切',
        'already_voted': '投票済み',
        'deadline_passed': '受付終了しました',
        'not_logged_in': 'ログインが必要です',
        'delete_confirm': '人が投票しています。削除しますか?',
        'wins': '勝',
    },
}

def t(key, lang='en'):
    """UI 텍스트 번역. 없으면 영어 폴백."""
    return UI_TEXTS.get(lang, UI_TEXTS['en']).get(key, UI_TEXTS['en'].get(key, key))

def detect_language(request):
    """브라우저 Accept-Language에서 지원 언어 감지"""
    supported = set(UI_TEXTS.keys())
    best = request.accept_languages.best_match(supported, default='en')
    return best
```

**문제 번역 (Gemini + 캐싱):**
```python
# services/gemini_client.py

def translate_issues(issues, lang):
    """이슈 목록을 지정 언어로 번역. 캐시 우선."""
    if lang == 'en':
        return

    for issue in issues:
        cache_key = f"{issue['issue_id']}_{lang}"
        cached = cache.get_or_fetch(
            cache.translations, cache_key,
            lambda i=issue: _fetch_or_translate(i, lang)
        )
        if cached:
            issue['question_title'] = cached['translated_title']
            issue['resolution_criteria'] = cached['translated_criteria']

def _fetch_or_translate(issue, lang):
    """DB에 번역 있으면 반환, 없으면 Gemini로 번역 후 DB 저장"""
    # 1. DB 조회
    result = supabase.table('Issue_Translations') \
        .select('*') \
        .eq('issue_id', issue['issue_id']) \
        .eq('lang_code', lang) \
        .execute()

    if result.data:
        return result.data[0]

    # 2. Gemini 번역
    try:
        translated = gemini_translate(
            issue['question_title'],
            issue['resolution_criteria'],
            lang
        )
        # 3. DB 저장 (캐싱)
        supabase.table('Issue_Translations').insert({
            'issue_id': issue['issue_id'],
            'lang_code': lang,
            'translated_title': translated['title'],
            'translated_criteria': translated['criteria']
        }).execute()
        return {
            'translated_title': translated['title'],
            'translated_criteria': translated['criteria']
        }
    except Exception:
        return None  # 실패 시 영어 원본 유지
```

### 8.4 Gemini API 상세

**문제 출제 프롬프트:**
```python
def gemini_generate_issues(count):
    prompt = f"""
    You are a prediction game question generator.
    Generate {count} prediction questions about current global hot issues.

    RULES:
    - Questions must have clear Yes/No answers
    - Results must be determinable within 24-48 hours
    - Include specific, verifiable resolution criteria
    - Categories: Sports, Economy, Tech, Entertainment, Politics, Science
    - Questions must be factual and objective (no opinion-based)
    - AVOID: controversial political figures by name, religious topics,
      discriminatory content, violence, gambling odds
    - Each question must be unique and not overlap with others

    Respond ONLY in JSON array format:
    [
        {{
            "category": "Sports",
            "question_title": "Will Manchester United win against Liverpool on Feb 25?",
            "resolution_criteria": "Based on the official match result of the Premier League game scheduled for Feb 25, 2026. If the match is postponed, this question is void."
        }}
    ]
    """
    # Gemini API 호출 (Search Grounding 활성화)
    response = model.generate_content(prompt)
    return parse_json_response(response.text)
```

**결과 판정 프롬프트:**
```python
def gemini_check_result(issue):
    prompt = f"""
    The following prediction question's deadline has passed.
    Check if the result is now known using current information.

    Question: {issue['question_title']}
    Resolution criteria: {issue['resolution_criteria']}
    Deadline was: {issue['betting_deadline']}

    Respond ONLY in JSON:
    {{
        "answer": "Yes" or "No" or "Unknown",
        "confidence": 0.0 to 1.0,
        "reasoning": "brief explanation with source"
    }}

    RULES:
    - If the event hasn't happened yet, answer "Unknown" with confidence 0.
    - If sources conflict, answer "Unknown" with low confidence.
    - Only answer "Yes" or "No" with confidence >= 0.9 when you have clear evidence.
    """
```

**Gemini JSON 파싱 안전장치:**
```python
def parse_json_response(text):
    """Gemini 응답에서 JSON 추출. markdown 코드블록 처리 포함."""
    # markdown 코드블록 제거
    text = text.strip()
    if text.startswith('```'):
        text = text.split('\n', 1)[1]  # 첫 줄 제거
        text = text.rsplit('```', 1)[0]  # 마지막 ``` 제거

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        # JSON 부분만 추출 시도
        import re
        match = re.search(r'[\[{].*[}\]]', text, re.DOTALL)
        if match:
            return json.loads(match.group())
        raise ValueError(f"Failed to parse Gemini response as JSON")
```

### 8.5 풀오토 엔진

```python
# services/auto_engine.py
from datetime import datetime, timezone, timedelta
import logging

logger = logging.getLogger('auto_engine')

def run_auto_cycle():
    """풀오토 1사이클. Render Cron Job으로 매 시간 실행."""
    config = _get_config()
    if config['auto_mode'] != 'on':
        logger.info("Auto mode is OFF. Skipping.")
        return

    # 동시 실행 방지 (lock)
    if config.get('auto_engine_lock') == 'true':
        logger.warning("Auto engine already running. Skipping.")
        return

    try:
        _set_lock(True)

        # Step 1: 마감 시간 지난 OPEN → CLOSED
        closed_count = auto_close_expired()
        logger.info(f"Auto-closed {closed_count} issues")

        # Step 2: CLOSED → RESOLVED (Gemini 판정)
        resolved_count = auto_resolve()
        logger.info(f"Auto-resolved {resolved_count} issues")

        # Step 3: OPEN 부족 시 새 문제 출제
        generated_count = auto_generate(config)
        logger.info(f"Auto-generated {generated_count} issues")

    finally:
        _set_lock(False)


def auto_close_expired():
    """betting_deadline 지난 OPEN → CLOSED"""
    result = supabase.table('Issues') \
        .update({'status': 'CLOSED'}) \
        .eq('status', 'OPEN') \
        .lt('betting_deadline', datetime.now(timezone.utc).isoformat()) \
        .execute()
    return len(result.data) if result.data else 0


def auto_resolve():
    """CLOSED 문제 → Gemini로 결과 확인 → 확신도 90%+ 시 RESOLVED"""
    closed = supabase.table('Issues') \
        .select('*').eq('status', 'CLOSED').execute()

    resolved = 0
    for issue in (closed.data or []):
        try:
            result = gemini_check_result(issue)

            if result.get('answer') == 'Unknown':
                logger.info(f"Issue #{issue['issue_id']}: result unknown, skipping")
                continue

            if result.get('confidence', 0) >= 0.9:
                supabase.rpc('resolve_issue', {
                    'p_issue_id': issue['issue_id'],
                    'p_correct_answer': result['answer']
                }).execute()
                resolved += 1
                logger.info(f"Issue #{issue['issue_id']}: resolved as {result['answer']} (confidence: {result['confidence']})")
            else:
                logger.info(f"Issue #{issue['issue_id']}: low confidence {result['confidence']}, skipping")

        except Exception as e:
            logger.error(f"Issue #{issue['issue_id']}: error during resolution - {e}")

    return resolved


def auto_generate(config):
    """OPEN 문제가 부족하면 자동 출제"""
    open_count = supabase.table('Issues') \
        .select('issue_id', count='exact').eq('status', 'OPEN').execute()

    target = int(config.get('auto_issue_count', 3))
    needed = target - (open_count.count or 0)

    if needed <= 0:
        return 0

    try:
        issues = gemini_generate_issues(needed)
        deadline = (
            datetime.now(timezone.utc) +
            timedelta(hours=int(config.get('auto_deadline_hours', 24)))
        ).isoformat()

        for issue in issues:
            supabase.table('Issues').insert({
                'category': issue['category'],
                'question_title': issue['question_title'],
                'resolution_criteria': issue['resolution_criteria'],
                'status': 'OPEN',  # 풀오토: DRAFT 스킵
                'source': 'auto',
                'betting_deadline': deadline
            }).execute()

        return len(issues)

    except Exception as e:
        logger.error(f"Auto-generate failed: {e}")
        return 0


def _get_config():
    result = supabase.table('System_Config').select('*').execute()
    return {row['key']: row['value'] for row in (result.data or [])}

def _set_lock(locked):
    supabase.table('System_Config') \
        .update({'value': str(locked).lower(), 'updated_at': datetime.now(timezone.utc).isoformat()}) \
        .eq('key', 'auto_engine_lock').execute()
```

---

## 9. 관리자 대시보드

### 9.1 레이아웃

```
┌──────────────────────────────────────────────┐
│  Admin Dashboard                             │
│                                              │
│  Operation Mode: [ Manual | Auto ]  ← 토글  │
│                                              │
│  ┌─ Auto Settings (auto=on일 때만 표시) ───┐ │
│  │ Daily issues: [3]                       │ │
│  │ Deadline: [24] hours                    │ │
│  │ [Save Settings]                         │ │
│  └─────────────────────────────────────────┘ │
│                                              │
│  === Emergency Controls (항상 표시) ===       │
│                                              │
│  OPEN Issues:                                │
│  ┌──────────────────────────────────────────┐│
│  │ #12 "Will BTC hit 100K?"                ││
│  │ 42 votes | auto | deadline: 2/25 18:00  ││
│  │ [Delete]                                ││
│  ├──────────────────────────────────────────┤│
│  │ #13 "Will Team A win?"                  ││
│  │ 18 votes | manual | deadline: 2/26 09:00││
│  │ [Delete]                                ││
│  └──────────────────────────────────────────┘│
│                                              │
│  CLOSED Issues (결과 대기):                   │
│  ┌──────────────────────────────────────────┐│
│  │ #10 "Fed rate announcement?"             ││
│  │ 89 votes | [Resolve: Yes] [Resolve: No] ││
│  └──────────────────────────────────────────┘│
│                                              │
│  === Manual Mode Only (auto=off일 때) ===    │
│  [Start Gemini AI] (10s cooldown)            │
│                                              │
│  DRAFT Issues:                               │
│  ┌──────────────────────────────────────────┐│
│  │ #14 "Will Apple announce...?"            ││
│  │ [Approve (→OPEN)] [Delete]              ││
│  └──────────────────────────────────────────┘│
└──────────────────────────────────────────────┘
```

### 9.2 관리자 인증

```python
# routes/admin.py
from functools import wraps

def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        uid = session.get('uid')
        if not uid:
            return redirect(url_for('auth.login'))
        role = session.get('role')
        if role != 'admin':
            abort(403)
        return f(*args, **kwargs)
    return decorated
```

---

## 10. 프론트엔드 JS (app.js) 핵심 로직

```javascript
// static/js/app.js

// === 베팅 ===
async function placeBet(issueId, choice) {
    const card = document.getElementById(`issue-${issueId}`);
    const btns = card.querySelectorAll('.bet-btn');

    // 즉시 비활성화 (낙관적 업데이트)
    btns.forEach(b => b.disabled = true);

    try {
        const res = await fetch('/api/bet', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ issue_id: issueId, choice })
        });
        const data = await res.json();

        if (data.success) {
            // 비율 바 애니메이션 업데이트
            updateVoteStats(card, data.updated_stats);
            // 내 선택 표시
            showMyChoice(card, choice);
            // 선택한 버튼 하이라이트
            const selectedBtn = card.querySelector(`.bet-btn-${choice.toLowerCase()}`);
            if (selectedBtn) selectedBtn.classList.add('selected');
        } else {
            // 실패 시 버튼 복원
            btns.forEach(b => b.disabled = false);
            showToast(getErrorMessage(data.error));
        }
    } catch (err) {
        btns.forEach(b => b.disabled = false);
        showToast('Network error. Please try again.');
    }
}

function updateVoteStats(card, stats) {
    const yesBar = card.querySelector('.progress-yes');
    const noBar = card.querySelector('.progress-no');
    const countEl = card.querySelector('.vote-count');

    if (yesBar && noBar) {
        yesBar.style.width = stats.yes_pct + '%';
        yesBar.textContent = `Yes ${stats.yes_pct}%`;
        noBar.style.width = stats.no_pct + '%';
        noBar.textContent = `No ${stats.no_pct}%`;
    }
    if (countEl) {
        const total = stats.total_yes + stats.total_no;
        countEl.textContent = `${total} ${window.TEXT_VOTES || 'votes'}`;
    }

    // 비율바가 숨겨져 있었으면 (0표→1표) 표시
    const statsContainer = card.querySelector('.vote-stats');
    if (statsContainer) statsContainer.style.display = 'block';
    const firstVote = card.querySelector('.first-vote-msg');
    if (firstVote) firstVote.style.display = 'none';
}

function showMyChoice(card, choice) {
    const el = card.querySelector('.my-choice');
    if (el) {
        el.textContent = `✅ ${window.TEXT_YOU_CHOSE || 'You chose'}: ${choice}`;
        el.style.display = 'block';
    }
}

// === 마감 카운트다운 ===
function updateDeadlines() {
    document.querySelectorAll('[data-deadline]').forEach(el => {
        const deadline = new Date(el.dataset.deadline);
        const now = new Date();
        const diff = deadline - now;

        if (diff <= 0) {
            el.textContent = window.TEXT_CLOSED || 'Betting Closed';
            el.classList.add('deadline-expired');
            // 해당 카드의 버튼 비활성화
            const card = el.closest('.issue-card');
            if (card) {
                card.querySelectorAll('.bet-btn').forEach(b => b.disabled = true);
            }
            return;
        }

        const hours = Math.floor(diff / 3600000);
        const mins = Math.floor((diff % 3600000) / 60000);

        if (hours >= 24) {
            el.textContent = `${hours}h ${mins}m`;
        } else if (hours >= 1) {
            el.textContent = `${hours}h ${mins}m`;
            el.classList.add('deadline-soon');
        } else {
            el.textContent = `${mins}m`;
            el.classList.add('deadline-urgent');
        }
    });
}

// 1분마다 갱신
setInterval(updateDeadlines, 60000);
updateDeadlines();

// === 언어 변경 ===
async function setLanguage(lang) {
    await fetch('/api/set-language', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ lang })
    });
    location.reload();
}

// === 토스트 메시지 ===
function showToast(msg, duration = 3000) {
    const toast = document.createElement('div');
    toast.className = 'toast';
    toast.textContent = msg;
    document.body.appendChild(toast);
    requestAnimationFrame(() => toast.classList.add('show'));
    setTimeout(() => {
        toast.classList.remove('show');
        setTimeout(() => toast.remove(), 300);
    }, duration);
}

function getErrorMessage(code) {
    const msgs = {
        'already_voted': window.TEXT_ALREADY_VOTED || 'Already voted',
        'deadline_passed': window.TEXT_DEADLINE_PASSED || 'Betting is closed',
        'issue_not_open': window.TEXT_DEADLINE_PASSED || 'Betting is closed',
        'not_logged_in': window.TEXT_NOT_LOGGED_IN || 'Please sign in',
        'issue_not_found': 'Issue not found'
    };
    return msgs[code] || 'Something went wrong';
}

// === 관리자: 10초 쿨다운 ===
function startGemini() {
    const btn = document.getElementById('gemini-btn');
    btn.disabled = true;
    let remaining = 10;

    const timer = setInterval(() => {
        remaining--;
        btn.textContent = `Cooldown: ${remaining}s`;
        if (remaining <= 0) {
            clearInterval(timer);
            btn.disabled = false;
            btn.textContent = 'Start Gemini AI';
        }
    }, 1000);

    fetch('/admin/generate', { method: 'POST' })
        .then(r => r.json())
        .then(data => {
            if (data.success) {
                showToast(`Generated ${data.count} issues`);
                setTimeout(() => location.reload(), 1500);
            } else {
                showToast('Generation failed: ' + (data.error || 'unknown'));
            }
        });
}

// === 관리자: 문제 삭제 확인 ===
function deleteIssue(issueId, betCount) {
    const msg = betCount > 0
        ? `${betCount} ${window.TEXT_DELETE_CONFIRM || 'users have bet on this. Delete?'}`
        : 'Delete this issue?';

    if (!confirm(msg)) return;

    fetch(`/admin/delete/${issueId}`, { method: 'POST' })
        .then(r => r.json())
        .then(data => {
            if (data.success) {
                document.getElementById(`admin-issue-${issueId}`)?.remove();
                showToast('Deleted');
            }
        });
}
```

---

## 11. 에러 처리 정책

| 에러 상황 | 처리 | 유저 메시지 |
|:---|:---|:---|
| Supabase 연결 실패 | try-except + 에러 페이지 | "Server connection failed. Please try again." |
| Gemini API 실패 | 재시도 1회 → 실패 시 에러 | "AI analysis failed. Please try again later." |
| Gemini JSON 파싱 실패 | 정규식 재파싱 → 실패 시 에러 로그 | (관리자에게만) "Cannot parse AI response" |
| 번역 실패 | 영어 원본 유지 | (에러 없이 자동 폴백) |
| 마감 문제 베팅 | RPC 거부 | "Betting is closed." |
| 중복 베팅 | UNIQUE 위반 캐치 | "Already voted." |
| 잘못된 문제 ID | 404 | "Issue not found." |
| 네트워크 타임아웃 | 5초 타임아웃 | "Request timed out. Please try again." |
| AdSense 실패 | 플레이스홀더 표시 | (회색 빈 박스) |
| 비로그인 베팅 | 401 | "Please sign in." |
| 풀오토 판정 실패 | 스킵 + 로그 | (유저 노출 없음) |
| 풀오토 출제 실패 | 스킵 + 로그 | (유저 노출 없음) |
| 캐시 미스 + DB 실패 | 빈 목록 반환 | (빈 상태 UI 표시) |

---

## 12. 보안 체크리스트

- [ ] `.env` → `.gitignore`에 포함
- [ ] Flask `SECRET_KEY` → 32바이트+ 랜덤 키
- [ ] `admin_required` 데코레이터 → 모든 admin 라우트
- [ ] CSRF 대응 → Flask-WTF 또는 세션 기반 토큰
- [ ] API 입력값 검증 → choice는 "Yes"/"No"만, issue_id는 정수만
- [ ] RESOLVED 문제 삭제 불가 → RPC에서 체크
- [ ] Supabase RLS → 추후 검토
- [ ] Rate limiting → 베팅 API에 IP당 분당 30회 제한

---

## 13. Phase별 개발 계획 + 테스트

### Phase 1: 프로젝트 초기 세팅 (Day 1)

| # | 작업 | 담당 | 상세 |
|:--|:---|:---|:---|
| 1-1 | 디렉토리 + 파일 구조 생성 | 백엔드 | 위 구조대로 |
| 1-2 | requirements.txt | 백엔드 | flask, python-dotenv, supabase, google-generativeai, gunicorn, cachetools |
| 1-3 | config.py + .env 템플릿 | 백엔드 | 환경 변수 |
| 1-4 | .gitignore | 백엔드 | .env, __pycache__/, *.pyc, .venv/ |
| 1-5 | app.py + Blueprint 등록 | 백엔드 | 기본 라우팅 |
| 1-6 | cache.py | 백엔드 | CacheManager |
| 1-7 | supabase_client.py | 백엔드 | 연결 + 캐싱 래퍼 |

**Phase 1 QA 체크:**
- [ ] `flask run` → 200 OK
- [ ] `.env`가 git status에 안 나옴
- [ ] Supabase 연결 → 에러 없음

---

### Phase 2: 데이터베이스 구축 (Day 1-2)

| # | 작업 | 담당 | 상세 |
|:--|:---|:---|:---|
| 2-1 | Users 테이블 + 인덱스 | 백엔드 | Supabase SQL Editor |
| 2-2 | Issues 테이블 + 인덱스 | 백엔드 | resolved_at 포함 |
| 2-3 | Issue_Translations 테이블 | 백엔드 | ON DELETE CASCADE |
| 2-4 | Bets 테이블 | 백엔드 | ON DELETE CASCADE, is_correct |
| 2-5 | System_Config 테이블 + 초기 데이터 | 백엔드 | auto_engine_lock 포함 |
| 2-6 | place_bet RPC | 백엔드 | FOR UPDATE + unique_violation 처리 |
| 2-7 | resolve_issue RPC | 백엔드 | 벌크 UPDATE |
| 2-8 | delete_issue_cascade RPC | 백엔드 | 원자적 삭제 |

**Phase 2 QA 체크:**
- [ ] Users INSERT → role='user' 기본값 확인
- [ ] Issues INSERT → source='manual' 기본값
- [ ] System_Config → auto_mode='off' 초기값
- [ ] Bets 중복 INSERT → unique_violation
- [ ] place_bet: 마감된 문제 → `{"success": false, "error": "deadline_passed"}`
- [ ] place_bet: 정상 → total_yes/no 증가 확인
- [ ] place_bet: 동시 2개 요청 → 하나만 성공, 하나는 already_voted
- [ ] resolve_issue: 정답 유저 → streak+1, wins+1
- [ ] resolve_issue: 오답 유저 → streak=0
- [ ] resolve_issue: max_streak 갱신 확인
- [ ] resolve_issue: is_correct 필드 정확히 설정됨
- [ ] delete_issue_cascade: OPEN 문제 삭제 → Bets, Translations 모두 삭제됨
- [ ] delete_issue_cascade: RESOLVED 문제 → 거부

---

### Phase 3: 사용자 인증 (Day 2-3)

| # | 작업 | 담당 | 상세 |
|:--|:---|:---|:---|
| 3-1 | Supabase Auth + Google OAuth 설정 | 백엔드 | GCP + Supabase 설정 |
| 3-2 | routes/auth.py | 백엔드 | login, callback, set-session, logout |
| 3-3 | Flask session 관리 | 백엔드 | uid, email, nickname, role |
| 3-4 | ensure_user_exists() | 백엔드 | 자동 프로필 생성 |
| 3-5 | check_streak_reset() | 백엔드 | 72시간 리셋 (UTC) |
| 3-6 | login.html | 프론트 | Google 로그인 버튼 |

**Phase 3 QA 체크:**
- [ ] Google 로그인 → OAuth 팝업 → 성공 → 메인으로 리다이렉트
- [ ] 첫 로그인 → Users 레코드 생성됨
- [ ] 재로그인 → 중복 레코드 없음
- [ ] 73시간 경과 후 접속 → current_streak=0
- [ ] 71시간 → current_streak 유지
- [ ] 리셋 시 max_streak 보존 확인
- [ ] 로그아웃 → session 클리어

---

### Phase 4: 메인 화면 + 결과 섹션 (Day 3-5)

| # | 작업 | 담당 | 상세 |
|:--|:---|:---|:---|
| 4-1 | base.html | 프론트 | 공통 레이아웃, 헤더, 푸터 |
| 4-2 | style.css | 프론트 | 위 CSS 전체 구현 |
| 4-3 | index.html | 프론트 | 메인 레이아웃 (결과 + 이슈 + 랭킹) |
| 4-4 | result_card.html | 프론트 | 결과 발표 카드 (정답/오답/미참여) |
| 4-5 | issue_card.html | 프론트 | 5가지 상태별 카드 |
| 4-6 | vote_stats.html | 프론트 | 비율 바 + 0표 처리 |
| 4-7 | ranking.html | 프론트 | Top 100 + 본인 하이라이트 |
| 4-8 | empty_state.html | 프론트 | 빈 상태 안내 |
| 4-9 | ad_banner.html | 프론트 | 개발/프로덕션 분기 |
| 4-10 | routes/main.py | 백엔드 | 캐싱된 데이터 로딩 |
| 4-11 | 면책 조항 footer | 프론트 | 다국어 |

**Phase 4 QA 체크:**
- [ ] PC: 2컬럼 (7:3) 정상
- [ ] 모바일 (768px 이하): 1컬럼, 랭킹 하단
- [ ] OPEN 문제만 "진행 중인 예측"에 표시
- [ ] RESOLVED 문제가 "최근 결과"에 표시 (최신순, 최대 5개)
- [ ] 결과 카드: 정답 → 초록 테두리, 오답 → 빨강 테두리
- [ ] 결과 카드: 미참여 → 흐린 카드
- [ ] 비율 바: 애니메이션 동작 (CSS transition)
- [ ] 0표 이슈: 비율 바 대신 "첫 투표를 해보세요!"
- [ ] 마감 카운트다운: 시간 정확히 표시
- [ ] 마감 임박 (1시간 이내): 빨간색
- [ ] 비로그인: 비율 보이고, 버튼 대신 "Sign in to vote"
- [ ] 랭킹: 1~3등 메달, 본인 노란 배경
- [ ] OPEN 0개: "새로운 예측이 곧 등장합니다"
- [ ] 광고: 이슈 2개마다 1개 삽입

---

### Phase 5: 베팅 AJAX (Day 5-6)

| # | 작업 | 담당 | 상세 |
|:--|:---|:---|:---|
| 5-1 | routes/api.py — /api/bet | 백엔드 | place_bet RPC 호출 |
| 5-2 | app.js — placeBet() | 프론트 | AJAX + 낙관적 업데이트 |
| 5-3 | 에러 처리 UI | 프론트 | 토스트 메시지 |

**Phase 5 QA 체크:**
- [ ] Yes 클릭 → 리로드 없이 버튼 비활성화
- [ ] 비율 바 부드럽게 업데이트 (슬라이딩)
- [ ] "You chose: Yes" 표시
- [ ] 새로고침 후에도 비활성화 유지
- [ ] 비로그인 → 토스트 "Please sign in"
- [ ] 중복 베팅 → 토스트 "Already voted"
- [ ] 마감된 문제 → 토스트 "Betting is closed"
- [ ] 네트워크 에러 → 토스트 + 버튼 복원

---

### Phase 6: 다국어 지원 (Day 6-7)

| # | 작업 | 담당 | 상세 |
|:--|:---|:---|:---|
| 6-1 | services/i18n.py | 백엔드 | UI_TEXTS + t() |
| 6-2 | context_processor | 백엔드 | Jinja2에 t() 등록 |
| 6-3 | 브라우저 언어 감지 | 백엔드 | request.accept_languages |
| 6-4 | 언어 선택 드롭다운 | 프론트 | 헤더 우측 |
| 6-5 | /api/set-language | 백엔드 | session + DB 저장 |
| 6-6 | 문제 번역 (Gemini) | 백엔드 | Issue_Translations 캐싱 |
| 6-7 | 템플릿 전체 t() 적용 | 프론트 | 모든 정적 텍스트 |

**Phase 6 QA 체크:**
- [ ] Accept-Language: en → 영어 UI
- [ ] Accept-Language: ko → 한국어 UI
- [ ] 드롭다운 ja 선택 → 일본어 + DB 저장
- [ ] 재접속 → preferred_lang 유지
- [ ] 문제 번역: DB에 캐시 HIT → Gemini 재호출 없음
- [ ] 문제 번역 실패 → 영어 원본 (에러 없이)
- [ ] 미지원 언어(예: th) → 영어 폴백

---

### Phase 7: Google AdSense (Day 7)

| # | 작업 | 담당 | 상세 |
|:--|:---|:---|:---|
| 7-1 | .env에 AdSense ID | 백엔드 | |
| 7-2 | base.html `<head>` | 프론트 | AdSense JS |
| 7-3 | ad_banner.html 분기 | 프론트 | 프로덕션=실제광고, 개발=플레이스홀더 |
| 7-4 | 이슈 2개마다 삽입 | 프론트 | Jinja2 loop.index |

**Phase 7 QA 체크:**
- [ ] 문제 4개 → 광고 1개 (2번째와 3번째 사이)
- [ ] 문제 1개 → 광고 없음
- [ ] 개발환경 → 회색 플레이스홀더
- [ ] 광고가 이슈 카드와 시각적으로 구분됨

---

### Phase 8: 관리자 + 풀오토 엔진 (Day 7-9)

| # | 작업 | 담당 | 상세 |
|:--|:---|:---|:---|
| 8-1 | admin_required 데코레이터 | 백엔드 | |
| 8-2 | admin/dashboard.html | 프론트 | 위 레이아웃 구현 |
| 8-3 | 모드 토글 (수동↔풀오토) | 백엔드+프론트 | System_Config 업데이트 |
| 8-4 | 수동: Gemini 출제 | 백엔드 | DRAFT 상태로 생성 |
| 8-5 | 수동: 승인/삭제 | 백엔드 | DRAFT → OPEN |
| 8-6 | 수동: 결과 확정 | 백엔드 | resolve_issue RPC |
| 8-7 | 10초 쿨다운 | 프론트 | JS 타이머 |
| 8-8 | services/auto_engine.py | 백엔드 | 풀오토 사이클 |
| 8-9 | 문제 즉시 삭제 | 백엔드+프론트 | delete_issue_cascade RPC + 확인 모달 |
| 8-10 | render.yaml (Cron Job) | 백엔드 | 매 시간 실행 |

**Phase 8 QA 체크:**
- [ ] role='user' → /admin 접근 → 403
- [ ] role='admin' → 대시보드 표시
- [ ] 모드 토글 off→on → System_Config 'on' 저장
- [ ] 모드 토글 on→off → 'off' 저장
- [ ] 풀오토: OPEN 부족 시 자동 출제 → 바로 OPEN (DRAFT 스킵)
- [ ] 풀오토: deadline 경과 → 자동 CLOSED
- [ ] 풀오토: Gemini 확신도 90%+ → 자동 RESOLVED
- [ ] 풀오토: 확신도 낮음 → 스킵 (로그만)
- [ ] 풀오토: 동시 실행 → lock으로 2번째 스킵
- [ ] 즉시 삭제: 확인 모달에 베팅 수 표시
- [ ] 즉시 삭제: OPEN 문제 삭제 → Bets+Translations 자동 삭제
- [ ] 즉시 삭제: RESOLVED 문제 → "Cannot delete" 거부
- [ ] 수동: Gemini 출제 → DRAFT 생성
- [ ] 수동: 승인 → OPEN, 마감시간 자동 설정
- [ ] 수동: 결과 확정 → RESOLVED + streak 업데이트
- [ ] 수동: 10초 쿨다운 동안 버튼 비활성

---

### Phase 9: 에러 처리 + 통합 테스트 + 배포 (Day 9-10)

| # | 작업 | 담당 | 상세 |
|:--|:---|:---|:---|
| 9-1 | Flask errorhandler (404, 500) | 백엔드 | 에러 페이지 |
| 9-2 | try-except 라우트별 | 백엔드 | |
| 9-3 | 타임아웃 5초 | 백엔드 | Supabase, Gemini |
| 9-4 | 통합 테스트 시나리오 | QA | 아래 참조 |
| 9-5 | Render.com 배포 | 백엔드 | web + cron |

**Phase 9 통합 테스트 시나리오:**

| # | 시나리오 | 검증 항목 |
|:--|:---|:---|
| A | 가입 → 베팅 → 정답 | streak=1, wins=1, total_played=1 |
| B | 가입 → 베팅 → 오답 | streak=0, wins=0, total_played=1 |
| C | streak 5 → 72시간 미접속 → 재접속 | streak=0, max_streak=5 |
| D | 마감된 문제에 직접 API 호출 | 거부 응답 |
| E | 같은 문제 2번 베팅 | 2번째 거부 |
| F | 한국어 유저 → 문제 번역 | 한국어 제목 + 한국어 UI |
| G | 문제 6개 | 광고 올바른 위치 (2번째 뒤, 4번째 뒤) |
| H | 비로그인 유저 | 열람 가능, 베팅 시 로그인 유도 |
| I | AJAX 베팅 | 리로드 없이 비율바 + 내선택 업데이트 |
| J | 풀오토 1사이클 | 출제→마감→판정 정상 동작 |
| K | 긴급 삭제 | OPEN 삭제 → streak 영향 없음 |
| L | 결과 발표 | 메인 상단에 정답/오답 카드 표시 |
| M | Supabase 다운 | 에러 페이지, 크래시 없음 |
| N | Gemini 키 없이 실행 | 에러 메시지, 크래시 없음 |
| O | 0표 이슈 표시 | "첫 투표를 해보세요" |
| P | OPEN 문제 0개 | "곧 새로운 예측이 등장합니다" |

---

## 14. 배포 설정

### render.yaml
```yaml
services:
  - type: web
    name: nostradamus-pick
    runtime: python
    buildCommand: pip install -r requirements.txt
    startCommand: gunicorn app:app --bind 0.0.0.0:$PORT --workers 2
    envVars:
      - key: FLASK_ENV
        value: production
      - key: FLASK_SECRET_KEY
        generateValue: true
      - key: SUPABASE_URL
        sync: false
      - key: SUPABASE_KEY
        sync: false
      - key: GEMINI_API_KEY
        sync: false

  - type: cron
    name: auto-engine
    runtime: python
    buildCommand: pip install -r requirements.txt
    schedule: "0 * * * *"
    startCommand: python -c "from services.auto_engine import run_auto_cycle; run_auto_cycle()"
    envVars:
      - key: SUPABASE_URL
        sync: false
      - key: SUPABASE_KEY
        sync: false
      - key: GEMINI_API_KEY
        sync: false
```

### requirements.txt
```
flask==3.1.0
python-dotenv==1.0.1
supabase==2.11.0
google-generativeai==0.8.4
gunicorn==23.0.0
cachetools==5.5.1
```

---

## 15. Phase 2 로드맵 (MVP 이후)

> MVP 검증 후 유저 피드백 기반으로 결정

| # | 기능 | 기대 효과 |
|:--|:---|:---|
| 1 | 결과 공유 카드 (SNS) | 바이럴 — DAU 증가 |
| 2 | 이메일/푸시 알림 | 리텐션 — 재방문 유도 |
| 3 | 예측 히스토리 페이지 | 몰입감 — 내 기록 열람 |
| 4 | "나의 순위" (상위 X%) | 동기부여 — Top 100 밖 유저 |
| 5 | 카테고리 필터 | UX — 관심 분야만 보기 |
| 6 | 다크 모드 | UX — 야간 사용 |
| 7 | 광고 위치 A/B 테스트 | 수익 — CPM 최적화 |

---

## 16. 비용 요약 (수정)

| 항목 | 월 비용 | 비고 |
|:---|:---|:---|
| Render Web | $7 | 상시 가동 |
| Render Cron | ~$1 | 매 시간 실행 |
| Supabase | $0 | Free Tier + 캐싱으로 유지 |
| Gemini API | $0~$2 | Free Tier 15 RPM |
| **합계** | **$8~10** | |

**손익분기: DAU ~130명** (캐싱으로 서버비 절감)
