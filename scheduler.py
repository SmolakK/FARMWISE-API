from apscheduler.schedulers.background import BackgroundScheduler
from api_utils import cleanup_old_files

scheduler = BackgroundScheduler()


def start_scheduler(temp_dir):
    scheduler.add_job(cleanup_old_files, 'interval', minutes=360, args=[temp_dir, 3600])
    scheduler.start()


def shutdown_scheduler():
    scheduler.shutdown()
