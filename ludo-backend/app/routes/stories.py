from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from app.models.story import Story
from app.models.user import User
from app.security import rate_limit, require_json_body, validate_media_type

stories_bp = Blueprint('stories', __name__, url_prefix='/api/stories')


@stories_bp.route('/upload', methods=['POST'])
@jwt_required()
@rate_limit(limit=12, window_seconds=60, scope='story_upload')
def upload_story():
    """Upload a new story (image or video)"""
    try:
        current_user = get_jwt_identity()
        print(f"\n{'='*60}")
        print(f"📤 Story upload request from: {current_user}")
        print(f"{'='*60}")

        # Support two upload modes:
        # 1) multipart/form-data with file field 'media' and form field 'media_type'
        # 2) JSON body with 'media_base64' and 'media_type' (existing fallback)

        media_bytes = None
        media_type = None

        # Multipart upload (preferred for large files / videos)
        if 'media' in request.files:
            print(f"📁 Multipart upload detected")
            file = request.files.get('media')
            if file:
                media_bytes = file.read()
                # determine media type from form or mime
                media_type = request.form.get('media_type') or ('video' if file.mimetype.startswith('video') else 'image')
                print(f"✅ File read: {file.filename} ({len(media_bytes)} bytes, MIME: {file.mimetype})")
                print(f"🎬 Media type: {media_type}")

        # Fallback to JSON base64 payload
        if media_bytes is None:
            print(f"📋 Fallback to JSON base64 payload")
            data, error_response = require_json_body()
            if error_response:
                return error_response
            if 'media_base64' not in data or 'media_type' not in data:
                print(f"❌ Missing required fields in JSON")
                return jsonify({
                    'success': False,
                    'message': 'Missing media_base64 or media_type'
                }), 400

            import base64 as _b64
            try:
                media_bytes = _b64.b64decode(data['media_base64'])
                print(f"✅ Base64 decoded: {len(media_bytes)} bytes")
            except Exception as e:
                print(f"❌ Base64 decode error: {e}")
                return jsonify({'success': False, 'message': f'Invalid base64 data: {e}'}), 400

            media_type = data['media_type']  # 'image' or 'video'

        valid_media_type, media_type_or_message = validate_media_type(media_type)
        if not valid_media_type:
            print(f"❌ Invalid media_type: {media_type}")
            return jsonify({
                'success': False,
                'message': media_type_or_message
            }), 400
        media_type = media_type_or_message

        if not media_bytes:
            return jsonify({'success': False, 'message': 'Media file is empty'}), 400

        # Upload story using raw bytes (avoid another decode step)
        print(f"⏳ Uploading {media_type} ({len(media_bytes)} bytes)...")
        story = Story.upload_story_bytes(
            username=current_user,
            media_bytes=media_bytes,
            media_type=media_type
        )

        if story:
            print(f"✅ Story created: {story['id']}")
            try:
                from app import socketio
                socketio.emit('new_story', {
                    'username': current_user,
                    'story': story
                })
                print(f"📡 WebSocket event emitted")
            except Exception as e:
                print(f"⚠️ WebSocket emit error: {e}")

            response = jsonify({
                'success': True,
                'message': 'Story uploaded successfully',
                'story': story
            })
            print(f"✅ Returning 201 response")
            print(f"{'='*60}\n")
            return response, 201
        else:
            print(f"❌ Story creation failed")
            return jsonify({
                'success': False,
                'message': 'Failed to upload story'
            }), 500
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        import traceback
        print(traceback.format_exc())
        return jsonify({
            'success': False,
            'message': f'Server error: {str(e)}'
        }), 500

    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'Error: {str(e)}'
        }), 500


@stories_bp.route('/active', methods=['GET'])
@jwt_required()
def get_active_stories():
    """Get all active stories from all users"""
    try:
        current_user = get_jwt_identity()

        # Clean up expired stories first
        Story.cleanup_expired_stories()

        # Get all active stories
        all_stories = Story.get_active_stories()

        # Group by user
        stories_by_user = {}
        for story in all_stories:
            username = story['username']
            if username not in stories_by_user:
                stories_by_user[username] = []
            stories_by_user[username].append(story)

        # Enhance with user profile info
        result = []
        for username, user_stories in stories_by_user.items():
            user = User.get_by_username(username)
            if user:
                result.append({
                    'username': username,
                    'displayName': f"{user.first_name} {user.last_name}".strip(),
                    'profileImage': user.profile_image,
                    'isOnline': User.is_online(username),
                    'stories': user_stories,
                    'hasUnviewed': any(
                        current_user not in [v.get('username') for v in s.get('viewers', [])] for s in user_stories
                    )
                })

        return jsonify({
            'success': True,
            'stories': result
        }), 200

    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'Error: {str(e)}'
        }), 500


