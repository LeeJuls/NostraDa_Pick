from config import config
from services.supabase_client import supabase

def fix_duplicates():
    # 1. Fetch all bets
    bets = supabase.table('bets').select('*').execute().data
    
    seen = set()
    duplicates_to_delete = []
    
    for b in bets:
        identifier = (b['user_id'], b['issue_id'])
        if identifier in seen:
            duplicates_to_delete.append(b['id'])
        else:
            seen.add(identifier)
            
    if duplicates_to_delete:
        print(f"Found {len(duplicates_to_delete)} duplicate bets. Deleting them...")
        for bet_id in duplicates_to_delete:
            supabase.table('bets').delete().eq('id', bet_id).execute()
        print("Duplicates deleted.")
    else:
        print("No duplicate bets found.")
        
    # 2. Recalculate points for the user
    user_id = "cf9306ad-f4e1-4921-b48b-851a656f1518"
    
    # Get all WON bets for the user after removing duplicates
    won_bets = supabase.table('bets').select('*').eq('user_id', user_id).eq('status', 'WON').execute().data
    
    correct_points = len(won_bets)
    print(f"User should have {correct_points} points.")
    
    # Update user points
    supabase.table('users').update({'points': correct_points}).eq('id', user_id).execute()
    print("User points updated successfully.")

if __name__ == '__main__':
    fix_duplicates()
