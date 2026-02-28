from flask import Blueprint, jsonify

api_bp = Blueprint('api', __name__)

from services.supabase_client import supabase
from flask import request, session, current_app

@api_bp.route('/issues/open', methods=['GET'])
def get_open_issues():
    """DB에서 OPEN 상태인 이슈 전체 + 정답 처리(RESOLVED)된 지 24시간 이내인 이슈를 가져옴"""
    if not supabase:
        return jsonify({"success": False, "error": "DB 연결 실패"}), 500

    try:
        from datetime import datetime, timedelta
        hide_threshold = (datetime.now() - timedelta(hours=24)).isoformat()

        # 1. OPEN 상태 이슈 모두 가져오기 (마감시간 지나도 정답 안나왔으면 표시)
        open_resp = supabase.table('issues').select('*').eq('status', 'OPEN').execute()
        open_issues = open_resp.data if open_resp.data else []

        # 2. RESOLVED 상태 이슈 중 정답 처리된지 24시간이 안 지난 이슈 가져오기
        # 주의: resolved_at 컬럼을 기준으로 판단
        resolved_resp = supabase.table('issues').select('*').eq('status', 'RESOLVED').gte('resolved_at', hide_threshold).execute()
        resolved_issues = resolved_resp.data if resolved_resp.data else []

        # 병합 후 close_at 기준으로 정렬 (필요에 따라 정렬 기준 변경 가능)
        issues = open_issues + resolved_issues
        issues.sort(key=lambda x: x.get('close_at', ''))

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
        # 편의상 이슈의 status가 'RESOLVED'이고, 이슈의 정답 옵션(correct_option_id)과 
        # 사용자의 베팅(option_id)이 일치하는 경우를 '정답'으로 간주합니다.
        
        my_bets_resp = supabase.table('bets').select('issue_id, option_id').eq('user_id', user['id']).execute()
        my_bets = { b['issue_id']: b['option_id'] for b in (my_bets_resp.data or []) }
        
        wins = 0
        streak = 0
        recent_correct = []
        
        if my_bets:
            # RESOLVED 이슈 전체 조회 (최신 마감순 정렬)
            resolved_issues_resp = supabase.table('issues').select('id, title, correct_option_id').eq('status', 'RESOLVED').order('close_at', desc=True).execute()
            resolved_issues = resolved_issues_resp.data or []
            
            # 과거부터 현재 순으로 탐색하여 Streak 계산.
            # 가장 최근 이슈부터 확인해서 연속으로 맞췄는지 봅니다.
            for issue in resolved_issues:
                issue_id = issue['id']
                if issue_id in my_bets:
                    # 유저가 참여한 경우 -> 정답 확인
                    if str(my_bets[issue_id]) == str(issue.get('correct_option_id')):
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
                    if str(my_bets[issue_id]) == str(issue.get('correct_option_id')):
                        streak += 1
                    else:
                        break

        # 3. 유저 닉네임 및 마지막 변경 시간 추가 조회
        user_info_resp = supabase.table('users').select('nickname, last_nickname_changed_at').eq('id', user['id']).single().execute()
        nickname = user_info_resp.data.get('nickname') if user_info_resp.data else "Anonymous"
        last_changed = user_info_resp.data.get('last_nickname_changed_at') if user_info_resp.data else None

        return jsonify({
            "success": True, 
            "data": {
                "rank": rank,
                "streak": streak,
                "wins": wins,
                "recent_correct": recent_correct,
                "nickname": nickname,
                "last_nickname_changed_at": last_changed
            }
        }), 200

    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@api_bp.route('/leaderboard', methods=['GET'])
def get_leaderboard():
    """포인트 순 상위 10명 조회 (이메일 대신 닉네임 노출)"""
    try:
        res = supabase.table('users').select('nickname, points').order('points', desc=True).limit(10).execute()
        return jsonify({"success": True, "data": res.data}), 200
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@api_bp.route('/users/nickname', methods=['POST'])
def change_nickname():
    """닉네임 변경 API (1일 1회 제한)"""
    user = session.get('user')
    if not user or not user.get('id'):
        return jsonify({"success": False, "error": "로그인이 필요합니다."}), 401
    
    data = request.get_json()
    new_nickname = data.get('nickname', '').strip()
    
    if not new_nickname or len(new_nickname) < 2 or len(new_nickname) > 20:
        return jsonify({"success": False, "error": "닉네임은 2자 이상 20자 이하로 입력해 주세요."}), 400

    try:
        from datetime import datetime, timezone, timedelta
        
        # 최신 유저 정보 조회
        user_resp = supabase.table('users').select('*').eq('id', user['id']).single().execute()
        if not user_resp.data:
            return jsonify({"success": False, "error": "유저 정보를 찾을 수 없습니다."}), 404
            
        current_data = user_resp.data
        last_changed_str = current_data.get('last_nickname_changed_at')
        
        now = datetime.now(timezone.utc)
        
        if last_changed_str:
            last_changed = datetime.fromisoformat(last_changed_str.replace('Z', '+00:00'))
            # 24시간 검증
            if now - last_changed < timedelta(hours=24):
                return jsonify({"success": False, "error": "닉네임 변경은 1일에 한 번만 가능합니다."}), 429
                
        # 닉네임 업데이트
        now_iso = now.isoformat()
        update_resp = supabase.table('users').update({
            'nickname': new_nickname,
            'last_nickname_changed_at': now_iso
        }).eq('id', user['id']).execute()
        
        # 세션 업데이트
        session_user = session.get('user')
        session_user['nickname'] = new_nickname
        session_user['last_nickname_changed_at'] = now_iso
        session['user'] = session_user
        session.modified = True
        
        return jsonify({"success": True, "message": "닉네임이 성공적으로 변경되었습니다."}), 200
        
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

    # 1.5. 중복 투표 방지 (DB의 UNIQUE 제약조건 외에도 선제적 방어) [GA]
    try:
        existing_bet = supabase.table('bets').select('id').eq('user_id', user.get('id')).eq('issue_id', issue_id).execute()
        if existing_bet.data:
            return jsonify({"success": False, "error": "이미 참여한 투표입니다!"}), 409
    except Exception as e:
        return jsonify({"success": False, "error": f"중복 체크 오류: {e}"}), 500

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

