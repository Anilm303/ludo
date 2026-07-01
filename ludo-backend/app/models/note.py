import base64
import os
import uuid
from datetime import datetime, timedelta

from app.storage import create_media_filename, delete_local_media_file, store_media_bytes, _storage_mode
from app.postgres_store import execute, fetch_all, fetch_one, json_value

UPLOADS_FOLDER = os.getenv('NOTE_UPLOADS_FOLDER', 'uploads/notes')
os.makedirs(UPLOADS_FOLDER, exist_ok=True)


class Note:
    @staticmethod
    def upload_note(username, text_content='', media_base64=None, media_type='text'):
        if media_type not in ['text', 'image', 'video']:
            return None

        media_url = None
        thumbnail_url = None

        if media_type == 'text':
            if not text_content or not text_content.strip():
                return None
        else:
            if not media_base64:
                return None

            extension = 'mp4' if media_type == 'video' else 'jpg'
            filename = create_media_filename(extension)

            try:
                media_bytes = base64.b64decode(media_base64)
                media_url = store_media_bytes('notes', filename, media_bytes, content_type='video/mp4' if media_type == 'video' else 'image/jpeg')

                if media_type == 'video':
                    from app.utils import generate_video_thumbnail

                    thumb_filename = f"{filename.split('.')[0]}_thumb.jpg"
                    thumb_filepath = os.path.join(UPLOADS_FOLDER, thumb_filename)
                    if generate_video_thumbnail(os.path.join(UPLOADS_FOLDER, filename), thumb_filepath):
                        with open(thumb_filepath, 'rb') as thumb_file:
                            thumbnail_url = store_media_bytes('notes', thumb_filename, thumb_file.read(), content_type='image/jpeg')
                        if _storage_mode() == 'postgres':
                            delete_local_media_file('notes', thumb_filename)
            except Exception as exception:
                print(f"Error saving note media: {exception}")
                return None

            if _storage_mode() == 'postgres':
                delete_local_media_file('notes', filename)

        note = {
            'id': str(uuid.uuid4()),
            'username': username,
            'text_content': text_content.strip() if text_content else '',
            'media_url': media_url,
            'thumbnail_url': thumbnail_url,
            'media_type': media_type,
            'timestamp': datetime.now().isoformat(),
            'viewers': [],
        }

        execute(
            """
            INSERT INTO notes (
                id, username, text_content, media_url, thumbnail_url,
                media_type, timestamp, viewers
            ) VALUES (
                %(id)s, %(username)s, %(text_content)s, %(media_url)s, %(thumbnail_url)s,
                %(media_type)s, %(timestamp)s, %(viewers)s
            )
            """,
            {
                **note,
                'viewers': json_value([]),
            }
        )
        return note

    @staticmethod
    def get_active_notes():
        notes = []
        now = datetime.now()
        for row in fetch_all('SELECT * FROM notes ORDER BY timestamp DESC'):
            try:
                note_time = row.get('timestamp')
                if not note_time:
                    continue
                age = now - note_time.replace(tzinfo=None) if hasattr(note_time, 'replace') else now - datetime.fromisoformat(str(note_time))
                if age < timedelta(hours=24):
                    notes.append({
                        'id': row['id'],
                        'username': row['username'],
                        'text_content': row.get('text_content', ''),
                        'media_url': row.get('media_url'),
                        'thumbnail_url': row.get('thumbnail_url'),
                        'media_type': row.get('media_type'),
                        'timestamp': row.get('timestamp').isoformat() if row.get('timestamp') else '',
                        'viewers': row.get('viewers') or [],
                    })
            except Exception:
                pass
        return notes

    @staticmethod
    def get_user_notes(username):
        return [note for note in Note.get_active_notes() if note['username'] == username]

    @staticmethod
    def mark_note_viewed(note_id, viewer_username):
        row = fetch_one('SELECT viewers FROM notes WHERE id = %(id)s', {'id': note_id})
        if not row:
            return False
        viewers = row.get('viewers') or []
        if not any(viewer.get('username') == viewer_username for viewer in viewers):
            viewers.append({'username': viewer_username, 'timestamp': datetime.now().isoformat()})
            execute('UPDATE notes SET viewers = %(viewers)s WHERE id = %(id)s', {'id': note_id, 'viewers': json_value(viewers)})
        return True

    @staticmethod
    def cleanup_expired_notes():
        cutoff = datetime.now() - timedelta(hours=24)
        execute('DELETE FROM notes WHERE timestamp < %(cutoff)s', {'cutoff': cutoff})
