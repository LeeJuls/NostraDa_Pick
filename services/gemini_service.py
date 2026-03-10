import google.generativeai as genai
from config import config
from services.supabase_client import supabase
from datetime import datetime, timedelta
import json
import requests  # 서버 측 번역 API 호출용

class GeminiService:
    def __init__(self):
        self.api_keys = config.GEMINI_API_KEYS
        self.current_key_idx = 0
        self.model = None
        self._setup_model()

    def _setup_model(self):
        if not self.api_keys:
            print("⚠️ GEMINI_API_KEYS is missing. GeminiService will not work.")
            return

        api_key = self.api_keys[self.current_key_idx]
        genai.configure(api_key=api_key)
        # 테스트를 위해 가장 최신이면서 할당량이 상대적으로 적은 경량 모델(2.0-flash-lite)로 변경
        self.model = genai.GenerativeModel(
            'gemini-2.0-flash-lite', 
            tools='google_search_retrieval'
        )
        print(f"🔄 Using Gemini API Key {self.current_key_idx + 1}/{len(self.api_keys)}")

    def _rotate_key(self):
        """API 키 한도 초과 시 다음 키로 교체"""
        if self.current_key_idx < len(self.api_keys) - 1:
            self.current_key_idx += 1
            print(f"⚠️ Quota exceeded. Rotating to Gemini API Key {self.current_key_idx + 1}/{len(self.api_keys)}...")
            self._setup_model()
            return True
        else:
            print("❌ All Gemini API keys have exhausted their quota.")
            return False

    def generate_trending_issues(self, count: int = 3):
        """
        Gemini를 이용해 실시간 트렌드 기반 예측 이슈 생성
        """
        if not self.model:
            return None

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

        now_str = datetime.now().strftime('%Y-%m-%d')
        
        # 타겟 주제가 있을 경우 프롬프트 강화
        target_focus_prompt = ""
        if target_topics:
            target_focus_prompt = f"""
            CRITICAL TARGET TOPICS TO INCLUDE:
            You MUST focus heavily on these specific trending topics or keywords: [{target_topics}].
            At least 1 to {count} generated prediction issues MUST be directly related to these topics.
            """

        prompt = f"""
        You are a top-tier analyst for a prediction market app 'NostraDa_Pick'.
        Today is {now_str}.
        CRITICAL: YOU MUST USE THE GOOGLE SEARCH TOOL to find the ABSOLUTE LATEST BREAKING NEWS today (e.g., major wars like US-Iran, stock market crashes, breaking political scandals, massive sports upsets). 
        Do not use old data. Create questions based ONLY on what is happening right now today.
        
        Generate {count} diverse, high-interest prediction issues based on CURRENT real-world trending news.
        {target_focus_prompt}
        {exclusion_text}
        
        Rules:
        1. Each issue must be a Yes/No question about a FUTURE event (e.g., matching results, stock price targets, policy changes).
        2. Provide exactly 2 options: 'Yes' and 'No'.
        3. Format the output as a JSON array of objects with these keys:
           - title: The prediction question (e.g., 'Will Bitcoin reach $100k by tomorrow?')
           - category: One of [economy, sports, politics, tech, etc]
           - hours_to_close: Integer, how many hours until the voting ends (MIN 1, MAX 6).
        
        Output only valid JSON.
        """

        max_retries = len(self.api_keys) if self.api_keys else 1
        for attempt in range(max_retries):
            try:
                response = self.model.generate_content(prompt)
                # JSON 파싱 (Gemini 응답에서 ```json ... ``` 부분 추출 대처)
                text = response.text.strip()
                if "```json" in text:
                    text = text.split("```json")[1].split("```")[0].strip()
                
                issues_data = json.loads(text)
                return issues_data
            except Exception as e:
                error_msg = str(e).lower()
                if "429" in error_msg or "quota" in error_msg or "exhausted" in error_msg:
                    print(f"❌ Rate limit hit (429): {e}")
                    if self._rotate_key():
                        continue
                    else:
                        break
                else:
                    print(f"❌ Error generating issues with Gemini: {e}")
                    return self._generate_fallback_issues(count) # 에러 시 폴백
                    
        # 모든 키가 한도를 초과하여 루프를 빠져나왔을 때 로컬 환경용 더미 생성
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
        
        dummy_pool = [
            {"title": f"Will Bitcoin reach ${random.randint(90000, 110000)} by tomorrow?", "category": "economy", "hours_to_close": 4},
            {"title": "Will Tesla announce a new AI product before the week ends?", "category": "tech", "hours_to_close": 4},
            {"title": "Will the Federal Reserve announce an emergency rate cut tonight?", "category": "economy", "hours_to_close": 4},
            {"title": "Will OpenAI unveil GPT-5 features this weekend?", "category": "tech", "hours_to_close": 4},
            {"title": f"Will Apple stock exceed ${random.randint(200, 250)} by today's market close?", "category": "economy", "hours_to_close": 4}
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
                # 마감 시간 고정 (무조건 생성 시간으로부터 +4시간)
                close_at = (datetime.now() + timedelta(hours=4)).isoformat()

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
