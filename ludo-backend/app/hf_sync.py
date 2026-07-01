import os
import json
import tempfile
import threading
import time
import logging
from typing import Optional

from huggingface_hub import HfApi, hf_hub_download

logger = logging.getLogger(__name__)

# Globals configured via initialize()
_api: Optional[HfApi] = None
_repo_id: Optional[str] = None
_repo_type: str = 'space'
_repo_path: Optional[str] = None  # path inside repo, e.g. data/chess/users.json
_token: Optional[str] = None
_upload_lock = threading.RLock()


def initialize(users_file_local_path: str,
               repo_id_env: str = 'HF_REPO_ID',
               token_env: str = 'HF_TOKEN',
               path_in_repo: str = None):
    """Initialize HF sync subsystem.

    - users_file_local_path: where the project's `users.json` lives (absolute or relative)
    - repo_id_env / token_env: environment variable names for repo id and token
    - path_in_repo: optional explicit path in the HF repo where users.json should be stored.
    """
    global _api, _repo_id, _token, _repo_path

    _repo_id = os.getenv(repo_id_env, '').strip() or None
    _token = os.getenv(token_env, '').strip() or None
    if path_in_repo:
        _repo_path = path_in_repo
    else:
        # default location inside a Space: /data/chess/users.json
        _repo_path = os.getenv('HF_USERS_PATH', 'data/chess/users.json')

    if not _repo_id or not _token:
        logger.info('HF sync disabled: HF_REPO_ID or HF_TOKEN not provided in environment')
        return

    _api = HfApi()

    # Attempt to download existing users.json from HF and write to local path.
    try:
        logger.info('Attempting to download users.json from HF repo %s path %s', _repo_id, _repo_path)
        cached = hf_hub_download(repo_id=_repo_id, filename=_repo_path, repo_type=_repo_type, token=_token)
        if os.path.exists(cached):
            # Atomically copy into place
            _atomic_copy(cached, users_file_local_path)
            logger.info('Downloaded users.json from HF and wrote to %s', users_file_local_path)
            return
    except Exception as e:
        logger.warning('Could not download users.json from HF: %s', e)

    # If we reach here, either repo/file not found or download failed -> ensure local file exists
    if not os.path.exists(users_file_local_path):
        try:
            os.makedirs(os.path.dirname(users_file_local_path) or '.', exist_ok=True)
            with open(users_file_local_path, 'w') as fh:
                json.dump({}, fh)
            logger.info('Initialized empty users.json at %s', users_file_local_path)
        except Exception:
            logger.exception('Failed to create local users.json at %s', users_file_local_path)


def _atomic_copy(src: str, dst: str):
    # copy src to dst atomically using a temp file then replace
    directory = os.path.dirname(dst)
    if directory:
        os.makedirs(directory, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=directory or None)
    os.close(fd)
    try:
        with open(src, 'rb') as r, open(tmp, 'wb') as w:
            w.write(r.read())
        os.replace(tmp, dst)
    finally:
        if os.path.exists(tmp):
            try:
                os.remove(tmp)
            except Exception:
                pass


def upload_users_async(local_users_path: str, commit_message: str = 'Update users.json from backend'):
    """Upload the local users file to HF repo in a background thread (non-blocking).

    This schedules a background upload which will retry on transient errors.
    """
    if not _repo_id or not _token:
        logger.debug('HF upload skipped: repo/token not configured')
        return

    # Start background thread for upload
    thr = threading.Thread(target=_upload_with_retries, args=(local_users_path, commit_message), daemon=True)
    thr.start()


def _upload_with_retries(local_users_path: str, commit_message: str, max_retries: int = 5):
    backoff = 1.0
    for attempt in range(1, max_retries + 1):
        try:
            _upload_once(local_users_path, commit_message)
            logger.info('Successfully uploaded users.json to HF on attempt %d', attempt)
            return
        except Exception as exc:
            logger.warning('Upload attempt %d failed: %s', attempt, exc)
            time.sleep(backoff)
            backoff = min(backoff * 2, 30)
    logger.error('Failed to upload users.json after %d attempts', max_retries)


def _upload_once(local_users_path: str, commit_message: str):
    with _upload_lock:
        if not os.path.exists(local_users_path):
            raise FileNotFoundError(f'Local users file not found: {local_users_path}')

        # Prepare a temp copy to avoid uploading a file that may be mid-write.
        fd, tmp = tempfile.mkstemp(suffix='.json')
        os.close(fd)
        try:
            with open(local_users_path, 'rb') as r, open(tmp, 'wb') as w:
                w.write(r.read())

            api = HfApi()
            # upload_file will create/overwrite the file in the repo with a commit
            api.upload_file(path_or_fileobj=tmp,
                            path_in_repo=_repo_path,
                            repo_id=_repo_id,
                            repo_type=_repo_type,
                            token=_token,
                            commit_message=commit_message)
        finally:
            try:
                os.remove(tmp)
            except Exception:
                pass
