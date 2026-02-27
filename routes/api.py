from flask import Blueprint, jsonify

api_bp = Blueprint('api', __name__)

from services.supabase_client import supabase
from flask import request, session, current_app

@api_bp.route('/issues/open', methods=['GET'])
def get_open_issues():
    """실제 DB에서 OPEN 상태이거나, 마감된지 24시간이 지나지 않은 이슈들을 가져옴"""
    if not supabase:
        return jsonify({"success": False, "error": "DB 연결 실패"}), 500

    try:
        # 기준 시간: 현재 시간으로부터 24시간 전 (이 시간 이후에 마감된 것만 + 아직 마감 안된 OPEN)
        from datetime import datetime, timedelta
        hide_threshold = (datetime.now() - timedelta(hours=24)).isoformat()

        # 1. 이슈 조회 (오래된 것 숨김 처리)
        # Supabase Python 클라이언트에서는 or_ 필터를 쓰거나, 상태별로 가져와 병합 가능
        # 간편하게 모든 이슈(최근 것들)를 가져온 뒤 파이썬에서 필터링하거나, gte 조건 사용
        issue_resp = supabase.table('issues').select('*').gte('close_at', hide_threshold).order('close_at').execute()
        issues = issue_resp.data if issue_resp.data else []

        if not issues:
            return jsonify({"success": True, "data": []}), 200

        # 2. 모든 이슈 ID 수집하여 한 번에 옵션 정보 가져오기 (N+1 최적화)
        issue_ids = [i['id'] for i in issues]
        opt_resp = supabase.table('options').select('*').in_('issue_id', issue_ids).execute()
        all_options = opt_resp.data if opt_resp.data else []

        # 옵션들을 이슈 ID별로 그룹화
        options_map = {}
        for opt in all_options:
            iid = opt['issue_id']
            if iid not in options_map:
                options_map[iid] = []
            options_map[iid].append(opt)

        # 3. 데이터 조립 및 퍼센트 계산
        for issue in issues:
            issue_options = options_map.get(issue['id'], [])
            issue['options'] = issue_options
            
            total_pool = sum(opt.get('pool_amount', 0) for opt in issue_options)
            for opt in issue_options:
                opt['percent'] = round((opt['pool_amount'] / total_pool * 100), 1) if total_pool > 0 else 0
            
            issue['total_pool'] = total_pool

        return jsonify({"success": True, "data": issues}), 200
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@api_bp.route('/issues/<string:issue_id>', methods=['GET'])
def get_issue_detail(issue_id):
    """이슈 상세 데이터와 옵션 반환"""
    try:
        issue_resp = supabase.table('issues').select('*').eq('id', issue_id).single().execute()
        if not issue_resp.data:
            return jsonify({"success": False, "error": "찾을 수 없는 이슈"}), 404
        
        issue = issue_resp.data
        opt_resp = supabase.table('options').select('*').eq('issue_id', issue_id).execute()
        issue['options'] = opt_resp.data
        
        return jsonify({"success": True, "data": issue}), 200
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@api_bp.route('/users/me', methods=['GET'])
def get_my_info():
    """로그인된 내 포인트 정보 조회"""
    user = session.get('user')
    if not user or not user.get('id'):
        return jsonify({"success": False, "error": "로그인 필요"}), 401
    
    try:
        res = supabase.table('users').select('*').eq('id', user['id']).single().execute()
        return jsonify({"success": True, "data": res.data}), 200
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@api_bp.route('/users/me/stats', methods=['GET'])
def get_my_stats():
    """내 순위, 연승, 승리 수 및 최근 맞춘 5문제 조회 (Mock Data 포함 실제 로직)"""
    user = session.get('user')
    if not user or not user.get('id'):
        return jsonify({"success": False, "error": "로그인 필요"}), 401
    
    try:
        # 1. 랭크 조회 (전체 유저 중 포인트 기반 등수 계산)
        all_users_resp = supabase.table('users').select('id, points').order('points', desc=True).execute()
        rank = "N/A"
        
        if all_users_resp.data:
            # 포인트 내림차순 정렬 (이미 되어있긴 하지만 확인)
            sorted_users = sorted(all_users_resp.data, key=lambda x: x.get('points', 0), reverse=True)
            for idx, u in enumerate(sorted_users):
                if str(u.get('id')) == str(user['id']):
                    rank = idx + 1
                    break

        # 2. Wins, Streak 계산 (이슈가 RESOLVED 되었으며, 유저가 맞춘 경우)
        # 이 프로젝트의 현재 DB 스키마상 'bets' 테이블에 정답 여부가 없다면,
        # bets와 issues를 조인(또는 각각 쿼리하여 매칭)해 정답 여부를 판단해야 합니다.
        # 편의상 이슈의 status가 'RESOLVED'이고, 이슈의 정답 옵션(resolved_option_id)과 
        # 사용자의 베팅(option_id)이 일치하는 경우를 '정답'으로 간주합니다.
        
        my_bets_resp = supabase.table('bets').select('issue_id, option_id').eq('user_id', user['id']).execute()
        my_bets = { b['issue_id']: b['option_id'] for b in (my_bets_resp.data or []) }
        
        wins = 0
        streak = 0
        recent_correct = []
        
        if my_bets:
            # RESOLVED 이슈 전체 조회 (최신 마감순 정렬)
            resolved_issues_resp = supabase.table('issues').select('id, title, resolved_option_id').eq('status', 'RESOLVED').order('close_at', desc=True).execute()
            resolved_issues = resolved_issues_resp.data or []
            
            # 과거부터 현재 순으로 탐색하여 Streak 계산.
            # 가장 최근 이슈부터 확인해서 연속으로 맞췄는지 봅니다.
            for issue in resolved_issues:
                issue_id = issue['id']
                if issue_id in my_bets:
                    # 유저가 참여한 경우 -> 정답 확인
                    if str(my_bets[issue_id]) == str(issue.get('resolved_option_id')):
                        wins += 1
                        recent_correct.append({'id': issue_id, 'title': issue['title']})
                    else:
                        # 한 번이라도 틀렸다면 연속 정답(Streak) 계산은 거기서 중단되어야 하나,
                        # 현재는 편의상 wins만 더하고 streak는 계산 로직이 복잡하여 기본 0으로 두거나 mock 처리
                        pass
            
            # 최근 정답 5개만 슬라이싱
            recent_correct = recent_correct[:5]
            
            # 연속 정답 계산 (최신순에서 틀린 값이 나오기 전까지의 개수)
            for issue in resolved_issues:
                issue_id = issue['id']
                if issue_id in my_bets:
                    if str(my_bets[issue_id]) == str(issue.get('resolved_option_id')):
                        streak += 1
                    else:
                        break

        return jsonify({
            "success": True, 
            "data": {
                "rank": rank,
                "streak": streak,
                "wins": wins,
                "recent_correct": recent_correct
            }
        }), 200

    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@api_bp.route('/leaderboard', methods=['GET'])
