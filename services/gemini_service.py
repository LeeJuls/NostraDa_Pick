import google.generativeai as genai
from config import config
from services.supabase_client import supabase
from services.sports_schedule_service import get_all_sports_matches, build_match_context
from services.news_feed_service import fetch_news_headlines, build_news_context
from services.stock_price_service import fetch_stock_prices, build_stock_context
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

    def _resolve_source_url(
        self,
        issue_title: str,
        headlines: list[dict],
        matches: list[dict],
        prices: list[dict],
    ) -> str:
        """
        이슈 제목에 맞는 실제 URL을 우선순위에 따라 반환:
          1. 스포츠 경기  → Google 검색 URL (match.search_url)
          2. 주가/암호화폐/원자재 → Yahoo Finance URL
          3. 뉴스 기반    → RSS 헤드라인 키워드 매칭
        """
        import re
        title_lower = issue_title.lower()

        # ── 1. 스포츠 경기 매칭 ───────────────────────────────────────────────
        skip_words = {'fc', 'sc', 'ac', 'cf', 'united', 'city', 'sporting'}
        for match in matches:
            for side in ('home', 'away'):
                name_words = [
                    w for w in match.get(side, '').lower().split()
                    if len(w) > 3 and w not in skip_words
                ]
                if any(w in title_lower for w in name_words):
                    return match.get('search_url', '')

        # ── 2. 주가 / 암호화폐 / 원자재 → Yahoo Finance ───────────────────────
        # 지수/원자재처럼 label만으로 잡기 어려운 종목을 위한 키워드 별칭
        TICKER_ALIASES = {
            "^GSPC":    ["s&p 500", "s&p500"],
            "^IXIC":    ["nasdaq composite", "nasdaq"],
            "^DJI":     ["dow jones", "djia"],
            "^VIX":     ["vix"],
            "GC=F":     ["gold"],
            "CL=F":     ["crude oil", "wti"],
            "SI=F":     ["silver"],
            "NG=F":     ["natural gas"],
            "EURUSD=X": ["eur/usd", "euro"],
            "JPY=X":    ["usd/jpy", "yen"],
            "GBPUSD=X": ["gbp/usd"],
            "^N225":    ["nikkei"],
            "^FTSE":    ["ftse"],
            "^HSI":     ["hang seng"],
        }
        # 별칭 먼저 체크 (정확한 문자열 포함 여부)
        for ticker, aliases in TICKER_ALIASES.items():
            if any(alias in title_lower for alias in aliases):
                return self._yahoo_finance_url(ticker)

        for p in prices:
            ticker = p.get('ticker', '')
            label  = p.get('label', '').lower()  # e.g. "bitcoin (btc)"

            # 레이블 첫 단어 매칭: "bitcoin", "nvidia" 등 — 최소 4글자 이상만 허용
            main_name = label.split()[0] if label else ''
            if main_name and len(main_name) >= 4 and main_name in title_lower:
                return self._yahoo_finance_url(ticker)

            # 괄호 안 심볼 매칭: 이슈 제목에도 "(BTC)", "(NVDA)" 형태로 있어야 함
            # → 단순 substr 대신 괄호 안 심볼이 제목에도 괄호 안에 있는 경우만 허용
            sym_match = re.search(r'\(([^)]{2,})\)', label)  # 2글자 이상 심볼만
            if sym_match:
                sym = sym_match.group(1).lower()
                if f'({sym})' in title_lower:
                    return self._yahoo_finance_url(ticker)

        # ── 3. RSS 헤드라인 키워드 매칭 ──────────────────────────────────────
        if not headlines:
            return ''

        stopwords = {
            'will', 'the', 'a', 'an', 'is', 'are', 'be', 'at', 'in', 'on',
            'by', 'of', 'to', 'and', 'or', 'for', 'from', 'with', 'its',
            'has', 'have', 'had', 'not', 'no', 'new', 'as', 'than', 'that',
            'this', 'it', 'more', 'above', 'below', 'over', 'after', 'before',
        }

        def tokenize(text):
            return set(re.sub(r'[^a-z0-9 ]', ' ', text.lower()).split()) - stopwords

        issue_words = tokenize(issue_title)
        best_score, best_url = 0, ''
        for h in headlines:
            overlap = len(issue_words & tokenize(h.get('title', '')))
            if overlap > best_score:
                best_score = overlap
                best_url = h.get('link', '')

        return best_url if best_score >= 2 else ''

    def generate_trending_issues(self, count: int = 3):
        """
        Gemini를 이용해 실시간 트렌드 기반 예측 이슈 생성
        GEMINI_USE_FIXTURE=true 이면 로컬 fixture JSON을 우선 사용해 API 호출 절약
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

        # 기존에 생성된 문제 제목들을 DB에서 가져와 중복 방지 [GA]
        existing_titles = []
        try:
            if supabase:
                resp = supabase.table('issues').select('title').execute()
                if resp.data:
                    existing_titles = [item['title'] for item in resp.data]
        except Exception as e:
            print(f"⚠️ Could not fetch existing issues for deduplication: {e}")

        exclusion_text = ""
        if existing_titles:
            exclusion_text = "\nCRITICAL RULE: DO NOT generate any questions that are similar to the following existing questions:\n"
            exclusion_text += "\n".join([f"- {title}" for title in existing_titles[-20:]]) # 최근 20개만 제한

        # DB에서 어드민이 설정한 타겟 주제(target_topics) 가져오기
        target_topics = ""
        try:
            if supabase:
                resp = supabase.table('app_settings').select('value').eq('key', 'target_topics').execute()
                if resp.data and resp.data[0].get('value'):
                    target_topics = resp.data[0]['value'].strip()
        except Exception as e:
            print(f"⚠️ Could not fetch target_topics from app_settings: {e}")

        # UTC 기준 현재 시각 및 마감 시각 (close_at과 동일한 +4h 기준)
        now_utc       = datetime.now(timezone.utc)
        close_utc     = now_utc + timedelta(hours=4)
        now_utc_str      = now_utc.strftime('(UTC+0) %Y-%m-%d %H:%M')
        close_utc_str    = close_utc.strftime('(UTC+0) %Y-%m-%d %H:%M')
        max_event_utc_str = (now_utc + timedelta(hours=48)).strftime('(UTC+0) %Y-%m-%d %H:%M')
        max_price_utc_str = (now_utc + timedelta(hours=24)).strftime('(UTC+0) %Y-%m-%d %H:%M')
        today_date        = now_utc.strftime('%Y-%m-%d')

        # 타겟 주제가 있을 경우 프롬프트 강화
        target_focus_prompt = ""
        if target_topics:
            target_focus_prompt = (
                f"FOCUS TOPICS: You MUST include at least 1 question directly related to: [{target_topics}]."
            )

        # 실제 경기 일정 가져오기: 축구(football-data.org) + NBA/MLB(api-sports.io)
        all_matches   = get_all_sports_matches(hours_ahead=48)
        match_context = build_match_context(all_matches)

        # 실제 뉴스 헤드라인 가져오기: CNN/BBC/Reuters 등 RSS 피드
        news_headlines = fetch_news_headlines(max_per_feed=5, max_age_hours=48)
        news_context   = build_news_context(news_headlines)

        # 실시간 주가/암호화폐 현재가 가져오기
        stock_prices  = fetch_stock_prices()
        stock_context = build_stock_context(stock_prices)

        sports_rule = (
            "[SPORTS — USE SCHEDULE BELOW ONLY]\n"
            "- For match result / winner / score questions, ONLY use matches listed in TODAY'S SPORTS SCHEDULE.\n"
            "- Do NOT invent match schedules from your training data.\n"
            "- If no matches are listed, do NOT generate sports match questions."
            if all_matches else
            "[SPORTS — NO VERIFIED SCHEDULE]\n"
            "- No verified match schedule available. Do NOT generate sports match questions.\n"
            "- Only use non-match sports questions (standings, rankings, awards)."
        )

        prompt = f"""You are an analyst for a real-time prediction market app 'NostraDa_Pick'.

