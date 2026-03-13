import sys
sys.path.insert(0, 'D:/WebService/NostraDa_Pick')
from dotenv import load_dotenv
load_dotenv('D:/WebService/NostraDa_Pick/.env')

# 실제 _resolve_source_url 로직 테스트
from services.sports_schedule_service import get_all_sports_matches
from services.news_feed_service import fetch_news_headlines
from services.stock_price_service import fetch_stock_prices
from services.gemini_service import gemini_service

# 현재 이슈 제목들
from services.supabase_client import supabase
r = supabase.table('issues').select('category,title').execute()

matches = get_all_sports_matches(hours_ahead=48)
headlines = fetch_news_headlines(max_per_feed=5, max_age_hours=48)
prices = fetch_stock_prices()

print(f"\n{'='*60}")
print(f"경기:{len(matches)}개 / 헤드라인:{len(headlines)}개 / 주가:{len(prices)}개")
print('='*60)

for x in r.data:
    title = x['title']
    url = gemini_service._resolve_source_url(title, headlines, matches, prices)
    print(f"[{x['category']}] {title[:55]}")
    print(f"   → {url or '(없음)'}")
    print()
