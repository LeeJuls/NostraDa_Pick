from services.supabase_client import supabase

options = supabase.table('options').select('id, issue_id, title').execute().data
for o in options[:10]:
    print(f"Option: '{o['title']}' ID: {o['id']}")
