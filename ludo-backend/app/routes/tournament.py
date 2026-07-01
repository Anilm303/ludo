import os
import uuid
from flask import Blueprint, request, jsonify, current_app
from app.postgres_store import fetch_all, fetch_one, execute
from datetime import datetime

from flask_jwt_extended import jwt_required, get_jwt_identity

# Blueprint for tournament endpoints
tournament_bp = Blueprint('tournament', __name__)

# Helper to convert Decimal to float for JSON serialization
def _decimal_to_float(value):
    try:
        return float(value)
    except Exception:
        return value

# Create a tournament
@tournament_bp.route('/create', methods=['POST'])
@jwt_required()
def create_tournament():
    data = request.get_json(silent=True) or {}
    required = ['title', 'game_type', 'entry_fee', 'max_players']
    missing = [k for k in required if k not in data]
    if missing:
        return jsonify({
            'success': False,
            'message': f"Missing fields: {', '.join(missing)}"
        }), 400
    
    owner = get_jwt_identity()
    tid = str(uuid.uuid4()) # Generate UUID in Python for compatibility

    # Insert tournament
    query = """
        INSERT INTO tournaments (id, title, game_type, entry_fee, max_players, owner, status, created_at, prize_pool)
        VALUES (%(id)s, %(title)s, %(game_type)s, %(entry_fee)s, %(max_players)s, %(owner)s, 'open', NOW(), 0.0)
        RETURNING id, title, game_type, entry_fee, max_players, owner, status, created_at
    """
    params = {
        'id': tid,
        'title': data['title'],
        'game_type': data['game_type'],
        'entry_fee': data['entry_fee'],
        'max_players': data['max_players'],
        'owner': owner
    }
    try:
        res = fetch_one(query, params)
        return jsonify({
            'success': True,
            'tournament': {k: _decimal_to_float(v) for k, v in res.items()}
        })
    except Exception as e:
        current_app.logger.exception('Failed to create tournament')
        return jsonify({'success': False, 'message': f"Database error: {str(e)}"}), 500

# List all tournaments
@tournament_bp.route('', methods=['GET'])
@jwt_required(optional=True)
def list_tournaments():
    try:
        query = "SELECT * FROM tournaments ORDER BY created_at DESC"
        rows = fetch_all(query)

        if rows is None:
            return jsonify({'success': True, 'tournaments': []})

        tournaments = []
        for row in rows:
            t = {k: _decimal_to_float(v) for k, v in row.items()}
            # Safe way to count paid participants
            try:
                count_query = "SELECT COUNT(*)::int as count FROM tournament_participants WHERE tournament_id = %(tid)s AND status = 'paid'"
                count_res = fetch_one(count_query, {'tid': t['id']})
                t['paid_players'] = count_res['count'] if count_res else 0
            except:
                t['paid_players'] = 0
            tournaments.append(t)

        return jsonify({'success': True, 'tournaments': tournaments})
    except Exception as e:
        current_app.logger.error(f"Error in list_tournaments: {e}")
        return jsonify({'success': False, 'message': 'Internal Server Error', 'error': str(e)}), 500

# Get tournament details
@tournament_bp.route('/<tid>', methods=['GET'])
@jwt_required(optional=True)
def get_tournament(tid):
    query = "SELECT * FROM tournaments WHERE id = %(tid)s"
    row = fetch_one(query, {'tid': tid})
    if not row:
        return jsonify({'success': False, 'message': 'Tournament not found'}), 404

    t = {k: _decimal_to_float(v) for k, v in row.items()}

    # Get participants
    participants_query = "SELECT * FROM tournament_participants WHERE tournament_id = %(tid)s"
    participants = fetch_all(participants_query, {'tid': tid})

    # Strictly count only those with status 'paid'
    paid_participants = [p for p in participants if p.get('status') == 'paid']
    paid_count = len(paid_participants)

    # Accurate Prize Pool Calculation: Entry Fee * Paid Count
    entry_fee = float(t.get('entry_fee', 0))
    accurate_prize_pool = round(entry_fee * paid_count, 2)

    t['paid_players'] = paid_count
    t['prize_pool'] = accurate_prize_pool

    # Sync DB if there's a discrepancy
    if abs(float(t.get('prize_pool', 0)) - accurate_prize_pool) > 0.01:
        execute("UPDATE tournaments SET prize_pool = %(pool)s WHERE id = %(tid)s",
                {'pool': accurate_prize_pool, 'tid': tid})

    return jsonify({
        'success': True,
        'tournament': t,
        'participants': participants
    })

