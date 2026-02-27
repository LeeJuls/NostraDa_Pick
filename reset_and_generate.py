import os
from config import config
from services.supabase_client import supabase
from services.gemini_service import gemini_service

def reset_and_generate():
    print("--- 🔴 Resetting Database Issues & Bets 🔴 ---")
    try:
        issues = supabase.table('issues').select('id').execute().data
        if issues:
            issue_ids = [issue['id'] for issue in issues]
            print(f"Deleting {len(issue_ids)} issues (Options and Bets will cascade delete)...")
            for issue_id in issue_ids:
                supabase.table('issues').delete().eq('id', issue_id).execute()
        print("✅ DB Reset Complete.")
    except Exception as e:
        print(f"❌ Error during reset: {e}")
        return

    print("\n--- 🧠 Generating New Issues via Gemini 🧠 ---")
    issues_data = gemini_service.generate_trending_issues()
    if issues_data:
        gemini_service.save_issues_to_db(issues_data)
        print("✅ Generation Complete.")
    else:
        print("❌ Failed to generate issues.")

if __name__ == '__main__':
    reset_and_generate()
