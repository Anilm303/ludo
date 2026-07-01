import os
import time
import threading
from app.models.story import Story
from app.models.note import Note
from app.models.message import get_messages

STORIES_UPLOADS_FOLDER = 'uploads/stories'
MESSAGES_UPLOADS_FOLDER = 'uploads/messages'

def run_cleanup():
    """Background task to remove expired stories and unreferenced files"""
    while True:
        try:
            # 1. Cleanup expired stories from JSON
            Story.cleanup_expired_stories()
            Note.cleanup_expired_notes()
            
            # 2. Cleanup orphaned story files
            active_stories = Story.get_active_stories()
            active_story_files = set(
                os.path.basename(story['media_url']) 
                for story in active_stories 
                if story.get('media_url')
            )
            
            if os.path.exists(STORIES_UPLOADS_FOLDER):
                for filename in os.listdir(STORIES_UPLOADS_FOLDER):
                    if filename not in active_story_files:
                        file_path = os.path.join(STORIES_UPLOADS_FOLDER, filename)
                        try:
                            os.remove(file_path)
                            print(f"Cleaned up old story file: {filename}")
                        except Exception as e:
                            print(f"Error deleting file {file_path}: {e}")

            # 3. Cleanup orphaned note files
            active_notes = Note.get_active_notes()
            active_note_files = set(
                os.path.basename(note['media_url'])
                for note in active_notes
                if note.get('media_url')
            )

            notes_uploads_folder = 'uploads/notes'
            if os.path.exists(notes_uploads_folder):
                for filename in os.listdir(notes_uploads_folder):
                    if filename not in active_note_files:
                        file_path = os.path.join(notes_uploads_folder, filename)
                        try:
                            os.remove(file_path)
                            print(f"Cleaned up old note file: {filename}")
                        except Exception as e:
                            print(f"Error deleting file {file_path}: {e}")

            # 4. (Optional) Cleanup orphaned message files if messages are deleted
            # Currently messages are never deleted from JSON, so we just check if
            # any file in uploads/messages is NOT in messages.json
            messages = get_messages()
            active_msg_files = set(
                os.path.basename(msg['media_url'])
                for msg in messages.values()
                if msg.get('media_url')
            )
            
            if os.path.exists(MESSAGES_UPLOADS_FOLDER):
                for filename in os.listdir(MESSAGES_UPLOADS_FOLDER):
                    if filename not in active_msg_files:
                        file_path = os.path.join(MESSAGES_UPLOADS_FOLDER, filename)
                        try:
                            os.remove(file_path)
                            print(f"Cleaned up orphaned message file: {filename}")
                        except Exception as e:
                            print(f"Error deleting file {file_path}: {e}")
                            
        except Exception as e:
            print(f"Cleanup task error: {e}")
            
        # Run every hour
        time.sleep(3600)

def start_cleanup_thread():
    thread = threading.Thread(target=run_cleanup, daemon=True)
    thread.start()
    print("Background cleanup thread started")
