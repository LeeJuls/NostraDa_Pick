import os
from flask import Blueprint, redirect, url_for, session, request, current_app
from authlib.integrations.flask_client import OAuth
from services.supabase_client import supabase

auth_bp = Blueprint('auth', __name__)
oauth = OAuth()

def init_oauth(app):
    oauth.init_app(app)
    oauth.register(
        name='google',
        client_id=os.environ.get('GOOGLE_CLIENT_ID', ''),
        client_secret=os.environ.get('GOOGLE_CLIENT_SECRET', ''),
        server_metadata_url='https://accounts.google.com/.well-known/openid-configuration',
        client_kwargs={
            'scope': 'openid email profile'
        }
    )

@auth_bp.route('/login')
def login():
    # Render와 같은 프록시 환경에서 HTTPS 보장을 위해 _scheme='https' 강제 (로컬 제외)
    scheme = 'https' if os.environ.get('FLASK_ENV') == 'production' else 'http'
    redirect_uri = url_for('auth.authorize', _external=True, _scheme=scheme)
    return oauth.google.authorize_redirect(redirect_uri)

@auth_bp.route('/callback')
def authorize():
    try:
        token = oauth.google.authorize_access_token()
        user_info = token.get('userinfo')
        if user_info:
            email = user_info.email
            nickname = user_info.name or user_info.given_name
            
            # Supabase 연동 로직
            user_id = None
            last_nickname_changed_at = None
            if supabase:
                # 1. 존재하는 사용자인지 이메일로 검색
                response = supabase.table('users').select('*').eq('email', email).execute()
                data = response.data
                if data and len(data) > 0:
                    # 기존 유저
                    user_id = data[0]['id']
                    db_nickname = data[0].get('nickname')
                    last_nickname_changed_at = data[0].get('last_nickname_changed_at')
                    if db_nickname:
                        nickname = db_nickname
                    else:
                        # 기존 유저 중 닉네임이 안 들어간 경우 이름으로 업데이트
                        supabase.table('users').update({'nickname': nickname}).eq('id', user_id).execute()
                else:
                    # 신규 유저 생성 (기본값 포인트 0)
                    insert_response = supabase.table('users').insert({
                        'email': email,
                        'nickname': nickname,
                        'points': 0
                    }).execute()
                    if insert_response.data:
                        user_id = insert_response.data[0]['id']

            session['user'] = {
                'id': user_id,
                'email': email,
                'nickname': nickname,
                'last_nickname_changed_at': str(last_nickname_changed_at) if last_nickname_changed_at else None,
                'picture': user_info.picture,
            }
            session.permanent = True
    except Exception as e:
        print(f"OAuth Error: {e}")
        # 에러 발생 시 상세 정보 세션에 임시 저장 (디버깅용)
        session['oauth_error'] = str(e)
    return redirect(url_for('index'))

@auth_bp.route('/logout')
def logout():
    session.pop('user', None)
    return redirect(url_for('index'))
