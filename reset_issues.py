from config import config
from services.supabase_client import supabase

def reset_db_issues():
    print("--- 🔴 Resetting Database Issues & Bets 🔴 ---")
    
    try:
        # Delete all options (this might fail if the table has no cascade constraints but in this case issue deletion should cascade anyway. Let's start with issues.)
        # The schema_init.sql shows ON DELETE CASCADE for options and bets referencing issues.
        # So we can just delete from issues.
        
        print("Fetching all issues...")
        issues = supabase.table('issues').select('id').execute().data
        
        if not issues:
            print("No issues found to delete.")
        else:
            issue_ids = [issue['id'] for issue in issues]
            print(f"Deleting {len(issue_ids)} issues (Options and Bets will be cascade deleted)...")
            
            # Submitting delete requests in loop or in/eq
            for issue_id in issue_ids:
                supabase.table('issues').delete().eq('id', issue_id).execute()
        
        print("✅ DB Reset Complete.")
        
    except Exception as e:
        print(f"❌ Error during reset: {e}")

if __name__ == '__main__':
    reset_db_issues()
