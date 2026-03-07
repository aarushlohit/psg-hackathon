"""CLARA server — JWT authentication service."""

import hashlib
import hmac
import json
import logging
import secrets
import time
from typing import Optional

from clara.config.settings import settings

logger = logging.getLogger("clara.connections")

_JWT_SECRET = settings.security.jwt_secret.encode()
_JWT_ALG = settings.security.jwt_algorithm
_JWT_EXP = settings.security.jwt_expire_minutes * 60


def _b64url(data: bytes) -> str:
    import base64
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _b64url_decode(s: str) -> bytes:
    import base64
    pad = 4 - len(s) % 4
    return base64.urlsafe_b64decode(s + "=" * pad)


def create_token(username: str, role: str = "user") -> str:
    """Create a HS256 JWT for the given user."""
    header = _b64url(json.dumps({"alg": "HS256", "typ": "JWT"}).encode())
    payload = _b64url(json.dumps({
        "sub": username,
        "role": role,
        "iat": int(time.time()),
        "exp": int(time.time()) + _JWT_EXP,
        "jti": secrets.token_hex(8),
    }).encode())
    sig_input = f"{header}.{payload}".encode()
    sig = _b64url(hmac.new(_JWT_SECRET, sig_input, hashlib.sha256).digest())
    return f"{header}.{payload}.{sig}"


def verify_token(token: str) -> Optional[dict]:
    """Verify a JWT and return the payload, or None if invalid."""
    try:
        parts = token.split(".")
        if len(parts) != 3:
            return None
        header_b64, payload_b64, sig_b64 = parts
        sig_input = f"{header_b64}.{payload_b64}".encode()
        expected_sig = _b64url(hmac.new(_JWT_SECRET, sig_input, hashlib.sha256).digest())
        if not hmac.compare_digest(sig_b64, expected_sig):
            return None
        payload = json.loads(_b64url_decode(payload_b64))
        if payload.get("exp", 0) < time.time():
            return None
        return payload
    except Exception:
        return None