# Delete tournament (Only by Owner)
@tournament_bp.route('/<tid>', methods=['DELETE'])
@jwt_required()
def delete_tournament(tid):
    try:
        user_id = get_jwt_identity()

        # 1. Check if tournament exists
        check_query = "SELECT owner, status FROM tournaments WHERE id = %(tid)s"
        tournament = fetch_one(check_query, {'tid': tid})

        if not tournament:
            return jsonify({'success': False, 'message': 'Tournament not found'}), 404

        # 2. Check ownership
        if tournament['owner'] != user_id:
            return jsonify({'success': False, 'message': 'Unauthorized: Only the creator can delete this'}), 403

        # 3. Prevent delete if someone has already paid
        try:
            count_query = "SELECT COUNT(*)::int as count FROM tournament_participants WHERE tournament_id = %(tid)s AND status = 'paid'"
            count_res = fetch_one(count_query, {'tid': tid})
            if count_res and count_res['count'] > 0:
                 return jsonify({'success': False, 'message': 'Cannot delete: Players have already paid'}), 400
        except:
            pass

        # 4. Perform Delete
        execute("DELETE FROM tournament_participants WHERE tournament_id = %(tid)s", {'tid': tid})
        execute("DELETE FROM tournaments WHERE id = %(tid)s", {'tid': tid})

        return jsonify({'success': True, 'message': 'Tournament deleted successfully'}), 200

    except Exception as e:
        current_app.logger.error(f"Error deleting tournament: {e}")
        return jsonify({'success': False, 'message': 'Server error during delete', 'error': str(e)}), 500

# Join tournament
@tournament_bp.route('/<tid>/join', methods=['POST'])
@jwt_required()
def join_tournament(tid):
    user_id = get_jwt_identity()

    # 1. First check if already joined to avoid constraint error
    check_query = "SELECT * FROM tournament_participants WHERE tournament_id = %(tid)s AND user_id = %(uid)s"
    existing = fetch_one(check_query, {'tid': tid, 'uid': user_id})

    if existing:
        return jsonify({
            'success': True,
            'message': 'Already joined',
            'participant': {k: _decimal_to_float(v) for k, v in existing.items()}
        }), 200

    # 2. Try to insert new participant
    insert_query = """
        INSERT INTO tournament_participants (tournament_id, user_id, status, joined_at)
        VALUES (%(tid)s, %(uid)s, 'joined', NOW())
        RETURNING id, tournament_id, user_id, status, joined_at
    """
    try:
        participant = fetch_one(insert_query, {'tid': tid, 'uid': user_id})
        if not participant:
             # If insert didn't return a row but didn't throw error, check once more
             existing = fetch_one(check_query, {'tid': tid, 'uid': user_id})
             if existing:
                 return jsonify({'success': True, 'participant': {k: _decimal_to_float(v) for k, v in existing.items()}})
             return jsonify({'success': False, 'message': 'Failed to join'}), 500

        return jsonify({
            'success': True,
            'participant': {k: _decimal_to_float(v) for k, v in participant.items()}
        }), 200
    except Exception as e:
        # 3. IF DUPLICATE ERROR OCCURS (Final fallback)
        # Catch "duplicate key" or "already exists" and return existing record
        err_str = str(e).lower()
        if 'duplicate' in err_str or 'already exists' in err_str:
            existing = fetch_one(check_query, {'tid': tid, 'uid': user_id})
            if existing:
                return jsonify({
                    'success': True,
                    'message': 'Already joined',
                    'participant': {k: _decimal_to_float(v) for k, v in existing.items()}
                }), 200

        current_app.logger.exception('Failed to join tournament')
        return jsonify({'success': False, 'message': f"Join error: {str(e)}"}), 500

