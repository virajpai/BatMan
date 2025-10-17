from apscheduler.schedulers.background import BackgroundScheduler
from .db import SessionLocal
from .models import Job
from .job_runner import execute_job

scheduler = BackgroundScheduler()

def schedule_job(job_id, args=None, cron=None):
    session = SessionLocal()
    job = session.query(Job).get(job_id)
    session.close()
    if job:
        scheduler.add_job(execute_job, "interval", minutes=cron or 5,
                          args=[job, args or job.default_args, "scheduler"],
                          id=str(job_id), replace_existing=True)

def start_scheduler():
    if not scheduler.running:
        scheduler.start()
