from flask_socketio import emit, join_room
from flask import request
from flask_jwt_extended import decode_token
from app.token_store import is_token_revoked
from app.models.user import User
from app.models.message import Message
from app.models.group import GroupChat
from app.security import validate_message_text, validate_username
import os
import firebase_admin
from firebase_admin import credentials, messaging
import threading
import time
from datetime import datetime

# Import socketio instance from __init__.py
from app import socketio

# Initialize Firebase Admin SDK
try:
    cred_path = os.path.join(os.getcwd(), 'serviceAccountKey.json')
    if os.path.exists(cred_path):
        cred = credentials.Certificate(cred_path)
        firebase_admin.initialize_app(cred)
        print("Firebase Admin initialized")
    else:
        print("serviceAccountKey.json not found. FCM will be disabled.")
except Exception as e:
    print(f"Error initializing Firebase Admin: {e}")

active_connections = {}
call_rooms = {}
pending_calls = {}
pending_call_timeouts = {}
CALL_RING_TIMEOUT = 30  # seconds to wait for answer before cleanup
group_call_rooms = {}
_SOCKET_RATE_LIMIT = {}
_SOCKET_RATE_LOCK = threading.Lock()


def _get_username_by_sid(sid):
    for username, socket_id in active_connections.items():
        if socket_id == sid:
            return username
    return None


def _check_socket_rate_limit(sid, event, limit=10, window_seconds=1):
    """Simple per-sid per-event in-memory rate limiter for socket events."""
    now = time.time()
    key = f"{sid}:{event}"
    with _SOCKET_RATE_LOCK:
        entry = _SOCKET_RATE_LIMIT.get(key)
        if not entry or now - entry['start'] >= window_seconds:
            _SOCKET_RATE_LIMIT[key] = {'start': now, 'count': 1}
            return True
        if entry['count'] >= limit:
            entry['count'] += 1
            return False
        entry['count'] += 1
        return True


@socketio.on('connect')
def handle_connect():
    """Handle user connection"""
    try:
        token = request.args.get('token')
        if token:
            decoded_token = decode_token(token)
            jti = decoded_token.get('jti')
            if is_token_revoked(jti):
                print(f"Rejected socket connect: token revoked (jti={jti})")
                return
            username = decoded_token['sub']
            User.set_online(username, request.sid)
            active_connections[username] = request.sid
            emit('user_online', {'username': username, 'is_online': True}, broadcast=True)
            print(f"User {username} connected with sid {request.sid}")
    except Exception as e:
        print(f"Connection error: {e}")

@socketio.on('disconnect')
def handle_disconnect():
    """Handle user disconnection"""
    try:
        for username, socket_id in list(active_connections.items()):
            if socket_id == request.sid:
                User.set_offline(username)
                del active_connections[username]
                emit('user_offline', {'username': username, 'is_online': False}, broadcast=True)
                for room_id, room in list(call_rooms.items()):
                    participants = room.get('participants', {})
                    if username in participants:
                        del participants[username]
                        emit('call_participant_left', {'room_id': room_id, 'username': username}, room=room_id)
                    if not participants:
                        del call_rooms[room_id]
                # If user disconnects while a call is still ringing, clean up using central helper
                for call_id, call_data in list(pending_calls.items()):
                    caller = call_data.get('caller_username')
                    callee = call_data.get('callee_username')
                    if username in {caller, callee}:
                        _cleanup_pending_call(call_id, reason='peer_disconnected')
                print(f"User {username} disconnected")
                break
    except Exception as e:
        print(f"Disconnection error: {e}")

@socketio.on('new_message')
def handle_new_message(data):
    # Rate-limit message events per-socket to avoid floods
    if not _check_socket_rate_limit(request.sid, 'new_message', limit=5, window_seconds=1):
        print(f"Dropping new_message from sid {request.sid} due to rate limit")
        return
    try:
        sender = data.get('sender')
        receiver = data.get('receiver')
        valid_sender, sender_or_message = validate_username(sender)
        valid_receiver, receiver_or_message = validate_username(receiver)
        if not valid_sender or not valid_receiver:
            return
        receiver_socket_id = active_connections.get(receiver_or_message)
        if receiver_socket_id:
            payload = {**data, 'sender': sender_or_message, 'receiver': receiver_or_message}
            emit('message_received', payload, to=receiver_socket_id)
            message_id = payload.get('id')
            if message_id:
                Message.mark_as_delivered(message_id)
                _emit_to_username(sender_or_message, 'message_delivered', {
                    'message_id': message_id,
                    'message_ids': [message_id],
                    'conversation_with': receiver_or_message,
                    'sender_username': sender_or_message,
                    'receiver_username': receiver_or_message,
                    'status': 'delivered',
                })
    except Exception as e:
        print(f"Error handling new_message: {e}")


