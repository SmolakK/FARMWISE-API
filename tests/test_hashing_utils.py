import pytest
from hashing_utils import get_password_hash, verify_password  # Adjust import paths based on your project structure

@pytest.fixture
def password():
    return "testpassword123"

def test_get_password_hash(password):
    hashed_password = get_password_hash(password)
    assert hashed_password != password  # Hash should not be the same as the plaintext password
    assert hashed_password.startswith("$2b$")  # bcrypt hash prefix

def test_verify_password(password):
    hashed_password = get_password_hash(password)
    assert verify_password(password, hashed_password)  # Should return True for correct password
    assert not verify_password("wrongpassword", hashed_password)  # Should return False for incorrect password
