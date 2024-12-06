import os
import time


def cleanup_old_files(folder_path, max_age_in_seconds):
    """
    Deletes files older than `max_age_in_seconds` in the specified `folder_path`.
    """
    for filename in os.listdir(folder_path):
        file_path = os.path.join(folder_path, filename)
        if os.path.isfile(file_path) and '.csv' in filename:
            file_age = time.time() - os.path.getmtime(file_path)
            if file_age > max_age_in_seconds:
                os.remove(file_path)
                print(f"Deleted {file_path}")


def secure_filename(filename):
    """
    Sanitize the filename to ensure it is safe for use in file paths.
    This function strips directory paths and removes non-alphanumeric characters.
    """
    # Remove any directory path information to isolate the filename
    filename = os.path.basename(filename)

    # Allow only valid filenames (alphanumeric, dashes, underscores)
    import re
    safe_pattern = re.compile(r'^[\w,\s-]+\.[A-Za-z]{1,4}$')
    if not safe_pattern.match(filename):
        raise ValueError("Invalid filename format")

    return filename
