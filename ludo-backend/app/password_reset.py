import logging
import os
import secrets
import threading
from datetime import datetime, timedelta

from werkzeug.security import generate_password_hash

from app.models.user import get_users, save_users
from app.postgres_store import execute, fetch_all, fetch_one

_LOCK = threading.Lock()


def _ensure_table():
    execute(
        """
        CREATE TABLE IF NOT EXISTS password_reset_tokens (
          token TEXT PRIMARY KEY,
          username TEXT NOT NULL,
          expires_at TIMESTAMPTZ
        )
        """
    )


def _find_user_by_email(email):
    users = get_users()
    for username, data in users.items():
        if data.get('email') == email:
            return username
    return None


def create_token_for_email(email, expiry_seconds=3600):
    """Create a one-time token for the user registered with `email`.

    Returns (True, {'token': token, 'dev': True}) on success when SMTP is not configured
    or (True, {'sent': True}) if the token was created and (attempted) to be emailed.
    Returns (False, 'message') on failure.
    """
    _ensure_table()
    username = _find_user_by_email(email)
    if not username:
        return False, 'Email not found'

    token = secrets.token_urlsafe(32)
    expires_at = datetime.utcnow() + timedelta(seconds=expiry_seconds)

    with _LOCK:
        execute(
            """
            INSERT INTO password_reset_tokens (token, username, expires_at)
            VALUES (%(token)s, %(username)s, %(expires_at)s)
            ON CONFLICT (token) DO UPDATE SET
                username = EXCLUDED.username,
                expires_at = EXCLUDED.expires_at
            """,
            {
                'token': token,
                'username': username,
                'expires_at': expires_at,
            }
        )

    try:
        smtp_host = os.getenv('SMTP_HOST')
        smtp_port = os.getenv('SMTP_PORT')
        smtp_user = os.getenv('SMTP_USER')
        smtp_pass = os.getenv('SMTP_PASSWORD')
        sender = os.getenv('SENDER_EMAIL')
        if smtp_host and smtp_port and sender:
            import smtplib
            from email.message import EmailMessage

            msg = EmailMessage()
            msg['Subject'] = 'Password reset for your Chess account'
            msg['From'] = sender
            msg['To'] = email
            msg.set_content(f"To reset your password, open the app and paste this token:\n\n{token}\n\nThis token expires in 1 hour.")

            server = smtplib.SMTP(smtp_host, int(smtp_port), timeout=10)
            try:
                server.starttls()
            except Exception:
                pass
            if smtp_user and smtp_pass:
                server.login(smtp_user, smtp_pass)
            server.send_message(msg)
            server.quit()
            return True, {'sent': True}
    except Exception:
        logging.getLogger(__name__).exception('Failed to send password reset email')

    if os.getenv('PASSWORD_RESET_RETURN_TOKEN', 'false').lower() in ('1', 'true', 'yes'):
        return True, {'token': token, 'dev': True}

    return True, {'sent': False}


def verify_and_consume_token(token, new_password):
    """Verify token, set new password for the corresponding user, and consume the token."""
    if not token:
        return False, 'Token required'

    _ensure_table()
    with _LOCK:
        row = fetch_one(
            'SELECT token, username, expires_at FROM password_reset_tokens WHERE token = %(token)s',
            {'token': token},
        )
        if not row:
            return False, 'Invalid token'

        now = datetime.utcnow()
        expires_at = row.get('expires_at')
        try:
            expires_dt = expires_at.replace(tzinfo=None) if hasattr(expires_at, 'replace') else datetime.fromisoformat(str(expires_at).replace('Z', '+00:00'))
        except Exception:
            expires_dt = now
        if expires_dt < now:
            execute('DELETE FROM password_reset_tokens WHERE token = %(token)s', {'token': token})
            return False, 'Token expired'

        execute('DELETE FROM password_reset_tokens WHERE token = %(token)s', {'token': token})

    username = row.get('username')
    users = get_users()
    if username not in users:
        return False, 'User not found'

    users[username]['password_hash'] = generate_password_hash(new_password)
    save_users(users)
    return True, 'Password updated'
