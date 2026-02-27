import google.generativeai as genai
from config import config
from services.supabase_client import supabase
from datetime import datetime
import json

class ResolverService:
    def __init__(self):
        self.api_key = config.GEMINI_API_KEY
        if self.api_key:
            genai.configure(api_key=self.api_key)
            self.model = genai.GenerativeModel('gemini-pro-latest')
        else:
            self.model = None

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

        except Exception as e:
            print(f"❌ Error resolving issue {issue['id']}: {e}")

    def _process_payouts(self, issue_id, correct_option_id):
        """
        정답을 맞춘 유저들에게 1포인트씩 지급
        """
        bets_resp = supabase.table('bets').select('*').eq('issue_id', issue_id).execute()
        bets = bets_resp.data if bets_resp.data else []

        for bet in bets:
            is_winner = str(bet['option_id']) == String(correct_option_id) # Comparison fix needed in logic below
            # Python comparison should be direct
            is_winner = str(bet['option_id']) == str(correct_option_id)

            new_status = 'WON' if is_winner else 'LOST'
            
            # 베팅 상태 업데이트
            supabase.table('bets').update({'status': new_status}).eq('id', bet['id']).execute()

            if is_winner:
                # 포인트 지급 (+1)
                user_resp = supabase.table('users').select('points').eq('id', bet['user_id']).single().execute()
                if user_resp.data:
                    current_pts = user_resp.data.get('points', 0)
                    supabase.table('users').update({'points': current_pts + 1}).eq('id', bet['user_id']).execute()

resolver_service = ResolverService()
