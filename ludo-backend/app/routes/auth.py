from flask import Blueprint, jsonify, request
from flask_jwt_extended import (
    create_access_token,
    create_refresh_token,
    decode_token,
    get_jwt,
    get_jwt_identity,
    jwt_required,
)
from app.models.user import User
from app.token_store import revoke_token
from app.security import (
    rate_limit,
    require_json_body,
    validate_email,
    validate_name,
    validate_password,
    validate_username,
)
from app.password_reset import create_token_for_email, verify_and_consume_token

auth_bp = Blueprint('auth', __name__)

@auth_bp.route('/register', methods=['POST'])
@rate_limit(limit=5, window_seconds=60, scope='auth_register')
def register():
    """Register a new user"""
    try:
        data, error_response = require_json_body()
        if error_response:
            return error_response

        required_fields = ['username', 'email', 'first_name', 'last_name', 'password']
        missing_fields = [field for field in required_fields if not data.get(field)]
        if missing_fields:
            return jsonify({'success': False, 'message': f"Missing required fields: {', '.join(missing_fields)}"}), 400

        valid_username, username_or_message = validate_username(data.get('username'))
        if not valid_username:
            return jsonify({'success': False, 'message': username_or_message}), 400

        valid_email, email_or_message = validate_email(data.get('email'))
        if not valid_email:
            return jsonify({'success': False, 'message': email_or_message}), 400

        valid_first_name, first_name_or_message = validate_name(data.get('first_name'), 'First name')
        if not valid_first_name:
            return jsonify({'success': False, 'message': first_name_or_message}), 400

        valid_last_name, last_name_or_message = validate_name(data.get('last_name'), 'Last name')
        if not valid_last_name:
            return jsonify({'success': False, 'message': last_name_or_message}), 400

        valid_password, password_or_message = validate_password(data.get('password'))
        if not valid_password:
            return jsonify({'success': False, 'message': password_or_message}), 400

        # Register user
        success, result = User.register(username_or_message, email_or_message, first_name_or_message, last_name_or_message, password_or_message)

        if not success:
            return jsonify({'success': False, 'message': result}), 400

        # Create access token
        access_token = create_access_token(identity=username_or_message)
        refresh_token = create_refresh_token(identity=username_or_message)

        return jsonify({
            'success': True,
            'message': 'User registered successfully',
            'access_token': access_token,
            'refresh_token': refresh_token,
            'user': result.to_dict()
        }), 201
    except Exception as exc:
        return jsonify({'success': False, 'message': f'Authentication backend error: {exc}'}), 500

@auth_bp.route('/login', methods=['POST'])
@rate_limit(limit=8, window_seconds=60, scope='auth_login')
def login():
    """Login user"""
    try:
        data, error_response = require_json_body()
        if error_response:
            return error_response

        username = data.get('username', '')
        password = data.get('password', '')

        valid_username, username_or_message = validate_username(username)
        if not valid_username:
            return jsonify({'success': False, 'message': username_or_message}), 400

        valid_password, password_or_message = validate_password(password)
        if not valid_password:
            return jsonify({'success': False, 'message': password_or_message}), 400

        # Authenticate user
        success, result = User.login(username_or_message, password_or_message)

        if not success:
            return jsonify({'success': False, 'message': result}), 401

        # Mark user as online
        User.set_online(username_or_message)

        # Create access token
        access_token = create_access_token(identity=username_or_message)
        refresh_token = create_refresh_token(identity=username_or_message)

        return jsonify({
            'success': True,
            'message': 'Login successful',
            'access_token': access_token,
            'refresh_token': refresh_token,
            'user': result.to_dict()
        }), 200
    except Exception as exc:
        return jsonify({'success': False, 'message': f'Authentication backend error: {exc}'}), 500

@auth_bp.route('/refresh', methods=['POST'])
@jwt_required(refresh=True)
def refresh_token():
    """Exchange a refresh token for a new access token"""
    username = get_jwt_identity()
    user = User.get_by_username(username)
    if not user:
        return jsonify({'success': False, 'message': 'User not found'}), 404

    access_token = create_access_token(identity=username)
    return jsonify({
        'success': True,
        'message': 'Token refreshed successfully',
        'access_token': access_token,
        'user': user.to_dict(),
    }), 200

