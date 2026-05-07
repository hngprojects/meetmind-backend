from datetime import datetime, timedelta, timezone
from typing import Any, Union
from jose import jwt
from app.core.config import settings
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError

ALGORITHM = "HS256"

# Initialize Argon2 PasswordHasher
ph = PasswordHasher()

def verify_password(password: str, hashed_password: str) -> bool:
    """Verify a password against an Argon2 hash. Safely handles missing hashes for SSO users."""
    if not hashed_password:
        return False
    try:
        return ph.verify(hashed_password, password)
    except VerifyMismatchError:
        return False

def get_password_hash(password: str) -> str:
    """Generate an Argon2 hash for a plaintext password."""
    return ph.hash(password)

def create_access_token(subject: Union[str, Any]) -> str:
    """Generate a timezone-aware JWT access token."""
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode = {
        "exp": expire,
        "sub": str(subject)
    }

    return jwt.encode(to_encode, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)

def create_refresh_token(subject: Union[str, Any]) -> str:
    """Generate a timezone-aware JWT refresh token."""
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.REFRESH_TOKEN_EXPIRE_MINUTES)

    to_encode = {
        "exp": expire,
        "sub": str(subject)
    }

    return jwt.encode(to_encode, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)