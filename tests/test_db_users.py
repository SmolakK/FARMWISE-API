import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sql_schemas import User
from user_database import Base
from db_users import add_user, delete_user  # Adjust import paths based on your project structure

# Set up an in-memory SQLite database for testing
TEST_DATABASE_URL = "sqlite:///:memory:"
engine = create_engine(TEST_DATABASE_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Create the database schema
Base.metadata.create_all(bind=engine)


@pytest.fixture
def db_session():
    """
    Fixture to provide a session for testing.
    """
    session = TestingSessionLocal()
    yield session
    session.close()


def test_add_user(db_session, monkeypatch):
    """
    Test adding a user to the database.
    """
    monkeypatch.setattr("db_users.SessionLocal", lambda: db_session)

    add_user("testuser", "test@example.com", "Test User", "password123")

    user = db_session.query(User).filter(User.username == "testuser").first()
    assert user is not None
    assert user.username == "testuser"
    assert user.email == "test@example.com"
    assert user.full_name == "Test User"
    assert user.disabled is False


def test_add_existing_user(db_session, monkeypatch):
    """
    Test adding a user with an existing username.
    """
    monkeypatch.setattr("db_users.SessionLocal", lambda: db_session)

    # Add the user once
    add_user("testuser", "test@example.com", "Test User", "password123")

    # Try to add the user again
    add_user("testuser", "test@example.com", "Test User", "password123")

    users = db_session.query(User).filter(User.username == "testuser").all()
    assert len(users) == 1  # Should still only have one user


def test_delete_user(db_session, monkeypatch):
    """
    Test deleting a user from the database.
    """
    monkeypatch.setattr("db_users.SessionLocal", lambda: db_session)

    # Add a user to delete
    add_user("testuser", "test@example.com", "Test User", "password123")

    # Delete the user
    delete_user("testuser")

    user = db_session.query(User).filter(User.username == "testuser").first()
    assert user is None


def test_delete_nonexistent_user(db_session, monkeypatch):
    """
    Test deleting a user that does not exist.
    """
    monkeypatch.setattr("db_users.SessionLocal", lambda: db_session)

    # Attempt to delete a non-existent user
    delete_user("nonexistentuser")

    # Ensure the database remains unaffected
    users = db_session.query(User).all()
    assert len(users) == 0
