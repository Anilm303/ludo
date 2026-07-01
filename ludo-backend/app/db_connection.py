# Database Connection Setup for PostgreSQL-backed Flask app
import logging

from app.postgres_store import get_connection

logger = logging.getLogger(__name__)


async def init_db():
    """Verify the database connection is available."""
    try:
        with get_connection():
            pass
        logger.info("Database connection verified successfully")
    except Exception as exc:
        logger.error(f"Error initializing database connection: {exc}")
        raise


async def close_db():
    """Kept for compatibility with the existing app startup hook."""
    logger.info("Database connection closed")


def get_db():
    """Compatibility generator retained for routes that may import it."""
    with get_connection() as connection:
        yield connection
