from services.supabase_client import supabase
from datetime import datetime, timedelta

def seed_real_news():
    print("🚀 Seeding real-time news (Feb 26, 2026) to Supabase...")
    
    issues = [
        {
            "title": "Will SpaceX successfully launch its next Starship test flight this weekend?",
            "category": "tech",
            "hours": 4
        },
        {
            "title": "Will the Federal Reserve announce an emergency interest rate cut before Friday?",
            "category": "economy",
            "hours": 4
        },
        {
            "title": "Will Apple officially unveil its rumored AR smart glasses at the upcoming event?",
            "category": "tech",
            "hours": 4
        },
        {
            "title": "Will Real Madrid win their highly anticipated Champions League quarter-final match tonight?",
            "category": "sports",
            "hours": 4
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
