import sys
sys.path.insert(0, 'D:/WebService/NostraDa_Pick')
from dotenv import load_dotenv
load_dotenv('D:/WebService/NostraDa_Pick/.env')
from supabase import create_client
import os, datetime

url = os.environ['SUPABASE_URL']
key = os.environ['SUPABASE_KEY']
sb = create_client(url, key)

# 1. gemini_api_mode = 'api' 로 설정
now_iso = datetime.datetime.now().isoformat()
check = sb.table('app_settings').select('id').eq('key', 'gemini_api_mode').execute()
if check.data:
    sb.table('app_settings').update({'value': 'api', 'updated_at': now_iso}).eq('key', 'gemini_api_mode').execute()
else:
    sb.table('app_settings').insert({'key': 'gemini_api_mode', 'value': 'api', 'updated_at': now_iso}).execute()
print('gemini_api_mode = api 설정 완료')

# 2. Gemini로 이슈 3개 생성 + DB 저장
from services.gemini_service import gemini_service

print('Gemini API 호출 중... (최대 1~2분 소요)')
issues_data = gemini_service.generate_trending_issues(count=3)
if not issues_data:
    print('ERROR: 이슈 생성 실패')
    sys.exit(1)

print(f'생성된 이슈 {len(issues_data)}개:')
for i, issue in enumerate(issues_data, 1):
    print(f'  {i}. [{issue.get("category","?")}] {issue.get("title","?")}')

gemini_service.save_issues_to_db(issues_data)
print('DB 저장 완료')

# 3. 저장 확인
saved = sb.table('issues').select('id, title, category, status').execute()
print(f'\n최종 issues 테이블: {len(saved.data)}개')
for row in saved.data:
    print(f'  - [{row["category"]}] {row["title"]} ({row["status"]})')
