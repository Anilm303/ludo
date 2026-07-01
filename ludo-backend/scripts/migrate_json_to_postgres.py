"""Migration script: import legacy JSON/log state into Postgres.

Usage:
  set DATABASE_URL=postgresql+psycopg2://user:pass@host:5432/chess_db
  python scripts/migrate_json_to_postgres.py
"""
import os
import sys
import json
import mimetypes
import tempfile
from uuid import uuid5, NAMESPACE_URL
from sqlalchemy import create_engine, text

PROJECT_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), '..'))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)


DATABASE_URL = os.getenv('DATABASE_URL')
if not DATABASE_URL:
    print('ERROR: DATABASE_URL not set')
    sys.exit(1)

engine = create_engine(DATABASE_URL, future=True)


def load_json(path):
    try:
        with open(path, 'r', encoding='utf-8') as f:
            raw = f.read().strip()
        if not raw:
            print(f'Warning: {path} is empty; skipping')
            return None
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            # Attempt to recover JSON from files that have accidental text prefixes.
            starts = [idx for idx in (raw.find('{'), raw.find('[')) if idx != -1]
            if not starts:
                raise
            start = min(starts)
            return json.loads(raw[start:])
    except FileNotFoundError:
        print(f'Warning: {path} not found; skipping')
        return None


def ensure_tables():
    sql_path = os.path.join(os.path.dirname(__file__), '..', 'sql', 'create_tables.sql')
    sql_path = os.path.normpath(sql_path)
    with open(sql_path, 'r', encoding='utf-8') as f:
        sql = f.read()
    with engine.begin() as conn:
        conn.execute(text(sql))


def migrate_users():
    users = load_json(os.path.join(os.getcwd(), 'users.json'))
    if not users:
        return
    with engine.begin() as conn:
        for username, data in users.items():
            stmt = text("""
            INSERT INTO users (
                username, email, first_name, last_name, password_hash,
                profile_image, bio, fcm_token, friends, friend_requests, profile
            )
            VALUES (
                :username, :email, :first_name, :last_name, :password_hash,
                :profile_image, :bio, :fcm_token, CAST(:friends AS JSONB), CAST(:friend_requests AS JSONB), CAST(:profile AS JSONB)
            )
            ON CONFLICT (username) DO UPDATE SET
                email = EXCLUDED.email,
                first_name = EXCLUDED.first_name,
                last_name = EXCLUDED.last_name,
                password_hash = EXCLUDED.password_hash,
                profile_image = EXCLUDED.profile_image,
                bio = EXCLUDED.bio,
                fcm_token = EXCLUDED.fcm_token,
                friends = EXCLUDED.friends,
                friend_requests = EXCLUDED.friend_requests,
                profile = EXCLUDED.profile
            """)
            profile = json.dumps({
                'bio': data.get('bio'),
                'profile_image': data.get('profile_image')
            })
            conn.execute(stmt, {
                'username': username,
                'email': data.get('email'),
                'first_name': data.get('first_name'),
                'last_name': data.get('last_name'),
                'password_hash': data.get('password_hash') or None,
                'profile_image': data.get('profile_image'),
                'bio': data.get('bio', ''),
                'fcm_token': data.get('fcm_token'),
                'friends': json.dumps(data.get('friends', [])),
                'friend_requests': json.dumps(data.get('friend_requests', [])),
                'profile': profile,
            })


