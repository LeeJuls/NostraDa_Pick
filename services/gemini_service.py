import google.generativeai as genai
from config import config
from services.supabase_client import supabase
from services.sports_schedule_service import get_all_sports_matches
from services.news_feed_service import fetch_news_headlines
from services.stock_price_service import fetch_stock_prices
from datetime import datetime, timedelta, timezone
import json
import os
import requests  # 서버 측 번역 API 호출용

FIXTURE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'tests', 'fixtures')
FIXTURE_FILE = os.path.join(FIXTURE_DIR, 'generated_issues.json')

# 모델 폴백 순서: quota 높은 순 → 낮은 순
FALLBACK_MODELS = [
    "gemini-3.1-flash-lite-preview",  # 1순위: 500 RPD
    "gemini-3-flash-preview",          # 2순위: 20 RPD
    "gemini-2.5-flash",                # 3순위: 20 RPD
    "gemini-2.5-flash-lite",           # 4순위: 20 RPD
]

class GeminiService:
    def __init__(self):
        self.api_keys = config.GEMINI_API_KEYS
        self.current_key_idx = 0
        self.current_model_idx = 0
        self.model = None
        self._setup_model()

    def _setup_model(self):
        if not self.api_keys:
            print("⚠️ GEMINI_API_KEYS is missing. GeminiService will not work.")
            return

        api_key = self.api_keys[self.current_key_idx]
        model_name = FALLBACK_MODELS[self.current_model_idx]
        genai.configure(api_key=api_key)
        self.model = genai.GenerativeModel(model_name)
        print(f"🔄 Gemini model={model_name}, key={self.current_key_idx + 1}/{len(self.api_keys)}")

    def _rotate_key(self):
        """현재 모델에서 다음 API 키로 교체"""
        if self.current_key_idx < len(self.api_keys) - 1:
            self.current_key_idx += 1
            print(f"⚠️ Quota exceeded. Rotating to key {self.current_key_idx + 1}/{len(self.api_keys)}...")
            self._setup_model()
            return True
        else:
            print(f"⚠️ All keys exhausted for model={FALLBACK_MODELS[self.current_model_idx]}.")
            return False

    def _rotate_model(self):
        """현재 모델의 모든 키 소진 시 다음 모델로 전환 + 키 인덱스 초기화"""
        if self.current_model_idx < len(FALLBACK_MODELS) - 1:
            self.current_model_idx += 1
            self.current_key_idx = 0
            model_name = FALLBACK_MODELS[self.current_model_idx]
            print(f"🔁 Rotating to next model: {model_name}")
            self._setup_model()
            return True
        else:
            print("❌ All Gemini models and API keys have exhausted their quota.")
            return False

    @staticmethod
    def _yahoo_finance_url(ticker: str) -> str:
        """티커 심볼 → Yahoo Finance 종목 페이지 URL"""
        from urllib.parse import quote
        return f"https://finance.yahoo.com/quote/{quote(ticker)}/"

    # ── 기사 선별 (Article-First Architecture) ────────────────────────────
    # tier-1 뉴스 소스 (politics/world 카테고리 전용)
    HIGH_CREDIBILITY_SOURCES = {
        "bbc", "reuters", "new york times", "nytimes",
        "associated press", "ap news", "the guardian", "guardian",
    }
    # 빅 대회 우선순위 (높을수록 우선)
    BIG_COMPETITIONS = {
        "UEFA Champions League": 10, "Premier League": 9,
        "La Liga": 8, "Bundesliga": 8, "Serie A": 8, "Ligue 1": 7,
        "NBA": 9, "MLB": 7, "Europa League": 6,
        "Eredivisie": 5, "Primeira Liga": 5,
    }
    # 항상 후보 풀에 포함할 핵심 티커
    ALWAYS_INCLUDE_TICKERS = {
        "^GSPC", "^IXIC", "^DJI", "BTC-USD", "ETH-USD",
    }

    def _select_candidates(
        self,
        headlines: list[dict],
        matches: list[dict],
        prices: list[dict],
        count: int = 8,
        existing_titles: list[str] | None = None,
    ) -> list[dict]:
        """
        뉴스·스포츠·주가에서 count개의 후보 기사를 선별.
        URL은 여기서 확정되며, Gemini 프롬프트에 그대로 전달됨.

        Returns:
            [{'type': 'news'|'sports'|'price', 'category': str,
              'title': str, 'url': str, 'source_name': str, 'context': str}, ...]
        """
        import re, random

        existing_titles = existing_titles or []
        existing_words = set()
        for t in existing_titles:
            existing_words |= set(re.sub(r'[^a-z0-9 ]', ' ', t.lower()).split())

        # 기존 이슈 제목 목록 (개별 비교용) — 날짜/숫자 제거 정규화 버전으로 저장
        # _normalize_title은 이 함수 아래에 정의되므로, 임시 인라인 정규화 사용
        def _pre_normalize(t: str) -> str:
            s = t.lower()
            s = re.sub(r'\d{4}-\d{2}-\d{2}', ' ', s)
            s = re.sub(r'\d{1,2}:\d{2}', ' ', s)
            s = re.sub(r'\$[\d,]+\.?\d*', ' ', s)
            s = re.sub(r'\b\d+\.?\d*\s*%?\b', ' ', s)
            s = re.sub(r'[^a-z ]', ' ', s)
            return s
        existing_titles_lower = set(_pre_normalize(t) for t in existing_titles)

        # 기존 OPEN 이슈의 source URL 목록 (동일 기사 중복 출제 방지)
        existing_sources: set[str] = set()
        try:
            if supabase:
                src_resp = supabase.table('issues').select('source').eq('status', 'OPEN').execute()
                existing_sources = {x['source'] for x in (src_resp.data or []) if x.get('source')}
        except Exception:
            pass

        stopwords = {'will','the','a','an','is','are','be','at','in','on','by',
                     'of','to','and','or','for','from','with','its','has','have',
                     'not','no','new','as','than','that','this','it','more',
                     'their','close','price','match','scheduled','above','below'}

        def _normalize_title(text: str) -> str:
            """날짜·시간·숫자·가격 제거 후 소문자 알파벳만 남김 (의미 단어만 비교)."""
            t = text.lower()
            t = re.sub(r'\d{4}-\d{2}-\d{2}', ' ', t)   # 2026-03-15
            t = re.sub(r'\d{1,2}:\d{2}', ' ', t)         # 16:36
            t = re.sub(r'\$[\d,]+\.?\d*', ' ', t)         # $73,500
            t = re.sub(r'\b\d+\.?\d*\s*%?\b', ' ', t)    # 83000, 5%
            t = re.sub(r'[^a-z ]', ' ', t)                # 특수문자 제거
            return t

        def _is_duplicate(title: str) -> bool:
            """기존 이슈 또는 현재 배치 내 이슈와 중복 여부 판정.
            날짜·숫자를 제거한 의미 단어만 비교하여 '날짜만 다른 같은 질문' 차단."""
            words = set(_normalize_title(title).split()) - stopwords
            words = {w for w in words if len(w) > 2}
            if not words:
                return False
            for ex in existing_titles_lower:
                ex_words = set(_normalize_title(ex).split()) - stopwords
                ex_words = {w for w in ex_words if len(w) > 2}
                overlap = len(words & ex_words)
                threshold = 2 if len(words) <= 5 else 3
                if overlap >= threshold:
                    return True
            return False

        def _is_source_duplicate(url: str) -> bool:
            """이미 OPEN 상태인 이슈에 동일 source URL이 있으면 중복."""
            return bool(url) and url in existing_sources

        # ── 1. 후보 풀 구축 ──────────────────────────────────────────────
        pool = {'politics': [], 'world': [], 'economy': [], 'tech': [],
                'sports': [], 'entertainment': [], 'crypto': []}

        # 1-a. 뉴스 헤드라인
        for h in headlines:
            cat = h.get('category', 'world')
            source = h.get('source', '').lower()
            # politics/world는 tier-1만
            if cat in ('politics', 'world'):
                if not any(s in source for s in self.HIGH_CREDIBILITY_SOURCES):
                    continue
            if _is_duplicate(h.get('title', '')) or _is_source_duplicate(h.get('link', '')):
                continue
            target_cat = cat if cat != 'crypto' else 'economy'
            pool.setdefault(target_cat, []).append({
                'type': 'news',
                'category': target_cat,
                'title': h['title'],
                'url': h['link'],
                'source_name': h.get('source', 'News'),
                'context': h.get('description', ''),  # RSS summary → Gemini에게 전달
                'is_coin': cat == 'crypto',            # CoinDesk/CoinTelegraph 뉴스도 코인 취급
            })

        # 1-b. 스포츠 경기
        for m in matches:
            comp = m.get('competition', '')
            priority = self.BIG_COMPETITIONS.get(comp, 3)
            match_title = f"{m['home']} vs {m['away']}"
            search_url = m.get('search_url', '')
            if _is_duplicate(match_title) or _is_source_duplicate(search_url):
                continue
            pool['sports'].append({
                'type': 'sports',
                'category': 'sports',
                'title': f"{m['home']} vs {m['away']}",
                'url': m.get('search_url', ''),
                'source_name': comp,
                'context': (f"Competition: {comp}, "
                            f"Kick-off: {m.get('kickoff_utc', '')}"),
                '_priority': priority,
            })
        # 빅 대회 우선 정렬
        pool['sports'].sort(key=lambda x: x.get('_priority', 0), reverse=True)

        # 1-c. 주가/코인 — 변동률 |%| 상위
        price_candidates = []
        for p in prices:
            ticker = p.get('ticker', '')
            change = abs(p.get('change_pct', 0))
            # 핵심 티커는 항상 포함 (우선순위 100)
            is_core = ticker in self.ALWAYS_INCLUDE_TICKERS
            # 이미 같은 티커로 이슈가 있으면 스킵 (중복 방지)
            label_title = p.get('label', ticker)
            yf_url = self._yahoo_finance_url(ticker)
            if _is_duplicate(label_title) or _is_source_duplicate(yf_url):
                continue
            # 암호화폐 여부: ticker가 '-USD'로 끝나면 코인 (BTC-USD, ETH-USD 등)
            is_crypto_price = ticker.endswith('-USD')
            price_candidates.append({
                'type': 'price',
                'category': 'economy',
                'title': f"{p['label']}: ${p['price']:,.2f} ({p.get('change_pct', 0):+.1f}%)",
                'url': self._yahoo_finance_url(ticker),
                'source_name': 'Yahoo Finance',
                'context': (f"Current price: ${p['price']:,.2f} USD. "
                            f"Daily change: {p.get('change_pct', 0):+.1f}%. "
                            f"Threshold must be within ±5% of current price."),
                'is_coin': is_crypto_price,            # 코인이면 True → economy 내 최대 1개 제한
                '_sort_key': 100 if is_core else change,
            })
        price_candidates.sort(key=lambda x: x['_sort_key'], reverse=True)
        # 가격 후보를 뉴스 경제 후보 앞에 배치 (가격이 더 좋은 예측 문제를 만듦)
        pool['economy'] = price_candidates[:10] + pool['economy']

        # ── 2. 카테고리 다양성 보장 선택 ──────────────────────────────────
        # 카테고리 순회 순서 (매번 셔플)
        categories = ['politics', 'world', 'economy', 'sports', 'tech']
        random.shuffle(categories)

        selected = []
        cat_count = {c: 0 for c in categories}
        coin_count = 0          # economy 내 코인(crypto) 최대 1개 제한
        import math
        max_per_cat = max(1, math.ceil(count / len(categories)))  # count=4 → 1, count=8 → 2

        # 라운드 로빈: 각 카테고리에서 1개씩 순환하며 count개까지 채움
        rounds = 0
        while len(selected) < count and rounds < 5:
            for cat in categories:
                if len(selected) >= count:
                    break
                if cat_count[cat] >= max_per_cat:
                    continue
                candidates_in_cat = pool.get(cat, [])
                if not candidates_in_cat:
                    continue

                # economy: 코인이 이미 1개 있으면 코인 후보는 건너뜀
                pick = None
                for idx, c in enumerate(candidates_in_cat):
                    if c.get('is_coin') and coin_count >= 1:
                        continue  # 코인 추가 불가 → 다음 후보로
                    pick = candidates_in_cat.pop(idx)
                    break

                if pick is None:
                    continue  # 이 카테고리에서 선택 가능한 후보 없음

                # 코인 선택 시 카운트 증가
                if pick.get('is_coin'):
                    coin_count += 1

                # 내부용 키 제거
                pick.pop('_priority', None)
                pick.pop('_sort_key', None)
                pick.pop('is_coin', None)
                selected.append(pick)
                cat_count[cat] += 1
                # 배치 내 중복 방지: 선택된 후보를 즉시 dedup 목록에 추가 (정규화 버전)
                existing_titles_lower.add(_pre_normalize(pick['title']))
                if pick.get('url'):
                    existing_sources.add(pick['url'])
            rounds += 1

        # 부족하면 남은 후보에서 아무거나 채움 (코인 제한 동일 적용)
        if len(selected) < count:
            remaining = []
            for cands in pool.values():
                remaining.extend(cands)
            for r in remaining:
                if len(selected) >= count:
                    break
                if r.get('is_coin') and coin_count >= 1:
                    continue  # 코인 추가 불가
                if r.get('is_coin'):
                    coin_count += 1
                r.pop('_priority', None)
                r.pop('_sort_key', None)
                r.pop('is_coin', None)
                selected.append(r)

        return selected[:count]

    # ── Article-First: generate_trending_issues ────────────────────────────

    def generate_trending_issues(self, count: int = 3):
        """
        Article-First Architecture:
        1. 데이터 수집 (headlines, matches, prices)
        2. _select_candidates()로 N개 기사 확정 (URL 포함)
        3. 확정 기사 기반 프롬프트 → Gemini 1회 호출
        4. source_url = candidates[article_index]['url'] (사후매칭 불필요)
        5. DB 저장
        """
        if not self.model:
            return None

        use_fixture = os.environ.get('GEMINI_USE_FIXTURE', '').lower() == 'true'

        if use_fixture:
            if os.path.exists(FIXTURE_FILE):
                with open(FIXTURE_FILE, 'r', encoding='utf-8') as f:
                    issues = json.load(f)
                print(f"📦 [FIXTURE] Loaded {len(issues)} issue(s) from fixture. No API call made.")
                return issues
            else:
                print(f"⚠️ [FIXTURE] GEMINI_USE_FIXTURE=true but no fixture found. Calling API once and saving...")

        # 기존에 생성된 문제 제목들을 DB에서 가져와 중복 방지
        existing_titles = []
        try:
            if supabase:
                resp = supabase.table('issues').select('title').execute()
                if resp.data:
                    existing_titles = [item['title'] for item in resp.data]
        except Exception as e:
            print(f"⚠️ Could not fetch existing issues for deduplication: {e}")

        # DB에서 어드민이 설정한 타겟 주제(target_topics) 가져오기
        target_topics = ""
        try:
            if supabase:
                resp = supabase.table('app_settings').select('value').eq('key', 'target_topics').execute()
                if resp.data and resp.data[0].get('value'):
                    target_topics = resp.data[0]['value'].strip()
        except Exception as e:
            print(f"⚠️ Could not fetch target_topics from app_settings: {e}")

        # UTC 기준 현재 시각 및 마감 시각
        now_utc       = datetime.now(timezone.utc)
        close_utc     = now_utc + timedelta(hours=4)
        now_utc_str      = now_utc.strftime('(UTC+0) %Y-%m-%d %H:%M')
        close_utc_str    = close_utc.strftime('(UTC+0) %Y-%m-%d %H:%M')
        max_event_utc_str = (now_utc + timedelta(hours=48)).strftime('(UTC+0) %Y-%m-%d %H:%M')
        max_price_utc_str = (now_utc + timedelta(hours=24)).strftime('(UTC+0) %Y-%m-%d %H:%M')
        today_date        = now_utc.strftime('%Y-%m-%d')

        # count 비례 카테고리 최대치: count=4 → 1개, count=8 → 2개
        import math as _math
        max_per_cat_display = max(1, _math.ceil(count / 5))

        target_focus_prompt = ""
        if target_topics:
            target_focus_prompt = (
                f"\nFOCUS TOPICS: You MUST include at least 1 question directly related to: [{target_topics}]."
            )

        # ── 1단계: 데이터 수집 ─────────────────────────────────────
        all_matches    = get_all_sports_matches(hours_ahead=48)
        news_headlines = fetch_news_headlines(max_per_feed=5, max_age_hours=48)
        stock_prices   = fetch_stock_prices()

        # ── 2단계: 후보 기사 선별 (URL 확정) ───────────────────────
        candidates = self._select_candidates(
            news_headlines, all_matches, stock_prices,
            count=count, existing_titles=existing_titles,
        )
        print(f"📰 Selected {len(candidates)} candidate article(s) for Gemini prompt.")

        if not candidates:
            print("⚠️ No candidates selected. Falling back to dummy issues.")
            return self._generate_fallback_issues(count)

        # ── 3단계: 기사별 프롬프트 구성 ────────────────────────────
        article_blocks = []
        for i, c in enumerate(candidates):
            if c['type'] == 'news':
                desc = c.get('context', '').strip()
                desc_line = f"Summary: {desc}\n" if desc else ""
                block = (
                    f"[ARTICLE {i}] (news / {c['category']})\n"
                    f"Source: {c['source_name']}\n"
                    f"Headline: \"{c['title']}\"\n"
                    f"{desc_line}"
                    f"→ Create a prediction about WHETHER the main claim/event in this article will materialize.\n"
                    f"⚠️ Your question MUST be about the MAIN ACTOR and MAIN EVENT described in this article.\n"
                    f"⚠️ Do NOT escalate to secondary institutions (UN, IAEA, etc.) unless the article explicitly names them."
                )
            elif c['type'] == 'sports':
                block = (
                    f"[ARTICLE {i}] (sports / sports)\n"
                    f"Match: {c['title']}\n"
                    f"{c['context']}\n"
                    f"→ Create a match result, score, or winner prediction for THIS specific match."
                )
            elif c['type'] == 'price':
                block = (
                    f"[ARTICLE {i}] (price / economy)\n"
                    f"{c['title']}\n"
                    f"{c['context']}\n"
                    f"→ Create a price threshold question for THIS specific ticker (within ±5% of current price).\n"
                    f"⚠️ Use the EXACT ticker and current price shown above."
                )
            else:
                block = (
                    f"[ARTICLE {i}] ({c['type']} / {c['category']})\n"
                    f"{c['title']}\n"
                    f"{c.get('context', '')}\n"
                    f"→ Create a prediction question about THIS specific topic."
                )
            article_blocks.append(block)

        articles_text = "\n\n".join(article_blocks)

        exclusion_text = ""
        if existing_titles:
            exclusion_text = "\nDo NOT generate questions similar to these existing ones:\n"
            exclusion_text += "\n".join([f"- {title}" for title in existing_titles[-20:]])

        prompt = f"""You are an analyst for a real-time prediction market app 'NostraDa_Pick'.

TIMEZONE BASELINE: All times are UTC+0 (UTC). Do NOT use KST, EST, JST or any other local timezone.
Current UTC+0 time : {now_utc_str}
Voting closes at   : {close_utc_str}

=== SELECTED ARTICLES (create ONE question per article) ===

{articles_text}

=== END OF ARTICLES ===

For EACH article above, generate exactly ONE prediction question.
{target_focus_prompt}
{exclusion_text}

=== STRICT RULES ===

[ARTICLE-BASED QUESTIONS — MANDATORY]
- You MUST create exactly ONE question for EACH article listed above.
- Each question must ask WHETHER the MAIN CLAIM or MAIN EVENT described in the article will actually happen/materialize.
- Ask about the PRIMARY ACTOR and PRIMARY EVENT. Do NOT escalate to secondary actors or indirect consequences.

  ❌ WRONG: Article says "Iran Supreme Leader pledges to close Strait of Hormuz"
            → "Will the UN Security Council hold an emergency session?" (secondary actor, NOT in article)
  ✅ RIGHT : Article says "Iran Supreme Leader pledges to close Strait of Hormuz"
            → "Will the Strait of Hormuz actually be blockaded/closed by [date]?" (primary event)

  ❌ WRONG: Article about US-Iran war context
            → "Will the IAEA declare Iran in violation of nuclear agreements?" (IAEA not mentioned)
  ✅ RIGHT : Article about US-Iran war context
            → "Will the US and Iran reach a ceasefire agreement by [date]?" (main topic of the article)

  ❌ WRONG: Article about a corporate earnings miss → question about SEC investigation (not in article)
  ✅ RIGHT : Article about a corporate earnings miss → question about the stock price reaction

- RULE: If the article mentions a SPECIFIC institution (UN, IAEA, NATO, Fed, etc.), you MAY ask about that institution.
  If the article does NOT mention that institution, do NOT invent their involvement.
- For news articles: ask about the direct outcome or verification of the article's main claim.
- For sports articles: create a match result/score/winner prediction for THAT SPECIFIC match.
- For price articles: create a price threshold question for THAT SPECIFIC ticker using the provided current price.
- Do NOT substitute a completely different topic.

[VERIFIABLE EVENTS ONLY]
- Do NOT reference investigations, reports, or statements that you cannot verify from the provided articles.
- If you are not 100% certain an event/investigation/statement exists, SKIP IT.

[OBJECTIVELY MEASURABLE — MANDATORY]
- Every question MUST have a clear, objective YES/NO criterion that anyone can verify.
- The answer must be determinable by checking a single public data point (price, score, official statement, etc.).
  ❌ BAD : "Will polling show a shift?" (what counts as a "shift"? 0.1%? 5%?)
  ❌ BAD : "Will news coverage indicate change?" (subjective — who decides?)
  ❌ BAD : "Will market sentiment improve?" (unmeasurable)
  ❌ BAD : "Will tensions escalate?" (vague, no clear threshold)
  ✅ GOOD: "Will Bitcoin (BTC) price exceed $75,000?" (exact number, checkable)
  ✅ GOOD: "Will PEC Zwolle score 2+ goals?" (exact number, match result)
  ✅ GOOD: "Will the S&P 500 close above 5,800?" (exact number, checkable)
- If the question involves a change/shift/increase/decrease, specify the EXACT threshold number.

[SPORTS — MATCH QUESTIONS]
- For sports match questions, ALWAYS use the EXACT competition name from the article.
  ❌ FORBIDDEN: calling a Serie A match 'UEFA Champions League', or an NBA game 'EuroLeague'
  ✅ CORRECT  : copy the competition name exactly as it appears in the article's context.
- If no sports articles are provided, do NOT generate sports match questions.
- WORD CHOICE — avoid "draw" as a verb (mistranslated as "lottery" in some languages).
  ❌ FORBIDDEN: "Will Team A and Team B draw?" / "Will the match end in a draw?"
  ✅ CORRECT  : "Will Team A and Team B finish tied (0-0 or equal score)?"
  ✅ CORRECT  : "Will Team A win against Team B?" / "Will Team A score 2 or more goals?"
- ALLOWED question types for sports: win/loss result, exact score, total goals, first scorer.

[FUTURE ONLY]
- Only generate questions about events DEFINITIVELY occurring AFTER {now_utc_str}.
- Do NOT use any event that occurred before {today_date}, or any event from 2025 or earlier.
- If you are not 100% certain an event is still in the future, SKIP IT.

[ABSOLUTE UTC TIME — MANDATORY]
- ALL time references in question titles MUST use absolute UTC format.
  CORRECT  : "by {close_utc_str}", "by (UTC+0) 2026-03-13 06:00"
  FORBIDDEN: "tomorrow", "tonight", "today", "by end of day",
             "by end of session", "within X hours", "오늘", "내일"
- Market/price references must also use absolute UTC open/close times:
  CORRECT  : "between {now_utc_str} and {close_utc_str}"
  FORBIDDEN: "today's opening price", "by end of trading session", "today's open"

[RESOLVABLE BY CLOSE TIME]
- The result must NOT become publicly known before {close_utc_str}.
- If the event has a specific scheduled time (announcement, press conference, match kick-off,
  earnings release, etc.), that scheduled time MUST be AFTER {close_utc_str}.
  ❌ BAD : ECB announces at 13:15 UTC but voting closes at {close_utc_str} (result known early → users can cheat)
  ✅ GOOD: Price / index level checked exactly AT {close_utc_str}
  ✅ GOOD: Scheduled event occurs AFTER {close_utc_str}
- Do NOT create questions whose natural deadline exceeds {close_utc_str}.

[WITHIN 48 HOURS — MANDATORY]
- The event must occur no later than {max_event_utc_str} (48 hours from now).
- Do NOT generate questions about events scheduled more than 48 hours away.

[PRICE/MARKET QUESTIONS — 24 HOURS MAX]
- For price or market-based questions (crypto, stocks, forex, indices, commodities),
  the check time MUST be within 24 hours: no later than {max_price_utc_str}.

[PRICE THRESHOLD — MUST BE GENUINELY UNCERTAIN]
- The price threshold MUST be set close to the CURRENT market price (from the article data).
- STEP 1: Read the current price from the article.
- STEP 2: Calculate ±5% range: threshold must be BETWEEN (price × 0.95) and (price × 1.05).
- STEP 3: If you cannot stay within ±5%, choose a threshold closer to the current price.

  Example: BTC current price = $83,000 → allowed range: $78,850 to $87,150
  ❌ BAD : BTC current $83,000 → asking "Will BTC exceed $73,500?" (−11%: too far)
  ❌ BAD : BTC current $83,000 → asking "Will BTC exceed $120,000?" (obviously NO — too hard)
  ❌ BAD : NVDA current $183 → asking "Will NVDA close above $140?" (obviously YES — too easy)
  ✅ GOOD: BTC current $83,000 → asking "Will BTC stay above $82,000?" (genuinely uncertain ±1%)
  ✅ GOOD: NVDA current $183 → asking "Will NVDA close above $180?" (genuinely uncertain ±2%)

[ECONOMY NEWS — ALREADY-RELEASED DATA]
- If the article describes economic data that has ALREADY been published (GDP, CPI, unemployment rate,
  trade balance, PMI, retail sales, etc.), do NOT ask about:
  ❌ "Will [agency] revise the figure?" — revisions take weeks/months, not 24–48 hours
  ❌ "Will next month's figure be higher/lower?" — next release is weeks away
  ❌ "Will [government] respond to the data?" — banned statement pattern
- Instead, ask about the IMMEDIATE MARKET REACTION, which is measurable within 24 hours:
  ✅ "Will GBP/USD fall below 1.28 by (UTC+0) 2026-03-14 07:00?" (currency reaction)
  ✅ "Will the FTSE 100 close below 8,300 by (UTC+0) 2026-03-14 16:30?" (index reaction)
  ✅ "Will UK 10-year gilt yields rise above 4.5% by (UTC+0) 2026-03-14 17:00?" (bond reaction)
  → Use the relevant currency pair, stock index, or bond yield from CURRENT MARKET PRICES.
  → The threshold must still be within ±5% of the current price listed in the article data.

[MINIMUM DEADLINE — NEWS-BASED QUESTIONS]
- For politics, world, and economy news-based questions (NOT sports or price checks),
  the deadline MUST be at least 24 hours from now (no earlier than {max_price_utc_str}).
  ❌ BAD : "Will the UK government announce X by (UTC+0) 2026-03-13 08:35?" (only 4 hours away)
  ✅ GOOD: "Will the UK government announce X by (UTC+0) 2026-03-14 18:00?" (≥24 hours)
- Sports match questions may use the actual kick-off/game time as deadline.
- Price/market questions follow the [PRICE/MARKET QUESTIONS] rule (within 24 hours).

[ANSWER NOT ALREADY KNOWN — MANDATORY]
- Do NOT create a question whose answer can already be determined from the provided article.
  ❌ BAD : Source says "at least 17 killed" → asking "Will death toll exceed 20?"
  ❌ BAD : Source says "Fed raises rates by 0.5%" → asking "Will the Fed raise rates?"
  ✅ GOOD: Source reports drone strike → asking "Will the UN hold an emergency session on Sudan by X?"
- The question must be about something that is GENUINELY UNKNOWN at the time of writing.
  If the source article already answers the question, SKIP IT and choose a different angle.

[ATTACK / TERRORISM / CONFLICT EVENTS — SPECIAL RULES]
- NEVER ask about the current incident's death toll, casualty count, or damage numbers.
  These are already mostly known from the source → not genuinely uncertain.
  ❌ FORBIDDEN: "Will the death toll from the Sudan strike exceed 20?" (source says 17; clearly close to final)
  ❌ FORBIDDEN: "Will the confirmed fatalities surpass [N]?" (answer already in the source)
  ❌ FORBIDDEN: "Will [government] release an official statement about the attack?" (banned pattern — unmeasurable)
  ❌ FORBIDDEN: "Will [government] confirm the attack was carried out by [group]?" (already reported)

- Instead, ask about the NEXT EVENT, ESCALATION, or SPECIFIC VERIFIABLE OUTCOME:
  ✅ "Will RSF carry out another drone attack on a civilian area in Sudan within 48 hours by X?"
     (genuinely uncertain — new event, not the same incident)
  ✅ "Will the UN Security Council hold an emergency vote on Sudan by X?"
     (specific verifiable action — UN votes are public record)
  ✅ "Will Sudan's government declare a state of emergency by X?"
     (specific verifiable act — state of emergency is a legal declaration)
  ✅ "Will the U.S. or EU announce new sanctions targeting RSF by X?"
     (specific verifiable outcome — sanction announcements are public)
  ✅ "Will [country] close its embassy in [city] due to the conflict by X?"
     (specific verifiable action)

- The key question to ask yourself: "Can this be verified by checking a single public record?"
  If YES → allowed. If NO or "depends on interpretation" → forbidden.

[CATEGORY — STOCK PRICE QUESTIONS MUST BE ECONOMY]
- Questions asking about a stock price, crypto price, commodity price, or index level
  MUST use the "economy" category — regardless of which company or sector it is.
  ❌ BAD : NVDA price question → category "tech"
  ✅ GOOD: NVDA price question → category "economy"
- Use "tech" ONLY for product launches, software releases, company strategies, tech news — NOT for stock prices.

[SPECIFIC & NAMED ENTITIES — MANDATORY]
- Every question MUST name the specific real-world entity involved.
  ❌ BAD : "Will the official press release confirm a delay in next-gen AI hardware?"
  ✅ GOOD: "Will NVIDIA's GTC 2026 keynote confirm a delay in the Blackwell Ultra GPU launch?"
- Required: company name, country/league name, person name, ticker symbol, or specific event name.
- NEVER use vague terms like "a company", "the government", "official press release", "the team".
- If you cannot name a specific real entity for an event, SKIP IT and choose a different topic.

[SPORTS SCORES — INTEGERS ONLY]
- Sports scores and goals MUST be whole numbers (integers).
  ❌ FORBIDDEN: "1.5 goals", "2.5 goals", "over 1.5", "under 3.5"
  ✅ CORRECT  : "2 goals or more", "3 goals or more", "over 2"

[ENTERTAINMENT — NO RELEASE/LAUNCH PREDICTIONS]
- Do NOT generate "will X be released/announced/launched?" questions.
  Your training data may be outdated — the product/show may already exist.
  ✅ ALLOWED  : viewership ratings, box office numbers, awards, streaming rankings

[BANNED QUESTION PATTERNS — NEVER USE THESE]
- The following question patterns are FORBIDDEN because the judgment criterion is subjective or unmeasurable:
  ❌ "Will [entity] issue an official response/statement about X?"
  ❌ "Will [entity] announce a formal response/position on X?"
  ❌ "Will [entity] address/comment on X publicly?"
  ❌ "Will [entity] face X?" (e.g., "face more resignations", "face criticism", "face pressure")
  ❌ "Will news coverage/reports confirm X?"
  ❌ "Will [entity] take action on X?" / "Will [entity] respond to X?"
  ❌ "Will [entity] release a follow-up/additional official statement about X?"
  ❌ "Will [entity] announce a new/specific [policy/funding/package/initiative] for X?"
  ❌ "Will [entity] issue a formal press release announcing [new sanctions/policy/decision]?"
  ❌ "Will [entity] announce new sanctions against [unnamed entities / groups / actors]?"
  ❌ "Will [government/military] officially/formally announce the deployment/dispatch/sending of X?"
     → The ANNOUNCEMENT is not the event. Ask about the ACTUAL EVENT:
     → ✅ "Will UK Royal Navy warships enter the Strait of Hormuz by X?"
     → ✅ "Will [country] military confirm active operations in [location] by X?"
  ❌ ANY question whose YES/NO depends entirely on whether a press release was issued,
     rather than whether the underlying real-world event actually occurred.
- Instead, ask about SPECIFIC, VERIFIABLE actions with indisputable YES/NO outcomes:
  ✅ "Will UK PM Keir Starmer make a formal statement in Parliament about the Mandelson affair by X?"
     (verifiable: UK Hansard / official parliamentary record)
  ✅ "Will Peter Mandelson resign as UK ambassador to the US by X?"
     (verifiable: official government press release)
  ✅ "Will the UK Labour Party's approval rating drop below 30% in a YouGov poll published by X?"
     (verifiable: specific published poll with a number)

[POLITICS / ELECTION QUESTIONS — HOW TO ASK CORRECTLY]
- Political questions must have ONE clear, publicly verifiable outcome. Use these verified patterns:

  PATTERN 1 — POLL NUMBER (requires a specific published poll):
  ✅ "Will Marine Le Pen's RN party receive more than 35% support in a French opinion poll published by X?"
  ✅ "Will the UK Labour Party fall below 30% in a YouGov poll by X?"

  PATTERN 2 — LEGAL / CONSTITUTIONAL DECISION (court ruling, disqualification, etc.):
  ✅ "Will the French Constitutional Council ban Marine Le Pen from the 2027 presidential race by X?"

  PATTERN 3 — PARLIAMENTARY VOTE (specific vote with pass/fail outcome):
  ✅ "Will the French National Assembly pass a motion of no confidence against PM François Bayrou by X?"

  PATTERN 4 — NAMED PERSON'S SPECIFIC ACTION (resignation, appointment, firing):
  ✅ "Will Emmanuel Macron dissolve the National Assembly before X?"
  ✅ "Will [named minister] resign from their post by X?"

  ❌ FORBIDDEN POLITICAL PATTERNS (judgment is ambiguous):
  ❌ "Will [party] take steps to address X?" (what counts as a "step"?)
  ❌ "Will [country]'s political situation stabilize by X?" (unmeasurable)
  ❌ "Will [party] gain momentum / lose support?" (no specific threshold)
  ❌ "Will [leader] face pressure over X?" (subjective)
  ❌ "Will [government] announce a formal reversal/cancellation/halt of X?"
  ❌ "Will [government] condemn / denounce / criticize X?"

[NAMED ENTITY REQUIRED — NO "ANY COUNTRY / ANY OFFICIAL / ANY GROUP"]
- NEVER use "any country", "any government", "any official", "any group", or similar vague subjects.
  ❌ BAD: "Will any country formally condemn the drone strike in Sudan by X?"
     → Almost certainly YES (any one of 193 UN members could say something) — zero uncertainty.
  ✅ GOOD: "Will the U.S. State Department formally sanction RSF leadership by X?" (specific entity + specific action)
- Every question subject MUST be a single named entity: a specific country, person, organization, or institution.

[TECH/KEYNOTE QUESTIONS — SPECIFIC OUTCOMES ONLY]
- For tech event questions (keynotes, product launches, announcements), NEVER ask:
  ❌ "Will X be mentioned/discussed/referenced/highlighted in the keynote?" → subjective
  ❌ "Will the keynote explicitly/specifically mention X?" → "explicitly" doesn't make it measurable
- Instead, ask about BINARY, VERIFIABLE PRODUCT OUTCOMES with specific thresholds:
  ✅ "Will NVIDIA officially announce a release date for the Blackwell Ultra GPU at GTC 2026?" (YES/NO)
  ✅ "Will NVDA stock price rise more than 5% within 24 hours after the GTC 2026 keynote by X?" (measurable)

[CATEGORY DIVERSITY — MAX {max_per_cat_display} PER CATEGORY]
- Among the {count} questions, NO single category may appear more than {max_per_cat_display} time(s).
  ❌ BAD : {max_per_cat_display + 1} or more questions from the same category
  ✅ GOOD: spread across economy, sports, politics, tech, world
- Use diverse categories from: economy, sports, politics, tech, entertainment, world

=== OUTPUT FORMAT ===
Return a JSON array. Each object must have:
  "article_index" : integer (0-based index matching the [ARTICLE N] this question is based on)
  "title"         : prediction question string (must contain absolute UTC deadline)
  "category"      : one of [economy, sports, politics, tech, entertainment, world]

Output only valid JSON, no markdown fences.
"""

        # ── 4단계: Gemini 호출 + article_index → URL 매핑 ──────────
        max_retries = len(FALLBACK_MODELS) * max(len(self.api_keys), 1)
        for attempt in range(max_retries):
            try:
                response = self.model.generate_content(prompt)
                text = response.text.strip()
                if "```json" in text:
                    text = text.split("```json")[1].split("```")[0].strip()

                issues_data = json.loads(text)

                # 카테고리 다양성 검증: count에 비례한 최대치 (count=4→1개, count=8→2개)
                import math
                from collections import Counter
                _max_per_cat = max(1, math.ceil(count / 5))
                cat_count = Counter()
                filtered = []
                for issue in issues_data:
                    cat = issue.get('category', '')
                    if cat_count[cat] < _max_per_cat:
                        filtered.append(issue)
                        cat_count[cat] += 1
                issues_data = filtered

                # ── article_index → 확정 URL 매핑 (핵심!) ──────────
                for issue in issues_data:
                    idx = issue.pop('article_index', None)
                    if idx is not None and isinstance(idx, int) and 0 <= idx < len(candidates):
                        issue['source_url'] = candidates[idx]['url']
                    else:
                        issue['source_url'] = ''
                    print(f"  📎 [{issue.get('category','')}] {issue.get('title','')[:60]}...")
                    print(f"     → URL: {issue.get('source_url','(none)')[:80]}")

                # GEMINI_USE_FIXTURE 환경에서 fixture가 없어서 API 호출한 경우 → 저장
                if use_fixture and not os.path.exists(FIXTURE_FILE):
                    os.makedirs(FIXTURE_DIR, exist_ok=True)
                    with open(FIXTURE_FILE, 'w', encoding='utf-8') as f:
                        json.dump(issues_data, f, ensure_ascii=False, indent=2)
                    print(f"💾 [FIXTURE] Saved {len(issues_data)} issue(s) to fixture for future reuse.")
                return issues_data
            except Exception as e:
                error_msg = str(e).lower()
                if "429" in error_msg or "quota" in error_msg or "exhausted" in error_msg or "resource_exhausted" in error_msg:
                    print(f"❌ Rate limit hit: {e}")
                    if not self._rotate_key():      # 현재 모델 키 소진 → 모델 전환 시도
                        if not self._rotate_model():
                            break                   # 전체 소진 → 루프 탈출
                else:
                    print(f"❌ Error generating issues with Gemini: {e}")
                    return self._generate_fallback_issues(count) # 비quota 에러 시 폴백

        # 모든 모델/키 소진 시 더미 데이터로 폴백
        return self._generate_fallback_issues(count)

    def _generate_fallback_issues(self, count: int = 3):
        """API 한도 초과 시 로컬 테스트를 위해 하드코딩된 더미 문제를 반환합니다."""
        import random
        import os
        from datetime import datetime

        # 라이브 서버에서는 더미 데이터를 생성하지 않음 (단, Gemini 실패로 인한 4시간 공백을 막기 위해 활성화)
        # if os.environ.get('FLASK_ENV') == 'production':
        #     print("⚠️ Production mode: Fallback dummy generation disabled.")
        #     return None

        print(f"💡 [TEST/FALLBACK MODE] Falling back to {count} dummy issue(s) due to API limit or error.")

        close_utc_str = (datetime.now(timezone.utc) + timedelta(hours=4)).strftime('(UTC+0) %Y-%m-%d %H:%M')
        btc_price = random.randint(90000, 110000)
        aapl_price = random.randint(200, 250)
        dummy_pool = [
            {"title": f"Will Bitcoin exceed ${btc_price:,} by {close_utc_str}?", "category": "economy"},
            {"title": f"Will Tesla make an official AI product announcement by {close_utc_str}?", "category": "tech"},
            {"title": f"Will the Federal Reserve issue an emergency statement by {close_utc_str}?", "category": "economy"},
            {"title": f"Will OpenAI publish a new model announcement by {close_utc_str}?", "category": "tech"},
            {"title": f"Will Apple (AAPL) exceed ${aapl_price} between now and {close_utc_str}?", "category": "economy"},
        ]

        # count 개수만큼만 무작위로 뽑기
        selected_issues = random.sample(dummy_pool, min(count, len(dummy_pool)))
        return selected_issues

    def _translate_to_all_langs(self, text: str) -> dict:
        """
        구글 무료 번역 API를 서버에서 호출하여 7개 언어로 번역합니다.
        이슈 생성 시 1회만 호출 → DB 저장 → 이후 사용자별 호출 없음.
        대상 언어: ko, ja, de, fr, es, pt, zh
        """
        target_langs = ['ko', 'ja', 'de', 'fr', 'es', 'pt', 'zh']
        translations = {}

        for lang in target_langs:
            try:
                url = (
                    f"https://translate.googleapis.com/translate_a/single"
                    f"?client=gtx&sl=en&tl={lang}&dt=t"
                    f"&q={requests.utils.quote(text)}"
                )
                resp = requests.get(url, timeout=5)
                data = resp.json()
                translated = data[0][0][0]
                # 한국어: "(UTC+0) YYYY-MM-DD HH:MM" → "UTC 0시 기준 YYYY-MM-DD HH:MM"
                if lang == 'ko':
                    translated = translated.replace('(UTC+0)', 'UTC 0시 기준')
                translations[f'title_{lang}'] = translated
            except Exception as e:
                print(f"⚠️ Translation failed for lang={lang}: {e}")
                translations[f'title_{lang}'] = text  # 실패 시 원문 사용

        return translations

    def save_issues_to_db(self, issues_data):
        """
        생성된 이슈 데이터를 Supabase에 저장
        """
        if not supabase or not issues_data:
            return False

        saved_count = 0
        for data in issues_data:
            try:
                # 1. 이슈(Issue) 저장
                # 마감 시간 고정 (UTC 기준 생성 시각 +4시간)
                close_at = (datetime.now(timezone.utc) + timedelta(hours=4)).isoformat()

                # 2. 7개 언어 번역 수행 (서버에서 1회, 이후 DB에서 바로 제공)
                print(f"🌐 Translating issue title to 7 languages: {data['title'][:40]}...")
                translations = self._translate_to_all_langs(data['title'])

                # DB 저장 데이터 구성
                insert_data = {
                    'title': data['title'],
                    'category': data['category'],
                    'status': 'OPEN',
                    'close_at': close_at,
                    **translations  # title_ko, title_ja, title_de, title_fr, title_es, title_pt, title_zh
                }
                # RSS 뉴스 기사 링크 (source 컬럼이 DB에 있을 경우)
                source_url = data.get('source_url', '')
                if source_url:
                    insert_data['source'] = source_url

                issue_resp = supabase.table('issues').insert(insert_data).execute()

                if issue_resp.data:
                    issue_id = issue_resp.data[0]['id']

                    # 2. 옵션(Options) 저장 (Yes/No)
                    supabase.table('options').insert([
                        {'issue_id': issue_id, 'title': 'Yes'},
                        {'issue_id': issue_id, 'title': 'No'}
                    ]).execute()

                    saved_count += 1
            except Exception as e:
                print(f"❌ Error saving issue to DB: {e}")

        print(f"✅ Successfully saved {saved_count} issues to Supabase.")
        return saved_count > 0

gemini_service = GeminiService()