# ==============================================================
# Admin 전용 (수동) 로컬 전용 테스트 API 추가
# ==============================================================
import os

def check_local_dev():
    """로컬 환경(개발)인지 검증. 실서버에서는 악용 방지를 위해 차단."""
    # Render 등에 배포 시 FLASK_ENV가 'production'으로 되어 있거나, HOST가 로컬이 아닌 경우 차단 가능
    if os.environ.get('FLASK_ENV') == 'production':
        return False
    return True

@api_bp.route('/admin/force-issue-gen', methods=['POST'])
def force_issue_generation():
    """Gemini API를 호출하여 즉시 문제 생성"""
    if not check_local_dev():
        return jsonify({"success": False, "error": "This API is only allowed in local development environment."}), 403
    
    try:
        from reset_and_generate import reset_and_generate
        reset_and_generate()
        return jsonify({"success": True, "message": "강제 이슈 생성이 완료되었습니다."}), 200
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@api_bp.route('/admin/force-resolve', methods=['POST'])
def force_resolve_issues():
    """모든 OPEN 이슈에 무작위 정답을 배정하고 RESOLVED 처리 후 포인트 지급"""
    if not check_local_dev():
        return jsonify({"success": False, "error": "This API is only allowed in local development environment."}), 403
    
    try:
        import random
        from datetime import datetime
        
        # 1. OPEN된 모든 이슈 가져오기
        issues_resp = supabase.table('issues').select('id, title').eq('status', 'OPEN').execute()
        open_issues = issues_resp.data or []
        
        if not open_issues:
            return jsonify({"success": True, "message": "OPEN 상태인 이슈가 없습니다."}), 200
        
        resolved_count = 0
        now_str = datetime.now().isoformat()
        
        for issue in open_issues:
            issue_id = issue['id']
            # 각 이슈의 옵션 가져오기 (Yes / No)
            opts_resp = supabase.table('options').select('id').eq('issue_id', issue_id).execute()
            options = opts_resp.data or []
            
            if not options:
                continue
                
            # 무작위 정답 선택 (AI가 아직 정답을 안 정해준 상태이므로 강제 무작위)
            winning_opt = random.choice(options)['id']
            
            # 이슈 상태를 RESOLVED로 변경하고 정답 기록
            supabase.table('issues').update({
                'status': 'RESOLVED',
                'correct_option_id': winning_opt,
                'resolved_at': now_str
            }).eq('id', issue_id).execute()
            
            # (추가) 정산 로직이 있다면 여기서 정답 맞춘 사람에게 포인트 지급
            # 임시 정산 로직: 맞춘 사람에게 +300 포인트, 틀린사람 -50 포인트 등... (원래는 상금 풀 배분이 올바름)
            bets_resp = supabase.table('bets').select('user_id, option_id').eq('issue_id', issue_id).execute()
            bets = bets_resp.data or []
            
            for bet in bets:
                try:
                    user_data_resp = supabase.table('users').select('points').eq('id', bet['user_id']).single().execute()
                    if user_data_resp.data:
                        current_points = int(user_data_resp.data.get('points', 0))
                        
                        # 이겼으면 1000포인트 줌, 졌으면 50포인트 삭감
                        if bet['option_id'] == winning_opt:
                            new_points = current_points + 1000
                        else:
                            new_points = max(0, current_points - 50)
                            
                        supabase.table('users').update({'points': new_points}).eq('id', bet['user_id']).execute()
                except Exception as e:
                    print(f"포인트 지급 오류 (User: {bet['user_id']}): {e}")
            
            resolved_count += 1
            
        return jsonify({"success": True, "message": f"{resolved_count}개 이슈 결과 랜덤 정산 및 포인트 지급 성공!"}), 200
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"success": False, "error": str(e)}), 500
