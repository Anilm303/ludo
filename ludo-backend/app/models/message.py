import base64
import os
import uuid
from datetime import datetime

from app.storage import create_media_filename, delete_local_media_file, store_media_bytes, _storage_mode
from app.postgres_store import execute, fetch_all, fetch_one, json_value

UPLOADS_FOLDER = os.getenv('MESSAGE_UPLOADS_FOLDER', 'uploads/messages')
os.makedirs(UPLOADS_FOLDER, exist_ok=True)
MAX_MESSAGE_SIZE = int(os.getenv('MAX_MESSAGE_SIZE', str(10 * 1024 * 1024)))


def _normalize_timestamp(value=None):
    if not value:
        return datetime.utcnow().isoformat()
    if isinstance(value, datetime):
        return value.isoformat()
    text = str(value).strip()
    if not text:
        return datetime.utcnow().isoformat()
    try:
        return datetime.fromisoformat(text.replace('Z', '+00:00')).isoformat()
    except Exception:
        return text


class Message:
    """Message model for one-to-one chat"""

    def __init__(self, sender, receiver, text='', message_type='text',
                 media_url=None, thumbnail_url=None, reply_to_id=None,
                 timestamp=None, status='sent', is_read=False, reactions=None):
        self.id = str(uuid.uuid4())
        self.sender = sender
        self.receiver = receiver
        self.text = text
        self.message_type = message_type
        self.media_url = media_url
        self.thumbnail_url = thumbnail_url
        self.reply_to_id = reply_to_id
        self.timestamp = _normalize_timestamp(timestamp)
        self.status = status
        self.is_read = is_read
        self.reactions = reactions or {}

    def to_dict(self):
        return {
            'id': self.id,
            'sender': self.sender,
            'receiver': self.receiver,
            'text': self.text,
            'message_type': self.message_type,
            'media_url': self.media_url,
            'thumbnail_url': self.thumbnail_url,
            'reply_to_id': self.reply_to_id,
            'timestamp': self.timestamp,
            'status': self.status,
            'is_read': self.is_read,
            'reactions': self.reactions,
        }

    @staticmethod
    def _row_to_dict(row):
        if not row:
            return None
        return {
            'id': row['id'],
            'sender': row['sender'],
            'receiver': row['receiver'],
            'text': row.get('text', ''),
            'message_type': row.get('message_type', 'text'),
            'media_url': row.get('media_url'),
            'thumbnail_url': row.get('thumbnail_url'),
            'reply_to_id': row.get('reply_to_id'),
            'timestamp': row.get('timestamp').isoformat() if row.get('timestamp') else '',
            'status': row.get('status', 'sent'),
            'is_read': row.get('is_read', False),
            'reactions': row.get('reactions') or {},
        }

    @staticmethod
    def _insert_message(message):
        execute(
            """
            INSERT INTO messages (
                id, sender, receiver, message_type, text, media_url, thumbnail_url,
                reply_to_id, timestamp, status, is_read, reactions
            ) VALUES (
                %(id)s, %(sender)s, %(receiver)s, %(message_type)s, %(text)s, %(media_url)s, %(thumbnail_url)s,
                %(reply_to_id)s, %(timestamp)s, %(status)s, %(is_read)s, %(reactions)s
            )
            """,
            {
                'id': message.id,
                'sender': message.sender,
                'receiver': message.receiver,
                'message_type': message.message_type,
                'text': message.text.strip() if message.text else '',
                'media_url': message.media_url,
                'thumbnail_url': message.thumbnail_url,
                'reply_to_id': message.reply_to_id,
                'timestamp': message.timestamp,
                'status': message.status,
                'is_read': message.is_read,
                'reactions': json_value(message.reactions or {}),
            }
        )
        return message

    @staticmethod
    def send_message(sender, receiver, text='', message_type='text',
                     media_base64=None, media_path=None, reply_to_id=None, timestamp=None):
        from .user import User

        sender_user = User.get_by_username(sender)
        receiver_user = User.get_by_username(receiver)

        if not sender_user:
            return False, 'Sender not found'
        if not receiver_user:
            return False, 'Receiver not found'

        media_url = None
        thumbnail_url = None
        if message_type == 'text':
            if not text or text.strip() == '':
                return False, 'Message cannot be empty'
        elif message_type == 'call':
            if not text or text.strip() == '':
                text = 'Incoming call'
        elif message_type in ['image', 'video', 'audio']:
            if media_path:
                media_url = media_path
            elif media_base64:
                extension = 'mp4' if message_type == 'video' else ('m4a' if message_type == 'audio' else 'jpg')
                filename = create_media_filename(extension)
                try:
                    media_bytes = base64.b64decode(media_base64)
                    if len(media_bytes) > MAX_MESSAGE_SIZE:
                        return False, 'File too large'
                    media_url = store_media_bytes(
                        'messages',
                        filename,
                        media_bytes,
                        content_type=(
                            'video/mp4' if message_type == 'video' else 'audio/mp4' if message_type == 'audio' else 'image/jpeg'
                        ),
                    )
                    if message_type == 'video':
                        try:
                            from app.utils import generate_video_thumbnail
                            thumb_filename = f"{filename.split('.')[0]}_thumb.jpg"
                            thumb_filepath = os.path.join(UPLOADS_FOLDER, thumb_filename)
                            local_video_path = os.path.join(UPLOADS_FOLDER, filename)
                            if os.path.exists(local_video_path) and generate_video_thumbnail(local_video_path, thumb_filepath):
                                with open(thumb_filepath, 'rb') as thumb_file:
                                    thumbnail_url = store_media_bytes('messages', thumb_filename, thumb_file.read(), content_type='image/jpeg')
                                if _storage_mode() == 'postgres':
                                    delete_local_media_file('messages', thumb_filename)
                        except Exception as thumb_error:
                            print(f"Video thumbnail generation failed: {thumb_error}")
                        if _storage_mode() == 'postgres':
                            delete_local_media_file('messages', filename)
                    elif _storage_mode() == 'postgres':
                        delete_local_media_file('messages', filename)
                except Exception as e:
                    print(f"Error saving file: {e}")
                    return False, 'Failed to save media file'
            else:
                return False, f'{message_type} data required'
        else:
            return False, 'Invalid message type'

        message = Message(sender, receiver, text.strip() if text else '', message_type, media_url, thumbnail_url, reply_to_id, timestamp=timestamp)
        Message._insert_message(message)
        return True, message

    @staticmethod
    def send_message_bytes(sender, receiver, text='', message_type='text',
                           media_bytes=None, media_path=None, reply_to_id=None, timestamp=None):
        from .user import User

        sender_user = User.get_by_username(sender)
        receiver_user = User.get_by_username(receiver)

        if not sender_user:
            return False, 'Sender not found'
        if not receiver_user:
            return False, 'Receiver not found'

        media_url = None
        thumbnail_url = None
        if message_type == 'text':
            if not text or text.strip() == '':
                return False, 'Message cannot be empty'
        elif message_type == 'call':
            if not text or text.strip() == '':
                text = 'Incoming call'
        elif message_type in ['image', 'video', 'audio']:
            if media_path:
                media_url = media_path
            elif media_bytes:
                if len(media_bytes) > MAX_MESSAGE_SIZE:
                    return False, 'File too large'
                extension = 'mp4' if message_type == 'video' else ('m4a' if message_type == 'audio' else 'jpg')
                filename = create_media_filename(extension)
                try:
                    media_url = store_media_bytes(
                        'messages',
                        filename,
                        media_bytes,
                        content_type=(
                            'video/mp4' if message_type == 'video' else 'audio/mp4' if message_type == 'audio' else 'image/jpeg'
                        ),
                    )
                    if message_type == 'video':
                        try:
                            from app.utils import generate_video_thumbnail
                            thumb_filename = f"{filename.split('.')[0]}_thumb.jpg"
                            thumb_filepath = os.path.join(UPLOADS_FOLDER, thumb_filename)
                            local_video_path = os.path.join(UPLOADS_FOLDER, filename)
                            if os.path.exists(local_video_path) and generate_video_thumbnail(local_video_path, thumb_filepath):
                                with open(thumb_filepath, 'rb') as thumb_file:
                                    thumbnail_url = store_media_bytes('messages', thumb_filename, thumb_file.read(), content_type='image/jpeg')
                                if _storage_mode() == 'postgres':
                                    delete_local_media_file('messages', thumb_filename)
                        except Exception as thumb_error:
                            print(f"Video thumbnail generation failed: {thumb_error}")
                        if _storage_mode() == 'postgres':
                            delete_local_media_file('messages', filename)
                    elif _storage_mode() == 'postgres':
                        delete_local_media_file('messages', filename)
                except Exception as e:
                    print(f"Error saving file: {e}")
                    return False, 'Failed to save media file'
            else:
                return False, f'{message_type} data required'
        else:
            return False, 'Invalid message type'

        message = Message(sender, receiver, text.strip() if text else '', message_type, media_url, thumbnail_url, reply_to_id, timestamp=timestamp)
        Message._insert_message(message)
        return True, message

    @staticmethod
    def get_messages(receiver_username=None, last_sync=None):
        query = "SELECT * FROM messages"
        params = {}
        filters = []

        if receiver_username:
            filters.append("receiver = %(receiver)s")
            params['receiver'] = receiver_username

        if last_sync:
            filters.append("timestamp > %(last_sync)s")
            params['last_sync'] = last_sync

        if filters:
            query += " WHERE " + " AND ".join(filters)

        query += " ORDER BY timestamp ASC"

        return {row['id']: Message._row_to_dict(row) for row in fetch_all(query, params)}

    @staticmethod
    def react_to_message(message_id, reactor, emoji):
        row = fetch_one('SELECT reactions FROM messages WHERE id = %(id)s', {'id': message_id})
        if not row:
            return False, {}
        reactions = row.get('reactions') or {}
        user_reactions = reactions.get(reactor, [])
        if emoji in user_reactions:
            user_reactions.remove(emoji)
        else:
            user_reactions.append(emoji)
        if user_reactions:
            reactions[reactor] = user_reactions
        else:
            reactions.pop(reactor, None)
        execute('UPDATE messages SET reactions = %(reactions)s WHERE id = %(id)s', {'id': message_id, 'reactions': json_value(reactions)})
        return True, reactions

    @staticmethod
    def delete_message(message_id, requestor_username):
        row = fetch_one('SELECT sender FROM messages WHERE id = %(id)s', {'id': message_id})
        if not row:
            return False, 'Message not found'
        if row['sender'] != requestor_username:
            return False, 'Unauthorized'
        execute("""
            UPDATE messages
            SET text = %(text)s, message_type = 'deleted', media_url = NULL, thumbnail_url = NULL
            WHERE id = %(id)s
        """, {'id': message_id, 'text': 'This message was unsent'})
        return True, Message._row_to_dict(fetch_one('SELECT * FROM messages WHERE id = %(id)s', {'id': message_id}))

    @staticmethod
    def get_conversation(user1, user2, limit=50, offset=0):
        rows = fetch_all(
            """
            SELECT * FROM messages
            WHERE (sender = %(user1)s AND receiver = %(user2)s)
               OR (sender = %(user2)s AND receiver = %(user1)s)
            ORDER BY timestamp DESC
            LIMIT %(limit)s OFFSET %(offset)s
            """,
            {'user1': user1, 'user2': user2, 'limit': limit, 'offset': offset},
        )
        conversation = [Message._row_to_dict(row) for row in rows]
        conversation.reverse()
        return conversation
    

    @staticmethod
    def get_all_conversations(username):
        rows = fetch_all(
            """
            SELECT DISTINCT CASE
                WHEN sender = %(username)s THEN receiver
                ELSE sender
            END AS other_user
            FROM messages
            WHERE sender = %(username)s OR receiver = %(username)s
            ORDER BY other_user
            """,
            {'username': username},
        )
        return [row['other_user'] for row in rows]

    @staticmethod
    def unread_count_between(user1, user2):
        row = fetch_one(
            """
            SELECT COUNT(*)::int AS count
            FROM messages
            WHERE sender = %(sender)s AND receiver = %(receiver)s AND is_read = FALSE
            """,
            {'sender': user2, 'receiver': user1},
        )
        return row['count'] if row else 0

    @staticmethod
    def mark_conversation_as_read(current_user, other_user):
        rows = fetch_all(
            """
            SELECT id FROM messages
            WHERE sender = %(sender)s AND receiver = %(receiver)s AND is_read = FALSE
            """,
            {'sender': other_user, 'receiver': current_user},
        )
        changed_ids = []
        for row in rows:
            changed_ids.append(row['id'])
            execute("UPDATE messages SET is_read = TRUE, status = 'seen' WHERE id = %(id)s", {'id': row['id']})
        return changed_ids

    @staticmethod
    def get_last_message(user1, user2):
        row = fetch_one(
            """
            SELECT * FROM messages
            WHERE (sender = %(user1)s AND receiver = %(user2)s)
               OR (sender = %(user2)s AND receiver = %(user1)s)
            ORDER BY timestamp DESC
            LIMIT 1
            """,
            {'user1': user1, 'user2': user2},
        )
        return Message._row_to_dict(row) if row else None

    @staticmethod
    def mark_as_read(message_id):
        execute("UPDATE messages SET is_read = TRUE, status = 'seen' WHERE id = %(id)s", {'id': message_id})
        row = fetch_one('SELECT * FROM messages WHERE id = %(id)s', {'id': message_id})
        return Message._row_to_dict(row) if row else None

    @staticmethod
    def mark_as_delivered(message_id):
        execute("UPDATE messages SET status = 'delivered' WHERE id = %(id)s", {'id': message_id})
        row = fetch_one('SELECT * FROM messages WHERE id = %(id)s', {'id': message_id})
        return Message._row_to_dict(row) if row else None

    @staticmethod
    def mark_as_seen(message_id):
        execute("UPDATE messages SET is_read = TRUE, status = 'seen' WHERE id = %(id)s", {'id': message_id})
        row = fetch_one('SELECT * FROM messages WHERE id = %(id)s', {'id': message_id})
        return Message._row_to_dict(row) if row else None


