from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from app.models.user import get_users, save_users, User
from app.security import validate_username, require_json_body
from app.websocket import _emit_to_username

friends_bp = Blueprint('friends', __name__)


@friends_bp.route('/request', methods=['POST'])
@jwt_required()
def send_friend_request():
    current = get_jwt_identity()
    data, err = require_json_body()
    if err:
        return err
    target = (data.get('username') or '').strip()
    valid, val_or_msg = validate_username(target)
    if not valid:
        return jsonify({'success': False, 'message': val_or_msg}), 400
    if target == current:
        return jsonify({'success': False, 'message': 'Cannot friend yourself'}), 400

    users = get_users()
    if target not in users:
        return jsonify({'success': False, 'message': 'User not found'}), 404

    # add pending request
    tgt = users[target]
    tgt_requests = tgt.get('friend_requests', [])
    if current in tgt_requests:
        return jsonify({'success': False, 'message': 'Request already sent'}), 400
    tgt_requests.append(current)
    tgt['friend_requests'] = tgt_requests
    save_users(users)
    # Notify recipient in real-time if connected
    try:
        _emit_to_username(target, 'friend_request', {
            'from': current,
            'username': current,
            'message': f'{current} sent you a friend request'
        })
        _emit_to_username(current, 'friend_request_sent', {
            'to': target,
            'username': target,
            'message': f'Friend request sent to {target}'
        })
    except Exception:
        pass
    return jsonify({'success': True, 'message': 'Friend request sent'}), 200


@friends_bp.route('/respond', methods=['POST'])
@jwt_required()
def respond_friend_request():
    current = get_jwt_identity()
    data, err = require_json_body()
    if err:
        return err
    requester = (data.get('username') or '').strip()
    accept = bool(data.get('accept', False))
    valid, val_or_msg = validate_username(requester)
    if not valid:
        return jsonify({'success': False, 'message': val_or_msg}), 400

    users = get_users()
    if current not in users:
        return jsonify({'success': False, 'message': 'Current user not found'}), 404
    if requester not in users:
        return jsonify({'success': False, 'message': 'Requester not found'}), 404

    current_user = users[current]
    reqs = current_user.get('friend_requests', [])
    pending_exists = requester in reqs
    if pending_exists:
        reqs.remove(requester)
    current_user['friend_requests'] = reqs

    if accept:
        # add to both friends lists
        current_friends = set(current_user.get('friends', []))
        requester_friends = set(users[requester].get('friends', []))
        current_friends.add(requester)
        requester_friends.add(current)
        current_user['friends'] = sorted(list(current_friends))
        users[requester]['friends'] = sorted(list(requester_friends))
        # Notify requester in real-time if connected
        try:
            _emit_to_username(requester, 'friend_request_responded', {
                'from': current,
                'accepted': True,
                'username': current,
                'message': f'{current} accepted your friend request',
            })
            # Also notify current user that friendship was established
            _emit_to_username(current, 'friend_added', {
                'username': requester,
                'message': f'You are now friends with {requester}'
            })
        except Exception:
            pass
        # Additionally emit updated friend lists to both users for immediate sync
        try:
            _emit_to_username(requester, 'friend_list_update', {
                'username': requester,
                'friends': users[requester].get('friends', []),
            })
            _emit_to_username(current, 'friend_list_update', {
                'username': current,
                'friends': users[current].get('friends', []),
            })
        except Exception:
            pass

    users[current] = current_user
    save_users(users)
    return jsonify({
        'success': True,
        'accepted': accept,
        'stale_request': not pending_exists,
    }), 200


@friends_bp.route('/contacts', methods=['GET'])
@jwt_required()
def list_contacts():
    current = get_jwt_identity()
    users = get_users()
    if current not in users:
        return jsonify({'success': False, 'message': 'User not found'}), 404
    me = users[current]
    friends = me.get('friends', [])
    friends_info = []
    for f in friends:
        u = users.get(f)
        if u:
            friends_info.append({
                'username': f,
                'first_name': u.get('first_name', ''),
                'last_name': u.get('last_name', ''),
                'profile_image': u.get('profile_image'),
                'is_online': User.is_online(f),
                'last_seen': u.get('last_seen', ''),
            })
    return jsonify({'success': True, 'friends': friends_info}), 200


@friends_bp.route('/requests', methods=['GET'])
@jwt_required()
def get_requests():
    current = get_jwt_identity()
    users = get_users()
    if current not in users:
        return jsonify({'success': False, 'message': 'User not found'}), 404
    reqs = users[current].get('friend_requests', [])
    return jsonify({'success': True, 'requests': reqs}), 200


@friends_bp.route('/check-pair', methods=['GET'])
@jwt_required()
def check_pair():
    """Debug endpoint: returns friends arrays for two users (u1 and u2 query params)."""
    u1 = (request.args.get('u1') or '').strip()
    u2 = (request.args.get('u2') or '').strip()
    if not u1 or not u2:
        return jsonify({'success': False, 'message': 'u1 and u2 query params required'}), 400
    users = get_users()
    if u1 not in users or u2 not in users:
        return jsonify({'success': False, 'message': 'One or both users not found', 'users': list(users.keys())}), 404

    return jsonify({
        'success': True,
        'u1': u1,
        'u2': u2,
        'u1_friends': users[u1].get('friends', []),
        'u2_friends': users[u2].get('friends', []),
        'u1_requests': users[u1].get('friend_requests', []),
        'u2_requests': users[u2].get('friend_requests', []),
    }), 200
