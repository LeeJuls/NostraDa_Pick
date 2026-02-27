import google.generativeai as genai
from config import config
from services.supabase_client import supabase
from datetime import datetime, timedelta
import json

class GeminiService:
    def __init__(self):
        self.api_key = config.GEMINI_API_KEY
        if self.api_key:
            genai.configure(api_key=self.api_key)
            # 최신 모델 사용 (사용자 설정에 따라 2.0 pro 등 선택 가능)
            self.model = genai.GenerativeModel('gemini-pro-latest')
        else:
            self.model = None
            print("⚠️ GEMINI_API_KEY is missing. GeminiService will not work.")

    def generate_trending_issues(self):
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

        prompt = f"""
        You are a top-tier analyst for a prediction market app 'NostraDa_Pick'.
        Generate 3 diverse, high-interest prediction issues based on CURRENT real-world trending news (Sports, Economy, Politics, Tech).
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

        try:
            response = self.model.generate_content(prompt)
            # JSON 파싱 (Gemini 응답에서 ```json ... ``` 부분 추출 대처)
            text = response.text.strip()
            if "```json" in text:
                text = text.split("```json")[1].split("```")[0].strip()
            
            issues_data = json.loads(text)
            return issues_data
        except Exception as e:
            print(f"❌ Error generating issues with Gemini: {e}")
            return None

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
