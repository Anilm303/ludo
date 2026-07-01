from flask import Blueprint, jsonify, request
from flask_jwt_extended import get_jwt_identity, jwt_required

from app.models.note import Note
from app.models.user import User
from app.security import rate_limit, require_json_body, validate_media_type, validate_message_text

notes_bp = Blueprint('notes', __name__, url_prefix='/api/notes')


@notes_bp.route('/upload', methods=['POST'])
@jwt_required()
@rate_limit(limit=12, window_seconds=60, scope='note_upload')
def upload_note():
    current_user = get_jwt_identity()
    data, error_response = require_json_body()
    if error_response:
        return error_response

    note_type = data.get('note_type', 'text')
    text_content = data.get('text_content', '')
    media_base64 = data.get('media_base64')

    valid_note_type, note_type_or_message = validate_media_type(note_type, allowed=('text', 'image', 'video'))
    if not valid_note_type:
        return jsonify({'success': False, 'message': note_type_or_message}), 400
    note_type = note_type_or_message

    if note_type == 'text':
        valid_text, text_or_message = validate_message_text(text_content, max_length=1000)
        if not valid_text:
            return jsonify({'success': False, 'message': text_or_message}), 400
        text_content = text_or_message
    elif not media_base64 or not isinstance(media_base64, str):
        return jsonify({'success': False, 'message': 'media_base64 is required for image and video notes'}), 400

    note = Note.upload_note(
        username=current_user,
        text_content=text_content,
        media_base64=media_base64,
        media_type=note_type,
    )

    if not note:
        return jsonify({
            'success': False,
            'message': 'Failed to upload note',
        }), 400

    try:
        from app import socketio
        socketio.emit('new_note', {
            'username': current_user,
            'note': note
        })
    except Exception as e:
        print(f"Websocket emit error: {e}")

    return jsonify({
        'success': True,
        'message': 'Note uploaded successfully',
        'note': note,
    }), 201


@notes_bp.route('/active', methods=['GET'])
@jwt_required()
def get_active_notes():
    current_user = get_jwt_identity()
    Note.cleanup_expired_notes()

    all_notes = Note.get_active_notes()
    notes_by_user = {}
    for note in all_notes:
        notes_by_user.setdefault(note['username'], []).append(note)

    result = []
    for username, user_notes in notes_by_user.items():
        user = User.get_by_username(username)
        if user:
            result.append({
                'username': username,
                'displayName': f"{user.first_name} {user.last_name}".strip(),
                'profileImage': user.profile_image,
                'isOnline': User.is_online(username),
                'notes': user_notes,
                'hasUnviewed': any(
                    current_user not in [viewer.get('username') for viewer in note.get('viewers', [])]
                    for note in user_notes
                ),
            })

    return jsonify({'success': True, 'notes': result}), 200


@notes_bp.route('/<note_id>/view', methods=['POST'])
@jwt_required()
@rate_limit(limit=60, window_seconds=60, scope='note_view')
def mark_note_viewed(note_id):
    current_user = get_jwt_identity()
    success = Note.mark_note_viewed(note_id, current_user)

    if not success:
        return jsonify({'success': False, 'message': 'Note not found'}), 404

    return jsonify({'success': True, 'message': 'Note marked as viewed'}), 200