import os
from flask import Flask, jsonify
from config import config

def create_app():
    # Flask 앱 생성 (템플릿 및 정적 파일 경로 기본값 사용)
    app = Flask(__name__)
    app.config.from_object(config)

    # ProxyFix 적용 (Render 등 프록시 환경에서 HTTPS 인식)
    from werkzeug.middleware.proxy_fix import ProxyFix
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1)

    # 1. 블루프린트 라우터 등록
    # from routes.main import main_bp
    from routes.auth import auth_bp, init_oauth
    from routes.api import api_bp
    # app.register_blueprint(main_bp)
    app.register_blueprint(auth_bp, url_prefix='/auth')
    app.register_blueprint(api_bp, url_prefix='/api')

    # 세션 사용을 위한 secret key 설정
    app.secret_key = config.SECRET_KEY
    
    # 5. 영구 세션 (자동 로그인 유지) 설정 (30일)
    from datetime import timedelta
    app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(days=30)
    
    # OAuth 초기화
    init_oauth(app)

    # Rate Limiter 설정
    from flask_limiter import Limiter
    from flask_limiter.util import get_remote_address
    
    limiter = Limiter(
        get_remote_address,
        app=app,
        default_limits=["200 per day", "50 per hour"],
        storage_uri="memory://"
    )
    
    # Limiter 객체를 외부 Blueprint에서도 사용 가능하도록 config에 저장
    app.config['LIMITER'] = limiter

    @app.route('/health')
    def health_check():
        """서버 상태 확인용 기본 엔드포인트"""
        return jsonify({"status": "healthy", "service": "NostraDa_Pick"}), 200

    @app.route('/')
    def index():
        """노다픽 메인 페이지 렌더링"""
        from flask import render_template
        return render_template('index.html')

    # 에러 핸들러 (API 대응)
    @app.errorhandler(404)
    def not_found_error(error):
        return jsonify({"success": False, "error": "Not Found"}), 404

    @app.errorhandler(500)
    def internal_error(error):
        return jsonify({"success": False, "error": "Internal Server Error"}), 500

    return app

if __name__ == '__main__':
    app = create_app()
    # 명세서: 배포는 Gunicorn 사용, 로컬은 FLASK_ENV=development
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port, debug=config.DEBUG)
