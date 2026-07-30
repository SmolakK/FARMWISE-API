import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from server.sql_schemas import Base
from server.schemas import UserCreate
from server.crud import (
    create_user,
    delete_user,
    get_user_by_email,
    get_user_by_username,
)
from server.hashing_utils import verify_password


# Setup test database
@pytest.fixture(scope="module")
def test_db():
    engine = create_engine("sqlite:///:memory:")
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


def test_create_user(test_db):
    user_data = UserCreate(
        username="testuser",
        email="testuser@example.com",
        full_name="Test User",
        password="password123",
    )
    user = create_user(test_db, user_data)
    assert user.username == "testuser"
    assert user.email == "testuser@example.com"
    assert user.full_name == "Test User"
    assert user.hashed_password != "password123"  # Ensure password is hashed
    assert verify_password("password123", user.hashed_password)


def test_get_user_by_username(test_db):
    user = get_user_by_username(test_db, "testuser")
    assert user is not None
    assert user.username == "testuser"


def test_get_user_by_email(test_db):
    user = get_user_by_email(test_db, "testuser@example.com")
    assert user is not None
    assert user.email == "testuser@example.com"


def test_delete_user(test_db):
    assert delete_user(test_db, "testuser") is True
    assert get_user_by_username(test_db, "testuser") is None
    assert delete_user(test_db, "testuser") is False
