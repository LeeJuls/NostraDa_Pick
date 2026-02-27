import os
from supabase import create_client, Client
from config import config

def test_connection():
    url = config.SUPABASE_URL
    key = config.SUPABASE_KEY
    
    if not url or not key:
        print("❌ 에러: SUPABASE_URL 또는 SUPABASE_KEY가 .env 파일에 없습니다.")
        return

    print("🔌 Supabase 연결 테스트 시작...")
    try:
        supabase: Client = create_client(url, key)
        
        # 테스트 1: users 테이블
        print("\n🧪 [테스트 1] 'users' 테이블 조회 중...")
        supabase.table('users').select('id').limit(1).execute()
        print("✅ users 테이블 접근 성공!")
        
        # 테스트 2: issues 테이블
        print("\n🧪 [테스트 2] 'issues' 테이블 조회 중...")
        supabase.table('issues').select('id').limit(1).execute()
        print("✅ issues 테이블 접근 성공!")

        # 테스트 3: options 테이블
        print("\n🧪 [테스트 3] 'options' 테이블 조회 중...")
        supabase.table('options').select('id').limit(1).execute()
        print("✅ options 테이블 접근 성공!")

        # 테스트 4: bets 테이블
        print("\n🧪 [테스트 4] 'bets' 테이블 조회 중...")
        supabase.table('bets').select('id').limit(1).execute()
        print("✅ bets 테이블 접근 성공!")

        print("\n🎉 모든 DB 테이블 뼈대가 정상적으로 확인되었습니다! (연결 테스트 통과)")

    except Exception as e:
        print(f"\n❌ DB 테스트 중 에러 발생: {e}")
        print("⚠️ Supabase SQL Editor에서 'docs/dev/schema_init.sql' 쿼리를 먼저 실행해주셨는지 확인해주세요.")

if __name__ == "__main__":
    test_connection()
