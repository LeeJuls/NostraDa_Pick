# NostraDa Pick - Article-First Architecture & URL Hallucination 제거 히스토리
**버전**: v1.0 | **날짜**: 2026-03-13 | **작업자**: Claude (Backend Agent)

---

## 배경 및 문제 정의

### 핵심 버그: source_url Hallucination

Gemini가 예측 문제를 생성할 때 `source_url` 필드를 **출력**으로 생성하는 구조적 결함.
키워드 매칭(`_resolve_source_url()`)으로 사후 교정을 시도했으나 실패 사례가 누적됨.

**실제 발생한 URL 불일치 사례:**

| 질문 주제 | 실제 연결된 URL | 올바른 URL |
|-----------|----------------|------------|
| 이란 제재 관련 질문 | NYTimes 미군 공중급유기 추락 기사 | 이란 제재 관련 기사 |
| 영국 노동당 지지율 YouGov 여론조사 | BBC 네팔 총선 래퍼 정치인 기사 | 영국 노동당 관련 기사 |
| Jensen Huang / NVIDIA GTC 질문 | Yahoo Finance NVDA 주가 페이지 | GTC 관련 뉴스 기사 |
| 유엔 안보리 수단 질문 | 링크 없음 | 수단 관련 BBC 기사 |

### _resolve_source_url() 구조적 한계

기존 방식: 이슈 제목 키워드 ↔ 뉴스 헤드라인 키워드 매칭
- "hang" → "change" 안에서 오매칭 (단어 경계 미처리)
- 정치 뉴스 질문 → 주가 URL 연결 (카테고리 무시)
- 주가 질문 → 관련 없는 테크 기사 URL 연결

### 추가 개선: 밈주식 / 고변동성 종목 자동 선정

`stock_price_service.py`에 밈주식이 없어서, GME 급등/GameStop 이슈 같은
재미있는 주제가 자동으로 후보에 올라오지 않는 문제.

---

## 핵심 결정 사항

| # | 결정 | 근거 |
|---|------|------|
| 1 | **Article-First Architecture** 도입 — URL을 출력→입력으로 전환 | hallucination 구조적 제거, 키워드 매칭 오류 원천 차단 |
| 2 | `_select_candidates()` 신규 메서드 — N개 기사 사전 선별 + URL 확정 | Gemini 호출 전에 URL이 확정되므로 불일치 불가 |
| 3 | 프롬프트를 context-dump → `[ARTICLE N]` article-specific 형식으로 전환 | Gemini가 각 기사별로 1개씩 정확한 질문 생성 |
| 4 | `article_index` 기반 URL 매핑 — `candidates[article_index]['url']` | 사후 키워드 매칭 완전 제거 |
| 5 | `_resolve_source_url()` 메서드 100줄+ 전면 삭제 | 복잡한 매칭 로직 불필요 |
| 6 | 밈주식 7개 추가 (GME, AMC, MSTR, RDDT, RKLB, IONQ, MARA) | 트렌드 이슈 종목 자동 포착 |
| 7 | `change_pct` 필드 추가 — yfinance `previousClose` 대비 일일 변동률 | 급등/급락 종목 우선 후보 선정 |
| 8 | 카테고리 다양성 보장 — round-robin, max 2 per category | politics/world/economy/sports/tech 고루 분산 |
| 9 | tier-1 소스 필터링 코드에서 처리 — BBC, Reuters, NYT, AP, Guardian | politics/world 카테고리 신뢰도 확보 |
| 10 | 가격 후보를 economy pool 앞에 배치 | 가격 질문이 더 명확한 예측 질문 생성 |

---

## 변경 파일 목록

| 파일 | 변경 내용 | 변경 규모 |
|------|-----------|-----------|
| `services/gemini_service.py` | `_select_candidates()` 추가, 프롬프트 재구성, `_resolve_source_url()` 삭제, `article_index` URL 매핑 | 대규모 |
| `services/stock_price_service.py` | 밈주식 7개 추가, `change_pct` 필드 추가 | 소규모 |

---

## Article-First Architecture 상세

### Before (context-dump 방식)

```
1. 데이터 수집 (headlines 60개, matches 32개, prices 70개)
2. 전체를 프롬프트에 덤프
3. Gemini: "이 중에서 알아서 8개 만들어줘" → source_url도 알아서 생성
4. _resolve_source_url()로 키워드 매칭 사후 교정 (실패율 높음)
5. DB 저장
```

### After (Article-First 방식)

```
1. 데이터 수집 (headlines, matches, prices) ← 동일
2. _select_candidates(count=8) → N개 기사 선별 + URL 확정 ← 신규
3. 확정 기사로 article-specific 프롬프트 구성 ← 구조 변경
4. Gemini: "[ARTICLE 0] ... [ARTICLE 7] 각각 1개씩" → article_index만 반환
5. source_url = candidates[article_index]['url'] ← 사후매칭 제거
6. DB 저장 ← 동일
```

### Candidate 데이터 구조

```python
candidate = {
    'type': 'news' | 'sports' | 'price',
    'category': 'world' | 'politics' | 'economy' | 'tech' | 'sports',
    'title': str,        # 헤드라인 / 경기명 / 종목+가격
    'url': str,          # 확정 URL (RSS link / Google Search / Yahoo Finance)
    'source_name': str,  # 'BBC News' / 'Premier League' / 'Yahoo Finance'
    'context': str,      # Gemini에게 전달할 추가 정보
}
```

### 소스 타입별 URL

