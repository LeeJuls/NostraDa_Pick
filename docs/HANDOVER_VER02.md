# NostraDa Pick 인수인계서
**버전**: VER02 | **날짜**: 2026-03-13 | **작성자**: Claude (Backend Agent)
> VER01 대비 변경: Article-First Architecture 도입 (URL hallucination 제거), 밈주식 추가, stock_price_service.py 신규

---

## 1. 프로젝트 개요

글로벌 핫이슈(스포츠, 경제, 정치 등)의 단기 결과(Yes/No)를 예측하는 텍스트 기반 시뮬레이션 게임.
4시간마다 Gemini AI가 자동으로 문제 출제 → 유저 투표 → AI가 결과 판정 → 포인트 지급.

- **라이브 URL**: https://nostrada-pick.onrender.com
- **GitHub**: https://github.com/LeeJuls/NostraDa_Pick

---

## 2. 기술 스택

| 영역 | 기술 |
|------|------|
| Backend | Flask (Python 3.11+) + Jinja2 |
| DB/Auth | Supabase (PostgreSQL) + Google OAuth |
| AI 출제 | Gemini API (`gemini-3.1-flash-lite-preview`) |
| AI 결과판정 | Gemini API (`gemini-2.0-flash-lite`) |
| 스포츠 API | football-data.org (축구) + api-sports.io (NBA/MLB) |
| 주가/코인 | yfinance (78개 종목, 4시간마다 실시간 조회) |
| 뉴스 | RSS 피드 18개 (BBC, Reuters, NYT, Guardian, TechCrunch 등) |
| 번역 | Google Translate API (이슈 생성 시 1회, 7개 언어 일괄) |
| 배포 | Render.com |
| Keep Alive | cron-job.org (10분 간격 ping) |
| CI/CD | GitHub Actions (issue_generator, issue_resolver) |

---

## 3. 핵심 파일 구조

```
├── app.py                          # Flask 엔트리포인트
├── config.py                       # 환경변수 관리
├── routes/
│   ├── api.py                      # AJAX API (베팅, 관리자 기능)
│   └── auth.py                     # Google OAuth 로그인
├── services/
│   ├── gemini_service.py           # ⭐ Gemini AI 출제 (Article-First Architecture)
│   │                               #    _select_candidates() — 기사 사전 선별 + URL 확정
│   │                               #    generate_trending_issues() — 출제 메인 플로우
│   │                               #    _translate_to_all_langs() — 7개 언어 번역
│   ├── resolver_service.py         # 결과 판정 (Yes/No + 포인트 지급)
│   ├── sports_schedule_service.py  # 스포츠 경기 일정 (football-data.org + api-sports.io)
│   ├── news_feed_service.py        # RSS 뉴스 피드 수집 (18개 소스)
│   ├── stock_price_service.py      # ⭐ 실시간 주가/코인 (78개 종목, change_pct 포함)
│   └── supabase_client.py          # DB 연결
├── templates/index.html            # 메인 페이지 (Jinja2)
├── static/
│   ├── css/style.css
│   └── js/app.js                   # ⭐ 프론트엔드 로직 + UI 라벨 7개 언어
├── scripts/
│   ├── reset_issues.py             # DB 이슈/베팅 전체 삭제
│   └── gen_new_issues.py           # 수동 이슈 생성 (python gen_new_issues.py 4)
├── .github/workflows/
│   ├── issue_generator.yml         # UTC 0,4,8,12,16,20시 자동 출제
│   └── issue_resolver.yml          # UTC 0:30,12:30 자동 결과 판정
├── render.yaml                     # Render 배포 설정
└── docs/
    ├── HANDOVER_VER01.md           # 이전 버전
    ├── HANDOVER_VER02.md           # ← 현재 파일
    ├── dev/                        # 기능 명세서
    └── history/                    # 작업 히스토리
```

---

## 4. 환경변수 (.env)

