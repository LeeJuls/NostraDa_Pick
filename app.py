import os
from flask import Flask, jsonify
from config import config

def create_app():
    # Flask 앱 생성 (템플릿 및 정적 파일 경로 기본값 사용)
    app = Flask(__name__)
    app.config.from_object(config)

    # 1. 블루프린트 라우터 등록 (추후 추가)
    # from routes.main import main_bp
    # from routes.auth import auth_bp
    # from routes.api import api_bp
    # app.register_blueprint(main_bp)
    # app.register_blueprint(auth_bp, url_prefix='/auth')
    # app.register_blueprint(api_bp, url_prefix='/api')

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
