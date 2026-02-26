import os
from supabase import create_client, Client
from config import config

class SupabaseManager:
    def __init__(self):
        self.url: str = config.SUPABASE_URL
        self.key: str = config.SUPABASE_KEY
        self.client: Client = None

        if self.url and self.key:
            try:
                self.client = create_client(self.url, self.key)
                print("✅ Supabase Client Initialized Successfully")
            except Exception as e:
                print(f"❌ Failed to initialize Supabase Client: {e}")
        else:
            print("⚠️ Supabase URL or Key is missing in environment variables.")

    def get_client(self) -> Client:
        return self.client

# 싱글톤 인스턴스 생성
supabase_mgr = SupabaseManager()
supabase: Client = supabase_mgr.get_client()