@socketio.on('typing')
def handle_typing(data):
    # Basic rate-limit for typing events
    if not _check_socket_rate_limit(request.sid, 'typing', limit=8, window_seconds=1):
        return
    sender = data.get('sender')
    receiver = data.get('receiver')
    is_typing = bool(data.get('is_typing', True))
    valid_receiver, receiver_or_message = validate_username(receiver)
    valid_sender, sender_or_message = validate_username(sender)
    if not valid_receiver or not valid_sender:
        return
    receiver_socket_id = active_connections.get(receiver_or_message)
    if receiver_socket_id:
        emit(
            'user_typing',
            {
                **data,
                'receiver': receiver_or_message,
                'sender': sender_or_message,
                'is_typing': is_typing,
            },
            to=receiver_socket_id,
        )


@socketio.on('message_ack')
def handle_message_ack(data):
    """Client acknowledges message receipt — mark delivered if needed."""
    try:
        message_ids = data.get('message_ids', [])
        ack_username = data.get('username')
        if not isinstance(message_ids, list) or not ack_username:
            return
        valid_user, user_or_msg = validate_username(ack_username)
        if not valid_user:
            return
        delivered = []
        for mid in message_ids:
            msg = Message.mark_as_delivered(mid)
            if msg:
                delivered.append(mid)
        if delivered:
            # notify sender(s) that these messages were delivered
            for mid in delivered:
                msg = Message.get_messages().get(mid) if hasattr(Message, 'get_messages') else None
            # Optionally emit a summary ack back to the client
            emit('message_ack_received', {'message_ids': delivered}, to=request.sid)
    except Exception as e:
        print(f"Error handling message_ack: {e}")


@socketio.on('heartbeat')
def handle_heartbeat(data):
    """Heartbeat from client to update last_seen without changing call state."""
    try:
        username = data.get('username')
        if not username:
            return
        valid_user, user_or_msg = validate_username(username)
        if not valid_user:
            return
        # update last_seen timestamp without toggling online status
        try:
            User.set_online(user_or_msg, request.sid)
        except Exception:
            # fallback: update last_seen field directly
            users = User.get_all_users()
            if username in users:
                users[username]['last_seen'] = datetime.utcnow().isoformat()
                from app.models.user import save_users
                save_users(users)
        emit('heartbeat_ack', {'timestamp': datetime.utcnow().isoformat()}, to=request.sid)
    except Exception as e:
        print(f"Heartbeat error: {e}")


@socketio.on('group_typing')
def handle_group_typing(data):
    group_id = data.get('group_id')
    username = data.get('username')
    is_typing = bool(data.get('is_typing', True))
    if not group_id or not username:
        return
    valid_username_value, username_or_message = validate_username(username)
    if not valid_username_value:
        return
    group = GroupChat.get_group(group_id)
    if not group:
        return
    for member in group.get('members', []):
        if member != username_or_message:
            _emit_to_username(member, 'group_user_typing', {**data, 'username': username_or_message, 'is_typing': is_typing})

def _emit_to_username(username, event, payload):
    socket_id = active_connections.get(username)
    if socket_id:
        try:
            print(f"Emitting event '{event}' to user '{username}' (sid={socket_id})")
            # Use socketio.emit instead of plain emit for REST-to-Socket compatibility
            socketio.emit(event, payload, to=socket_id)
            return True
        except Exception as e:
            print(f"Error emitting to {username} (sid={socket_id}): {e}")
            return False
    else:
        print(f"Target user {username} not found in active_connections.")
        return False