```env
# Supabase
SUPABASE_URL=https://xxx.supabase.co
SUPABASE_KEY=xxx

# Gemini (복수 키 가능: key1,key2,key3)
GEMINI_API_KEY=xxx

# Google OAuth
GOOGLE_CLIENT_ID=xxx
GOOGLE_CLIENT_SECRET=xxx

# Flask
FLASK_ENV=development       # 로컬: development | 서버: production
SECRET_KEY=xxx

# 스포츠 API
FOOTBALL_DATA_API_KEY=xxx   # football-data.org
API_SPORTS_KEY=xxx          # api-sports.io (NBA/MLB)

# Python
PYTHON_VERSION=3.11.0

# 로컬 개발 옵션
DISABLE_SCHEDULER=false     # true: APScheduler 비활성 (Actions 사용)
GEMINI_USE_FIXTURE=false    # true: fixture JSON 재사용 (API 호출 절약)
```

> **Render에도 동일한 변수 등록 필요** (FLASK_ENV=production, DISABLE_SCHEDULER=true)

---

## 5. 로컬 개발 환경 세팅

```bash
# 1. 클론
git clone https://github.com/LeeJuls/NostraDa_Pick.git
cd NostraDa_Pick

# 2. 가상환경
python -m venv .venv
.venv\Scripts\activate          # Windows
source .venv/bin/activate       # Mac/Linux

# 3. 의존성 설치
pip install -r requirements.txt

# 4. .env 파일 생성 (위 섹션 참고)

# 5. 실행
flask run --debug
# → http://localhost:5000
# → Admin Panel: http://localhost:5000/admin (localhost에서만 노출)
```

---

## 6. 주요 스크립트

```bash
# Windows 인코딩 설정 (이모지 출력 오류 방지)
set PYTHONIOENCODING=utf-8

# 이슈 전체 삭제 (bets → issues 순서로 삭제)
python scripts/reset_issues.py

# 수동 이슈 생성 (숫자: 생성할 문제 수)
python scripts/gen_new_issues.py 4
```

---

## 7. 자동화 스케줄

| 구분 | 주기 | 역할 |
|------|------|------|
| GitHub Actions: issue_generator | UTC 0,4,8,12,16,20시 | 자동 문제 출제 |
| GitHub Actions: issue_resolver | UTC 0:30, 12:30 | 자동 결과 판정 + 포인트 지급 |
| cron-job.org | 10분 간격 | Render Sleep 방지 ping |

**GitHub Actions Secrets 필요 (레포 → Settings → Secrets):**
`SUPABASE_URL`, `SUPABASE_KEY`, `GEMINI_API_KEY`, `GEMINI_API_KEYS`

---

## 8. Gemini 출제 아키텍처 (Article-First) ⭐

> VER01 대비 핵심 변경. URL hallucination 구조적 제거.

### 8.1 출제 플로우

```
1. 데이터 수집
   ├── get_all_sports_matches()    → 32경기 (48시간 이내)
   ├── fetch_news_headlines()      → 60개 헤드라인 (18개 RSS 피드)
   └── fetch_stock_prices()        → 78개 종목 (실시간 + change_pct)

2. _select_candidates(count=N)    ← 핵심 신규 메서드
   ├── politics/world: tier-1 소스만 (BBC, Reuters, NYT, AP, Guardian)
   ├── sports: 빅 대회 우선 (Champions League 10점, Premier League 9점...)
   ├── economy: 가격 후보 먼저 (|change_pct| 기준 정렬)
   ├── 카테고리 다양성: max 2 per category, round-robin
   └── 중복 방지: 기존 DB 이슈와 키워드 3개 이상 겹치면 스킵

3. [ARTICLE 0]...[ARTICLE N] 형식 프롬프트 구성

4. Gemini 1회 호출
   → [{article_index, title, category}, ...]

5. source_url = candidates[article_index]['url']  ← URL 직접 매핑

6. DB 저장
```

### 8.2 URL 타입별 출처

| 기사 타입 | URL | 예시 |
|-----------|-----|------|
| news | RSS 원본 링크 | `https://bbc.com/news/articles/...` |
| sports | Google Search URL | `https://google.com/search?q=Arsenal+vs+Chelsea+Premier+League` |
| price | Yahoo Finance | `https://finance.yahoo.com/quote/BTC-USD/` |

### 8.3 주요 프롬프트 규칙

