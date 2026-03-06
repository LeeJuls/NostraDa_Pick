import google.generativeai as genai
from config import config
from services.supabase_client import supabase
from datetime import datetime, timedelta
import json

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

        now_str = datetime.now().strftime('%Y-%m-%d')
        prompt = f"""
        You are a top-tier analyst for a prediction market app 'NostraDa_Pick'.
        Today is {now_str}.
        CRITICAL: YOU MUST USE THE GOOGLE SEARCH TOOL to find the ABSOLUTE LATEST BREAKING NEWS today (e.g., major wars like US-Iran, stock market crashes, breaking political scandals, massive sports upsets). 
        Do not use old data. Create questions based ONLY on what is happening right now today.
        
        Generate {count} diverse, high-interest prediction issues based on CURRENT real-world trending news.
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
                
                issue_resp = supabase.table('issues').insert({
                    'title': data['title'],
                    'category': data['category'],
                    'status': 'OPEN',
                    'close_at': close_at
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
