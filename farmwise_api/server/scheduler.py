from apscheduler.schedulers.background import BackgroundScheduler
from farmwise_api.server.api_utils import cleanup_old_files
from farmwise_api.server.jobs import registry

scheduler = BackgroundScheduler()


def start_scheduler(temp_dir) -> None:
    scheduler.add_job(cleanup_old_files, 'interval', minutes=60, args=[temp_dir, 3600])
    # Asynchronous job records outlive their files by a couple of hours, then go.
    scheduler.add_job(registry.purge_expired, 'interval', minutes=30)
    scheduler.start()


def shutdown_scheduler() -> None:
    scheduler.shutdown()