def migrate_messages():
    msgs = load_json(os.path.join(os.getcwd(), 'messages.json'))
    if not msgs:
        return
    # messages.json format may be a list or dict; handle common shapes
    items = []
    if isinstance(msgs, dict):
        # try 'messages' key
        items = msgs.get('messages') or []
        if not items:
            # dict of message_id -> message_object
            for value in msgs.values():
                if isinstance(value, dict):
                    items.append(value)
                elif isinstance(value, list):
                    items.extend(value)
    elif isinstance(msgs, list):
        items = msgs

    with engine.begin() as conn:
        for m in items:
            try:
                conn.execute(text(
                    """
                    INSERT INTO messages (
                        id, sender, receiver, message_type, text,
                        media_url, thumbnail_url, reply_to_id, status,
                        is_read, reactions, metadata, timestamp
                    ) VALUES (
                        :id, :s, :r, :t, :txt,
                        :media_url, :thumbnail_url, :reply_to_id, :status,
                        :is_read, CAST(:reactions AS JSONB), CAST(:meta AS JSONB), :timestamp
                    )
                    ON CONFLICT (id) DO UPDATE SET
                        sender = EXCLUDED.sender,
                        receiver = EXCLUDED.receiver,
                        message_type = EXCLUDED.message_type,
                        text = EXCLUDED.text,
                        media_url = EXCLUDED.media_url,
                        thumbnail_url = EXCLUDED.thumbnail_url,
                        reply_to_id = EXCLUDED.reply_to_id,
                        status = EXCLUDED.status,
                        is_read = EXCLUDED.is_read,
                        reactions = EXCLUDED.reactions,
                        metadata = EXCLUDED.metadata,
                        timestamp = EXCLUDED.timestamp
                    """
                ), {
                    'id': m.get('id'),
                    's': m.get('sender'),
                    'r': m.get('receiver'),
                    't': m.get('message_type'),
                    'txt': m.get('text'),
                    'media_url': m.get('media_url') or m.get('media_path'),
                    'thumbnail_url': m.get('thumbnail_url'),
                    'reply_to_id': m.get('reply_to_id'),
                    'status': m.get('status') or ('seen' if m.get('is_read') else 'sent'),
                    'is_read': bool(m.get('is_read', False)),
                    'reactions': json.dumps(m.get('reactions', {})),
                    'meta': json.dumps(m.get('metadata', {})),
                    'timestamp': m.get('timestamp'),
                })
            except Exception as e:
                print('Warning: failed to insert message', e)


def migrate_groups():
    groups = load_json(os.path.join(os.getcwd(), 'groups.json'))
    if not groups:
        return

    if isinstance(groups, dict):
        group_items = list(groups.values())
    elif isinstance(groups, list):
        group_items = groups
    else:
        return

    with engine.begin() as conn:
        for group in group_items:
            try:
                conn.execute(text("""
                    INSERT INTO groups (
                        id, name, avatar, created_by, admins, members,
                        created_at, updated_at, last_message, last_message_time
                    ) VALUES (
                        :id, :name, :avatar, :created_by,
                        CAST(:admins AS JSONB), CAST(:members AS JSONB),
                        :created_at, :updated_at, :last_message, :last_message_time
                    )
                    ON CONFLICT (id) DO NOTHING
                """), {
                    'id': group.get('id'),
                    'name': group.get('name'),
                    'avatar': group.get('avatar'),
                    'created_by': group.get('created_by'),
                    'admins': json.dumps(group.get('admins', [])),
                    'members': json.dumps(group.get('members', [])),
                    'created_at': group.get('created_at'),
                    'updated_at': group.get('updated_at'),
                    'last_message': group.get('last_message'),
                    'last_message_time': group.get('last_message_time'),
                })
            except Exception as exc:
                print('Warning: failed to insert group', exc)


def migrate_group_messages():
    group_messages = load_json(os.path.join(os.getcwd(), 'group_messages.json'))
    if not group_messages:
        return

    if isinstance(group_messages, dict):
        items = list(group_messages.values())
    elif isinstance(group_messages, list):
        items = group_messages
    else:
        return

    with engine.begin() as conn:
        for message in items:
            try:
                conn.execute(text("""
                    INSERT INTO group_messages (
                        id, group_id, sender, text, message_type,
                        media_url, thumbnail_url, timestamp, seen_by
                    ) VALUES (
                        :id, :group_id, :sender, :text, :message_type,
                        :media_url, :thumbnail_url, :timestamp, CAST(:seen_by AS JSONB)
                    )
                    ON CONFLICT (id) DO NOTHING
                """), {
                    'id': message.get('id'),
                    'group_id': message.get('group_id'),
                    'sender': message.get('sender'),
                    'text': message.get('text'),
                    'message_type': message.get('message_type'),
                    'media_url': message.get('media_url'),
                    'thumbnail_url': message.get('thumbnail_url'),
                    'timestamp': message.get('timestamp'),
                    'seen_by': json.dumps(message.get('seen_by', [])),
                })
            except Exception as exc:
                print('Warning: failed to insert group message', exc)


