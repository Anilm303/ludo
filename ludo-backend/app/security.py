import re
import threading
import time
from functools import wraps

from flask import jsonify, request
from flask_jwt_extended import get_jwt_identity, verify_jwt_in_request

_RATE_LIMIT_STORE = {}
_RATE_LIMIT_LOCK = threading.Lock()

USERNAME_RE = re.compile(r'^[A-Za-z0-9_.-]{3,32}$')
EMAIL_RE = re.compile(r'^[^\s@]+@[^\s@]+\.[^\s@]+$')
NAME_RE = re.compile(r'^[A-Za-z0-9][A-Za-z0-9 .\'-]{0,49}$')


def get_client_ip():
    forwarded_for = request.headers.get('X-Forwarded-For', '')
    if forwarded_for:
        return forwarded_for.split(',')[0].strip()
    real_ip = request.headers.get('X-Real-IP', '').strip()
    if real_ip:
        return real_ip
    return request.remote_addr or 'unknown'


def normalize_text(value, max_length=5000):
    if value is None:
        return ''
    text = str(value).strip()
    text = ''.join(ch for ch in text if ch == '\n' or ch == '\r' or ch == '\t' or ord(ch) >= 32)
    return text[:max_length]


def validate_username(username):
    value = normalize_text(username, 32)
    if not USERNAME_RE.match(value):
        return False, 'Username must be 3-32 characters and may contain letters, numbers, dots, underscores, or hyphens.'
    return True, value


def validate_email(email):
    value = normalize_text(email, 254)
    if not EMAIL_RE.match(value):
        return False, 'Invalid email address.'
    return True, value


def validate_name(name, field_name='Name'):
    value = normalize_text(name, 50)
    if not NAME_RE.match(value):
        return False, f'{field_name} must be 1-50 characters and contain only letters, numbers, spaces, dots, apostrophes, or hyphens.'
    return True, value


def validate_password(password, min_length=6, max_length=128):
    value = str(password or '')
    if len(value) < min_length:
      return False, f'Password must be at least {min_length} characters.'
    if len(value) > max_length:
        return False, f'Password must be at most {max_length} characters.'
    return True, value


def validate_message_text(text, max_length=4000):
    value = normalize_text(text, max_length)
    if not value:
        return False, 'Message text is required.'
    return True, value


def validate_bio(bio, max_length=280):
    return True, normalize_text(bio, max_length)


def validate_media_type(media_type, allowed=('image', 'video', 'audio')):
    value = normalize_text(media_type, 16).lower()
    if value not in allowed:
        return False, f'media_type must be one of: {", ".join(allowed)}'
    return True, value


def require_json_body():
    if not request.is_json:
        return None, (jsonify({'success': False, 'message': 'Request must be JSON'}), 400)
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return None, (jsonify({'success': False, 'message': 'Invalid JSON body'}), 400)
    return data, None


def rate_limit(limit=10, window_seconds=60, scope=None):
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            identity = None
            try:
                verify_jwt_in_request(optional=True)
                identity = get_jwt_identity()
            except Exception:
                identity = None

            actor = identity or get_client_ip()
            route_scope = scope or request.endpoint or func.__name__
            key = f'{route_scope}:{actor}'
            now = time.time()

            with _RATE_LIMIT_LOCK:
                bucket = _RATE_LIMIT_STORE.get(key)
                if bucket is None or now - bucket['window_start'] >= window_seconds:
                    _RATE_LIMIT_STORE[key] = {'window_start': now, 'count': 1}
                else:
                    if bucket['count'] >= limit:
                        retry_after = max(1, int(window_seconds - (now - bucket['window_start'])))
                        response = jsonify({
                            'success': False,
                            'message': 'Too many requests. Please try again later.',
                        })
                        response.status_code = 429
                        response.headers['Retry-After'] = str(retry_after)
                        return response
                    bucket['count'] += 1

                expired = [k for k, v in _RATE_LIMIT_STORE.items() if now - v['window_start'] >= window_seconds]
                for expired_key in expired:
                    _RATE_LIMIT_STORE.pop(expired_key, None)

            return func(*args, **kwargs)

        return wrapper

    return decorator
