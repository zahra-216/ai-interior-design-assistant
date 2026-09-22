"""
Signed login tokens, shared by Agent 1 (issues them at login) and Agent 2 (checks them).

A token is  base64url("<user_id>:<expires_at>") + "." + base64url(HMAC-SHA256 signature).
Only a server that knows AUTH_SECRET can create a valid one, so the browser can no longer
claim to be any user it likes. Tokens expire (default 7 days), after which the user logs in again.

Both agents must use the same secret. Set it in each agent's .env:
    AUTH_SECRET=<a long random string>
    AUTH_TOKEN_TTL_HOURS=168
"""

import base64
import hashlib
import hmac
import os
import time

from dotenv import load_dotenv
from fastapi import Header, HTTPException

load_dotenv()

_DEV_SECRET = "dev-only-insecure-secret-change-me"
SECRET = os.getenv("AUTH_SECRET") or _DEV_SECRET
TOKEN_TTL_S = int(float(os.getenv("AUTH_TOKEN_TTL_HOURS", "168")) * 3600)

if SECRET == _DEV_SECRET:
    print("WARNING: AUTH_SECRET is not set in .env; using an insecure development secret.")


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def _sign(payload: bytes) -> bytes:
    return hmac.new(SECRET.encode(), payload, hashlib.sha256).digest()


def create_token(user_id) -> tuple:
    """Returns (token, expires_at unix seconds)."""
    expires_at = int(time.time()) + TOKEN_TTL_S
    payload = f"{user_id}:{expires_at}".encode()
    return f"{_b64(payload)}.{_b64(_sign(payload))}", expires_at


def verify_token(token: str):
    """The user id inside a valid, unexpired token, otherwise None."""
    try:
        payload_part, sig_part = token.split(".")
        payload = _unb64(payload_part)
        if not hmac.compare_digest(_sign(payload), _unb64(sig_part)):
            return None
        user_id, expires_at = payload.decode().rsplit(":", 1)
        if int(expires_at) < time.time():
            return None
        return user_id
    except (ValueError, UnicodeDecodeError):
        return None


def current_user(authorization: str = Header(default="")) -> str:
    """FastAPI dependency: the logged-in user's id, or 401."""
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Please log in.")
    user_id = verify_token(authorization[len("Bearer "):].strip())
    if user_id is None:
        raise HTTPException(status_code=401, detail="Your session has expired. Please log in again.")
    return user_id


def ensure_owner(current_user_id: str, user_id) -> None:
    """403 unless the request is about the logged-in user's own data."""
    if str(user_id) != str(current_user_id):
        raise HTTPException(status_code=403, detail="You can only access your own designs.")
