from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordRequestForm
from farmwise_api.server.security import authenticate_user, create_access_token, get_current_active_user, limiter, ACCESS_TOKEN_EXPIRE_MINUTES
from farmwise_api.server.schemas import Token, User
from datetime import timedelta
from farmwise_api.server.user_database import get_db
from sqlalchemy.orm import Session

auth_router = APIRouter()


@auth_router.post("/token", response_model=Token)
# Password guessing was unthrottled while the service is reachable from the
# public internet, where it is already enumerated by scanners. Ten attempts a
# minute leaves room for a mistyped password and none for a dictionary.
@limiter.limit("10/minute")
async def login_for_access_token(request: Request, form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)) -> dict[str, str]:
    """
    Authenticates a user and generates an access token.

    :param request: the HTTP request, required by the rate limiter.

    This endpoint receives user credentials (username and password),
    authenticates the user, and returns a JWT access token if the credentials are valid.

    :param form_data: An instance of OAuth2PasswordRequestForm containing the username and password.
    :param db: The database session dependency.
    :raises HTTPException: If authentication fails, raises a 401 Unauthorized error with a message.
    :return: A dictionary containing the access token and its type (Bearer).
    """
    user = authenticate_user(db, form_data.username, form_data.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": user.username}, expires_delta=access_token_expires
    )
    return {"access_token": access_token, "token_type": "bearer"}


@auth_router.get("/users/me", response_model=User)
async def read_users_me(current_user: User = Depends(get_current_active_user)) -> User:
    """
    Retrieves the current authenticated user's information.

    This endpoint returns the details of the currently logged-in user.

    :param current_user: The current authenticated user, retrieved through dependency injection.
    :return: The current user's details as a User object.
    """
    return current_user
