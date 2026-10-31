import os
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any
import jwt
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError, InvalidHashError

# Argon2id password hasher (RFC 9106 recommended)
_hasher = PasswordHasher()

def get_jwt_secret() -> str:
    return os.getenv("JWT_SECRET_KEY", "library-automation-super-secret-key-change-in-prod-2026")

ALGORITHM = "HS256"
DEFAULT_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", str(60 * 24)))  # 24 hours

def hash_password(password: str) -> str:
    """Hashes a plain text password using Argon2id."""
    if not password or len(password) < 6:
        raise ValueError("Password must be at least 6 characters.")
    return _hasher.hash(password)

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verifies a plain text password against an Argon2id hash."""
    if not plain_password or not hashed_password:
        return False
    try:
        return _hasher.verify(hashed_password, plain_password)
    except (VerifyMismatchError, InvalidHashError, Exception):
        return False

def create_access_token(data: Dict[str, Any], expires_delta: Optional[timedelta] = None) -> str:
    """Creates a signed JSON Web Token (JWT)."""
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=DEFAULT_EXPIRE_MINUTES)
        
    to_encode.update({"exp": expire, "iat": datetime.now(timezone.utc)})
    secret = get_jwt_secret()
    encoded_jwt = jwt.encode(to_encode, secret, algorithm=ALGORITHM)
    return encoded_jwt

def decode_access_token(token: str) -> Optional[Dict[str, Any]]:
    """Decodes and validates a JWT token. Returns payload dict or None on any failure."""
    if not token or not isinstance(token, str):
        return None
    try:
        secret = get_jwt_secret()
        payload = jwt.decode(token, secret, algorithms=[ALGORITHM])
        return payload
    except (jwt.PyJWTError, Exception):
        return None
