import os
from dotenv import load_dotenv

# .env 로드
load_dotenv()

from supabase import create_client, Client

url: str = os.environ.get("SUPABASE_URL")
key: str = os.environ.get("SUPABASE_KEY")

if not url or not key:
    print("SUPABASE_URL or SUPABASE_KEY is missing in env")
    exit(1)

supabase: Client = create_client(url, key)

def reset_points():
    try:
        # 모든 유저의 points를 0으로 초기화
        # Supabase Python SDK에서는 조건 없이 전체 업데이트를 지원하지 않을 수 있으므로
        # 모든 유저를 가져온 후 일괄 업데이트 하거나 조건(예: points > 0)을 줍니다.
        
        # 1. points가 존재하는(또는 0이 아닌) 유저 조회
        users_resp = supabase.table('users').select('id, points').neq('points', 0).execute()
        users = users_resp.data

        if not users:
            print("업데이트할 유저가 없습니다. (모두 0점이거나 유저 없음)")
            return

        print(f"총 {len(users)}명의 유저 포인트를 0으로 초기화합니다...")
        
        # 2. 업데이트 실행
        for user in users:
            supabase.table('users').update({'points': 0}).eq('id', user['id']).execute()
            print(f"User {user['id']} points reset to 0.")
            
        print("초기화 완료!")
    except Exception as e:
        print(f"Error resetting points: {e}")

if __name__ == "__main__":
    reset_points()
