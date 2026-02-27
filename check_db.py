from config import config
from services.supabase_client import supabase

def check_db():
    print("--- USERS ---")
    users = supabase.table('users').select('id, email, points').execute().data
    for u in users:
        print(f"{u['email']}: {u['points']} pts")
    
    print("\n--- BETS ---")
    bets = supabase.table('bets').select('*').execute().data
    for b in bets:
        print(f"User {b['user_id']} voted Option {b['option_id']} on Issue {b['issue_id']} (Status: {b.get('status', 'N/A')})")

    print("\n--- ISSUES ---")
    issues = supabase.table('issues').select('id, title, status, correct_option_id').execute().data
    for i in issues:
        print(f"Issue {i['id']}: {i['title']} [{i['status']}] Correct: {i.get('correct_option_id')}")

if __name__ == '__main__':
    check_db()