def _are_friends(user_a, user_b):
    users = User.get_all_users()
    friends_a = set(users.get(user_a, {}).get('friends', []))
    friends_b = set(users.get(user_b, {}).get('friends', []))
    return user_b in friends_a and user_a in friends_b


def _cleanup_pending_call(call_id, reason='timeout'):
    """Clean up a pending call and notify parties."""
    try:
        call_data = pending_calls.pop(call_id, None)
        # Cancel and remove any timeout timer
        timeout = pending_call_timeouts.pop(call_id, None)
        try:
            if timeout:
                timeout.cancel()
        except Exception:
            pass

        if not call_data:
            return

        caller = call_data.get('caller_username')
        callee = call_data.get('callee_username')
        room_id = call_data.get('room_id')

        print(f'📞 Call {call_id} cleaned up: {reason}')

        for user in (caller, callee):
            if user:
                _emit_to_username(user, 'call_ended', {
                    'call_id': call_id,
                    'room_id': room_id,
                    'reason': reason,
                })

        # remove empty call room
        if room_id and room_id in call_rooms:
            participants = call_rooms[room_id].get('participants', {})
            if not participants:
                try:
                    del call_rooms[room_id]
                except Exception:
                    pass
    except Exception as e:
        print(f'Error cleaning up call {call_id}: {e}')

def _send_fcm_notification(username, data):
    """Send FCM notification to a user"""
    token = User.get_fcm_token(username)
    if not token:
        print(f"⚠️ Cannot send FCM to {username}: No token found")
        return False
        
    try:
        # Build flexible payload depending on message type
        payload_type = str(data.get('type', 'notification'))
        fcm_data = {'type': payload_type}

        if payload_type == 'incoming_call':
            fcm_data.update({
                'call_id': str(data.get('call_id', '')),
                'room_id': str(data.get('room_id', '')),
                'caller_username': str(data.get('caller_username', '')),
                'caller_display_name': str(data.get('caller_display_name', '')),
                'caller_profile_image': str(data.get('caller_profile_image', '')),
                'call_type': str(data.get('call_type', 'video')),
            })
        elif payload_type in ('message', 'text'):
            # message payload: include sender, snippet, id
            text = str(data.get('text') or data.get('body') or '')
            snippet = (text[:120] + '...') if len(text) > 120 else text
            fcm_data.update({
                'message_id': str(data.get('id', '')),
                'sender': str(data.get('sender', '')),
                'conversation_with': str(data.get('sender', '')),
                'text_snippet': snippet,
            })
        else:
            # Generic keys pass-through
            for k, v in (data or {}).items():
                try:
                    fcm_data[str(k)] = str(v)
                except Exception:
                    continue

        message = messaging.Message(
            data=fcm_data,
            token=token,
            android=messaging.AndroidConfig(priority='high'),
            apns=messaging.APNSConfig(payload=messaging.APNSPayload(aps=messaging.Aps(content_available=True))),
        )
        response = messaging.send(message)
        print(f"FCM sent to {username}: {response} payload_type={payload_type}")
        return True
    except Exception as e:
        print(f"Error sending FCM to {username}: {e}")
        return False

