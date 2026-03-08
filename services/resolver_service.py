import google.generativeai as genai
from config import config
from services.supabase_client import supabase
from datetime import datetime
import json

class ResolverService:
    def __init__(self):
        self.api_keys = config.GEMINI_API_KEYS
        self.current_key_idx = 0
        self.model = None
        self._setup_model()

    def _setup_model(self):
        if not self.api_keys:
            print("⚠️ GEMINI_API_KEYS is missing. ResolverService will not work.")
            return

        api_key = self.api_keys[self.current_key_idx]
        genai.configure(api_key=api_key)
        self.model = genai.GenerativeModel(
            'gemini-2.0-flash-lite',
            tools='google_search_retrieval'
        )
        print(f"🔄 Resolver Using Gemini API Key {self.current_key_idx + 1}/{len(self.api_keys)}")

    def _rotate_key(self):
        """API 키 한도 초과 시 다음 키로 교체"""
        if len(self.api_keys) <= 1:
            return False
            
        self.current_key_idx = (self.current_key_idx + 1) % len(self.api_keys)
        self._setup_model()
        return True

    def resolve_expired_issues(self):
        """
        마감 시간이 지났지만 아직 정답이 확정되지 않은(OPEN) 이슈들을 찾아 정답 처리함
        """
        if not supabase or not self.model:
            print("⚠️ DB or Gemini not connected.")
            return

        # 1. 마감된 OPEN 이슈 조회
        now = datetime.now().isoformat()
        resp = supabase.table('issues').select('*').eq('status', 'OPEN').lt('close_at', now).execute()
        issues = resp.data if resp.data else []

        if not issues:
            print("📅 No expired issues to resolve.")
            return

        for issue in issues:
            print(f"🧐 Resolving issue: {issue['title']}")
            self._resolve_single_issue(issue)

    def _resolve_single_issue(self, issue):
        """
        Gemini를 통해 단일 이슈의 실제 정답을 확인하고 결과 반영
        """
        prompt = f"""
        Prediction Issue: "{issue['title']}"
        Category: {issue['category']}
        
        Is this statement true based on real-world events that have occurred up to now?
        Provide the answer as 'Yes' or 'No' and a brief reason.
        Format output as valid JSON: {{"answer": "Yes" or "No", "reason": "..."}}
        """

        max_retries = len(self.api_keys)
        for attempt in range(max_retries):
            try:
                response = self.model.generate_content(prompt)
                text = response.text.strip()
                if "```json" in text:
                    text = text.split("```json")[1].split("```")[0].strip()
                
                result = json.loads(text)
                answer = result.get('answer') # 'Yes' or 'No'

                # 2. 정답 옵션 ID 조회
                opt_resp = supabase.table('options').select('id').eq('issue_id', issue['id']).eq('title', answer).single().execute()
                if not opt_resp.data:
                    print(f"❌ Option matching '{answer}' not found for issue {issue['id']}")
                    return

                correct_option_id = opt_resp.data['id']

                # 3. 이슈 상태 업데이트
                supabase.table('issues').update({
                    'status': 'RESOLVED',
                    'correct_option_id': correct_option_id,
                    'resolved_at': datetime.now().isoformat()
                }).eq('id', issue['id']).execute()

                # 4. 베팅 결과 처리 및 포인트 지급
                self._process_payouts(issue['id'], correct_option_id)
                print(f"✅ Successfully resolved: {issue['title']} -> {answer}")
                return # 성공 시 함수 종료

            except Exception as e:
                err_msg = str(e).lower()
                print(f"❌ Error resolving issue {issue['id']}: {e}")
                if "429" in err_msg or "quota" in err_msg or "exhausted" in err_msg:
                    print(f"⚠️ API Quota exhausted on key {self.current_key_idx + 1}. Attempting to rotate...")
                    if self._rotate_key():
                        continue
                break # 다른 에러거나 더 이상 로테이션 할 수 없으면 포기

    def _process_payouts(self, issue_id, correct_option_id):
        """
        정답을 맞춘 유저에게 +10점, 오답 유저에게 -10점 지급 (최소 0점 보장)
        """
        bets_resp = supabase.table('bets').select('*').eq('issue_id', issue_id).execute()
        bets = bets_resp.data if bets_resp.data else []

        for bet in bets:
            is_winner = str(bet['option_id']) == str(correct_option_id)
            new_status = 'WON' if is_winner else 'LOST'
            
            # 베팅 상태 업데이트
            supabase.table('bets').update({'status': new_status}).eq('id', bet['id']).execute()

            # 포인트 지급: 정답 +10점, 오답 -10점 (최소 0점)
            user_resp = supabase.table('users').select('points').eq('id', bet['user_id']).single().execute()
            if user_resp.data:
                current_pts = user_resp.data.get('points', 0)
                if is_winner:
                    new_pts = current_pts + 10
                else:
                    new_pts = max(0, current_pts - 10)
                supabase.table('users').update({'points': new_pts}).eq('id', bet['user_id']).execute()

resolver_service = ResolverService()
