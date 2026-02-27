from services.supabase_client import supabase
from datetime import datetime, timedelta

def update_all_issues_to_6_hours():
    try:
        # 진행 중(OPEN)이거나 이미 확정된(RESOLVED) 이슈 모두 가져오기
        resp = supabase.table('issues').select('id, created_at').execute()
        issues = resp.data if resp.data else []
        
        updated_count = 0
        for issue in issues:
            # created_at 값을 datetime 객체로 변환 (ISO 형식, 'Z' 또는 '+00:00' 등 처리)
            created_str = issue['created_at'].replace('Z', '+00:00')
            created_time = datetime.fromisoformat(created_str)
            
            # 생성 시간 + 정각 6시간으로 마감 시간 재설정
            new_close_time = created_time + timedelta(hours=6)
            
            # 업데이트
            supabase.table('issues').update({
                'close_at': new_close_time.isoformat()
            }).eq('id', issue['id']).execute()
            updated_count += 1
            
        print(f"✅ Successfully updated {updated_count} issues to exactly 6 hours from creation.")
    except Exception as e:
        print(f"❌ Error updating issues: {e}")

if __name__ == "__main__":
    update_all_issues_to_6_hours()
