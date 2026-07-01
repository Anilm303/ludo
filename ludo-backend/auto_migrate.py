"""Auto-run SQL migrations on startup.

Reads all .sql files from the sql/ directory (in alphabetical order) and
executes them against the configured DATABASE_URL. Idempotent: every
statement uses `IF NOT EXISTS` so it's safe to run on every startup.

The splitter is smart enough to skip `;` characters that live inside
PostgreSQL dollar-quoted blocks (`$$ ... $$`).
"""
import logging
import os
import sys
from pathlib import Path

logger = logging.getLogger(__name__)

SQL_DIR = Path(__file__).resolve().parent / 'sql'


def _split_sql_statements(text):
    """Split a SQL script on top-level `;` that ends a line, ignoring empty
    lines and lines inside `$$ ... $$` dollar-quoted blocks."""
    statements = []
    buf = []
    in_dollar = False
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith('--'):
            continue
        # Toggle dollar-quoted state when we see a $$ on its own.
        if '$$' in line:
            in_dollar = not in_dollar
        buf.append(line)
        if not in_dollar and stripped.endswith(';'):
            statements.append('\n'.join(buf).rstrip(';').strip())
            buf = []
    if buf:
        leftover = '\n'.join(buf).strip()
        if leftover:
            statements.append(leftover)
    return statements


def run_all_migrations():
    """Run every .sql file in sql/ in order. Returns a summary dict."""
    if not os.getenv('DATABASE_URL', '').strip():
        msg = 'DATABASE_URL not set - skipping migrations'
        logger.warning(msg)
        return {'status': 'skipped', 'reason': msg}

    if not SQL_DIR.exists():
        msg = f'SQL directory {SQL_DIR} not found'
        logger.error(msg)
        return {'status': 'error', 'reason': msg}

    sql_files = sorted(SQL_DIR.glob('*.sql'))
    if not sql_files:
        msg = f'No .sql files found in {SQL_DIR}'
        logger.warning(msg)
        return {'status': 'skipped', 'reason': msg}

    logger.info('Running %d migration file(s) from %s', len(sql_files), SQL_DIR)

    summary = {
        'status': 'ok',
        'files_run': 0,
        'statements_executed': 0,
        'errors': [],
    }

    try:
        from app.postgres_store import get_connection
        with get_connection() as conn:
            for sql_file in sql_files:
                logger.info('Running migration: %s', sql_file.name)
                statements = _split_sql_statements(
                    sql_file.read_text(encoding='utf-8')
                )
                # Each statement runs in its own short transaction so a
                # syntax error in one doesn't poison the rest.
                for stmt in statements:
                    if not stmt.strip():
                        continue
                    try:
                        with conn.cursor() as cur:
                            cur.execute(stmt)
                        conn.commit()
                        summary['statements_executed'] += 1
                    except Exception as exc:
                        conn.rollback()
                        err = f'{sql_file.name}: {exc}'
                        logger.warning('Migration statement failed: %s', err)
                        summary['errors'].append(err)
                summary['files_run'] += 1
    except Exception as exc:
        logger.exception('Migration run failed')
        summary['status'] = 'error'
        summary['errors'].append(str(exc))

    return summary


if __name__ == '__main__':
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    )
    result = run_all_migrations()
    print('\n=== Migration summary ===')
    for key, value in result.items():
        if isinstance(value, list) and len(value) > 5:
            print(f'  {key}: [{len(value)} entries, first 3:]')
            for item in value[:3]:
                print(f'    - {item[:120]}')
        else:
            print(f'  {key}: {value}')
    sys.exit(0 if result.get('status') == 'ok' else 1)
