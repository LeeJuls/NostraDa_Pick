import google.generativeai as genai
from config import config
from services.supabase_client import supabase
from services.gemini_service import FALLBACK_MODELS
from datetime import datetime, timezone
import json
import time

MAX_AGE_HOURS = 48   # 이 시간 초과한 이슈는 배치 채점으로 처리
BATCH_CHUNK_SIZE = 50  # 배치 1회 프롬프트 당 최대 이슈 수

class ResolverService:
    def __init__(self):
        self.api_keys = config.GEMINI_API_KEYS
        self.current_key_idx = 0
        self.current_model_idx = 0
        self.model = None
        self._setup_model()

    def _setup_model(self):
        if not self.api_keys:
            print("⚠️ GEMINI_API_KEYS is missing. ResolverService will not work.")
            return

        model_name = FALLBACK_MODELS[self.current_model_idx % len(FALLBACK_MODELS)]
        api_key = self.api_keys[self.current_key_idx]
        genai.configure(api_key=api_key)
        self.model = genai.GenerativeModel(model_name)
        print(f"🔄 Resolver model={model_name}, key={self.current_key_idx + 1}/{len(self.api_keys)}")

    def _rotate_key(self):
        """API 키 또는 모델 로테이션 (generator와 동일 방식)"""
        if self.current_key_idx < len(self.api_keys) - 1:
            self.current_key_idx += 1
            print(f"⚠️ Rotating to key {self.current_key_idx + 1}/{len(self.api_keys)}...")
            self._setup_model()
            return True
        elif self.current_model_idx < len(FALLBACK_MODELS) - 1:
            self.current_model_idx += 1
            self.current_key_idx = 0
            print(f"🔁 Rotating to next model: {FALLBACK_MODELS[self.current_model_idx]}")
            self._setup_model()
            return True
        else:
            print("❌ All Gemini models and API keys exhausted.")
            return False

    def resolve_expired_issues(self):
        """마감된 OPEN 이슈를 채점:
        - 48h 이내: 개별 Gemini 호출 (정확도 우선)
        - 48h 초과: 배치 Gemini 호출 (1회로 한꺼번에 처리)
        """
        if not supabase or not self.model:
            print("⚠️ DB or Gemini not connected.")
            return

        now = datetime.now(timezone.utc)
        resp = supabase.table('issues').select('*').eq('status', 'OPEN').lt('close_at', now.isoformat()).execute()
        issues = resp.data if resp.data else []

        if not issues:
            print("📅 No expired issues to resolve.")
            return

        print(f"📋 Found {len(issues)} expired issue(s) to resolve.")

        old_issues = []
        fresh_issues = []
        for issue in issues:
            close_at_str = issue['close_at'].replace('Z', '+00:00')
            close_at = datetime.fromisoformat(close_at_str)
            age_hours = (now - close_at).total_seconds() / 3600
            if age_hours > MAX_AGE_HOURS:
                old_issues.append(issue)
            else:
                fresh_issues.append(issue)

        print(f"  → 48h 초과(배치): {len(old_issues)}개 | 48h 이내(개별): {len(fresh_issues)}개")

        # 오래된 이슈 → 배치 채점
        if old_issues:
            self._resolve_batch(old_issues)

        # 최근 이슈 → 개별 채점
        for i, issue in enumerate(fresh_issues):
            print(f"🧐 [{i+1}/{len(fresh_issues)}] Resolving: {issue['title'][:60]}")
            self._resolve_single_issue(issue)
            if i < len(fresh_issues) - 1:
                time.sleep(6)

    def _resolve_batch(self, issues: list):
        """여러 이슈를 하나의 Gemini 호출로 채점. BATCH_CHUNK_SIZE개씩 청크 분할."""
        total = len(issues)
        print(f"📦 Batch resolving {total} old issues ({BATCH_CHUNK_SIZE}/chunk)...")

        for chunk_start in range(0, total, BATCH_CHUNK_SIZE):
            chunk = issues[chunk_start:chunk_start + BATCH_CHUNK_SIZE]
            chunk_label = f"[{chunk_start+1}~{chunk_start+len(chunk)}/{total}]"
            print(f"  Chunk {chunk_label}")

            lines = []
            for idx, issue in enumerate(chunk):
                lines.append(
                    f'[{idx}] created={issue["created_at"][:10]}, '
                    f'closed={issue["close_at"][:10]}\n'
                    f'     "{issue["title"]}"'
                )

            prompt = (
                "You are a factual judge. For each prediction question below, "
                "answer Yes or No based on real-world events that occurred up to the close date.\n\n"
                + "\n".join(lines)
                + f"\n\nReturn ONLY a JSON array (no explanation, no markdown):\n"
                  f'[{{"index": 0, "answer": "Yes"}}, {{"index": 1, "answer": "No"}}, ...]\n'
                  f"Include ALL {len(chunk)} items."
            )

            results = self._call_gemini_with_retry(prompt)
            if results is None:
                print(f"  ❌ Batch chunk {chunk_label} failed. Skipping.")
                continue

            # 파싱된 결과 적용
            answer_map = {}
            if isinstance(results, list):
                for r in results:
                    if isinstance(r, dict) and 'index' in r and 'answer' in r:
                        answer_map[int(r['index'])] = r['answer']

            for idx, issue in enumerate(chunk):
                answer = answer_map.get(idx)
                if answer not in ('Yes', 'No'):
                    print(f"  ⚠️ No valid answer for index {idx}: {issue['title'][:50]}")
                    continue
                self._apply_resolution(issue, answer)

            # 청크 간 대기 (rate limit 방지)
            if chunk_start + BATCH_CHUNK_SIZE < total:
                time.sleep(10)

    def _call_gemini_with_retry(self, prompt: str):
        """Gemini 호출 + rate limit 시 키/모델 로테이션 재시도. 파싱된 객체 반환."""
        max_attempts = len(self.api_keys) * len(FALLBACK_MODELS)
        for attempt in range(max_attempts):
            try:
                response = self.model.generate_content(prompt)
                text = response.text.strip()
                # 마크다운 코드블록 제거
                if "```" in text:
                    text = text.split("```")[1]
                    if text.startswith("json"):
                        text = text[4:]
                    text = text.strip()
                return json.loads(text)
            except Exception as e:
                err_msg = str(e).lower()
                print(f"  ❌ Gemini error: {e}")
                if "429" in err_msg or "quota" in err_msg or "exhausted" in err_msg:
                    print(f"  ⚠️ Rate limit. Waiting 60s...")
                    time.sleep(60)
                    if not self._rotate_key():
                        break
                else:
                    break
        return None

    def _resolve_single_issue(self, issue):
        """단일 이슈 Gemini 채점."""
        prompt = (
            f'Prediction Issue: "{issue["title"]}"\n'
            f'Category: {issue["category"]}\n\n'
            f'Created: {issue["created_at"]} (UTC), Closed: {issue["close_at"]} (UTC).\n'
            f'IMPORTANT: Relative expressions ("today","tomorrow","this week") refer to the creation date '
            f'({issue["created_at"][:10]}), not current time.\n'
            f'Based on real-world events up to close date ({issue["close_at"][:10]}), '
            f'was this prediction correct?\n\n'
            f'Return valid JSON only: {{"answer": "Yes" or "No", "reason": "..."}}'
        )

        result = self._call_gemini_with_retry(prompt)
        if result is None:
            print(f"  ❌ Skipping issue {issue['id']} (all retries failed).")
            return

        answer = result.get('answer') if isinstance(result, dict) else None
        if answer not in ('Yes', 'No'):
            print(f"  ❌ Invalid answer '{answer}' for issue {issue['id']}")
            return

        self._apply_resolution(issue, answer)

    def _apply_resolution(self, issue, answer: str):
        """정답 옵션 조회 → 이슈 RESOLVED 업데이트 → 포인트 지급."""
        try:
            opt_resp = (
                supabase.table('options')
                .select('id')
                .eq('issue_id', issue['id'])
                .eq('title', answer)
                .single()
                .execute()
            )
            if not opt_resp.data:
                print(f"  ❌ Option '{answer}' not found for issue {issue['id']}")
                return

            correct_option_id = opt_resp.data['id']

            supabase.table('issues').update({
                'status': 'RESOLVED',
                'correct_option_id': correct_option_id,
                'resolved_at': datetime.now(timezone.utc).isoformat()
            }).eq('id', issue['id']).execute()

            self._process_payouts(issue['id'], correct_option_id)
            print(f"  ✅ {issue['title'][:55]} → {answer}")
        except Exception as e:
            print(f"  ❌ _apply_resolution error for {issue['id']}: {e}")

    def _process_payouts(self, issue_id, correct_option_id):
        """정답 +10점, 오답 -10점 (최소 0점)"""
        bets_resp = supabase.table('bets').select('*').eq('issue_id', issue_id).execute()
        bets = bets_resp.data if bets_resp.data else []

        for bet in bets:
            is_winner = str(bet['option_id']) == str(correct_option_id)
            supabase.table('bets').update({
                'status': 'WON' if is_winner else 'LOST'
            }).eq('id', bet['id']).execute()

            user_resp = supabase.table('users').select('points').eq('id', bet['user_id']).single().execute()
            if user_resp.data:
                current_pts = user_resp.data.get('points', 0)
                new_pts = current_pts + 10 if is_winner else max(0, current_pts - 10)
                supabase.table('users').update({'points': new_pts}).eq('id', bet['user_id']).execute()

resolver_service = ResolverService()