def migrate_group_call_history():
    history = load_json(os.path.join(os.getcwd(), 'group_call_history.json'))
    if not history:
        return

    if isinstance(history, dict):
        items = list(history.values())
    elif isinstance(history, list):
        items = history
    else:
        return

    with engine.begin() as conn:
        for call in items:
            try:
                conn.execute(text("""
                    INSERT INTO group_call_history (
                        id, group_id, started_by, call_type, participants,
                        status, started_at, ended_at
                    ) VALUES (
                        :id, :group_id, :started_by, :call_type, CAST(:participants AS JSONB),
                        :status, :started_at, :ended_at
                    )
                    ON CONFLICT (id) DO NOTHING
                """), {
                    'id': call.get('id'),
                    'group_id': call.get('group_id'),
                    'started_by': call.get('started_by'),
                    'call_type': call.get('call_type'),
                    'participants': json.dumps(call.get('participants', [])),
                    'status': call.get('status'),
                    'started_at': call.get('started_at'),
                    'ended_at': call.get('ended_at'),
                })
            except Exception as exc:
                print('Warning: failed to insert call history', exc)


def migrate_stories():
    stories = load_json(os.path.join(os.getcwd(), 'stories.json'))
    if not stories:
        return

    if isinstance(stories, dict):
        items = list(stories.values())
    elif isinstance(stories, list):
        items = stories
    else:
        return

    with engine.begin() as conn:
        for story in items:
            try:
                conn.execute(text("""
                    INSERT INTO stories (
                        id, username, media_url, thumbnail_url, media_type,
                        timestamp, viewers, reactions, reaction_details
                    ) VALUES (
                        :id, :username, :media_url, :thumbnail_url, :media_type,
                        :timestamp, CAST(:viewers AS JSONB), CAST(:reactions AS JSONB), CAST(:reaction_details AS JSONB)
                    )
                    ON CONFLICT (id) DO NOTHING
                """), {
                    'id': story.get('id'),
                    'username': story.get('username'),
                    'media_url': story.get('media_url'),
                    'thumbnail_url': story.get('thumbnail_url'),
                    'media_type': story.get('media_type'),
                    'timestamp': story.get('timestamp'),
                    'viewers': json.dumps(story.get('viewers', [])),
                    'reactions': json.dumps(story.get('reactions', {})),
                    'reaction_details': json.dumps(story.get('reaction_details', {})),
                })
            except Exception as exc:
                print('Warning: failed to insert story', exc)


def migrate_notes():
    notes = load_json(os.path.join(os.getcwd(), 'notes.json'))
    if not notes:
        return

    if isinstance(notes, dict):
        items = list(notes.values())
    elif isinstance(notes, list):
        items = notes
    else:
        return

    with engine.begin() as conn:
        for note in items:
            try:
                conn.execute(text("""
                    INSERT INTO notes (
                        id, username, text_content, media_url, thumbnail_url,
                        media_type, timestamp, viewers
                    ) VALUES (
                        :id, :username, :text_content, :media_url, :thumbnail_url,
                        :media_type, :timestamp, CAST(:viewers AS JSONB)
                    )
                    ON CONFLICT (id) DO NOTHING
                """), {
                    'id': note.get('id'),
                    'username': note.get('username'),
                    'text_content': note.get('text_content'),
                    'media_url': note.get('media_url'),
                    'thumbnail_url': note.get('thumbnail_url'),
                    'media_type': note.get('media_type'),
                    'timestamp': note.get('timestamp'),
                    'viewers': json.dumps(note.get('viewers', [])),
                })
            except Exception as exc:
                print('Warning: failed to insert note', exc)


