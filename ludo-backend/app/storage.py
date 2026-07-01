import os
import tempfile
from uuid import uuid4

from app.postgres_store import execute, fetch_one
from app.postgres_store import is_database_url_configured

DATA_ROOT = os.getenv('DATA_ROOT', '').strip()
UPLOAD_ROOT = os.getenv('UPLOAD_ROOT', '').strip() or (
    os.path.join(DATA_ROOT, 'uploads') if DATA_ROOT else 'uploads'
)


def _storage_mode():
    configured = os.getenv('MEDIA_STORAGE', '').strip().lower()
    if configured:
        return configured
    return 'postgres' if is_database_url_configured() else 'local'


def _normalize_public_base_url():
    base = os.getenv('MEDIA_PUBLIC_BASE_URL', '').strip().rstrip('/')
    return base


def store_media_bytes(category, filename, data, content_type='application/octet-stream'):
    """Store media locally or in S3, depending on MEDIA_STORAGE."""
    mode = _storage_mode()
    category = category.strip('/').strip()
    if not category:
        category = 'misc'

    if mode == 's3':
        bucket = os.getenv('S3_BUCKET', '').strip()
        region = os.getenv('S3_REGION', '').strip()
        if not bucket or not region:
            raise RuntimeError('S3_BUCKET and S3_REGION are required when MEDIA_STORAGE=s3')

        import boto3

        key = f'{category}/{filename}'
        client = boto3.client(
            's3',
            region_name=region,
            aws_access_key_id=os.getenv('S3_ACCESS_KEY_ID', '').strip() or None,
            aws_secret_access_key=os.getenv('S3_SECRET_ACCESS_KEY', '').strip() or None,
        )
        client.put_object(
            Bucket=bucket,
            Key=key,
            Body=data,
            ContentType=content_type,
        )

        # Keep a local copy so thumbnail generation and local debugging still work.
        folder = os.path.join(UPLOAD_ROOT, category)
        os.makedirs(folder, exist_ok=True)
        local_filepath = os.path.join(folder, filename)
        with open(local_filepath, 'wb') as file_handle:
            file_handle.write(data)

        public_base = _normalize_public_base_url()
        if public_base:
            return f'{public_base}/{key}'

        return f'https://{bucket}.s3.{region}.amazonaws.com/{key}'

    if mode == 'postgres':
        execute(
            """
            CREATE TABLE IF NOT EXISTS media_files (
              id TEXT PRIMARY KEY,
              category TEXT NOT NULL,
              filename TEXT NOT NULL,
              content_type TEXT,
              data BYTEA NOT NULL,
              created_at TIMESTAMPTZ DEFAULT now()
            )
            """
        )
        media_id = str(uuid4())
        folder = os.path.join(UPLOAD_ROOT, category)
        os.makedirs(folder, exist_ok=True)
        filepath = os.path.join(folder, filename)
        with open(filepath, 'wb') as file_handle:
            file_handle.write(data)
        execute(
            """
            INSERT INTO media_files (id, category, filename, content_type, data)
            VALUES (%(id)s, %(category)s, %(filename)s, %(content_type)s, %(data)s)
            """,
            {
                'id': media_id,
                'category': category,
                'filename': filename,
                'content_type': content_type,
                'data': data,
            },
        )
        if os.path.exists(filepath):
            try:
                os.remove(filepath)
            except Exception:
                pass
        return f'/media/{media_id}'

    folder = os.path.join(UPLOAD_ROOT, category)
    os.makedirs(folder, exist_ok=True)
    filepath = os.path.join(folder, filename)
    with open(filepath, 'wb') as file_handle:
        file_handle.write(data)
    return f'/uploads/{category}/{filename}'


def delete_local_media_file(category, filename):
    folder = os.path.join(UPLOAD_ROOT, category)
    filepath = os.path.join(folder, filename)
    if os.path.exists(filepath):
        try:
            os.remove(filepath)
        except Exception:
            pass


def delete_stored_media(media_url):
    """Delete a stored media record and any matching local file copy."""
    if not media_url:
        return

    url = str(media_url).strip()
    if url.startswith('/media/'):
        media_id = url.rsplit('/', 1)[-1]
        execute('DELETE FROM media_files WHERE id = %(media_id)s', {'media_id': media_id})
        return

    if url.startswith('/uploads/'):
        relative_path = url[len('/uploads/'):].lstrip('/')
        if '/' in relative_path:
          category, filename = relative_path.split('/', 1)
          delete_local_media_file(category, filename)
        return


def get_media_file(media_id):
    return fetch_one(
        'SELECT id, category, filename, content_type, data FROM media_files WHERE id = %(media_id)s',
        {'media_id': media_id},
    )


def create_media_filename(extension):
    return f'{uuid4()}.{extension.lstrip(".")}'