def get_messages():
    return Message.get_messages()


def save_messages(messages):
    for message_id, message_data in messages.items():
        execute(
            """
            INSERT INTO messages (
                id, sender, receiver, message_type, text, media_url, thumbnail_url,
                reply_to_id, timestamp, status, is_read, reactions
            ) VALUES (
                %(id)s, %(sender)s, %(receiver)s, %(message_type)s, %(text)s, %(media_url)s, %(thumbnail_url)s,
                %(reply_to_id)s, %(timestamp)s, %(status)s, %(is_read)s, %(reactions)s
            )
            ON CONFLICT (id) DO UPDATE SET
                sender = EXCLUDED.sender,
                receiver = EXCLUDED.receiver,
                message_type = EXCLUDED.message_type,
                text = EXCLUDED.text,
                media_url = EXCLUDED.media_url,
                thumbnail_url = EXCLUDED.thumbnail_url,
                reply_to_id = EXCLUDED.reply_to_id,
                timestamp = EXCLUDED.timestamp,
                status = EXCLUDED.status,
                is_read = EXCLUDED.is_read,
                reactions = EXCLUDED.reactions
            """,
            {
                'id': message_id,
                'sender': message_data.get('sender'),
                'receiver': message_data.get('receiver'),
                'message_type': message_data.get('message_type'),
                'text': message_data.get('text', ''),
                'media_url': message_data.get('media_url'),
                'thumbnail_url': message_data.get('thumbnail_url'),
                'reply_to_id': message_data.get('reply_to_id'),
                'timestamp': message_data.get('timestamp'),
                'status': message_data.get('status', 'sent'),
                'is_read': message_data.get('is_read', False),
                'reactions': json_value(message_data.get('reactions', {})),
            }
        )