@auth_bp.route('/validate-token', methods=['GET'])
@jwt_required()
def validate_token():
    """Validate JWT token and return user info"""
    username = get_jwt_identity()
    user = User.get_by_username(username)
    
    if not user:
        return jsonify({'success': False, 'message': 'User not found'}), 404
    
    return jsonify({
        'success': True,
        'user': user.to_dict()
    }), 200

@auth_bp.route('/logout', methods=['POST'])
@jwt_required()
def logout():
    """Logout user and mark as offline"""
    username = get_jwt_identity()
    User.set_offline(username)
    jwt_payload = get_jwt()
    revoke_token(jwt_payload.get('jti'), token_type=jwt_payload.get('type', 'access'))

    data = None
    try:
        data = request.get_json(silent=True) or {}
    except Exception:
        data = {}
    refresh_token_value = data.get('refresh_token') if isinstance(data, dict) else None
    if refresh_token_value:
        try:
            decoded_refresh = decode_token(refresh_token_value)
            revoke_token(decoded_refresh.get('jti'), token_type=decoded_refresh.get('type', 'refresh'))
        except Exception:
            pass
    
    # If user has an active socket connection, attempt to disconnect it so
    # revoked tokens cannot be used to stay connected.
    try:
        from app import socketio
        from app import websocket as ws_handlers
        sid = ws_handlers.active_connections.get(username)
        if sid:
            try:
                socketio.disconnect(sid) 
            except Exception:
                # best-effort only
                pass
    except Exception:
        pass

    return jsonify({
        'success': True,
        'message': 'Logout successful'
    }), 200

@auth_bp.route('/update-fcm-token', methods=['POST'])
@jwt_required()
@rate_limit(limit=20, window_seconds=60, scope='auth_update_fcm_token')
def update_fcm_token():
    """Update user's FCM token"""
    username = get_jwt_identity()  
    data, error_response = require_json_body()
    if error_response:
        return error_response

    token = data.get('fcm_token')
    if not token or not str(token).strip():
        return jsonify({'success': False, 'message': 'FCM token required'}), 400
        
    success = User.set_fcm_token(username, token)
    if success:
        return jsonify({'success': True, 'message': 'FCM token updated'}), 200
    else:
        return jsonify({'success': False, 'message': 'Failed to update FCM token'}), 500

@auth_bp.route('/health', methods=['GET'])
def health():
    """Health check endpoint"""
    return jsonify({'status': 'healthy', 'service': 'chess-auth-api'}), 200


@auth_bp.route('/forgot-password', methods=['POST'])
@rate_limit(limit=5, window_seconds=60, scope='auth_forgot_password')
def forgot_password():
    data, error_response = require_json_body()
    if error_response:
        return error_response

    email = data.get('email', '')
    valid_email, email_or_message = validate_email(email)
    if not valid_email:
        return jsonify({'success': False, 'message': email_or_message}), 400

    success, result = create_token_for_email(email_or_message)

    # Prevent email enumeration: if the email is not found, still return a generic success message.
    if not success:
        if result == 'Email not found':
            return jsonify({'success': True, 'message': 'If the email is registered, a reset link was sent.'}), 200
        return jsonify({'success': False, 'message': result}), 400

    # If we return token in dev mode (controlled by PASSWORD_RESET_RETURN_TOKEN), include it for testing.
    if isinstance(result, dict) and result.get('dev'):
        return jsonify({'success': True, 'message': 'Password reset token created (dev)', 'token': result.get('token')}), 200

    return jsonify({'success': True, 'message': 'If the email is registered, a reset link was sent.'}), 200


@auth_bp.route('/reset-password', methods=['POST'])
@rate_limit(limit=5, window_seconds=60, scope='auth_reset_password')
def reset_password():
    data, error_response = require_json_body()
    if error_response:
        return error_response

    token = data.get('token', '')
    new_password = data.get('new_password', '')

    valid_password, password_or_message = validate_password(new_password)
    if not valid_password:
        return jsonify({'success': False, 'message': password_or_message}), 400

    success, message = verify_and_consume_token(token, password_or_message)
    if not success:
        return jsonify({'success': False, 'message': message}), 400

    return jsonify({'success': True, 'message': 'Password has been reset successfully'}), 200
