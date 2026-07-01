import os
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel
from jose import jwt, JWTError

from app.models.user import User
from app.token_store import revoke_token, is_token_revoked

router = APIRouter()

ALGORITHM = 'HS256'
SECRET_KEY = os.getenv('JWT_SECRET_KEY') or os.getenv('SECRET_KEY') or 'change-me-in-production'
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv('ACCESS_TOKEN_EXPIRE_MINUTES', '60'))
REFRESH_TOKEN_EXPIRE_DAYS = int(os.getenv('REFRESH_TOKEN_EXPIRE_DAYS', '30'))


class LoginRequest(BaseModel):
    username: str
    password: str


class RegisterRequest(BaseModel):
    username: str
    email: str
    first_name: str
    last_name: str
    password: str


class RefreshRequest(BaseModel):
    refresh_token: str


class FcmTokenRequest(BaseModel):
    fcm_token: str


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _user_payload(user: User) -> dict:
    return {
        'username': user.username,
        'email': user.email,
        'first_name': user.first_name,
        'last_name': user.last_name,
        'created_at': user.created_at,
    }


def _create_token(user: User, token_type: str, expires_delta: timedelta) -> str:
    now = _now_utc()
    payload = {
        'sub': user.username,
        'type': token_type,
        'jti': uuid.uuid4().hex,
        'iat': int(now.timestamp()),
        'exp': int((now + expires_delta).timestamp()),
        'username': user.username,
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def _decode_token(token: str) -> dict:
    try:
        return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except JWTError as exc:
        raise HTTPException(status_code=401, detail='Invalid token') from exc


def _extract_bearer_token(authorization: str | None) -> str:
    if not authorization:
        raise HTTPException(status_code=401, detail='Missing authorization header')
    if not authorization.lower().startswith('bearer '):
        raise HTTPException(status_code=401, detail='Invalid authorization header')
    return authorization.split(' ', 1)[1].strip()


@router.post('/auth/register')
async def register(payload: RegisterRequest):
    success, result = User.register(
        payload.username,
        payload.email,
        payload.first_name,
        payload.last_name,
        payload.password,
    )
    if not success:
        raise HTTPException(status_code=400, detail=result)

    user = result
    access_token = _create_token(user, 'access', timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    refresh_token = _create_token(user, 'refresh', timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS))
    return {
        'success': True,
        'message': 'Registration successful',
        'access_token': access_token,
        'refresh_token': refresh_token,
        'user': _user_payload(user),
    }


@router.post('/auth/login')
async def login(payload: LoginRequest):
    success, result = User.login(payload.username, payload.password)
    if not success:
        raise HTTPException(status_code=401, detail=result)

    user = result
    access_token = _create_token(user, 'access', timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    refresh_token = _create_token(user, 'refresh', timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS))
    return {
        'success': True,
        'message': 'Login successful',
        'access_token': access_token,
        'refresh_token': refresh_token,
        'user': _user_payload(user),
    }


@router.get('/auth/validate-token')
async def validate_token(authorization: str | None = Header(default=None, alias='Authorization')):
    token = _extract_bearer_token(authorization)
    payload = _decode_token(token)
    if is_token_revoked(payload.get('jti')):
        raise HTTPException(status_code=401, detail='Token has been revoked')

    username = payload.get('username') or payload.get('sub')
    user = User.get_by_username(username)
    if not user:
        raise HTTPException(status_code=401, detail='User not found')

    return {
        'success': True,
        'message': 'Token valid',
        'user': _user_payload(user),
    }


@router.post('/auth/refresh')
async def refresh(payload: RefreshRequest):
    decoded = _decode_token(payload.refresh_token)
    if decoded.get('type') != 'refresh':
        raise HTTPException(status_code=401, detail='Invalid refresh token')
    if is_token_revoked(decoded.get('jti')):
        raise HTTPException(status_code=401, detail='Refresh token has been revoked')

    username = decoded.get('username') or decoded.get('sub')
    user = User.get_by_username(username)
    if not user:
        raise HTTPException(status_code=401, detail='User not found')

    revoke_token(decoded.get('jti'), token_type='refresh')
    access_token = _create_token(user, 'access', timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    refresh_token = _create_token(user, 'refresh', timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS))
    return {
        'success': True,
        'message': 'Token refreshed',
        'access_token': access_token,
        'refresh_token': refresh_token,
        'user': _user_payload(user),
    }


@router.post('/auth/logout')
async def logout(authorization: str | None = Header(default=None, alias='Authorization')):
    token = _extract_bearer_token(authorization)
    payload = _decode_token(token)
    revoke_token(payload.get('jti'), token_type=payload.get('type', 'access'))
    return {'success': True, 'message': 'Logged out successfully'}


@router.post('/auth/update-fcm-token')
async def update_fcm_token(payload: FcmTokenRequest, authorization: str | None = Header(default=None, alias='Authorization')):
    token = _extract_bearer_token(authorization)
    decoded = _decode_token(token)
    if decoded.get('type') != 'access':
        raise HTTPException(status_code=401, detail='Invalid access token')

    username = decoded.get('username') or decoded.get('sub')
    if not User.set_fcm_token(username, payload.fcm_token):
        raise HTTPException(status_code=404, detail='User not found')
    return {'success': True, 'message': 'FCM token updated'}


@router.get('/auth/health')
async def health():
    return {'success': True, 'message': 'Auth service is healthy'}


@router.post('/auth/forgot-password')
async def forgot_password(payload: dict):
    email = (payload or {}).get('email', '')
    return {'success': True, 'message': 'Password reset request accepted', 'email': email}


@router.post('/auth/reset-password')
async def reset_password(payload: dict):
    return {'success': True, 'message': 'Password reset successful'}