@stories_bp.route('/<story_id>/view', methods=['POST'])
@jwt_required()
@rate_limit(limit=60, window_seconds=60, scope='story_view')
def mark_story_viewed(story_id):
    """Mark a story as viewed"""
    try:
        current_user = get_jwt_identity()

        success = Story.mark_story_viewed(story_id, current_user)

        if success:
            return jsonify({
                'success': True,
                'message': 'Story marked as viewed'
            }), 200
        else:
            return jsonify({
                'success': False,
                'message': 'Story not found'
            }), 404

    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'Error: {str(e)}'
        }), 500


@stories_bp.route('/<story_id>/react', methods=['POST'])
@jwt_required()
@rate_limit(limit=60, window_seconds=60, scope='story_react')
def react_to_story(story_id):
    """Add/toggle an emoji reaction on a story"""
    try:
        current_user = get_jwt_identity()
        data, error_response = require_json_body()
        if error_response:
            return error_response
        emoji = data.get('emoji', '')

        if not emoji:
            return jsonify({'success': False, 'message': 'emoji is required'}), 400

        success, reactions, reaction_details, story_owner = Story.react_to_story(story_id, current_user, emoji)
        if not success:
            return jsonify({'success': False, 'message': 'Story not found'}), 404

        try:
            from app import socketio
            from app.websocket import active_connections
            from datetime import datetime
            
            # Emit notification to the story owner if it's not their own reaction
            if story_owner and story_owner != current_user:
                socket_id = active_connections.get(story_owner)
                if socket_id:
                    socketio.emit('story_reaction', {
                        'username': current_user,
                        'reaction': emoji,
                        'message': f'reacted {emoji} to your story',
                        'timestamp': datetime.now().isoformat()
                    }, to=socket_id)
        except Exception as e:
            print(f"Reaction notification error: {e}")

        return jsonify({
            'success': True,
            'reactions': reactions,
            'reaction_details': reaction_details
        }), 200

    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'Error: {str(e)}'
        }), 500


@stories_bp.route('/<story_id>', methods=['DELETE'])
@jwt_required()
@rate_limit(limit=20, window_seconds=60, scope='story_delete')
def delete_story(story_id):
    """Delete a story owned by the authenticated user."""
    try:
        current_user = get_jwt_identity()
        success, message = Story.delete_story(story_id, current_user)

        if not success:
            status_code = 404 if message == 'Story not found' else 403
            return jsonify({'success': False, 'message': message}), status_code

        return jsonify({'success': True, 'message': message}), 200

    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'Error: {str(e)}'
        }), 500


@stories_bp.route('/<story_id>/reactions', methods=['GET'])
@jwt_required()
def get_story_reactions(story_id):
    """Get all reactions for a story"""
    try:
        reactions = Story.get_story_reactions(story_id)
        return jsonify({'success': True, 'reactions': reactions}), 200
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'Error: {str(e)}'
        }), 500


@stories_bp.route('/<story_id>/viewers', methods=['GET'])
@jwt_required()
def get_story_viewers(story_id):
    """Get list of viewers for a story with timestamps"""
    try:
        viewers = Story.get_story_viewers(story_id)
        return jsonify({'success': True, 'viewers': viewers}), 200
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'Error: {str(e)}'
        }), 500


@stories_bp.route('/<story_id>/reaction-details', methods=['GET'])
@jwt_required()
def get_story_reaction_details(story_id):
    """Get detailed reaction info including timestamps"""
    try:
        reaction_details = Story.get_story_reaction_details(story_id)
        return jsonify({'success': True, 'reaction_details': reaction_details}), 200
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'Error: {str(e)}'
        }), 500


@stories_bp.route('/<story_id>/analytics', methods=['GET'])
@jwt_required()
def get_story_analytics(story_id):
    """Get combined analytics for a story (views + reactions with details)"""
    try:
        viewers = Story.get_story_viewers(story_id)
        reaction_details = Story.get_story_reaction_details(story_id)
        reactions = Story.get_story_reactions(story_id)
        
        return jsonify({
            'success': True,
            'views_count': len(viewers),
            'reactions_count': len(reactions),
            'viewers': viewers,
            'reaction_details': reaction_details,
            'reactions': reactions
        }), 200
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'Error: {str(e)}'
        }), 500
