"""
GitHub Actions용 이슈 판정 실행 스크립트
Usage: python scripts/run_resolve.py
"""
import sys
import os

# 프로젝트 루트를 Python 경로에 추가
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.resolver_service import resolver_service

def main():
    print("[run_resolve] Starting issue resolution...")
    try:
        resolver_service.resolve_expired_issues()
        print("[run_resolve] Done.")
    except Exception as e:
        print(f"[run_resolve] Error: {e}")
        sys.exit(1)

if __name__ == '__main__':
    main()
