"""
FastAPI dependency helpers: JWT authentication + RBAC, DB session.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import settings
from domain.models import UserRole
from infra.database import db_session_dep

# ── Password hashing ──────────────────────────────────────────────────────────
_pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/token")


def _verify_password(plain: str, hashed: str) -> bool:
    return _pwd_context.verify(plain, hashed)


def _hash_password(plain: str) -> str:
    return _pwd_context.hash(plain)


# ── Static user store (loaded from HEALER_USERS env) ─────────────────────────
def _load_users() -> dict[str, dict]:
    """Returns {username: {hashed_password, role}} from config."""
    users = {}
    for entry in settings.get_users():
        users[entry["username"]] = {
            "hashed_password": _hash_password(entry["password"]),
            "role": entry["role"],
        }
    return users


_USERS: dict[str, dict] | None = None


def _get_users() -> dict[str, dict]:
    global _USERS
    if _USERS is None:
        _USERS = _load_users()
    return _USERS


# ── JWT helpers ────────────────────────────────────────────────────────────────
def create_access_token(username: str, role: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(
        minutes=settings.jwt_access_token_expire_minutes
    )
    return jwt.encode(
        {"sub": username, "role": role, "exp": expire},
        settings.jwt_secret_key,
        algorithm=settings.jwt_algorithm,
    )


def authenticate_user(username: str, password: str) -> dict | None:
    users = _get_users()
    user = users.get(username)
    if user and _verify_password(password, user["hashed_password"]):
        return {"username": username, "role": user["role"]}
    return None


# ── FastAPI dependencies ──────────────────────────────────────────────────────
async def get_current_user(token: Annotated[str, Depends(oauth2_scheme)]) -> dict:
    credentials_exc = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired token",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
        username: str = payload.get("sub", "")
        role: str = payload.get("role", "")
        if not username:
            raise credentials_exc
        return {"username": username, "role": role}
    except JWTError:
        raise credentials_exc


def require_role(*allowed_roles: UserRole | str):
    """Factory: returns a dependency that enforces one of the given roles."""
    def _check(current_user: Annotated[dict, Depends(get_current_user)]) -> dict:
        if current_user["role"] not in [r.value if isinstance(r, UserRole) else r for r in allowed_roles]:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Requires role: {allowed_roles}",
            )
        return current_user
    return _check


# Shorthand role guards
require_viewer  = require_role(UserRole.VIEWER, UserRole.OPERATOR, UserRole.ADMIN)
require_operator = require_role(UserRole.OPERATOR, UserRole.ADMIN)
require_admin   = require_role(UserRole.ADMIN)

# DB session dependency alias
DbSession = Annotated[AsyncSession, Depends(db_session_dep)]
