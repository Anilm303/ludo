import os
import threading
from datetime import datetime

from app.postgres_store import execute, fetch_all, fetch_one
from app.postgres_store import is_database_url_configured

_TOKEN_LOCK = threading.Lock()
_MEMORY_TOKEN_BLOCKLIST = {}


def _cleanup_memory_blocklist(now=None):
    now = now or datetime.utcnow()
    expired = [
        jti for jti, payload in _MEMORY_TOKEN_BLOCKLIST.items()
        if payload.get('expires_at') is not None and payload['expires_at'] <= now
    ]
    for jti in expired:
        _MEMORY_TOKEN_BLOCKLIST.pop(jti, None)


def _ensure_table():
    if not is_database_url_configured():
        return
    execute(
        """
        CREATE TABLE IF NOT EXISTS auth_token_blocklist (
          jti TEXT PRIMARY KEY,
          token_type TEXT,
          revoked_at TIMESTAMPTZ,
          expires_at TIMESTAMPTZ
        )
        """
    )


def revoke_token(jti, token_type='access', expires_at=None):
    if not jti:
        return
    with _TOKEN_LOCK:
        if not is_database_url_configured():
            _MEMORY_TOKEN_BLOCKLIST[jti] = {
                'token_type': token_type,
                'revoked_at': datetime.utcnow(),
                'expires_at': expires_at,
            }
            _cleanup_memory_blocklist()
            return

        _ensure_table()
        execute(
            """
            INSERT INTO auth_token_blocklist (jti, token_type, revoked_at, expires_at)
            VALUES (%(jti)s, %(token_type)s, %(revoked_at)s, %(expires_at)s)
            ON CONFLICT (jti) DO UPDATE SET
                token_type = EXCLUDED.token_type,
                revoked_at = EXCLUDED.revoked_at,
                expires_at = EXCLUDED.expires_at
            """,
            {
                'jti': jti,
                'token_type': token_type,
                'revoked_at': datetime.utcnow(),
                'expires_at': expires_at,
            }
        )


def is_token_revoked(jti):
    if not jti:
        return True
    if not is_database_url_configured():
        with _TOKEN_LOCK:
            _cleanup_memory_blocklist()
            return jti in _MEMORY_TOKEN_BLOCKLIST

    _ensure_table()
    row = fetch_one('SELECT 1 FROM auth_token_blocklist WHERE jti = %(jti)s', {'jti': jti})
    return bool(row)


def cleanup_blocklist():
    with _TOKEN_LOCK:
        if not is_database_url_configured():
            _cleanup_memory_blocklist()
            return

        _ensure_table()
        execute(
            """
            DELETE FROM auth_token_blocklist
            WHERE expires_at IS NOT NULL AND expires_at <= %(now)s
            """,
            {'now': datetime.utcnow()},
        )


def clear_blocklist():
    """Remove all revoked tokens from the database."""
    with _TOKEN_LOCK:
        if not is_database_url_configured():
            _MEMORY_TOKEN_BLOCKLIST.clear()
            return

        _ensure_table()
        execute('DELETE FROM auth_token_blocklist')