def migrate_game_rooms():
    rooms_dir = os.path.join(os.getcwd(), 'data', 'games')
    if not os.path.isdir(rooms_dir):
        return

    with engine.begin() as conn:
        for filename in os.listdir(rooms_dir):
            if not filename.endswith('.json'):
                continue
            room_path = os.path.join(rooms_dir, filename)
            room_data = load_json(room_path)
            if not room_data:
                continue
            try:
                conn.execute(text("""
                    INSERT INTO game_rooms (room_id, room_data)
                    VALUES (:room_id, CAST(:room_data AS JSONB))
                    ON CONFLICT (room_id) DO UPDATE SET
                        room_data = EXCLUDED.room_data,
                        updated_at = now()
                """), {
                    'room_id': room_data.get('roomId') or os.path.splitext(filename)[0],
                    'room_data': json.dumps(room_data),
                })
            except Exception as exc:
                print('Warning: failed to insert game room', exc)


def migrate_audit_log():
    audit_path = os.path.join(os.getcwd(), 'logs', 'audit.log')
    if not os.path.exists(audit_path):
        return

    with open(audit_path, 'r', encoding='utf-8') as f, engine.begin() as conn:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
                conn.execute(text("""
                    INSERT INTO audit_events (event_type, payload, created_at)
                    VALUES (:event_type, CAST(:payload AS JSONB), :created_at)
                """), {
                    'event_type': entry.get('type') or 'legacy',
                    'payload': json.dumps(entry),
                    'created_at': entry.get('ts'),
                })
            except Exception as exc:
                print('Warning: failed to insert audit log entry', exc)


def migrate_uploads_media():
    uploads_root = os.path.join(os.getcwd(), 'uploads')
    if not os.path.isdir(uploads_root):
        return

    imported = 0
    media_map = {}

    with engine.begin() as conn:
        for root_dir, _, files in os.walk(uploads_root):
            for filename in files:
                filepath = os.path.join(root_dir, filename)
                relpath = os.path.relpath(filepath, uploads_root).replace(os.sep, '/')
                category = os.path.dirname(relpath).replace('\\', '/').strip('/') or 'misc'
                media_id = str(uuid5(NAMESPACE_URL, f'legacy-media:{relpath}'))
                content_type = mimetypes.guess_type(filename)[0] or 'application/octet-stream'

                try:
                    with open(filepath, 'rb') as file_handle:
                        data = file_handle.read()

                    conn.execute(text("""
                        INSERT INTO media_files (id, category, filename, content_type, data)
                        VALUES (:id, :category, :filename, :content_type, :data)
                        ON CONFLICT (id) DO UPDATE SET
                            category = EXCLUDED.category,
                            filename = EXCLUDED.filename,
                            content_type = EXCLUDED.content_type,
                            data = EXCLUDED.data
                    """), {
                        'id': media_id,
                        'category': category,
                        'filename': filename,
                        'content_type': content_type,
                        'data': data,
                    })
                    media_map[f'/uploads/{relpath}'] = media_id
                    media_map[f'uploads/{relpath}'] = media_id
                    imported += 1
                except Exception as exc:
                    print('Warning: failed to import upload media', filepath, exc)

        if media_map:
            for table, columns in (
                ('messages', ('media_url', 'thumbnail_url')),
                ('group_messages', ('media_url', 'thumbnail_url')),
                ('stories', ('media_url', 'thumbnail_url')),
                ('notes', ('media_url', 'thumbnail_url')),
            ):
                for old_url, media_id in media_map.items():
                    new_url = f'/media/{media_id}'
                    for column in columns:
                        try:
                            conn.execute(text(f"""
                                UPDATE {table}
                                SET {column} = :new_url
                                WHERE {column} = :old_url
                            """), {
                                'new_url': new_url,
                                'old_url': old_url,
                            })
                        except Exception as exc:
                            print(f'Warning: failed to update {table}.{column}', exc)

    print(f'Imported {imported} media files from uploads/')


