from services.supabase_client import supabase
from datetime import datetime, timedelta

def seed_real_news():
    print("🚀 Seeding real-time news (Feb 26, 2026) to Supabase...")
    
    issues = [
        {
            "title": "Will Philadelphia Union defeat Defence Force F.C. in tonight's Concacaf match?",
            "category": "sports",
            "hours": 12
        },
        {
            "title": "Will China's 'Silver Economy' policy blueprints lead to a stock market surge next week?",
            "category": "economy",
            "hours": 72
        },
        {
            "title": "Will the Philippines House justice panel approve the impeachment charges against the Vice President?",
            "category": "politics",
            "hours": 168
        },
        {
            "title": "Will the Louvre's new director successfully recover the stolen French crown jewels by the end of March?",
            "category": "misc",
            "hours": 800
        }
    ]

    for data in issues:
        try:
            close_at = (datetime.now() + timedelta(hours=data['hours'])).isoformat()
            res = supabase.table('issues').insert({
                'title': data['title'],
                'category': data['category'],
                'status': 'OPEN',
                'close_at': close_at
            }).execute()
            
            if res.data:
                issue_id = res.data[0]['id']
                supabase.table('options').insert([
                    {'issue_id': issue_id, 'title': 'Yes'},
                    {'issue_id': issue_id, 'title': 'No'}
                ]).execute()
                print(f"✅ Inserted: {data['title']}")
        except Exception as e:
            print(f"❌ Error inserting {data['title']}: {e}")

if __name__ == "__main__":
    seed_real_news()
