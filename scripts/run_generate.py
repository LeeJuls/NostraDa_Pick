"""
GitHub Actions용 이슈 출제 실행 스크립트
Usage: python scripts/run_generate.py
"""
import sys
import os

# 프로젝트 루트를 Python 경로에 추가
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.gemini_service import gemini_service

def main():
    print("[run_generate] Starting issue generation...")
    try:
        issues = gemini_service.generate_trending_issues()
        if issues:
            gemini_service.save_issues_to_db(issues)
            print(f"[run_generate] Done. {len(issues)} issue(s) generated and saved.")
        else:
            print("[run_generate] No issues generated.")
            sys.exit(1)
    except Exception as e:
        print(f"[run_generate] Error: {e}")
        sys.exit(1)

if __name__ == '__main__':
    main()
