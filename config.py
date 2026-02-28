import os
from dotenv import load_dotenv

# .env 파일 로드
load_dotenv()

class Config:
    # Flask Settings
    SECRET_KEY = os.environ.get('SECRET_KEY', 'default-dev-nostradamus-key-2026')
    DEBUG = os.environ.get('FLASK_ENV') != 'production'

    # Supabase (Database/Auth) Settings
    SUPABASE_URL = os.environ.get('SUPABASE_URL')
    SUPABASE_KEY = os.environ.get('SUPABASE_KEY')

    # Google Gemini API Settings (다중 키 지원)
    _keys_str = os.environ.get('GEMINI_API_KEYS') or os.environ.get('GEMINI_API_KEY')
    GEMINI_API_KEYS = [k.strip() for k in _keys_str.split(',')] if _keys_str else []
    GEMINI_API_KEY = GEMINI_API_KEYS[0] if GEMINI_API_KEYS else None

    # 기타 글로벌 설정
    TIMEZONE = 'UTC' # 명세서 v6.1: 서버/DB/프론트 전부 UTC 사용
    
config = Config()
