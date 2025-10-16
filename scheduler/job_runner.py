import subprocess, datetime
from .db import SessionLocal
from .models import Run

def execute_job(job, args, triggered_by="manual"):
    session = SessionLocal()
    run = Run(job_id=job.id, args=args, status="running",
              start_time=datetime.datetime.utcnow(), triggered_by=triggered_by)
    session.add(run)
    session.commit()

    try:
        cmd = ["python", job.script_path] if job.script_type == "python" else [job.script_path]
        if args:
            cmd += args.split()
        result = subprocess.run(cmd, capture_output=True, text=True)
        run.output_log = result.stdout + "\n" + result.stderr
        run.status = "success" if result.returncode == 0 else "failed"
    except Exception as e:
        run.status = "failed"
        run.output_log = str(e)
    finally:
        run.end_time = datetime.datetime.utcnow()
        session.commit()
        session.close()
