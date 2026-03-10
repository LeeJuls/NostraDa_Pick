from services.supabase_client import supabase
import os

def verify():
    print(f"Current FLASK_ENV: {os.environ.get('FLASK_ENV')}")
    try:
        # issues 테이블(실제로는 dev_issues)에 쿼리
        res = supabase.table('issues').select('count', count='exact').execute()
        print(f"✅ Connection successful!")
        print(f"📊 Current count in 'dev_issues': {res.count}")
        
        # 테이블 이름 확인 (prefix가 잘 붙었는지 간접 확인)
        # 만약 dev_issues가 없으면 여기서 에러가 날 것임.
    except Exception as e:
        print(f"❌ Verification failed: {e}")

if __name__ == "__main__":
    verify()
