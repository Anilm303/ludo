from flask import Blueprint, jsonify
from pathlib import Path
import os

debug_bp = Blueprint('debug', __name__)


@debug_bp.route('/db', methods=['GET'])
def db_check():
    """Simple debug endpoint to check database connectivity and local users.json."""
    result = {
        'db_url': os.getenv('DATABASE_URL') or '',
        'db_connected': False,
        'db_error': None,
        'local_user_store_exists': False,
    }

    # Check local users.json
    try:
        users_path = Path(__file__).resolve().parents[2] / 'data' / 'users.json'
        result['local_user_store_exists'] = users_path.exists()
    except Exception as e:
        result['local_user_store_check_error'] = str(e)

    # Try simple DB query if DATABASE_URL present
    try:
        from app.postgres_store import fetch_one, get_database_url

        # will raise if DATABASE_URL is missing or placeholder
        _ = get_database_url()
        row = fetch_one('SELECT 1 as ok')
        result['db_connected'] = bool(row)
    except Exception as e:
        result['db_error'] = str(e)

    return jsonify(result), 200
