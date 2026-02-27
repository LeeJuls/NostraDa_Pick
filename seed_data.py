import os
import sys

# 현재 디렉토리를 path에 추가하여 services 임포트 가능하게 함
sys.path.append(os.getcwd())

from services.gemini_service import gemini_service

def main():
    print("🚀 Generating real-world prediction issues via Gemini AI...")
    issues = gemini_service.generate_trending_issues()
    
    if issues:
        print(f"✨ Gemini suggested {len(issues)} issues.")
        success = gemini_service.save_issues_to_db(issues)
        if success:
            print("✅ Successfully seeded Supabase with real issues.")
        else:
            print("❌ Failed to save issues to DB.")
    else:
        print("❌ Gemini failed to generate issues (Check API Key).")

if __name__ == "__main__":
    main()
