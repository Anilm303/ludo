"""PostgreSQL store that works for both local Postgres and Neon (cloud).

Behavior:
  * If the URL points to `localhost` / `127.0.0.1` we connect WITHOUT SSL
    (so the local dev Postgres you have running on port 5432 works).
  * For everything else (Neon, Supabase, RDS, etc.) we require SSL.
  * One automatic retry on OperationalError (HF Spaces cold-start).
  * All DB helpers catch OperationalError so the request returns a clean
    503 (or empty list/None) instead of a 500.

To switch between local and Neon, just edit the DATABASE_URL in .env.
The change is picked up on the next request.
"""
import logging
import os
import time
from contextlib import contextmanager
from typing import Any, Optional

import psycopg2
from psycopg2 import OperationalError
from psycopg2.extras import Json, RealDictCursor
from sqlalchemy.engine import make_url

logger = logging.getLogger(__name__)


def is_database_url_configured() -> bool:
    database_url = os.getenv('DATABASE_URL', '').strip()
    if not database_url:
        return False
    try:
        url = make_url(database_url)
    except Exception:
        return False
    host = (url.host or '').strip().lower()
    return bool(host and host not in {'host', '#host#'})


def is_local_postgres() -> bool:
    """True when DATABASE_URL points at localhost / 127.0.0.1."""
    database_url = os.getenv('DATABASE_URL', '').strip()
    if not database_url:
        return False
    try:
        url = make_url(database_url)
    except Exception:
        return False
    host = (url.host or '').strip().lower()
    return host in {'localhost', '127.0.0.1', '::1'}


def get_database_url() -> str:
    database_url = os.getenv('DATABASE_URL', '').strip()
    if not database_url:
        raise RuntimeError('DATABASE_URL is not set')
    if not is_database_url_configured():
        raise RuntimeError(
            'DATABASE_URL is still using a placeholder host. '
            'Replace "host" with your real PostgreSQL hostname.'
        )
    return database_url


def _build_connect_kwargs() -> dict:
    """Build psycopg2 connect() kwargs, adapting SSL for local vs cloud."""
    url = make_url(get_database_url())
    port = url.port or 5432
    query = dict(url.query) if url.query else {}

    # Decide on SSL
    if is_local_postgres():
        # Local Postgres typically doesn't have SSL configured.
        sslmode = query.get('sslmode') or 'disable'
    else:
        # Cloud providers (Neon, Supabase, RDS) require SSL.
        sslmode = query.get('sslmode') or 'require'

    connect_timeout = int(query.get('connect_timeout', '10'))

    return {
        'host': url.host,
        'port': int(port),
        'user': url.username,
        'password': url.password,
        'dbname': url.database,
        'cursor_factory': RealDictCursor,
        'connect_timeout': connect_timeout,
        'application_name': 'chess-backend',
        'sslmode': sslmode,
    }


@contextmanager
def get_connection():
    """Yield a connection, retrying once on OperationalError (cold start)."""
    for attempt in (1, 2):
        try:
            connection = psycopg2.connect(**_build_connect_kwargs())
            break
        except OperationalError as exc:
            logger.warning('Postgres connection attempt %d/2 failed: %s', attempt, exc)
            if attempt == 2:
                logger.exception('Postgres connection failed after retries')
                raise
            time.sleep(1.5)
    try:
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def fetch_one(query: str, params: Optional[dict] = None) -> Optional[dict]:
    if not is_database_url_configured():
        logger.warning('fetch_one: DATABASE_URL not configured — returning None (dev fallback)')
        return None
    try:
        with get_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(query, params or {})
                row = cursor.fetchone()
                return dict(row) if row else None
    except OperationalError as exc:
        logger.error('fetch_one OperationalError: %s', exc)
        return None


def fetch_all(query: str, params: Optional[dict] = None) -> list[dict]:
    if not is_database_url_configured():
        logger.warning('fetch_all: DATABASE_URL not configured — returning [] (dev fallback)')
        return []
    try:
        with get_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(query, params or {})
                return [dict(row) for row in cursor.fetchall()]
    except OperationalError as exc:
        logger.error('fetch_all OperationalError: %s', exc)
        return []


def execute(query: str, params: Optional[dict] = None) -> int:
    if not is_database_url_configured():
        logger.warning('execute: DATABASE_URL not configured — returning 0 (dev fallback)')
        return 0
    try:
        with get_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(query, params or {})
                return cursor.rowcount
    except OperationalError as exc:
        logger.error('execute OperationalError: %s', exc)
        return 0


def execute_returning(query: str, params: Optional[dict] = None) -> Optional[dict]:
    if not is_database_url_configured():
        logger.warning('execute_returning: DATABASE_URL not configured — returning None (dev fallback)')
        return None
    try:
        with get_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(query, params or {})
                row = cursor.fetchone()
                return dict(row) if row else None
    except OperationalError as exc:
        logger.error('execute_returning OperationalError: %s', exc)
        return None


def json_value(value: Any) -> Json:
    return Json(value)