@socketio.on('call_user')
def handle_call_user(data):
    callee_username = data.get('callee_username')
    caller_username = data.get('caller_username')
    call_id = data.get('call_id')
    room_id = data.get('room_id')
    print(f"Call from {caller_username} to {callee_username}")

    valid_caller, caller_or_message = validate_username(caller_username)
    valid_callee, callee_or_message = validate_username(callee_username)
    if not valid_caller or not valid_callee:
        return

    if not _are_friends(caller_or_message, callee_or_message):
        _emit_to_username(caller_or_message, 'call_rejected', {
            'callee_username': callee_or_message,
            'reason': 'not_friends',
            'message': 'Call is allowed only between friends',
            'call_type': data.get('call_type') or 'video',
        })
        return

    if call_id and caller_or_message and callee_or_message:
        pending_calls[call_id] = {
            'caller_username': caller_or_message,
            'callee_username': callee_or_message,
            'room_id': room_id,
            'call_type': data.get('call_type') or 'video',
        }
        # start cleanup timeout in case call is not answered
        try:
            timer = threading.Timer(CALL_RING_TIMEOUT, lambda: _cleanup_pending_call(call_id, reason='no_answer'))
            timer.daemon = True
            timer.start()
            pending_call_timeouts[call_id] = timer
        except Exception as e:
            print(f"Error starting call timeout for {call_id}: {e}")

    if callee_or_message:
        sent_socket = _emit_to_username(callee_or_message, 'incoming_call', {**data, 'caller_username': caller_or_message, 'callee_username': callee_or_message})
        call_type = data.get('call_type') or 'video'
        caller_display_name = data.get('caller_display_name') or caller_or_message or 'Unknown'
        call_text = f"Incoming {call_type} call from {caller_display_name}"

        try:
            Message.send_message(
                caller_or_message,
                callee_or_message,
                text=call_text,
                message_type='call',
            )
        except Exception as e:
            print(f"Error saving call message for {callee_username}: {e}")

        # ALWAYS send FCM as a backup, or only if socket fails?
        # For calls, it's better to send both to ensure high reliability.
        _send_fcm_notification(callee_or_message, {**data, 'caller_username': caller_or_message, 'callee_username': callee_or_message})
        
        if not sent_socket and caller_username:
            pass

@socketio.on('call_add_participant')
def handle_call_add_participant(data):
    invitee_username = data.get('invitee_username')
    inviter_username = data.get('inviter_username')
    print(f"Adding participant {invitee_username} to call room {data.get('room_id')}")

    valid_invitee, invitee_or_message = validate_username(invitee_username)
    valid_inviter, inviter_or_message = validate_username(inviter_username)
    if not valid_invitee or not valid_inviter:
        return

    if not _are_friends(inviter_or_message, invitee_or_message):
        _emit_to_username(inviter_or_message, 'call_rejected', {
            'callee_username': invitee_or_message,
            'reason': 'not_friends',
            'message': 'Call is allowed only between friends',
            'call_type': data.get('call_type') or 'video',
        })
        return

    if invitee_or_message:
        sent = _emit_to_username(invitee_or_message, 'incoming_call', {
            'call_id': data.get('call_id'),
            'room_id': data.get('room_id'),
            'caller_username': inviter_or_message,
            'caller_display_name': data.get('inviter_display_name', inviter_or_message),
            'caller_profile_image': data.get('inviter_profile_image'),
            'callee_username': invitee_or_message,
            'callee_display_name': data.get('invitee_display_name', invitee_or_message),
            'callee_profile_image': data.get('invitee_profile_image'),
            'call_type': data.get('call_type') or 'video',
        })
        if not sent and inviter_or_message:
            _emit_to_username(inviter_or_message, 'missed_call', {
                'caller_username': inviter_or_message,
                'callee_username': invitee_or_message,
                'username': invitee_or_message,
                'reason': 'callee_not_found',
                'callType': data.get('call_type') or data.get('callType')
            })


@socketio.on('group_message')
def handle_group_message(data):
    group_id = data.get('group_id')
    sender = data.get('sender')
    text = data.get('text', '')
    message_type = data.get('message_type', 'text')
    timestamp = data.get('timestamp')
    if not group_id or not sender:
        return
    valid_sender, sender_or_message = validate_username(sender)
    if not valid_sender:
        return
    group = GroupChat.get_group(group_id)
    if not group or sender_or_message not in group.get('members', []):
        return
    message_type = str(message_type or 'text').strip().lower()
    if message_type == 'text':
        valid_text, text_or_message = validate_message_text(text)
        if not valid_text:
            return
        text = text_or_message
    success, result = GroupChat.send_group_message(
        group_id,
        sender_or_message,
        text,
        message_type,
        timestamp=timestamp,
    )
    if not success:
        _emit_to_username(sender, 'group_message_error', {'message': result})
        return
    group = GroupChat.get_group(group_id)
    for member in group.get('members', []):
        _emit_to_username(member, 'group_message_received', result)