TIMEZONE BASELINE: All times are UTC+0 (UTC). Do NOT use KST, EST, JST or any other local timezone.
Current UTC+0 time : {now_utc_str}
Voting closes at   : {close_utc_str}

{match_context}

{news_context}

{stock_context}

Generate {count} diverse, high-interest prediction issues based on the REAL NEWS HEADLINES provided above.
{target_focus_prompt}
{exclusion_text}

=== STRICT RULES ===

[NEWS-BASED QUESTIONS — MANDATORY]
- You MUST base your questions on the RECENT NEWS HEADLINES provided above.
- Each question should be inspired by a real, current news event from the headlines.
- Do NOT invent events that are not in the news headlines or today's sports schedule.
- If a headline is about a past event, create a FORWARD-LOOKING prediction about what happens next.

[SOURCE URL — MUST MATCH THE QUESTION]
- Include the "source_url" field with the exact URL of the news headline that inspired the question.
- The source_url MUST be directly relevant to the question topic.
  ❌ BAD : A question about PEC Zwolle match linking to an article about Aston Villa
  ✅ GOOD: A question about Bitcoin linking to a CoinDesk article about Bitcoin
- For sports match questions based on the SPORTS SCHEDULE, use the "search:" URL provided next to that match in the schedule.
  Do NOT grab a random sports news link — use the search URL from the schedule data.

