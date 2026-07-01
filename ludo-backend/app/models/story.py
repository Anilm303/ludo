import base64
import os
import uuid
from datetime import datetime, timedelta

from app.storage import create_media_filename, delete_local_media_file, delete_stored_media, store_media_bytes, _storage_mode
from app.postgres_store import execute, fetch_all, fetch_one, json_value

UPLOADS_FOLDER = os.getenv('STORY_UPLOADS_FOLDER', 'uploads/stories')
os.makedirs(UPLOADS_FOLDER, exist_ok=True)


class Story:
    """Model for user stories (status updates)"""

    @staticmethod
    def _row_to_story(row):
        if not row:
            return None
        return {
            'id': row['id'],
            'username': row['username'],
            'media_url': row.get('media_url'),
            'thumbnail_url': row.get('thumbnail_url'),
            'media_type': row.get('media_type'),
            'timestamp': row.get('timestamp').isoformat() if row.get('timestamp') else '',
            'viewers': row.get('viewers') or [],
            'reactions': row.get('reactions') or {},
            'reaction_details': row.get('reaction_details') or {},
        }

    @staticmethod
    def upload_story(username, media_base64, media_type):
        extension = 'mp4' if media_type == 'video' else 'jpg'
        filename = create_media_filename(extension)

        try:
            media_bytes = base64.b64decode(media_base64)
        except Exception as exception:
            print(f"Error saving file: {exception}")
            return None

        try:
            media_url = store_media_bytes(
                'stories',
                filename,
                media_bytes,
                content_type='video/mp4' if media_type == 'video' else 'image/jpeg',
            )
        except Exception as exception:
            print(f"Error storing story media: {exception}")
            return None

        story_id = str(uuid.uuid4())
        thumbnail_url = None

        if media_type == 'video':
            try:
                from app.utils import generate_video_thumbnail

                thumb_filename = f"{filename.split('.')[0]}_thumb.jpg"
                thumb_filepath = os.path.join(UPLOADS_FOLDER, thumb_filename)
                media_filepath = os.path.join(UPLOADS_FOLDER, filename)
                if generate_video_thumbnail(media_filepath, thumb_filepath):
                    with open(thumb_filepath, 'rb') as thumb_file:
                        thumbnail_url = store_media_bytes(
                            'stories',
                            thumb_filename,
                            thumb_file.read(),
                            content_type='image/jpeg',
                        )
                    if _storage_mode() == 'postgres':
                        delete_local_media_file('stories', thumb_filename)
            except Exception as exception:
                print(f"⚠️ Thumbnail generation error (non-blocking): {exception}")

        if _storage_mode() == 'postgres':
            delete_local_media_file('stories', filename)

        story = {
            'id': story_id,
            'username': username,
            'media_url': media_url,
            'thumbnail_url': thumbnail_url,
            'media_type': media_type,
            'timestamp': datetime.now().isoformat(),
            'viewers': [],
            'reactions': {},
            'reaction_details': {},
        }

        execute(
            """
            INSERT INTO stories (
                id, username, media_url, thumbnail_url, media_type,
                timestamp, viewers, reactions, reaction_details
            ) VALUES (
                %(id)s, %(username)s, %(media_url)s, %(thumbnail_url)s, %(media_type)s,
                %(timestamp)s, %(viewers)s, %(reactions)s, %(reaction_details)s
            )
            """,
            {
                **story,
                'viewers': json_value([]),
                'reactions': json_value({}),
                'reaction_details': json_value({}),
            }
        )
        return story

    @staticmethod
    def upload_story_bytes(username, media_bytes, media_type):
        """Upload raw bytes (used by multipart form uploads)."""
        extension = 'mp4' if media_type == 'video' else 'jpg'
        filename = create_media_filename(extension)

        try:
            media_url = store_media_bytes(
                'stories',
                filename,
                media_bytes,
                content_type='video/mp4' if media_type == 'video' else 'image/jpeg',
            )
        except Exception as exception:
            print(f"❌ Error storing file bytes: {exception}")
            return None

        story_id = str(uuid.uuid4())
        thumbnail_url = None

        if media_type == 'video':
            try:
                from app.utils import generate_video_thumbnail

                thumb_filename = f"{filename.split('.')[0]}_thumb.jpg"
                thumb_filepath = os.path.join(UPLOADS_FOLDER, thumb_filename)
                media_filepath = os.path.join(UPLOADS_FOLDER, filename)
                print(f"🎬 Attempting thumbnail generation: {thumb_filepath}")
                if generate_video_thumbnail(media_filepath, thumb_filepath):
                    with open(thumb_filepath, 'rb') as thumb_file:
                        thumbnail_url = store_media_bytes(
                            'stories',
                            thumb_filename,
                            thumb_file.read(),
                            content_type='image/jpeg',
                        )
                    print("✅ Thumbnail generated successfully")
                    if _storage_mode() == 'postgres':
                        delete_local_media_file('stories', thumb_filename)
                else:
                    print("⚠️ Thumbnail generation returned False, continuing without thumbnail")
            except Exception as exception:
                print(f"⚠️ Thumbnail generation error (non-blocking): {exception}")

        if _storage_mode() == 'postgres':
            delete_local_media_file('stories', filename)

        story = {
            'id': story_id,
            'username': username,
            'media_url': media_url,
            'thumbnail_url': thumbnail_url,
            'media_type': media_type,
            'timestamp': datetime.now().isoformat(),
            'viewers': [],
            'reactions': {},
            'reaction_details': {},
        }

        try:
            execute(
                """
                INSERT INTO stories (
                    id, username, media_url, thumbnail_url, media_type,
                    timestamp, viewers, reactions, reaction_details
                ) VALUES (
                    %(id)s, %(username)s, %(media_url)s, %(thumbnail_url)s, %(media_type)s,
                    %(timestamp)s, %(viewers)s, %(reactions)s, %(reaction_details)s
                )
                """,
                {
                    **story,
                    'viewers': json_value([]),
                    'reactions': json_value({}),
                    'reaction_details': json_value({}),
                }
            )
            print(f"✅ Story saved to PostgreSQL: {story_id}")
            return story
        except Exception as exception:
            print(f"❌ Error saving story to DB: {exception}")
            return None

    @staticmethod
    def get_active_stories():
        rows = fetch_all('SELECT * FROM stories ORDER BY timestamp DESC')
        active = []
        now = datetime.now()
        for row in rows:
            try:
                story_time = row.get('timestamp')
                if not story_time:
                    continue
                age = now - story_time.replace(tzinfo=None) if hasattr(story_time, 'replace') else now - datetime.fromisoformat(str(story_time))
                if age < timedelta(hours=24):
                    active.append(Story._row_to_story(row))
            except Exception:
                pass
        return active

    @staticmethod
    def get_user_stories(username):
        return [s for s in Story.get_active_stories() if s['username'] == username]

    @staticmethod
    def mark_story_viewed(story_id, viewer_username):
        row = fetch_one('SELECT viewers FROM stories WHERE id = %(id)s', {'id': story_id})
        if not row:
            return False
        viewers = row.get('viewers') or []
        if not any(v.get('username') == viewer_username for v in viewers):
            viewers.append({'username': viewer_username, 'timestamp': datetime.now().isoformat()})
            execute('UPDATE stories SET viewers = %(viewers)s WHERE id = %(id)s', {'id': story_id, 'viewers': json_value(viewers)})
        return True

    @staticmethod
    def react_to_story(story_id, reactor_username, emoji):
        row = fetch_one('SELECT username, reactions, reaction_details FROM stories WHERE id = %(id)s', {'id': story_id})
        if not row:
            return False, {}, {}, None
        reactions = row.get('reactions') or {}
        reaction_details = row.get('reaction_details') or {}

        if reactions.get(reactor_username) == emoji:
            reactions.pop(reactor_username, None)
            reaction_details.pop(reactor_username, None)
        else:
            reactions[reactor_username] = emoji
            reaction_details[reactor_username] = {
                'emoji': emoji,
                'timestamp': datetime.now().isoformat(),
            }
        execute(
            'UPDATE stories SET reactions = %(reactions)s, reaction_details = %(reaction_details)s WHERE id = %(id)s',
            {'id': story_id, 'reactions': json_value(reactions), 'reaction_details': json_value(reaction_details)},
        )
        return True, reactions, reaction_details, row.get('username')

    @staticmethod
    def get_story_reactions(story_id):
        row = fetch_one('SELECT reactions FROM stories WHERE id = %(id)s', {'id': story_id})
        return row.get('reactions', {}) if row else {}

    @staticmethod
    def get_story_viewers(story_id):
        row = fetch_one('SELECT viewers FROM stories WHERE id = %(id)s', {'id': story_id})
        return row.get('viewers', []) if row else []

    @staticmethod
    def get_story_reaction_details(story_id):
        row = fetch_one('SELECT reaction_details FROM stories WHERE id = %(id)s', {'id': story_id})
        return row.get('reaction_details', {}) if row else {}

    @staticmethod
    def cleanup_expired_stories():
        now = datetime.now()
        execute('DELETE FROM stories WHERE timestamp < %(cutoff)s', {'cutoff': now - timedelta(hours=24)})

    @staticmethod
    def delete_story(story_id, username):
        row = fetch_one('SELECT username, media_url, thumbnail_url FROM stories WHERE id = %(id)s', {'id': story_id})
        if not row:
            return False, 'Story not found'

        if row.get('username') != username:
            return False, 'You can only delete your own story'

        delete_stored_media(row.get('media_url'))
        delete_stored_media(row.get('thumbnail_url'))

        execute('DELETE FROM stories WHERE id = %(id)s', {'id': story_id})
        return True, 'Story deleted successfully'