def migrate_missing_message_thumbnails():
    legacy_rows = []
    with engine.begin() as conn:
        result = conn.execute(text("""
            SELECT id, media_url, thumbnail_url
            FROM messages
            WHERE position('/uploads/' in coalesce(thumbnail_url, '')) > 0
               OR position('uploads/' in coalesce(thumbnail_url, '')) > 0
        """))
        legacy_rows = [dict(row._mapping) for row in result]

    if not legacy_rows:
        return

    updated = 0
    with engine.begin() as conn:
        for row in legacy_rows:
            media_url = row.get('media_url') or ''
            if not media_url.startswith('/media/'):
                continue

            media_id = media_url.removeprefix('/media/')
            media_row = conn.execute(text("""
                SELECT id, category, filename, content_type, data
                FROM media_files
                WHERE id = :media_id
            """), {'media_id': media_id}).mappings().first()
            if not media_row:
                continue

            filename = media_row.get('filename') or ''
            content_type = (media_row.get('content_type') or '').lower()
            if not (content_type.startswith('video/') or filename.lower().endswith(('.mp4', '.mov', '.mkv', '.avi', '.webm'))):
                continue

            thumb_name = f"{os.path.splitext(filename)[0]}_thumb.jpg"
            thumb_relpath = f"messages/{thumb_name}"
            thumb_id = str(uuid5(NAMESPACE_URL, f'legacy-media-thumb:{thumb_relpath}'))
            thumb_url = f'/media/{thumb_id}'

            existing_thumb = conn.execute(text("""
                SELECT id
                FROM media_files
                WHERE id = :thumb_id
            """), {'thumb_id': thumb_id}).mappings().first()

            if not existing_thumb:
                try:
                    from app.utils import generate_video_thumbnail
                except Exception:
                    generate_video_thumbnail = None

                if generate_video_thumbnail is not None:
                    with tempfile.TemporaryDirectory() as tmpdir:
                        source_path = os.path.join(tmpdir, filename)
                        thumb_path = os.path.join(tmpdir, thumb_name)
                        with open(source_path, 'wb') as source_file:
                            source_file.write(media_row['data'])
                        if generate_video_thumbnail(source_path, thumb_path):
                            with open(thumb_path, 'rb') as thumb_file:
                                thumb_data = thumb_file.read()
                            conn.execute(text("""
                                INSERT INTO media_files (id, category, filename, content_type, data)
                                VALUES (:id, :category, :filename, :content_type, :data)
                                ON CONFLICT (id) DO UPDATE SET
                                    category = EXCLUDED.category,
                                    filename = EXCLUDED.filename,
                                    content_type = EXCLUDED.content_type,
                                    data = EXCLUDED.data
                            """), {
                                'id': thumb_id,
                                'category': media_row.get('category') or 'messages',
                                'filename': thumb_name,
                                'content_type': 'image/jpeg',
                                'data': thumb_data,
                            })
                        else:
                            thumb_url = media_url
                else:
                    thumb_url = media_url

            conn.execute(text("""
                UPDATE messages
                SET thumbnail_url = :thumb_url
                WHERE id = :message_id
            """), {
                'thumb_url': thumb_url,
                'message_id': row['id'],
            })
            updated += 1

    print(f'Backfilled {updated} legacy message thumbnails')


if __name__ == '__main__':
    print('Ensuring tables...')
    ensure_tables()
    print('Migrating users...')
    migrate_users()
    print('Migrating messages...')
    migrate_messages()
    print('Migrating groups...')
    migrate_groups()
    print('Migrating group messages...')
    migrate_group_messages()
    print('Migrating group call history...')
    migrate_group_call_history()
    print('Migrating stories...')
    migrate_stories()
    print('Migrating notes...')
    migrate_notes()
    print('Migrating game rooms...')
    migrate_game_rooms()
    print('Migrating audit log...')
    migrate_audit_log()
    print('Migrating uploads media...')
    migrate_uploads_media()
    print('Migrating missing message thumbnails...')
    migrate_missing_message_thumbnails()
    print('Done')
