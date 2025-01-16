import pytest
from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import sessionmaker
from user_database import Base
from sql_schemas import User


# Configure a SQLite in-memory database for testing
@pytest.fixture(scope="module")
def test_db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)  # Create the tables in the test database
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = TestingSessionLocal()
    yield session  # Provide the session to tests
    session.close()  # Cleanup after tests


def test_user_table_creation(test_db):
    # Ensure the table is created
    inspector = inspect(test_db.get_bind())
    assert "users" in inspector.get_table_names(), "The 'users' table was not created."


def test_user_insertion(test_db):
    # Insert a test user
    new_user = User(
        username="testuser",
        email="testuser@example.com",
        full_name="Test User",
        hashed_password="hashedpassword",
        disabled=False,
    )
    test_db.add(new_user)
    test_db.commit()

    # Verify the user exists in the database
    user = test_db.query(User).filter(User.username == "testuser").first()
    assert user is not None, "User not found in the database"
    assert user.username == "testuser"
    assert user.email == "testuser@example.com"


def test_user_retrieval(test_db):
    # Retrieve a user and verify fields
    user = test_db.query(User).filter(User.username == "testuser").first()
    assert user is not None, "User retrieval failed"
    assert user.full_name == "Test User"
    assert not user.disabled, "User should not be disabled by default"


def test_unique_constraints(test_db):
    # Try inserting a user with a duplicate username or email
    new_user1 = User(
        username="duplicateuser",
        email="uniqueemail@example.com",
        full_name="Duplicate User",
        hashed_password="hashedpassword",
        disabled=False,
    )
    new_user2 = User(
        username="duplicateuser",  # Duplicate username
        email="duplicateemail@example.com",  # New email
        full_name="Another User",
        hashed_password="hashedpassword",
        disabled=False,
    )

    test_db.add(new_user1)
    test_db.commit()

    with pytest.raises(Exception):
        test_db.add(new_user2)
        test_db.commit()