@socketio.on('message_seen')
def handle_message_seen(data):
    message_ids = data.get('message_ids') or []
    reader_username = data.get('reader_username')
    sender_username = data.get('sender_username')
    if not isinstance(message_ids, list) or not reader_username or not sender_username:
        return

    valid_reader, reader_or_message = validate_username(reader_username)
    valid_sender, sender_or_message = validate_username(sender_username)
    if not valid_reader or not valid_sender:
        return

    seen_ids = []
    for message_id in message_ids:
        message = Message.mark_as_seen(message_id)
        if message and message.get('sender') == sender_or_message and message.get('receiver') == reader_or_message:
            seen_ids.append(message_id)

    if seen_ids:
        _emit_to_username(sender_or_message, 'message_seen', {
            'message_ids': seen_ids,
            'reader_username': reader_or_message,
            'sender_username': sender_or_message,
            'conversation_with': reader_or_message,
            'status': 'seen',
        })


@socketio.on('group_call_user')
def handle_group_call_user(data):
    group_id = data.get('group_id')
    room_id = data.get('room_id')
    caller_username = data.get('caller_username')
    call_type = data.get('call_type') or 'video'
    if not group_id or not room_id or not caller_username:
        return
    group = GroupChat.get_group(group_id)
    if not group:
        return
    group_call_rooms[room_id] = {
        'group_id': group_id,
        'call_type': call_type,
        'participants': set([caller_username]),
    }
    for member in group.get('members', []):
        if member == caller_username:
            continue
        _emit_to_username(member, 'incoming_group_call', data)


@socketio.on('group_call_join')
def handle_group_call_join(data):
    room_id = data.get('room_id')
    username = data.get('username')
    if not room_id or not username:
        return
    join_room(room_id)
    room = group_call_rooms.setdefault(room_id, {'participants': set(), 'group_id': data.get('group_id')})
    room['participants'].add(username)
    emit('group_call_participant_joined', {'room_id': room_id, 'username': username}, room=room_id, include_self=False)


@socketio.on('group_call_end')
def handle_group_call_end(data):
    room_id = data.get('room_id')
    group_id = data.get('group_id')
    ended_by = data.get('username')
    call_type = data.get('call_type') or 'video'
    if not room_id:
        return
    room = group_call_rooms.pop(room_id, None)
    participants = sorted(list(room.get('participants', set()))) if room else []
    emit('group_call_ended', data, room=room_id)
    if group_id and ended_by:
        GroupChat.log_call(group_id, ended_by, call_type, participants or [ended_by], status='ended')

@socketio.on('accept_call')
def handle_accept_call(data):
    room_id = data.get('room_id')
    call_id = data.get('call_id')
    caller_username = data.get('caller_username')
    callee_username = data.get('callee_username')

    if call_id:
        # cancel timeout for this pending call
        timeout = pending_call_timeouts.pop(call_id, None)
        try:
            if timeout:
                timeout.cancel()
        except Exception:
            pass
        pending_calls.pop(call_id, None)

    room = call_rooms.setdefault(room_id, {'participants': {}, 'call_id': data.get('call_id')})
    if caller_username and caller_username not in room['participants']:
        room['participants'][caller_username] = {
            'display_name': data.get('caller_display_name', caller_username),
            'profile_image': data.get('caller_profile_image'),
            'is_local': False,
        }
    room['participants'][callee_username] = {
        'display_name': data.get('callee_display_name', callee_username),
        'profile_image': data.get('callee_profile_image'),
        'is_local': True,
    }

    _emit_to_username(caller_username, 'call_accepted', data)

@socketio.on('reject_call')
def handle_reject_call(data):
    caller_username = data.get('caller_username')
    call_id = data.get('call_id')
    print(f"Call rejected by {data.get('callee_username')}")
    if call_id:
        timeout = pending_call_timeouts.pop(call_id, None)
        try:
            if timeout:
                timeout.cancel()
        except Exception:
            pass
        pending_calls.pop(call_id, None)
    _emit_to_username(caller_username, 'call_rejected', data)
    _emit_to_username(caller_username, 'call_declined', {
        'username': data.get('callee_username'),
        'callType': data.get('call_type') or data.get('callType'),
        'message': 'Call declined by recipient'
    })

    try:
        caller_display_name = data.get('caller_display_name') or caller_username or 'Unknown'
        callee_username = data.get('callee_username')
        callee_display_name = data.get('callee_display_name') or callee_username or 'Unknown'
        Message.send_message(
            callee_username,
            caller_username,
            text=f"Missed {data.get('call_type') or 'video'} call from {callee_display_name}",
            message_type='call',
        )
    except Exception as e:
        print(f"Error saving missed call message for {caller_username}: {e}")

