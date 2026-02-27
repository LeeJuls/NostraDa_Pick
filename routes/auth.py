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
    redirect_uri = url_for('auth.authorize', _external=True)
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
            if supabase:
                # 1. 존재하는 사용자인지 이메일로 검색
                response = supabase.table('users').select('*').eq('email', email).execute()
                data = response.data
                if data and len(data) > 0:
                    # 기존 유저
                    user_id = data[0]['id']
                else:
                    # 신규 유저 생성 (기본값 포인트 1000)
                    insert_response = supabase.table('users').insert({
                        'email': email,
                        'points': 0
                    }).execute()
                    if insert_response.data:
                        user_id = insert_response.data[0]['id']

            session['user'] = {
                'id': user_id,
                'email': email,
                'nickname': nickname,
                'picture': user_info.picture,
            }
            session.permanent = True
    except Exception as e:
        print(f"OAuth Error: {e}")
    return redirect(url_for('index'))

@auth_bp.route('/logout')
def logout():
    session.pop('user', None)
    return redirect(url_for('index'))
