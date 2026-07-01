from datetime import datetime

from app.postgres_store import execute, json_value


def _ensure_table() -> None:
    execute(
        """
        CREATE TABLE IF NOT EXISTS audit_events (
          id BIGSERIAL PRIMARY KEY,
          event_type TEXT NOT NULL,
          payload JSONB,
          created_at TIMESTAMPTZ DEFAULT now()
        )
        """
    )

def audit_event(event_type: str, payload: dict) -> None:
    try:
        _ensure_table()
        execute(
            """
            INSERT INTO audit_events (event_type, payload, created_at)
            VALUES (%(event_type)s, %(payload)s, %(created_at)s)
            """,
            {
                'event_type': event_type,
                'payload': json_value({
                    'ts': datetime.utcnow().isoformat() + 'Z',
                    'payload': payload,
                }),
                'created_at': datetime.utcnow(),
            },
        )
    except Exception:
        # avoid raising in production paths
        pass
