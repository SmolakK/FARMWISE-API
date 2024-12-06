import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sql_schemas import Base, User
from schemas import UserCreate
from crud import get_user_by_username, get_user_by_email, create_user
from hashing_utils import verify_password


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