| 규칙 | 내용 |
|------|------|
| ARTICLE-BASED | 각 기사별 1개 질문, 해당 기사 주제에서 벗어나면 안 됨 |
| FUTURE ONLY | 과거 이벤트 금지, 2025년 이전 금지 |
| ABSOLUTE UTC TIME | "tomorrow/today" 금지 → `(UTC+0) 2026-03-13 18:00` 형식 강제 |
| RESOLVABLE BY CLOSE TIME | 투표 마감(+4h) 전 결과 공개 이벤트 금지 |
| WITHIN 48 HOURS | 이벤트 최대 48시간 이내 |
| PRICE/MARKET 24H | 가격 예측은 24시간 이내, ±5% 이내 임계값 |
| MINIMUM DEADLINE | 뉴스 기반 질문은 최소 24시간 이후 마감 |
| SPECIFIC ENTITIES | 회사명·국가명·선수명 등 구체적 명시 필수 |
| SPORTS INTEGERS | 골/점수 정수만 허용 (1.5골 금지) |
| NO RELEASE PREDICTIONS | 엔터테인먼트 출시/발표 예측 금지 |
| CATEGORY MAX 2 | 동일 카테고리 최대 2개 (코드 레벨 검증 병행) |
| BANNED PATTERNS | statement/response/announce/face 등 측정불가 패턴 금지 |
| NAMED ENTITY REQUIRED | "any country", "any official" 등 불특정 주체 금지 |

---

## 9. 시간 처리 주의사항 ⚠️

- **모든 시간은 UTC+0 기준** → `datetime.now(timezone.utc)` 사용 필수
- `datetime.now()` 사용 금지 → 서버 로컬 시간(KST+9) 반환 → 9시간 오차 발생
- `close_at` = 이슈 생성 시점 + 4시간 (UTC)
- strftime 형식: `'(UTC+0) %Y-%m-%d %H:%M'`
- 한국어 후처리: `(UTC+0)` → `UTC 0시 기준` (자동 치환)

---

## 10. 배포 프로세스

1. `main` 브랜치에 push → Render 자동 배포 (약 2~3분 소요)
2. Render 환경변수는 대시보드에서 별도 관리 (push와 무관)
3. GitHub Actions는 push와 무관하게 cron으로 독립 실행

---

## 11. 외부 서비스 계정

| 서비스 | 용도 | 대시보드 |
|--------|------|---------|
| Render | 배포 서버 | https://dashboard.render.com |
| Supabase | DB + Auth | https://supabase.com/dashboard |
| cron-job.org | Keep Alive | https://console.cron-job.org |
| GitHub | 소스코드 + CI/CD | https://github.com/LeeJuls/NostraDa_Pick |
| football-data.org | 축구 경기 일정 | https://www.football-data.org |
| api-sports.io | NBA/MLB 일정 | https://api-sports.io |
| Google Cloud | OAuth + Translate API | https://console.cloud.google.com |

---

## 12. 알려진 이슈 / 주의사항

- **Article-specific 미준수 (드물게)**: Gemini가 간혹 기사 주제와 다른 질문 생성
  → `⚠️ Your question MUST be about THIS specific headline topic.` 규칙으로 완화
- **금지 패턴 잔류 (드물게)**: "announce/statement" 등 금지 패턴이 간혹 생성
  → 프롬프트 지속 보완 필요
- **Gemini 429 에러**: 무료 쿼터 초과 시 키/모델 자동 로테이션 → 전부 소진 시 더미 데이터 폴백
- **번역**: 이슈 생성 시 1회 Google Translate → DB 저장. 이후 API 호출 없음
- **Admin Panel**: `localhost`에서만 접근 가능 (프로덕션에서는 숨김)
- **스포츠 일정 의존**: API에 없는 경기는 출제 안 됨 (의도된 동작)

---

## 13. 버전 히스토리

| 버전 | 날짜 | 주요 변경 |
|------|------|-----------|
| VER01 | 2026-03-13 | UTC 통일, 스포츠 API 연동, Keep Alive cron-job.org 전환 |
| VER02 | 2026-03-13 | **Article-First Architecture** — URL hallucination 제거, 밈주식 추가 |
