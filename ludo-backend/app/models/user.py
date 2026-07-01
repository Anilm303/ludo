import json
import os
from datetime import datetime
from pathlib import Path
from werkzeug.security import generate_password_hash, check_password_hash

from sqlalchemy.engine import make_url

from app.postgres_store import execute, execute_returning, fetch_all, fetch_one, json_value

ONLINE_USERS = {}  # Track online users and their socket IDs
LOCAL_USER_STORE = Path(__file__).resolve().parents[2] / 'data' / 'users.json'


def _database_url_is_valid() -> bool:
    database_url = os.getenv('DATABASE_URL', '').strip()
    if not database_url:
      return False

    try:
        url = make_url(database_url)
    except Exception:
        return False

    host = (url.host or '').strip().lower()
    return bool(host and host not in {'host', '#host#'})


def _use_local_user_store() -> bool:
    return not _database_url_is_valid()


def _load_local_users():
    if not LOCAL_USER_STORE.exists():
        LOCAL_USER_STORE.parent.mkdir(parents=True, exist_ok=True)
        LOCAL_USER_STORE.write_text('{}', encoding='utf-8')
        return {}

    try:
        with LOCAL_USER_STORE.open('r', encoding='utf-8') as file_handle:
            data = json.load(file_handle)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _save_local_users(users):
    LOCAL_USER_STORE.parent.mkdir(parents=True, exist_ok=True)
    with LOCAL_USER_STORE.open('w', encoding='utf-8') as file_handle:
        json.dump(users, file_handle, indent=2)


def _now_iso():
    return datetime.utcnow().isoformat()


