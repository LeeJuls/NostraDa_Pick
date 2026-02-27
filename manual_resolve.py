from services.supabase_client import supabase
from datetime import datetime

issue_id = 'e4160345-2f46-46cf-bcd1-1fbaa62228b8'

# 1. 'Yes' 옵션 ID 찾기
opt_resp = supabase.table('options').select('id').eq('issue_id', issue_id).eq('title', 'Yes').single().execute()

if opt_resp.data:
    correct_opt_id = opt_resp.data['id']
    
    # 2. 상태 업데이트
    supabase.table('issues').update({
        'status': 'RESOLVED', 
        'correct_option_id': correct_opt_id, 
        'resolved_at': datetime.now().isoformat()
    }).eq('id', issue_id).execute()
    print("✅ Issue marked as RESOLVED (Yes)")
    
    # 3. 베팅 결과 처리
    bets_resp = supabase.table('bets').select('*').eq('issue_id', issue_id).execute()
    bets = bets_resp.data if bets_resp.data else []
    for bet in bets:
        is_winner = str(bet['option_id']) == str(correct_opt_id)
        new_status = 'WON' if is_winner else 'LOST'
        supabase.table('bets').update({'status': new_status}).eq('id', bet['id']).execute()
        
        if is_winner:
            user_resp = supabase.table('users').select('points').eq('id', bet['user_id']).single().execute()
            if user_resp.data:
                current_pts = user_resp.data.get('points', 0)
                supabase.table('users').update({'points': current_pts + 1}).eq('id', bet['user_id']).execute()
    print("✅ Bets processed.")
else:
    print("❌ Yes option not found")
