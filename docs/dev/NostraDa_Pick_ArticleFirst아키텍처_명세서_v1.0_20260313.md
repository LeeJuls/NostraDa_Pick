# NostraDa Pick - Article-First 출제 아키텍처 명세서
**버전**: v1.0 | **작성일**: 2026-03-13

---

## 1. 개요

Gemini AI가 예측 문제를 생성할 때 source_url을 **출력**으로 생성하는 방식의 구조적 결함(hallucination)을 제거하기 위해 도입된 아키텍처.

**핵심 전환**: URL을 Gemini의 출력 → Python의 **입력**으로 바꿈.
기사를 먼저 확정하고, 확정된 기사를 Gemini에게 넘겨 질문을 만들게 함.

---

## 2. 아키텍처 비교

### 2.1 Before: Context-Dump 방식

```
뉴스 60개 + 경기 32개 + 주가 70개
         ↓
    Gemini 프롬프트 (거대)
         ↓
Gemini 출력: {title, category, source_url}
         ↓
_resolve_source_url() 키워드 매칭 사후 교정
         ↓
DB 저장
```

**문제점:**
- Gemini가 source_url을 지어냄 → 관련 없는 기사 URL 연결
- 키워드 매칭도 오매칭 빈발 (예: "hang" → "change" 안에서 매칭)

### 2.2 After: Article-First 방식

```
뉴스 60개 + 경기 32개 + 주가 70개
         ↓
_select_candidates(count=N) → N개 기사 선별 + URL 확정
         ↓
    [ARTICLE 0] ... [ARTICLE N] 형식 프롬프트
         ↓
Gemini 출력: {article_index, title, category}
         ↓
source_url = candidates[article_index]['url']
         ↓
DB 저장
```

**장점:**
- URL 불일치 원천 불가 (URL은 Python에서 확정)
- 프롬프트가 간결해짐 (선별된 N개만 전달)
- 키워드 매칭 로직 100줄+ 완전 삭제

---

## 3. 핵심 컴포넌트

### 3.1 `_select_candidates()` — 기사 선별 메서드

**위치**: `services/gemini_service.py` > `GeminiService._select_candidates()`

**시그니처:**
```python
def _select_candidates(
    self,
    headlines: list[dict],   # fetch_news_headlines() 결과
    matches: list[dict],     # get_all_sports_matches() 결과
    prices: list[dict],      # fetch_stock_prices() 결과
    count: int = 8,
    existing_titles: list[str] | None = None,
) -> list[dict]:
```

**반환 구조:**
```python
{
    'type': 'news' | 'sports' | 'price',
    'category': 'politics' | 'world' | 'economy' | 'tech' | 'sports',
    'title': str,        # 헤드라인 / "Home vs Away" / "Label: $price (±%)"
    'url': str,          # 확정 URL
    'source_name': str,  # 출처 이름
    'context': str,      # 추가 컨텍스트 (경기 시간, 가격 정보 등)
}
```

**선별 알고리즘:**

| 단계 | 내용 |
|------|------|
| 1-a. 뉴스 풀 | politics/world는 HIGH_CREDIBILITY_SOURCES만 허용 |
| 1-b. 스포츠 풀 | BIG_COMPETITIONS 점수 기준 내림차순 정렬 |
| 1-c. 가격 풀 | \|change_pct\| 기준 정렬, ALWAYS_INCLUDE_TICKERS 우선순위 100 |
| 2. 선택 | round-robin, max 2 per category, 총 count개까지 채움 |
| 3. 중복 방지 | 기존 DB 이슈와 키워드 3개 이상 겹치면 스킵 |

**클래스 상수:**
```python
HIGH_CREDIBILITY_SOURCES = {
    "bbc", "reuters", "new york times", "nytimes",
    "associated press", "ap news", "the guardian", "guardian",
}
BIG_COMPETITIONS = {
    "UEFA Champions League": 10, "Premier League": 9,
    "La Liga": 8, "Bundesliga": 8, "Serie A": 8, "Ligue 1": 7,
    "NBA": 9, "MLB": 7, "Europa League": 6,
}
ALWAYS_INCLUDE_TICKERS = {
    "^GSPC", "^IXIC", "^DJI", "BTC-USD", "ETH-USD",
}
```

### 3.2 `generate_trending_issues()` — 출제 메인 플로우

