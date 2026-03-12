import sys
sys.path.insert(0, 'D:/WebService/NostraDa_Pick')
from dotenv import load_dotenv
load_dotenv('D:/WebService/NostraDa_Pick/.env')
from supabase import create_client
import os

url = os.environ['SUPABASE_URL']
key = os.environ['SUPABASE_KEY']
sb = create_client(url, key)

# 1. bets 전부 삭제 (issues FK 참조)
bets = sb.table('bets').select('id').execute()
print(f'bets 행 수: {len(bets.data)}')
if bets.data:
    sb.table('bets').delete().neq('id', '00000000-0000-0000-0000-000000000000').execute()
    print('bets 전부 삭제 완료')
else:
    print('bets 없음')

# 2. issues 전부 삭제
issues = sb.table('issues').select('id').execute()
print(f'issues 행 수: {len(issues.data)}')
if issues.data:
    sb.table('issues').delete().neq('id', '00000000-0000-0000-0000-000000000000').execute()
    print('issues 전부 삭제 완료')
else:
    print('issues 없음')

# 3. 확인
remaining = sb.table('issues').select('id').execute()
print(f'삭제 후 issues 잔여: {len(remaining.data)}개')
print('DONE')
