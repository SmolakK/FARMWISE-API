from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.middleware import SlowAPIMiddleware
import jwt
from datetime import datetime, timedelta, timezone
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from farmwise_api.server.schemas import TokenData, User
from farmwise_api.server.user_database import get_db
from farmwise_api.server.crud import get_user_by_username
from dotenv import load_dotenv
import os
from typing import Literal
from sqlalchemy.orm import Session
from farmwise_api.server.hashing_utils import verify_password
from farmwise_api.core.utils.paths import PROJECT_ROOT

# Create Limiter instance
limiter = Limiter(key_func=get_remote_address)


def setup_security(app) -> None:
    app.state.limiter = limiter
    app.add_exception_handler(429, _rate_limit_exceeded_handler)
    app.add_middleware(SlowAPIMiddleware)


# Constants
load_dotenv(PROJECT_ROOT / "fidel.env")
SECRET_KEY = os.getenv("SECRET_KEY")
ALGORITHM = os.getenv("ALGORITHM", "HS256").upper()
ACCESS_TOKEN_EXPIRE_MINUTES = 60

_ALLOWED_JWT_ALGORITHMS = {"HS256", "HS384", "HS512"}
if ALGORITHM not in _ALLOWED_JWT_ALGORITHMS:
    raise RuntimeError(
        f"Unsupported JWT algorithm {ALGORITHM!r}. FARMWISE accepts only "
        f"{', '.join(sorted(_ALLOWED_JWT_ALGORITHMS))}."
    )

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")


def _secret_key() -> str:
    """Return the configured JWT secret, or explain what is missing.

    SECRET_KEY is read at import so the library and the test suite can be
    imported without a server configuration; a request that actually needs
    to sign or verify a token fails here with an actionable message rather
    than deep inside PyJWT.
    """
    if not SECRET_KEY:
        raise RuntimeError(
            "SECRET_KEY is not configured. Set it as an environment "
            "variable, or provide it in the JWT settings file."
        )
    return SECRET_KEY


def authenticate_user(db: Session, username: str, password: str) -> User | Literal[False]:
    user = get_user_by_username(db, username)
    if not user:
        return False
    if not verify_password(password, user.hashed_password):
        return False
    return user


def create_access_token(
    data: dict, expires_delta: timedelta | None = None
) -> str:
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=15)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, _secret_key(), algorithm=ALGORITHM)
    return encoded_jwt


async def get_current_user(db: Session = Depends(get_db), token: str = Depends(oauth2_scheme)) -> User:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, _secret_key(), algorithms=[ALGORITHM])
        username = payload.get("sub")
        if username is None:
            raise credentials_exception
        # validates the claim; `username` is already known to be present
        TokenData(username=username)
    except jwt.PyJWTError:
        raise credentials_exception
    user = get_user_by_username(db, username=username)
    if user is None:
        raise credentials_exception
    return user


async def get_current_active_user(current_user: User = Depends(get_current_user)) -> User:
    if current_user.disabled:
        raise HTTPException(status_code=400, detail="Inactive user")
    return current_user