[POLITICS & WORLD — HIGH-CREDIBILITY SOURCES ONLY]
- For "politics" and "world" category questions, you MUST only use headlines marked
  with [BBC], [Reuters], [The New York Times], [AP News], [The Guardian], or similar
  tier-1 wire/broadcast sources from the NEWS HEADLINES section above.
- Do NOT base politics/world questions on CNN, TechCrunch, CoinDesk, ESPN, CNBC, or
  any source not listed above.
- The sections [WORLD] and [POLITICS] in the headlines are labeled
  "← HIGH-CREDIBILITY SOURCES ONLY" — use ONLY those.
- If no high-credibility headline is available for politics/world, skip that category
  and pick a different one (tech, economy, sports, etc.).

[VERIFIABLE EVENTS ONLY]
- Do NOT reference investigations, reports, or statements that you cannot verify from the provided news.
- If you are not 100% certain an event/investigation/statement exists, SKIP IT.

[OBJECTIVELY MEASURABLE — MANDATORY]
- Every question MUST have a clear, objective YES/NO criterion that anyone can verify.
- The answer must be determinable by checking a single public data point (price, score, official statement, etc.).
  ❌ BAD : "Will polling show a shift?" (what counts as a "shift"? 0.1%? 5%?)
  ❌ BAD : "Will news coverage indicate change?" (subjective — who decides?)
  ❌ BAD : "Will market sentiment improve?" (unmeasurable)
  ❌ BAD : "Will tensions escalate?" (vague, no clear threshold)
  ✅ GOOD: "Will Bitcoin (BTC) price exceed $75,000?" (exact number, checkable)
  ✅ GOOD: "Will Trump post about tariffs on Truth Social?" (yes/no, verifiable)
  ✅ GOOD: "Will PEC Zwolle score 2+ goals?" (exact number, match result)
  ✅ GOOD: "Will the S&P 500 close above 5,800?" (exact number, checkable)
- If the question involves a change/shift/increase/decrease, specify the EXACT threshold number.

{sports_rule}

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
  ❌ BAD : Match scheduled on 2026-03-17 (5 days away)
  ✅ GOOD: Event occurring before {max_event_utc_str}

[PRICE/MARKET QUESTIONS — 24 HOURS MAX]
- For price or market-based questions (crypto, stocks, forex, indices, commodities),
  the check time MUST be within 24 hours: no later than {max_price_utc_str}.
  ❌ BAD : "Will BTC exceed $115,000 at (UTC+0) 2026-03-14 09:00?" (46 hours away)
  ✅ GOOD: "Will BTC exceed $85,000 at (UTC+0) {max_price_utc_str}?" (within 24 hours)

[PRICE THRESHOLD — MUST BE GENUINELY UNCERTAIN]
- The price threshold MUST be set close to the CURRENT market price (from CURRENT MARKET PRICES above).
- The threshold must be within ±5% of the current price listed above.
  ❌ BAD : NVDA current $183 → asking "Will NVDA close above $140?" (obviously YES — too easy)
  ❌ BAD : BTC current $83,000 → asking "Will BTC exceed $120,000?" (obviously NO — too hard)
  ✅ GOOD: NVDA current $183 → asking "Will NVDA close above $180?" (genuinely uncertain ±2%)
  ✅ GOOD: BTC current $83,000 → asking "Will BTC stay above $82,000?" (genuinely uncertain ±1%)