@socketio.on('end_call')
def handle_end_call(data):
    call_id = data.get('call_id')
    room_id = data.get('room_id')
    ended_by = data.get('username')
    print(f"Call ended in room {room_id}")

    # Handle unanswered/ringing calls where callee may not have joined the room yet.
    if call_id:
        # cancel timeout and remove pending call
        timeout = pending_call_timeouts.pop(call_id, None)
        try:
            if timeout:
                timeout.cancel()
        except Exception:
            pass
        pending = pending_calls.pop(call_id, None)
        if pending:
            caller = pending.get('caller_username')
            callee = pending.get('callee_username')
            for user in {caller, callee}:
                if user and user != ended_by:
                    _emit_to_username(user, 'call_ended', {
                        'call_id': call_id,
                        'room_id': pending.get('room_id') or room_id,
                        'reason': 'call_ended',
                    })

    if room_id:
        emit('call_ended', data, room=room_id)
        if room_id in call_rooms:
            del call_rooms[room_id]

@socketio.on('call_join_room')
def handle_call_join_room(data):
    room_id = data.get('room_id')
    username = data.get('username')
    if room_id and username:
        join_room(room_id)
        room = call_rooms.setdefault(room_id, {'participants': {}, 'call_id': data.get('call_id')})
        room['participants'][username] = {
            'display_name': data.get('display_name', username),
            'profile_image': data.get('profile_image'),
            'is_local': True,
        }

        emit('call_participant_joined', {
            'room_id': room_id,
            'username': username,
            'display_name': data.get('display_name', username),
            'profile_image': data.get('profile_image'),
        }, room=room_id, include_self=False)

        participants = [
            {
                'username': k,
                'display_name': v.get('display_name', k),
                'profile_image': v.get('profile_image'),
            }
            for k, v in room['participants'].items()
        ]
        emit('call_room_state', {'room_id': room_id, 'participants': participants})

@socketio.on('call_offer')
def handle_call_offer(data):
    to_username = data.get('to')
    from_username = data.get('from')
    print(f"SDP Offer: {from_username} -> {to_username}")
    if to_username:
        _emit_to_username(to_username, 'call_offer', data)

@socketio.on('call_answer')
def handle_call_answer(data):
    to_username = data.get('to')
    from_username = data.get('from')
    print(f"SDP Answer: {from_username} -> {to_username}")
    if to_username:
        _emit_to_username(to_username, 'call_answer', data)

@socketio.on('call_ice_candidate')
def handle_call_ice(data):
    to_username = data.get('to')
    from_username = data.get('from')
    candidate = data.get('candidate', '')
    cand_type = "unknown"
    if "typ host" in candidate: cand_type = "HOST"
    elif "typ srflx" in candidate: cand_type = "STUN"
    elif "typ relay" in candidate: cand_type = "TURN"

    print(f"ICE Candidate ({cand_type}): {from_username} -> {to_username}")
    if to_username:
        _emit_to_username(to_username, 'call_ice_candidate', data)

@socketio.on('chess_join')
def handle_chess_join(data):
    tournament_id = data.get('tournament_id')
    if tournament_id:
        room_name = f"chess_{tournament_id}"
        join_room(room_name)
        print(f"DEBUG: User {request.sid} joined chess room: {room_name}")

@socketio.on('chess_move')
def handle_chess_move(data):
    tournament_id = data.get('tournament_id')
    if tournament_id:
        room_name = f"chess_{tournament_id}"
        print(f"DEBUG: Broadcasting chess_move to room {room_name}")
        # Use socketio.emit to ensure the event reaches everyone in the room
        socketio.emit('chess_move_received', data, room=room_name, include_self=False)

@socketio.on('story_reaction_notification')
def handle_story_reaction_notification(data):
    _emit_to_username(data.get('recipient_username'), 'story_reaction', data)

@socketio.on('note_reaction_notification')
def handle_note_reaction_notification(data):
    _emit_to_username(data.get('recipient_username'), 'note_reaction', data)