| 타입 | URL | 예시 |
|------|-----|------|
| news | RSS 기사 원본 링크 | `https://bbc.com/news/articles/...` |
| sports | Google Search URL (경기명+대회) | `https://google.com/search?q=Arsenal+vs+Chelsea+Premier+League` |
| price | Yahoo Finance 종목 페이지 | `https://finance.yahoo.com/quote/BTC-USD/` |

### _select_candidates() 선별 알고리즘

**1. 후보 풀 구축:**
- 뉴스: politics/world는 tier-1 소스만 (BBC, Reuters, NYT, AP, Guardian)
- 스포츠: 빅 대회 우선 (Champions League: 10점, Premier League: 9점, NBA: 9점...)
- 주가: |change_pct| 기준 정렬 + ALWAYS_INCLUDE_TICKERS(S&P500, BTC, ETH 등) 우선순위 100

**2. 카테고리 다양성 보장:**
```
categories = ['politics', 'world', 'economy', 'sports', 'tech']
max_per_cat = 2  # 각 카테고리 최대 2개
round-robin 순환 → count개까지 채움
```

**3. 중복 방지:**
- 기존 DB 이슈 제목과 키워드 3개 이상 겹치면 스킵

### Gemini 프롬프트 구조 변경

**Before:**
```
{match_context}   ← 전체 32경기
{news_context}    ← 전체 60개 헤드라인
{stock_context}   ← 전체 70개 주가
"이 중에서 알아서 8개 만들어줘"
```

**After:**
```
=== SELECTED ARTICLES (create ONE question per article) ===

[ARTICLE 0] (news / world)
Source: BBC News
Headline: "Sudan drone strike kills 17 at school"
→ Create a forward-looking prediction about what happens NEXT.
⚠️ Your question MUST be about THIS specific headline topic.

[ARTICLE 1] (sports / sports)
Match: Arsenal FC vs Everton FC
Competition: Premier League, Kick-off: (UTC+0) 2026-03-14 17:30
→ Create a match result, score, or winner prediction for THIS specific match.

[ARTICLE 2] (price / economy)
Bitcoin (BTC): $71,573.00 (+2.3%)
Current price: $71,573.00 USD. Threshold must be within ±5%.
→ Create a price threshold question for THIS specific ticker.
⚠️ Use the EXACT ticker and current price shown above.

=== END OF ARTICLES ===
```

**Output 형식 변경:**

Before:
```json
{"title": "...", "category": "...", "source_url": "https://..."}
```

After:
```json
{"article_index": 2, "title": "...", "category": "..."}
```
→ Python에서 `candidates[article_index]['url']` 직접 매핑

---

## stock_price_service.py 변경사항

### 밈주식 추가 (7개)

```python
"GME":   "GameStop (GME)",
"AMC":   "AMC Entertainment (AMC)",
"MSTR":  "MicroStrategy (MSTR)",
"RDDT":  "Reddit (RDDT)",
"RKLB":  "Rocket Lab (RKLB)",
"IONQ":  "IonQ (IONQ)",
"MARA":  "Marathon Digital (MARA)",
```

### change_pct 필드 추가

```python
# yfinance fast_info로 previousClose 조회
tickers_obj = yf.Tickers(tickers_str)
for ticker in WATCH_TICKERS:
    info = tickers_obj.tickers[ticker].fast_info
    prev = getattr(info, 'previous_close', None)
    if prev:
        prev_close_map[ticker] = float(prev)

# 변동률 계산
change_pct = round((price - prev) / prev * 100, 2) if prev else 0.0
results.append({
    "ticker": ticker, "label": label,
    "price": round(price, 2), "currency": "USD",
    "change_pct": change_pct,  # ← 신규 필드
})
```

---

## 테스트 결과

### URL 매칭 정확도

| 회차 | Before (키워드 매칭) | After (Article-First) |
|------|---------------------|----------------------|
| 1차 테스트 | 4/8 불일치 (50%) | 8/8 일치 (100%) |
| 2차 테스트 | - | 8/8 일치 (100%) |

### 2차 생성 결과 예시 (URL 완벽 매칭)

| 질문 | URL | 타입 |
|------|-----|------|
| Sunderland AFC vs Brighton 경기 결과 | Google Search (Premier League) | sports ✅ |
| UK 정부 BBC World Service 예산 증액 | Guardian BBC 기사 | news ✅ |
| IAEA 이란 핵 협정 위반 선언 | BBC 이란 분쟁 기사 | news ✅ |
| Bitcoin 가격 $67,722 이상 유지 | Yahoo Finance BTC-USD | price ✅ |
| Alphabet 양자컴퓨팅 스타트업 파트너십 | TechCrunch 양자컴 기사 | news ✅ |
| Burnley vs Bournemouth 합산 3골 이상 | Google Search (Premier League) | sports ✅ |
| UK 내각 장관 사임 | Guardian 사임 기사 | news ✅ |
| UN 안보리 호르무즈 해협 긴급 소집 | BBC 해협 관련 기사 | news ✅ |

---

## 관련 커밋

| 커밋 | 내용 |
|------|------|
| `dfa82f4` | Article-First Architecture 핵심 구현 |
| `2a64c13` | PR #8 머지 → main 반영 |

---

## 알려진 잔여 이슈

- **Article-specific 미준수 (드물게 발생)**: Gemini가 간혹 기사 주제와 다른 질문 생성
  → `⚠️ Your question MUST be about THIS specific headline topic.` 규칙으로 완화
- **뱅 패턴 (announce/statement)**: 금지 패턴이 간혹 생성됨 (별도 프롬프트 개선 필요)
- **카테고리 오분류**: 원유 가격 질문이 "tech"로 분류되는 경우 (드물게)
  → 카테고리 규칙은 프롬프트에 명시되어 있으나 Gemini가 간혹 무시