```
1. DB에서 existing_titles 조회 (중복 방지)
2. DB에서 target_topics 조회 (어드민 설정)
3. UTC 시각 계산
4. 데이터 수집: get_all_sports_matches() + fetch_news_headlines() + fetch_stock_prices()
5. _select_candidates(count) → candidates list (URL 확정)
6. candidates → [ARTICLE 0]...[ARTICLE N] 프롬프트 구성
7. Gemini 호출 → [{article_index, title, category}, ...]
8. article_index → candidates[idx]['url'] 매핑
9. 반환
```

### 3.3 Article 블록 형식 (프롬프트 내)

**뉴스 기사:**
```
[ARTICLE 0] (news / world)
Source: BBC News
Headline: "Sudan drone strike kills 17 at school"
→ Create a forward-looking prediction about what happens NEXT.
⚠️ Your question MUST be about THIS specific headline topic.
```

**스포츠 경기:**
```
[ARTICLE 1] (sports / sports)
Match: Arsenal FC vs Everton FC
Competition: Premier League, Kick-off: (UTC+0) 2026-03-14 17:30
→ Create a match result, score, or winner prediction for THIS specific match.
```

**주가/코인:**
```
[ARTICLE 2] (price / economy)
Bitcoin (BTC): $71,573.00 (+2.3%)
Current price: $71,573.00 USD. Daily change: +2.3%. Threshold must be within ±5%.
→ Create a price threshold question for THIS specific ticker (within ±5% of current price).
⚠️ Use the EXACT ticker and current price shown above.
```

### 3.4 Gemini 출력 → URL 매핑

```python
# Gemini 출력 예시
[
    {"article_index": 0, "title": "Will RSF...", "category": "world"},
    {"article_index": 1, "title": "Will Arsenal...", "category": "sports"},
    {"article_index": 2, "title": "Will BTC...", "category": "economy"},
]

# Python에서 URL 매핑
for issue in issues_data:
    idx = issue.pop('article_index', None)
    if idx is not None and 0 <= idx < len(candidates):
        issue['source_url'] = candidates[idx]['url']
    else:
        issue['source_url'] = ''
```

---

## 4. stock_price_service.py 변경사항

### 4.1 추가된 밈주식 / 화제주

| 티커 | 종목명 | 추가 이유 |
|------|--------|-----------|
| GME | GameStop | 밈주식 대표주 |
| AMC | AMC Entertainment | 밈주식 대표주 |
| MSTR | MicroStrategy | 비트코인 보유 기업 |
| RDDT | Reddit | SNS 기반 화제주 |
| RKLB | Rocket Lab | 우주 화제주 |
| IONQ | IonQ | 양자컴퓨팅 화제주 |
| MARA | Marathon Digital | 비트코인 마이닝 |

### 4.2 change_pct 필드

- yfinance `fast_info.previous_close` 대비 당일 변동률 (%)
- `_select_candidates()`에서 급등/급락 종목 자동 우선 선정에 활용
- 밈주식이 급등 시 자동으로 예측 문제 후보에 등장

---

## 5. 운영 패턴

| 시나리오 | count | Gemini 호출 횟수 |
|----------|-------|-----------------|
| 초기 8개 일괄 생성 | 8 | 1회 (배치) |
| 4시간 주기 운영 | 1 | 1회 |
| 테스트 | 4~8 | 1회 |

**Gemini 호출은 항상 1회** (배치/단건 무관) → API 쿼터 효율적 사용

---

## 6. 파일 의존성

```
generate_trending_issues()
├── get_all_sports_matches()         ← sports_schedule_service.py
├── fetch_news_headlines()           ← news_feed_service.py
├── fetch_stock_prices()             ← stock_price_service.py (change_pct 포함)
└── _select_candidates()             ← gemini_service.py (내부)
    ├── HIGH_CREDIBILITY_SOURCES     (클래스 상수)
    ├── BIG_COMPETITIONS             (클래스 상수)
    ├── ALWAYS_INCLUDE_TICKERS       (클래스 상수)
    └── _yahoo_finance_url()         (정적 메서드)
```

---

## 7. 삭제된 코드

| 삭제 항목 | 이유 |
|-----------|------|
| `_resolve_source_url()` 메서드 (100줄+) | article_index 매핑으로 대체 |
| `TICKER_ALIASES` dict | _resolve_source_url 내부 사용 → 삭제 |
| `build_news_context()` import | 프롬프트에 뉴스 덤프 방식 제거 |
| `build_match_context()` import | 프롬프트에 경기 덤프 방식 제거 |
| `build_stock_context()` import | 프롬프트에 주가 덤프 방식 제거 |
