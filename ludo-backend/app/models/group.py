import base64
import os
import uuid
from datetime import datetime

from app.postgres_store import execute, fetch_all, fetch_one, json_value
from app.storage import create_media_filename, delete_local_media_file, store_media_bytes, _storage_mode

UPLOADS_FOLDER = os.getenv('GROUP_UPLOADS_FOLDER', 'uploads/messages')
os.makedirs(UPLOADS_FOLDER, exist_ok=True)


class GroupChat:
    """Group chat backed by PostgreSQL."""

    @staticmethod
    def create_group(name, creator, member_usernames, avatar=None):
        unique_members = sorted(set([creator, *member_usernames]))
        if len(unique_members) < 2:
            return False, 'A group must include at least 2 members'

        group_id = str(uuid.uuid4())
        now = datetime.utcnow()
        execute(
            """
            INSERT INTO groups (
                id, name, avatar, created_by, admins, members,
                created_at, updated_at, last_message, last_message_time
            ) VALUES (
                %(id)s, %(name)s, %(avatar)s, %(created_by)s, %(admins)s, %(members)s,
                %(created_at)s, %(updated_at)s, %(last_message)s, %(last_message_time)s
            )
            """,
            {
                'id': group_id,
                'name': name.strip() or 'Untitled Group',
                'avatar': avatar,
                'created_by': creator,
                'admins': json_value([creator]),
                'members': json_value(unique_members),
                'created_at': now,
                'updated_at': now,
                'last_message': '',
                'last_message_time': now,
            }
        )
        return True, GroupChat.get_group(group_id)

    @staticmethod
    def list_groups_for_user(username):
        return fetch_all(
            """
            SELECT * FROM groups
            WHERE members ? %(username)s
            ORDER BY COALESCE(last_message_time, created_at) DESC
            """,
            {'username': username},
        )

    @staticmethod
    def get_group(group_id):
        return fetch_one('SELECT * FROM groups WHERE id = %(id)s', {'id': group_id})

    @staticmethod
    def add_member(group_id, requester, member_username):
        group = GroupChat.get_group(group_id)
        if not group:
            return False, 'Group not found'
        if requester not in (group.get('admins') or []):
            return False, 'Only group admins can add members'
        members = set(group.get('members') or [])
        if member_username in members:
            return False, 'User already in group'
        members.add(member_username)
        execute(
            "UPDATE groups SET members = %(members)s, updated_at = %(updated_at)s WHERE id = %(id)s",
            {'id': group_id, 'members': json_value(sorted(members)), 'updated_at': datetime.utcnow()},
        )
        return True, GroupChat.get_group(group_id)

    @staticmethod
    def remove_member(group_id, requester, member_username):
        group = GroupChat.get_group(group_id)
        if not group:
            return False, 'Group not found'
        if requester not in (group.get('admins') or []):
            return False, 'Only group admins can remove members'
        if member_username not in (group.get('members') or []):
            return False, 'User is not a member'
        if member_username == group.get('created_by'):
            return False, 'Group creator cannot be removed'
        members = [m for m in (group.get('members') or []) if m != member_username]
        admins = [a for a in (group.get('admins') or []) if a != member_username]
        execute(
            "UPDATE groups SET members = %(members)s, admins = %(admins)s, updated_at = %(updated_at)s WHERE id = %(id)s",
            {'id': group_id, 'members': json_value(members), 'admins': json_value(admins), 'updated_at': datetime.utcnow()},
        )
        return True, GroupChat.get_group(group_id)

    @staticmethod
    def set_admin(group_id, requester, member_username, is_admin):
        group = GroupChat.get_group(group_id)
        if not group:
            return False, 'Group not found'
        if requester not in (group.get('admins') or []):
            return False, 'Only group admins can update admin role'
        if member_username not in (group.get('members') or []):
            return False, 'User is not a member'

        admins = set(group.get('admins') or [])
        if is_admin:
            admins.add(member_username)
        else:
            if member_username == group.get('created_by'):
                return False, 'Group creator must remain admin'
            admins.discard(member_username)
        execute(
            "UPDATE groups SET admins = %(admins)s, updated_at = %(updated_at)s WHERE id = %(id)s",
            {'id': group_id, 'admins': json_value(sorted(admins)), 'updated_at': datetime.utcnow()},
        )
        return True, GroupChat.get_group(group_id)

    @staticmethod
    def send_group_message(group_id, sender, text, message_type='text', media_base64=None, media_bytes=None, timestamp=None):
        group = GroupChat.get_group(group_id)
        if not group:
            return False, 'Group not found'
        if sender not in (group.get('members') or []):
            return False, 'Not a group member'
        if message_type == 'text' and not text.strip():
            return False, 'Message cannot be empty'

        media_url = None
        thumbnail_url = None
        if message_type in ['image', 'video']:
            extension = 'mp4' if message_type == 'video' else 'jpg'
            filename = create_media_filename(extension)
            filepath = os.path.join(UPLOADS_FOLDER, filename)
            try:
                if media_bytes is not None:
                    with open(filepath, 'wb') as file_handle:
                        file_handle.write(media_bytes)
                elif media_base64:
                    with open(filepath, 'wb') as file_handle:
                        file_handle.write(base64.b64decode(media_base64))
                else:
                    return False, f'{message_type} data required'
                with open(filepath, 'rb') as file_handle:
                    media_url = store_media_bytes('messages', filename, file_handle.read(), content_type='video/mp4' if message_type == 'video' else 'image/jpeg')
                if message_type == 'video':
                    try:
                        from app.utils import generate_video_thumbnail

                        thumb_filename = f"{filename.split('.')[0]}_thumb.jpg"
                        thumb_filepath = os.path.join(UPLOADS_FOLDER, thumb_filename)
                        if generate_video_thumbnail(filepath, thumb_filepath):
                            with open(thumb_filepath, 'rb') as thumb_file:
                                thumbnail_url = store_media_bytes('messages', thumb_filename, thumb_file.read(), content_type='image/jpeg')
                            if _storage_mode() == 'postgres':
                                delete_local_media_file('messages', thumb_filename)
                    except Exception:
                        thumbnail_url = None
                if _storage_mode() == 'postgres':
                    delete_local_media_file('messages', filename)
            except Exception as exc:
                print(f'Error saving group media: {exc}')
                return False, 'Failed to save media file'

        message_id = str(uuid.uuid4())
        now = timestamp or datetime.utcnow().isoformat()
        message = {
            'id': message_id,
            'group_id': group_id,
            'sender': sender,
            'text': text.strip(),
            'message_type': message_type,
            'media_url': media_url,
            'thumbnail_url': thumbnail_url,
            'timestamp': now,
            'seen_by': [sender],
        }
        execute(
            """
            INSERT INTO group_messages (
                id, group_id, sender, text, message_type,
                media_url, thumbnail_url, timestamp, seen_by
            ) VALUES (
                %(id)s, %(group_id)s, %(sender)s, %(text)s, %(message_type)s,
                %(media_url)s, %(thumbnail_url)s, %(timestamp)s, %(seen_by)s
            )
            """,
            {
                **message,
                'seen_by': json_value(message['seen_by']),
            }
        )

        last_message = message['text'] if message['text'] else message_type.capitalize()
        execute(
            "UPDATE groups SET last_message = %(last_message)s, last_message_time = %(last_message_time)s, updated_at = %(updated_at)s WHERE id = %(id)s",
            {'id': group_id, 'last_message': last_message, 'last_message_time': now, 'updated_at': now},
        )
        return True, message

    @staticmethod
    def get_group_messages(group_id, requester):
        group = GroupChat.get_group(group_id)
        if not group:
            return False, 'Group not found'
        if requester not in (group.get('members') or []):
            return False, 'Not a group member'

        rows = fetch_all(
            'SELECT * FROM group_messages WHERE group_id = %(group_id)s ORDER BY timestamp',
            {'group_id': group_id},
        )
        return True, [
            {
                'id': row['id'],
                'group_id': row['group_id'],
                'sender': row['sender'],
                'text': row.get('text', ''),
                'message_type': row.get('message_type', 'text'),
                'media_url': row.get('media_url'),
                'thumbnail_url': row.get('thumbnail_url'),
                'timestamp': row.get('timestamp').isoformat() if row.get('timestamp') else '',
                'seen_by': row.get('seen_by') or [],
            }
            for row in rows
        ]

    @staticmethod
    def mark_group_seen(group_id, username):
        rows = fetch_all('SELECT id, seen_by FROM group_messages WHERE group_id = %(group_id)s', {'group_id': group_id})
        changed = False
        for row in rows:
            seen_by = set(row.get('seen_by') or [])
            if username not in seen_by:
                seen_by.add(username)
                execute('UPDATE group_messages SET seen_by = %(seen_by)s WHERE id = %(id)s', {'id': row['id'], 'seen_by': json_value(sorted(seen_by))})
                changed = True
        return changed

    @staticmethod
    def unread_count_for_group(group_id, username):
        row = fetch_one(
            """
            SELECT COUNT(*)::int AS count
            FROM group_messages
            WHERE group_id = %(group_id)s
              AND sender <> %(username)s
              AND NOT (seen_by ? %(username)s)
            """,
            {'group_id': group_id, 'username': username},
        )
        return row['count'] if row else 0

    @staticmethod
    def log_call(group_id, started_by, call_type, participants, status='completed'):
        call_id = str(uuid.uuid4())
        now = datetime.utcnow().isoformat()
        execute(
            """
            INSERT INTO group_call_history (
                id, group_id, started_by, call_type, participants,
                status, started_at, ended_at
            ) VALUES (
                %(id)s, %(group_id)s, %(started_by)s, %(call_type)s, %(participants)s,
                %(status)s, %(started_at)s, %(ended_at)s
            )
            """,
            {
                'id': call_id,
                'group_id': group_id,
                'started_by': started_by,
                'call_type': call_type,
                'participants': json_value(participants),
                'status': status,
                'started_at': now,
                'ended_at': now,
            }
        )
        return {
            'id': call_id,
            'group_id': group_id,
            'started_by': started_by,
            'call_type': call_type,
            'participants': participants,
            'status': status,
            'timestamp': now,
        }