class User:
    """User model with profile support and tournament wallet"""

    def __init__(self, username, email, first_name, last_name, password_hash,
                 profile_image=None, bio=None, fcm_token=None, created_at=None,
                 last_seen=None, friends=None, friend_requests=None,
                 wallet_balance=0.0):
        self.username = username
        self.email = email
        self.first_name = first_name
        self.last_name = last_name
        self.password_hash = password_hash
        self.profile_image = profile_image
        self.bio = bio or ""
        self.fcm_token = fcm_token
        self.created_at = created_at or datetime.utcnow().isoformat()
        self.last_seen = last_seen or datetime.utcnow().isoformat()
        self.friends = friends or []
        self.friend_requests = friend_requests or []
        self.wallet_balance = float(wallet_balance or 0)

    def to_dict(self, include_password=False):
        data = {
            'username': self.username,
            'email': self.email,
            'first_name': self.first_name,
            'last_name': self.last_name,
            'profile_image': self.profile_image,
            'bio': self.bio,
            'fcm_token': self.fcm_token,
            'created_at': self.created_at,
            'last_seen': self.last_seen,
            'friends': self.friends,
            'friend_requests': self.friend_requests,
            'is_online': ONLINE_USERS.get(self.username) is not None,
            'wallet_balance': self.wallet_balance,
        }
        if include_password:
            data['password_hash'] = self.password_hash
        return data

    # --------------- Wallet helpers ---------------
    @staticmethod
    def _persist_wallet(username: str, balance: float) -> None:
        if _use_local_user_store():
            users = _load_local_users()
            u = users.get(username)
            if u is None:
                return
            u['wallet_balance'] = float(balance)
            users[username] = u
            _save_local_users(users)
        else:
            execute(
                'UPDATE users SET wallet_balance = %(bal)s WHERE username = %(u)s',
                {'bal': float(balance), 'u': username},
            )

    @staticmethod
    def get_wallet_balance(username: str) -> float:
        u = User.get_by_username(username)
        return float(u.wallet_balance) if u else 0.0

    @staticmethod
    def credit_wallet(username: str, amount: float) -> float:
        """Add funds to a user's wallet. Returns the new balance."""
        if amount <= 0:
            return User.get_wallet_balance(username)
        u = User.get_by_username(username)
        if not u:
            raise ValueError('User not found')
        new_balance = float(u.wallet_balance) + float(amount)
        User._persist_wallet(username, new_balance)
        return new_balance

    @staticmethod
    def debit_wallet(username: str, amount: float) -> float:
        """Remove funds from a user's wallet. Raises if insufficient balance."""
        if amount <= 0:
            return User.get_wallet_balance(username)
        u = User.get_by_username(username)
        if not u:
            raise ValueError('User not found')
        if float(u.wallet_balance) < float(amount):
            raise ValueError('Insufficient wallet balance')
        new_balance = float(u.wallet_balance) - float(amount)
        User._persist_wallet(username, new_balance)
        return new_balance

    @staticmethod
    def _row_to_user(row):
        if not row:
            return None
        return User(
            row['username'],
            row.get('email'),
            row.get('first_name'),
            row.get('last_name'),
            row.get('password_hash'),
            row.get('profile_image'),
            row.get('bio'),
            row.get('fcm_token'),
            row.get('created_at').isoformat() if row.get('created_at') else None,
            row.get('last_seen').isoformat() if row.get('last_seen') else None,
            row.get('friends') or [],
            row.get('friend_requests') or [],
        )

    @staticmethod
    def register(username, email, first_name, last_name, password):
        """Register a new user"""
        if User.get_by_username(username):
            return False, 'Username already exists'

        if any(user.get('email') == email for user in get_users().values()):
            return False, 'Email already registered'

        password_hash = generate_password_hash(password)
        now = datetime.utcnow()

        if _use_local_user_store():
            users = _load_local_users()
            users[username] = {
                'username': username,
                'email': email,
                'first_name': first_name,
                'last_name': last_name,
                'password_hash': password_hash,
                'profile_image': None,
                'bio': '',
                'fcm_token': None,
                'friends': [],
                'friend_requests': [],
                'created_at': now.isoformat(),
                'last_seen': now.isoformat(),
            }
            _save_local_users(users)
            return True, User.get_by_username(username)

        query = """
            INSERT INTO users (
                username, email, first_name, last_name, password_hash,
                profile_image, bio, fcm_token, friends, friend_requests,
                created_at, last_seen
            ) VALUES (
                %(username)s, %(email)s, %(first_name)s, %(last_name)s, %(password_hash)s,
                %(profile_image)s, %(bio)s, %(fcm_token)s,
                %(friends)s, %(friend_requests)s,
                %(created_at)s, %(last_seen)s
            )
        """
        execute(query, {
            'username': username,
            'email': email,
            'first_name': first_name,
            'last_name': last_name,
            'password_hash': password_hash,
            'profile_image': None,
            'bio': '',
            'fcm_token': None,
            'friends': json_value([]),
            'friend_requests': json_value([]),
            'created_at': now,
            'last_seen': now,
        })
        return True, User.get_by_username(username)

    @staticmethod
    def login(username, password):
        """Authenticate user with a specific error message."""
        user = User.get_by_username(username)
        if not user:
            return False, 'No account found with this username. Please register first.'
        if not check_password_hash(user.password_hash, password):
            return False, 'Wrong password. Please try again.'
        return True, user

    @staticmethod
    def get_by_username(username):
        """Get user by username"""
        if _use_local_user_store():
            user_data = _load_local_users().get(username)
            if not user_data:
                return None
            return User(
                user_data.get('username', ''),
                user_data.get('email'),
                user_data.get('first_name', ''),
                user_data.get('last_name', ''),
                user_data.get('password_hash', ''),
                user_data.get('profile_image'),
                user_data.get('bio', ''),
                user_data.get('fcm_token'),
                user_data.get('created_at'),
                user_data.get('last_seen'),
                user_data.get('friends') or [],
                user_data.get('friend_requests') or [],
            )

        row = fetch_one(
            "SELECT * FROM users WHERE username = %(username)s",
            {'username': username},
        )
        return User._row_to_user(row)

    @staticmethod
    def get_all_users():
        """Get all registered users with online status"""
        if _use_local_user_store():
            users = _load_local_users()
            for username, user_data in users.items():
                user_data['is_online'] = ONLINE_USERS.get(username) is not None
            return users

        rows = fetch_all("SELECT * FROM users ORDER BY username")
        users = {}
        for row in rows:
            users[row['username']] = {
                'username': row['username'],
                'email': row.get('email'),
                'first_name': row.get('first_name', ''),
                'last_name': row.get('last_name', ''),
                'password_hash': row.get('password_hash'),
                'profile_image': row.get('profile_image'),
                'bio': row.get('bio', ''),
                'fcm_token': row.get('fcm_token'),
                'created_at': row.get('created_at').isoformat() if row.get('created_at') else None,
                'last_seen': row.get('last_seen').isoformat() if row.get('last_seen') else '',
                'friends': row.get('friends') or [],
                'friend_requests': row.get('friend_requests') or [],
            }
        return users

    @staticmethod
    def update_profile(username, first_name=None, last_name=None, bio=None, profile_image=None):
        """Update user profile information"""
        user = User.get_by_username(username)
        if not user:
            return False, 'User not found'

        if _use_local_user_store():
            users = _load_local_users()
            user_data = users.get(username)
            if not user_data:
                return False, 'User not found'
            if first_name is not None:
                user_data['first_name'] = first_name
            if last_name is not None:
                user_data['last_name'] = last_name
            if bio is not None:
                user_data['bio'] = bio
            if profile_image is not None:
                user_data['profile_image'] = profile_image
            users[username] = user_data
            _save_local_users(users)
            return True, 'Profile updated'

        query = """
            UPDATE users
            SET first_name = COALESCE(%(first_name)s, first_name),
                last_name = COALESCE(%(last_name)s, last_name),
                bio = COALESCE(%(bio)s, bio),
                profile_image = COALESCE(%(profile_image)s, profile_image)
            WHERE username = %(username)s
        """
        execute(query, {
            'username': username,
            'first_name': first_name,
            'last_name': last_name,
            'bio': bio,
            'profile_image': profile_image,
        })
        return True, 'Profile updated'

    @staticmethod
    def set_fcm_token(username, token):
        """Update user's FCM token"""
        if _use_local_user_store():
            users = _load_local_users()
            user_data = users.get(username)
            if not user_data:
                return False
            user_data['fcm_token'] = token
            users[username] = user_data
            _save_local_users(users)
            return True

        rowcount = execute(
            "UPDATE users SET fcm_token = %(token)s WHERE username = %(username)s",
            {'username': username, 'token': token},
        )
        return rowcount > 0

    @staticmethod
    def get_fcm_token(username):
        """Get user's FCM token"""
        if _use_local_user_store():
            user_data = _load_local_users().get(username)
            if not user_data:
                return None
            return user_data.get('fcm_token')

        row = fetch_one(
            "SELECT fcm_token FROM users WHERE username = %(username)s",
            {'username': username},
        )
        return row.get('fcm_token') if row else None

    @staticmethod
    def set_online(username, socket_id=None):
        """Mark user as online"""
        ONLINE_USERS[username] = socket_id or True
        if _use_local_user_store():
            users = _load_local_users()
            user_data = users.get(username)
            if user_data:
                user_data['last_seen'] = _now_iso()
                users[username] = user_data
                _save_local_users(users)
            return

        execute(
            "UPDATE users SET last_seen = %(last_seen)s WHERE username = %(username)s",
            {'username': username, 'last_seen': datetime.utcnow()},
        )

    @staticmethod
    def set_offline(username):
        """Mark user as offline"""
        ONLINE_USERS.pop(username, None)
        if _use_local_user_store():
            users = _load_local_users()
            user_data = users.get(username)
            if user_data:
                user_data['last_seen'] = _now_iso()
                users[username] = user_data
                _save_local_users(users)
            return

        execute(
            "UPDATE users SET last_seen = %(last_seen)s WHERE username = %(username)s",
            {'username': username, 'last_seen': datetime.utcnow()},
        )

    @staticmethod
    def is_online(username):
        """Check if user is online"""
        return ONLINE_USERS.get(username) is not None

    @staticmethod
    def get_online_users():
        """Get list of online users"""
        return list(ONLINE_USERS.keys())


