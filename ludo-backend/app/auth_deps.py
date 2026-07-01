"""Shared FastAPI dependencies for auth-related helpers.

Kept in its own module to avoid circular imports between the payments and
tournament routers (both of which need to read the user id off the JWT).
"""
from typing import Optional

from fastapi import Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import base64
import json

security = HTTPBearer(auto_error=False)


def get_current_user_id(
    creds: Optional[HTTPAuthorizationCredentials] = Depends(security),
) -> Optional[str]:
    """Best-effort extraction of the user id from a Bearer JWT.

    Returns None when no token is supplied (anonymous request). The router
    decides whether anonymous access is allowed (typically only for local dev
    with no database configured).
    """
    if not creds or not creds.credentials:
        return None
    try:
        parts = creds.credentials.split('.')
        if len(parts) < 2:
            return None
        payload_b64 = parts[1] + '=' * (-len(parts[1]) % 4)
        payload = json.loads(base64.urlsafe_b64decode(payload_b64))
        return str(payload.get('sub') or payload.get('user_id') or '') or None
    except Exception:
        return None