- If a ticker is NOT listed in CURRENT MARKET PRICES, do NOT invent a price — skip that question.

[MINIMUM DEADLINE — NEWS-BASED QUESTIONS]
- For politics, world, and economy news-based questions (NOT sports or price checks),
  the deadline MUST be at least 24 hours from now (no earlier than {max_price_utc_str}).
  ❌ BAD : "Will the UK government announce X by (UTC+0) 2026-03-13 08:35?" (only 4 hours away)
  ❌ BAD : "Will the US issue a statement by (UTC+0) 2026-03-13 09:00?" (too soon — governments take days)
  ✅ GOOD: "Will the UK government announce X by (UTC+0) 2026-03-14 18:00?" (≥24 hours)
  ✅ GOOD: "Will the US Senate pass the bill by (UTC+0) 2026-03-15 00:00?" (≥24 hours)
- Sports match questions may use the actual kick-off/game time as deadline.
- Price/market questions follow the [PRICE/MARKET QUESTIONS] rule (within 24 hours).

[ANSWER NOT ALREADY KNOWN — MANDATORY]
- Do NOT create a question whose answer can already be determined from the provided source article.
  ❌ BAD : Source says "at least 17 killed" → asking "Will death toll exceed 20?" (17 is already reported; 20 is likely NO)
  ❌ BAD : Source says "Fed raises rates by 0.5%" → asking "Will the Fed raise rates?" (already happened)
  ❌ BAD : Source says "Company X files for bankruptcy" → asking "Will Company X file for bankruptcy?"
  ✅ GOOD: Source reports first RSF drone strike on a school → asking "Will RSF carry out another drone strike on a civilian target in Sudan within 48 hours?"
  ✅ GOOD: Source says "17 killed in Sudan strike" → asking "Will the UN Security Council hold an emergency session on Sudan by X?"
- The question must be about something that is GENUINELY UNKNOWN at the time of writing.
  If the source article already answers the question, SKIP IT and choose a different angle.

[DEATH TOLL / CASUALTY COUNT — SPECIAL RULE]
- NEVER ask "Will the death toll/casualty count from [existing incident] exceed [any number]?"
  These questions are almost always answerable from the source → answer is obvious → not genuinely uncertain.
  ❌ FORBIDDEN: "Will the death toll from the Sudan strike exceed 20?" (source says 17; clearly close to final)
  ❌ FORBIDDEN: "Will the confirmed fatalities from [event] surpass [N]?"
- Instead, ask about the NEXT event, ESCALATION, or OFFICIAL RESPONSE:
  ✅ "Will RSF carry out another drone attack on a civilian area in Sudan by X?" (genuinely uncertain follow-up)
  ✅ "Will the UN Security Council convene an emergency session on Sudan by X?" (forward-looking)
  ✅ "Will the Sudanese government declare a national state of emergency by X?" (forward-looking)

[CATEGORY — STOCK PRICE QUESTIONS MUST BE ECONOMY]
- Questions asking about a stock price, crypto price, commodity price, or index level
  MUST use the "economy" category — regardless of which company or sector it is.
  ❌ BAD : NVDA price question → category "tech"
  ❌ BAD : Apple stock → category "tech"
  ❌ BAD : Oil price → category "world"
  ✅ GOOD: NVDA price question → category "economy"
  ✅ GOOD: Bitcoin price → category "economy"
  ✅ GOOD: S&P 500 level → category "economy"
- Use "tech" ONLY for product launches, software releases, company strategies, tech news — NOT for stock prices.

