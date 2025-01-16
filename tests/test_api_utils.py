import os
import time
import pytest
import tempfile
from unittest.mock import patch
from api_utils import cleanup_old_files, secure_filename


# Test for cleanup_old_files
@pytest.fixture
def temp_folder():
    # Create a temporary directory
    with tempfile.TemporaryDirectory() as temp_dir:
        yield temp_dir


def test_cleanup_old_files(temp_folder):
    # Create test files
    old_file = os.path.join(temp_folder, "old_file.csv")
    new_file = os.path.join(temp_folder, "new_file.csv")
    with open(old_file, "w"), open(new_file, "w"):
        pass
    # Set modification times
    os.utime(old_file, (time.time() - 10000, time.time() - 10000))
    os.utime(new_file, None)  # Keep current time

    # Run cleanup
    cleanup_old_files(temp_folder, max_age_in_seconds=5000)

    # Verify results
    assert not os.path.exists(old_file), "Old file was not deleted"
    assert os.path.exists(new_file), "New file was incorrectly deleted"


def test_cleanup_old_files_empty_folder(temp_folder):
    cleanup_old_files(temp_folder, max_age_in_seconds=5000)
    # Should not raise errors on empty directory


def test_cleanup_old_files_nonexistent_folder():
    with pytest.raises(FileNotFoundError):
        cleanup_old_files("nonexistent_folder", max_age_in_seconds=5000)


# Test for secure_filename
@pytest.mark.parametrize("filename,expected", [
    ("valid_file.csv", "valid_file.csv"),
    ("another_file.TXT", "another_file.TXT"),
    ("../etc/passwd", pytest.raises(ValueError)),
    ("file|name.csv", pytest.raises(ValueError)),
    ("filename", pytest.raises(ValueError)),
    ("My File.txt", "My File.txt"),
    ("ANOTHER_file.CSV", "ANOTHER_file.CSV"),
    ("", pytest.raises(ValueError)),
])
def test_secure_filename(filename, expected):
    if not isinstance(expected, str):
        with pytest.raises(ValueError, match="Invalid filename format"):
            secure_filename(filename)
    else:
        assert secure_filename(filename) == expected
