from flask import Flask, jsonify
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

app = Flask(__name__)
limiter = Limiter(get_remote_address, app=app, default_limits=["200 per day", "50 per hour"], storage_uri="memory://")
app.config['LIMITER'] = limiter

@app.route('/test')
def test():
    try:
        current_limiter = app.config.get('LIMITER')
        if current_limiter:
            current_limiter.check()
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})

if __name__ == '__main__':
    with app.test_client() as client:
        res = client.get('/test')
        print("Status code:", res.status_code)
        print("Data:", res.get_data(as_text=True))