# Compatibility helpers expected by routes and websocket code.
def get_users():
    return User.get_all_users()


def save_users(users):
    """Upsert a users dict into PostgreSQL."""
    if _use_local_user_store():
        _save_local_users(users)
        return

    for username, user_data in users.items():
        execute(
            """
            INSERT INTO users (
                username, email, first_name, last_name, password_hash,
                profile_image, bio, fcm_token, friends, friend_requests,
                created_at, last_seen
            ) VALUES (
                %(username)s, %(email)s, %(first_name)s, %(last_name)s, %(password_hash)s,
                %(profile_image)s, %(bio)s, %(fcm_token)s,
                %(friends)s, %(friend_requests)s,
                %(created_at)s, %(last_seen)s
            )
            ON CONFLICT (username) DO UPDATE SET
                email = EXCLUDED.email,
                first_name = EXCLUDED.first_name,
                last_name = EXCLUDED.last_name,
                password_hash = EXCLUDED.password_hash,
                profile_image = EXCLUDED.profile_image,
                bio = EXCLUDED.bio,
                fcm_token = EXCLUDED.fcm_token,
                friends = EXCLUDED.friends,
                friend_requests = EXCLUDED.friend_requests,
                last_seen = EXCLUDED.last_seen
            """,
            {
                'username': username,
                'email': user_data.get('email'),
                'first_name': user_data.get('first_name'),
                'last_name': user_data.get('last_name'),
                'password_hash': user_data.get('password_hash'),
                'profile_image': user_data.get('profile_image'),
                'bio': user_data.get('bio', ''),
                'fcm_token': user_data.get('fcm_token'),
                'friends': json_value(user_data.get('friends', [])),
                'friend_requests': json_value(user_data.get('friend_requests', [])),
                'created_at': user_data.get('created_at') or datetime.utcnow(),
                'last_seen': user_data.get('last_seen') or datetime.utcnow(),
            }
        )
