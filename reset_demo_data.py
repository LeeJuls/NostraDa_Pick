import os
from services.supabase_client import supabase
from services.gemini_service import gemini_service

def reset_and_generate():
    try:
        print("1. 기존 베팅 기록 삭제 중...")
        supabase.table('bets').delete().neq('id', '00000000-0000-0000-0000-000000000000').execute()
        
        print("2. 기존 옵션 데이터 삭제 중...")
        supabase.table('options').delete().neq('id', '00000000-0000-0000-0000-000000000000').execute()
        
        print("3. 기존 문제(이슈) 삭제 중...")
        supabase.table('issues').delete().neq('id', '00000000-0000-0000-0000-000000000000').execute()
        
        print("✅ 초기화 완료. 유저(리더보드) 데이터는 보존되었습니다.\n")
        
        print("4. 새로운 문제 4개 생성 중 (AI 호출)...")
        issues_data = gemini_service.generate_trending_issues(count=4)
        
        if issues_data:
            gemini_service.save_issues_to_db(issues_data)
            print("✅ 4개의 문제가 새로 출제되어 DB에 반영되었습니다!")
        else:
            print("❌ 문제 생성에 실패했습니다.")
    except Exception as e:
        print(f"❌ 작업 중 에러 발생: {e}")

if __name__ == '__main__':
    reset_and_generate()
