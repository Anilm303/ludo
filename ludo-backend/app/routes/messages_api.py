from fastapi import APIRouter, Header, HTTPException
from typing import List

from app.models.user import get_users, User
from app.routes.auth_api import _decode_token, _extract_bearer_token

router = APIRouter()


def _user_to_chatuser(user_data: dict) -> dict:
    return {
        'username': user_data.get('username'),
        'first_name': user_data.get('first_name') or '',
        'last_name': user_data.get('last_name') or '',
        'email': user_data.get('email') or '',
        'profile_image': user_data.get('profile_image'),
        'bio': user_data.get('bio') or '',
        'is_online': user_data.get('is_online', False),
        'last_seen': user_data.get('last_seen') or None,
        'last_message': None,
        'last_message_time': None,
        'unread_count': 0,
    }


@router.get('/messages/users')
async def list_users():
    """Return list of registered users in a shape the frontend expects."""
    users = get_users() or {}
    # get_users returns a dict keyed by username
    result = [ _user_to_chatuser(u) for u in users.values() ]
    return {'success': True, 'users': result, 'count': len(result)}


@router.get('/messages/profile')
async def profile(authorization: str | None = Header(default=None, alias='Authorization')):
    """Return current user profile based on bearer token."""
    token = _extract_bearer_token(authorization)
    payload = _decode_token(token)
    username = payload.get('username') or payload.get('sub')
    if not username:
        raise HTTPException(status_code=401, detail='Invalid token payload')
    user = User.get_by_username(username)
    if not user:
        raise HTTPException(status_code=404, detail='User not found')
    # Return a ChatUser-like payload
    data = {
        'username': user.username,
        'first_name': user.first_name or '',
        'last_name': user.last_name or '',
        'email': user.email or '',
        'profile_image': user.profile_image,
        'bio': user.bio or '',
        'is_online': User.is_online(user.username),
        'last_seen': user.last_seen,
    }
    return {'success': True, 'user': data}


@router.get('/messages/conversations')
async def conversations():
    """Return an empty conversations list for now (frontend can handle empty)."""
    return {'success': True, 'conversations': []}