[SPECIFIC & NAMED ENTITIES — MANDATORY]
- Every question MUST name the specific real-world entity involved.
  ❌ BAD : "Will the official press release confirm a delay in next-gen AI hardware?"
  ❌ BAD : "Will the legislative vote pass with a simple majority?"
  ❌ BAD : "Will the government policy announcement mention renewable energy?"
  ✅ GOOD: "Will NVIDIA's GTC 2026 keynote confirm a delay in the Blackwell Ultra GPU launch?"
  ✅ GOOD: "Will the U.S. Senate vote on the Clean Energy Act pass by (UTC+0) 2026-03-14 08:00?"
  ✅ GOOD: "Will Bitcoin (BTC) exceed $115,000 at (UTC+0) 2026-03-14 09:00?"
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
  ❌ FORBIDDEN: "Will Netflix announce Squid Game Season 2 release date?"
  ❌ FORBIDDEN: "Will Apple announce a new iPhone at the event?"
  ✅ ALLOWED  : viewership ratings, box office numbers, awards, streaming rankings

[BANNED QUESTION PATTERNS — NEVER USE THESE]
- The following question patterns are FORBIDDEN because the judgment criterion is subjective or unmeasurable:
  ❌ "Will [entity] issue an official response/statement about X?"
     → What counts as "official"? A tweet? A press briefing? A parliamentary speech? Unmeasurable.
  ❌ "Will [entity] announce a formal response/position on X?"
     → Same problem — "formal" and "response" have no objective definition.
  ❌ "Will [entity] address/comment on X publicly?"
     → A single background briefing could count — completely subjective.
  ❌ "Will [entity] face X?" (e.g., "face more resignations", "face criticism", "face pressure")
     → Outcome depends on who decides what "facing" means.
  ❌ "Will news coverage/reports confirm X?"
     → We're betting on real events, not on media coverage of events.
  ❌ "Will [entity] take action on X?" / "Will [entity] respond to X?"
     → Vague — any minor action could satisfy this criterion.
- Instead, ask about SPECIFIC, VERIFIABLE actions with indisputable YES/NO outcomes:
  ✅ "Will UK PM Keir Starmer make a formal statement in Parliament about the Mandelson affair by X?"
     (verifiable: UK Hansard / official parliamentary record)
  ✅ "Will Peter Mandelson resign as UK ambassador to the US by X?"
     (verifiable: official government press release)
  ✅ "Will the UK Labour Party's approval rating drop below 30% in a YouGov poll published by X?"
     (verifiable: specific published poll with a number)

[CATEGORY DIVERSITY — MAX 2 PER CATEGORY]
- Among the {count} questions, NO single category may appear more than 2 times.
  ❌ BAD : 3 economy questions out of 4
  ✅ GOOD: 2 economy + 1 tech + 1 sports
- Use diverse categories from: economy, sports, politics, tech, entertainment, world

=== OUTPUT FORMAT ===
Return a JSON array. Each object must have:
  "title"      : prediction question string (must contain absolute UTC deadline)
  "category"   : one of [economy, sports, politics, tech, entertainment, world]
  "source_url" : URL of the news article this question is based on (from provided headlines)

Output only valid JSON, no markdown fences.
"""

        # 모델 수 × 키 수만큼 최대 재시도 (모델 로테이션 포함)
        max_retries = len(FALLBACK_MODELS) * max(len(self.api_keys), 1)
        for attempt in range(max_retries):
            try:
                response = self.model.generate_content(prompt)
                # JSON 파싱 (Gemini 응답에서 ```json ... ``` 부분 추출 대처)
                text = response.text.strip()
                if "```json" in text:
                    text = text.split("```json")[1].split("```")[0].strip()

                issues_data = json.loads(text)
                # 카테고리 다양성 검증: 동일 카테고리 최대 2개까지만
                from collections import Counter
                cat_count = Counter()
                filtered = []
                for issue in issues_data:
                    cat = issue.get('category', '')
                    if cat_count[cat] < 2:
                        filtered.append(issue)
                        cat_count[cat] += 1
                issues_data = filtered

                # ── Gemini의 hallucinated source_url → 실제 URL로 교체 ──────────
                # 우선순위: 스포츠 Google검색 > Yahoo Finance > RSS 헤드라인
                for issue in issues_data:
                    real_url = self._resolve_source_url(
                        issue.get('title', ''),
                        news_headlines,
                        all_matches,
                        stock_prices,
                    )
                    issue['source_url'] = real_url  # 매칭 실패 시 빈 문자열 (링크 미표시)

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
