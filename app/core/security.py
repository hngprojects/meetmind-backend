from datetime import datetime, timedelta
from typing import Any, Union
from jose import jwt
from app.core.config import settings
from passlib.context import CryptContext

ALGORITHM = "HS256"

password_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def verify_password(password: str, hashed_password: str) -> bool:
    return password_context.verify(password, hashed_password)



def create_access_token(subject: Union[str, Any]) -> str:
    expire = datetime.utcnow() + timedelta(minutes=15)
    to_encode = {
        "exp": expire,
        "sub": str(subject)
    }

    encoded_jwt = jwt.encode(to_encode, settings.JWT_ACCESS_SECRET, algorithm=ALGORITHM)

    return encoded_jwt

def create_refresh_token(subject: Union[str, Any]) -> str:
    expire = datetime.utcnow() + timedelta(days=7)

    to_encode = {
        "exp": expire,
        "sub": str(subject)
    }

    encoded_jwt = jwt.encode(to_encode, settings.JWT_REFRESH_SECRET, algorithm=ALGORITHM)

    return encoded_jwt
    