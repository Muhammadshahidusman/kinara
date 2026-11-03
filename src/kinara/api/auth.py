"""Logins and roles (TRD.md section 9): OAuth2 password flow, argon2 hashes, short-lived JWT.

Roles, each including the one before:
  viewer          read everything
  field_officer   + record verification verdicts
  admin           + runs, users, settings
The signing key comes from KINARA_SECRET_KEY. Without it a random key is generated once and kept in
data/processed/.secret_key (git-ignored) so tokens survive an API restart on the development PC.
"""

from __future__ import annotations

import datetime as dt
import os
import secrets
from collections.abc import Callable
from pathlib import Path

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer

from kinara.api.store import ROLES
from kinara.config import get_logger, settings

log = get_logger("kinara.api.auth")

ALGORITHM = "HS256"
_hasher = PasswordHasher()
oauth2 = OAuth2PasswordBearer(tokenUrl="/api/auth/token")


def hash_password(password: str) -> str:
    """argon2id hash for storage."""
    return _hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    """True if the password matches the stored hash (False for a malformed hash)."""
    try:
        return _hasher.verify(password_hash, password)
    except (VerifyMismatchError, InvalidHashError):
        return False


def secret_key(processed: Path | None = None) -> str:
    """Signing key from KINARA_SECRET_KEY, else a persisted random key."""
    env = os.getenv("KINARA_SECRET_KEY")
    if env:
        return env
    f = Path(processed or settings()["paths"]["processed"]) / ".secret_key"
    if not f.exists():
        f.write_text(secrets.token_urlsafe(48), encoding="utf-8")
        log.warning(f"KINARA_SECRET_KEY not set; generated a local key in {f}")
    return f.read_text(encoding="utf-8").strip()


def make_token(username: str, role: str, key: str, minutes: int) -> str:
    """Signed JWT carrying the username (sub) and role, valid for `minutes`."""
    now = dt.datetime.now(dt.UTC)
    return jwt.encode({"sub": username, "role": role, "iat": now, "exp": now + dt.timedelta(minutes=minutes)},
                      key, algorithm=ALGORITHM)


def read_token(token: str, key: str) -> dict:
    """Decoded claims.

    Raises:
        HTTPException 401: If the token is expired or invalid.
    """
    try:
        return jwt.decode(token, key, algorithms=[ALGORITHM])
    except jwt.ExpiredSignatureError as e:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "session expired, please sign in again",
                            headers={"WWW-Authenticate": "Bearer"}) from e
    except jwt.InvalidTokenError as e:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid token",
                            headers={"WWW-Authenticate": "Bearer"}) from e


def role_at_least(role: str, needed: str) -> bool:
    """Role hierarchy check: viewer < field_officer < admin."""
    return ROLES.index(role) >= ROLES.index(needed)


def require(needed: str, key_fn: Callable[[], str], user_fn: Callable[[str], dict | None]) -> Callable:
    """FastAPI dependency that returns the signed-in user if their role is at least `needed`.

    The user record is re-read on every request, so deactivating a user or changing their role
    takes effect immediately rather than when their token expires.
    """
    def dep(token: str = Depends(oauth2)) -> dict:
        claims = read_token(token, key_fn())
        user = user_fn(claims.get("sub", ""))
        if not user or not user.get("active", True):
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "unknown or inactive user",
                                headers={"WWW-Authenticate": "Bearer"})
        if not role_at_least(user["role"], needed):
            raise HTTPException(status.HTTP_403_FORBIDDEN, f"needs the {needed} role")
        return {"username": user["username"], "role": user["role"], "full_name": user.get("full_name", "")}
    return dep
