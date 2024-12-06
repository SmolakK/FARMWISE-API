import pytest
from unittest.mock import MagicMock, patch
from scheduler import start_scheduler, shutdown_scheduler


@patch("scheduler.cleanup_old_files")
@patch("scheduler.scheduler")
def test_start_scheduler(mock_scheduler, mock_cleanup_old_files):
    # Mock the BackgroundScheduler instance
    mock_instance = MagicMock()
    mock_scheduler.return_value = mock_instance

    # Call the function under test
    temp_dir = "/mock/temp/dir"
    start_scheduler(temp_dir)

    # Assertions
    mock_scheduler.add_job.assert_called_once_with(
        mock_cleanup_old_files,  # The function to be scheduled
        'interval',  # Job type
        minutes=60,  # Interval
        args=[temp_dir, 3600]  # Arguments for the job
    )
    mock_scheduler.start.assert_called_once()  # Verify scheduler was started


@patch("scheduler.scheduler")
def test_shutdown_scheduler(mock_scheduler):
    # Mock the scheduler's shutdown method
    mock_scheduler.shutdown = MagicMock()

    # Call the function under test
    shutdown_scheduler()

    # Assert that shutdown was called once
    mock_scheduler.shutdown.assert_called_once()