def get_leaderboard():
    """포인트 순 상위 10명 조회"""
    try:
        res = supabase.table('users').select('email, points').order('points', desc=True).limit(10).execute()
        return jsonify({"success": True, "data": res.data}), 200
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

# 새로 추가된 베팅(투표) 엔드포인트
from flask import request, session
from services.supabase_client import supabase

@api_bp.route('/bet', methods=['POST'])
def place_bet():
    # Blueprint 안에서 Rate Limit 적용 (current_app 사용)
    from flask import current_app
    limiter = current_app.config.get('LIMITER')
    if limiter:
        # 이 분 안에서 수동으로 제한 체크 (라우터 레벨 데코레이터가 아니므로 약간의 트릭 사용)
        limiter.check() # 기본적으로 데코레이터를 쓰는게 정석. 하지만 구조상 아래처럼 적용합니다.

    user = session.get('user')
    if not user or not user.get('id'):
        return jsonify({"success": False, "error": "로그인이 필요합니다."}), 401

    data = request.get_json()
    issue_id = data.get('issue_id')
    option_id = data.get('option_id')
    amount = data.get('amount', 100) # 더미 금액 100

    if not issue_id or not option_id:
        return jsonify({"success": False, "error": "잘못된 요청입니다."}), 400

    if not supabase:
        return jsonify({"success": False, "error": "DB 연결이 불안정합니다."}), 500

    # 1. 이슈가 OPEN 상태인지 확인
    try:
        issue_resp = supabase.table('issues').select('status').eq('id', issue_id).execute()
        if not issue_resp.data or issue_resp.data[0]['status'] != 'OPEN':
            return jsonify({"success": False, "error": "종료된 투표입니다."}), 400
    except Exception as e:
        return jsonify({"success": False, "error": f"이슈 조회 오류: {e}"}), 500

    # 2. 베팅 삽입 시도 (user_id + issue_id 유니크 위반 시 에러)
    try:
        bet_resp = supabase.table('bets').insert({
            'user_id': user.get('id'),
            'issue_id': issue_id,
            'option_id': option_id,
            'amount': amount
        }).execute()
        
        # 3. 투표 성공 시, 해당 option의 pool_amount(여기서는 투표 수)를 1 증가시킴
        # (원래 pool_amount는 상금이었지만, 이제는 1인 1표이므로 투표 수(1)로 취급)
        if bet_resp.data:
            # 먼저 현재 값을 가져옵니다.
            opt_data = supabase.table('options').select('pool_amount').eq('id', option_id).single().execute()
            if opt_data.data:
                current_pool = opt_data.data.get('pool_amount', 0)
                # 1 증가시킨 값으로 업데이트
                supabase.table('options').update({'pool_amount': current_pool + 1}).eq('id', option_id).execute()

        return jsonify({"success": True, "message": "투표가 기록되었습니다!"}), 200

    except Exception as e:
        err_msg = str(e)
        if "unique" in err_msg.lower() or "violation" in err_msg.lower():
            return jsonify({"success": False, "error": "이미 참여한 투표입니다!"}), 409
        return jsonify({"success": False, "error": err_msg}), 500

@api_bp.route('/bets/me', methods=['GET'])
def get_my_bets():
    """로그인 유저가 참여한 투표(issue_id) 목록 반환 API"""
    from flask import current_app
    limiter = current_app.config.get('LIMITER')
    if limiter:
        limiter.check()

    user = session.get('user')
    if not user or not user.get('id'):
        return jsonify({"success": False, "error": "로그인이 필요합니다.", "data": []}), 401
    
    if not supabase:
        return jsonify({"success": False, "error": "DB 연결이 불안정합니다.", "data": []}), 500

    try:
        # DB에서 해당 유저가 베팅한 issue_id와 선택한 option_id를 맵핑하여 반환
        resp = supabase.table('bets').select('issue_id, option_id').eq('user_id', user.get('id')).execute()
        # { "issue_id": "option_id" } 형태의 딕셔너리 생성
        voted_data = {row['issue_id']: row['option_id'] for row in resp.data} if resp.data else {}
        return jsonify({"success": True, "data": voted_data}), 200
    except Exception as e:
        return jsonify({"success": False, "error": f"조회 중 오류 발생: {str(e)}", "data": []}), 500
