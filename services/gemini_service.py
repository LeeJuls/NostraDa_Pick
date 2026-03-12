import google.generativeai as genai
from config import config
from services.supabase_client import supabase
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
        now_utc_str   = now_utc.strftime('%Y-%m-%d %H:%M UTC')
        close_utc_str = close_utc.strftime('%Y-%m-%d %H:%M UTC')
        today_date    = now_utc.strftime('%Y-%m-%d')

        # 타겟 주제가 있을 경우 프롬프트 강화
        target_focus_prompt = ""
        if target_topics:
            target_focus_prompt = (
                f"FOCUS TOPICS: You MUST include at least 1 question directly related to: [{target_topics}]."
            )

        prompt = f"""You are an analyst for a real-time prediction market app 'NostraDa_Pick'.

Current UTC time : {now_utc_str}
Voting closes at : {close_utc_str}

Generate {count} diverse, high-interest prediction issues based on REAL-WORLD events.
{target_focus_prompt}
{exclusion_text}

=== STRICT RULES ===

[FUTURE ONLY]
- Only generate questions about events DEFINITIVELY occurring AFTER {now_utc_str}.
- Do NOT use any event that occurred before {today_date}, or any event from 2025 or earlier.
- If you are not 100% certain an event is still in the future, SKIP IT.

[ABSOLUTE UTC TIME — MANDATORY]
- ALL time references in question titles MUST use absolute UTC format.
  CORRECT  : "by {close_utc_str}", "by 2026-03-13 06:00 UTC"
  FORBIDDEN: "tomorrow", "tonight", "today", "by end of day",
             "by end of session", "within X hours", "오늘", "내일"
- Market/price references must also use absolute UTC open/close times:
  CORRECT  : "between {now_utc_str} and {close_utc_str}"
  FORBIDDEN: "today's opening price", "by end of trading session", "today's open"

[RESOLVABLE BY CLOSE TIME]
- The event must have a clear, publicly verifiable Yes/No answer by {close_utc_str}.
- Do NOT create questions whose natural deadline exceeds {close_utc_str}.

=== OUTPUT FORMAT ===
Return a JSON array. Each object must have:
  "title"    : prediction question string (must contain absolute UTC deadline)
  "category" : one of [economy, sports, politics, tech, entertainment, world]

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
        
        close_utc_str = (datetime.now(timezone.utc) + timedelta(hours=4)).strftime('%Y-%m-%d %H:%M UTC')
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

                issue_resp = supabase.table('issues').insert({
                    'title': data['title'],
                    'category': data['category'],
                    'status': 'OPEN',
                    'close_at': close_at,
                    **translations  # title_ko, title_ja, title_de, title_fr, title_es, title_pt, title_zh
                }).execute()
                
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
