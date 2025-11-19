# services/scheduler_daemon.py
"""
Scheduler Daemon

- Polls schedules from DB (schedules table)
- Decides which schedules should run at current time
- Spawns job execution tasks (subprocess) in a ThreadPoolExecutor
- Logs each run in the Runs table (insert + updates)
- Supports retries, concurrency limits, graceful shutdown
- Configurable via services/config.yaml
"""

import os
import sys
import time
import yaml
import signal
import logging
import calendar
import traceback
from datetime import datetime, timezone, date
from concurrent.futures import ThreadPoolExecutor, as_completed
from logging.handlers import RotatingFileHandler
from typing import List, Dict, Any, Optional

import subprocess
from utils.db_utils import DbOps
from utils.db_models import Job, Schedule, Run, get_session

# ---------------------------
# Utility / Config
# ---------------------------
DEFAULT_CONFIG_PATH = os.path.join("services", "config.yaml")


def load_config(path: str = DEFAULT_CONFIG_PATH) -> Dict[str, Any]:
    if not os.path.exists(path):
        raise FileNotFoundError(f"Config not found: {path}")
    with open(path, "r") as f:
        cfg = yaml.safe_load(f)
    return cfg


def setup_logging(log_file: str, log_level: str = "INFO"):
    os.makedirs(os.path.dirname(log_file), exist_ok=True)
    logger = logging.getLogger("scheduler_daemon")
    logger.setLevel(getattr(logging, log_level.upper(), logging.INFO))
    handler = RotatingFileHandler(log_file, maxBytes=5_000_000, backupCount=3, encoding="utf-8")
    fmt = logging.Formatter("%(asctime)s - %(levelname)s - %(threadName)s - %(message)s")
    handler.setFormatter(fmt)
    logger.addHandler(handler)

    # Also stream to stdout for interactive runs
    stream_h = logging.StreamHandler(sys.stdout)
    stream_h.setFormatter(fmt)
    logger.addHandler(stream_h)
    return logger


# ---------------------------
# Schedule interpretation helpers
# ---------------------------
def nth_business_day(year: int, month: int, n: int) -> Optional[date]:
    """
    Return the date of nth business day in the given month (Mon-Fri),
    or None if n is out of range.
    """
    if n < 1:
        return None
    cal = calendar.Calendar()
    business_days = [d for d in cal.itermonthdates(year, month)
                     if d.month == month and d.weekday() < 5]  # Mon-Fri -> weekday() 0..4
    if n <= len(business_days):
        return business_days[n - 1]
    return None


def last_day_of_month(year: int, month: int) -> date:
    last_day = calendar.monthrange(year, month)[1]
    return date(year, month, last_day)


def should_run_schedule(schedule_row: Dict[str, Any], now: datetime, logger, interval=60) -> bool:
    """
    Decide whether a schedule (DB row) should run at the 'now' timestamp.
    schedule_row fields: schedule_type, run_option, hour, minute
    """
    stype = schedule_row.get("schedule_type")
    option = schedule_row.get("run_option")
    hour = int(schedule_row.get("hour", 0))
    minute = int(schedule_row.get("minute", 0))
    last_run = schedule_row.get("last_run_at", None)

    # Time must match hour and minute
    if now.hour != hour or now.minute != minute:
        return False

    # The last run check: prevent multiple runs within 'interval' seconds
    if last_run:
        delta = now - last_run.replace(tzinfo=now.tzinfo)
        logger.info(f"Schedule ID {schedule_row.get('id')} last run at {last_run}, delta seconds: {delta.total_seconds()}")
        # prevent multiple runs within same minute
        if delta.total_seconds() <= interval:
            return False

    if stype == "Daily":
        if option == "All Days":
            return True
        if option == "Weekdays Only":
            return now.weekday() < 5  # Mon-Fri
        return False

    if stype == "Weekly":
        # option like "Monday", "Tuesday", ...
        weekday_map = {
            "Sunday": 6,  # we will map Sunday to 6 for isoweekday mismatch; alternative mapping below
        }
        # Python weekday(): Monday==0 ... Sunday==6
        try:
            day_index = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"].index(option)
        except ValueError:
            return False
        return now.weekday() == day_index

    if stype == "Monthly":
        # option: "Month-start", "Month-end", or "BD1".."BD20"
        if option == "Month-start":
            return now.day == 1
        if option == "Month-end":
            last_d = last_day_of_month(now.year, now.month)
            return now.day == last_d.day
        if option.startswith("BD"):
            try:
                n = int(option.replace("BD", ""))
            except ValueError:
                return False
            bd_date = nth_business_day(now.year, now.month, n)
            return bd_date is not None and (bd_date.day == now.day and bd_date.month == now.month and bd_date.year == now.year)
        return False

    return False


# ---------------------------
# DB helpers (using DbOps)
# ---------------------------
class DB:
    def __init__(self, db_path: str):
        self.dbops = DbOps()
        self.dbops.db_path = db_path

    def get_active_schedules(self) -> List[Dict[str, Any]]:
        """
        Returns list of schedule dicts with necessary fields.
        """
        cols = ["id", "schedule_name", "job_id", "schedule_type", "run_option", "hour", "minute", "last_run_at"]
        df = self.dbops.select_records(Schedule, filters={'schedule_type': '~Inactive'}, columns=cols)
        # convert DataFrame to list of dicts
        return df.to_dict(orient="records") if not df.empty else []

    def get_job(self, job_id: int) -> Optional[Dict[str, Any]]:
        df = self.dbops.select_records(Job, filters={"id": job_id}, columns=["id", "name", "script_path", "script_type", "args"])
        if df.empty:
            return None
        return df.iloc[0].to_dict()

    def insert_run(self, run_payload: Dict[str, Any]) -> int:
        """Insert into Run table, return inserted rows count (should be 1)."""
        return self.dbops.insert_record(Run, run_payload)

    def update_run(self, filters: Dict[str, Any], updates: Dict[str, Any]) -> int:
        return self.dbops.update_records(Run, filters=filters, updates=updates)

    def update_schedule_last_run(self, schedule_id: int, run_time: datetime) -> int:
        return self.dbops.update_records(Schedule, filters={"id": schedule_id}, updates={"last_run_at": run_time})


# ---------------------------
# Execution helpers
# ---------------------------
def build_command_for_job(job: Dict[str, Any], args_str: Optional[str]) -> List[str]:
    """
    Construct command list to be passed to subprocess.
    job: dict with script_path and script_type
    args_str: string of arguments (already placeholder-resolved)
    """
    script = job["script_path"]
    if job["script_type"].lower() == "py":
        cmd = ["python", script]
    else:
        cmd = [script]
    if args_str:
        # split on whitespace (caller should have built proper quoting if needed)
        cmd.extend(args_str.split())
    return cmd


def resolve_placeholders_in_args(args_value):
    """
    args_value could be:
      - JSON string (e.g. '{"--date":"##Previous Month##", ...}')
      - Python dict
      - Plain string
    This returns a single args string with placeholders replaced.
    """
    import json as _json
    from utils.job_helper import resolve_date_placeholders

    if args_value is None:
        return ""
    if isinstance(args_value, dict):
        parts = []
        for k, v in args_value.items():
            v_resolved = resolve_date_placeholders(str(v))
            parts.append(f"{k} {v_resolved}")
        return " ".join(parts)
    if isinstance(args_value, str):
        # If it looks like JSON, try to parse
        try:
            parsed = _json.loads(args_value)
            if isinstance(parsed, dict):
                return resolve_placeholders_in_args(parsed)
        except Exception:
            # treat as raw string
            return resolve_date_placeholders(args_value)
    # fallback
    return str(args_value)


def run_job_process(db: DB, job: Dict[str, Any], schedule_row: Dict[str, Any], attempts: int = 0, max_attempts: int = 1, backoff: int = 60, logger: logging.Logger = None, _timezone=timezone.utc) -> Dict[str, Any]:
    """
    Execute the job (subprocess), create Run record, update status, support retries.
    This function runs in a worker thread.
    """
    logger = logger or logging.getLogger("scheduler_daemon")
    schedule_id = schedule_row.get("id", None)
    schedule_name = schedule_row.get("schedule_name", "manual_run")

    # --- Prepare log directory ---
    log_dir = os.path.join("logs", "run_logs")
    os.makedirs(log_dir, exist_ok=True)

    # --- Log file name ---
    ts = datetime.now(_timezone).strftime("%Y%m%d_%H%M%S")
    safe_name = schedule_name.replace(" ", "_").replace("/", "_")
    log_file = os.path.join(log_dir, f"{safe_name}_{ts}.log")

    job_id = job["id"]
    run_payload = {
        "job_id": job_id,
        "schedule_id": schedule_id,
        "run_type": "Scheduled" if schedule_id else "Manual",
        "status": "Running",
        "start_time": datetime.now(_timezone),
        "created_at": datetime.now(_timezone),
        "created_by": "scheduler_daemon",
        "log_path": log_file,
    }

    # Insert run entry (note: DbOps.insert_record returns count of inserted rows)
    try:
        inserted = db.insert_run(run_payload)
        # We don't have inserted row id from insert_record; to get id we must query latest run for job and start_time
        session = get_session(db.dbops.db_path)
        try:
            latest = session.query(Run).filter(Run.job_id == job_id).order_by(Run.start_time.desc()).first()
            run_id = latest.id if latest else None
        finally:
            session.close()
    except Exception as e:
        logger.exception("Failed to insert run record: %s", e)
        return {"status": "error", "message": str(e)}

    cmd_args = resolve_placeholders_in_args(job.get("args"))
    cmd = build_command_for_job(job, cmd_args)

    # Run in subprocess
    stdout_text = ""
    stderr_text = ""
    exit_code = None

    # Change working directory to parent dir of script
    workdir = os.path.dirname(job["script_path"]) or "."
    try:
        logger.info(f"Starting job_id={job_id} schedule_id={schedule_id} cmd={' '.join(cmd)} cwd={workdir}")
        proc = subprocess.run(cmd, capture_output=True, text=True, cwd=workdir, timeout=None)
        stdout_text = proc.stdout or ""
        stderr_text = proc.stderr or ""
        exit_code = proc.returncode

        status = "Success" if exit_code == 0 else "Failed"
        # --- Write everything to log file ---
        with open(log_file, "w", encoding="utf-8") as f:
            f.write("=== COMMAND ===\n")
            f.write(" ".join(cmd) + "\n\n")
            f.write("=== START TIME ===\n")
            f.write(str(run_payload["start_time"]) + "\n\n")
            f.write("=== STDOUT ===\n")
            f.write(stdout_text + "\n\n")
            f.write("=== STDERR ===\n")
            f.write(stderr_text + "\n\n")
            f.write("=== EXIT CODE ===\n")
            f.write(str(exit_code) + "\n")

        updates = {
            "status": status,
            "end_time": datetime.now(_timezone),
            "exit_code": exit_code,
            "error_message": (stderr_text[:2000] if stderr_text else None),
            "log_path": log_file,
            # "modified_by": "scheduler_daemon",
            # "modified_at": datetime.now(_timezone),
        }
        db.update_run(filters={"id": run_id}, updates=updates)
        db.update_schedule_last_run(schedule_id, datetime.now(_timezone))
        logger.info(f"Finished job_id={job_id} run_id={run_id} status={status} exit={exit_code}")

        if status == "Failed" and attempts + 1 < max_attempts:
            # schedule retry with backoff (synchronous here; the caller could implement async scheduling)
            logger.warning(f"Job failed, will retry (attempt {attempts + 1}/{max_attempts}) after {backoff} seconds")
            time.sleep(backoff)
            return run_job_process(db, job, schedule_row, attempts=attempts + 1, max_attempts=max_attempts, backoff=backoff * 2, logger=logger, _timezone=_timezone)

        return {"status": status, "exit_code": exit_code, "stdout": stdout_text, "stderr": stderr_text, "log_file": log_file}

    except Exception as e:
        logger.exception("Exception while running job_id=%s: %s", job_id, e)
        updates = {
            "status": "Failed",
            "end_time": datetime.now(_timezone),
            "exit_code": -1,
            "error_message": str(e)[:2000],
            "log_path": log_file,
            # "modified_by": "scheduler_daemon",
            # "modified_at": datetime.now(_timezone),
        }
        try:
            db.update_run(filters={"id": run_id}, updates=updates)
            db.update_schedule_last_run(schedule_id, datetime.now(_timezone))
        except Exception:
            logger.exception("Failed to update run record after crash.")

                # Write crash to log too
        try:
            with open(log_file, "a", encoding="utf-8") as f:
                f.write("\n=== CRASH ===\n")
                f.write(str(e) + "\n")
        except:
            pass
        
        return {"status": "error", "message": str(e)}


# ---------------------------
# Daemon main loop
# ---------------------------
class SchedulerDaemon:
    def __init__(self, config_path: str = DEFAULT_CONFIG_PATH):
        self.cfg = load_config(config_path)
        self.logger = setup_logging(self.cfg.get("log_file", "logs/scheduler.log"), self.cfg.get("log_level", "INFO"))
        self.db = DB(self.cfg.get("db_path", "sqlite:///data/scheduler.db"))
        self.poll_interval = int(self.cfg.get("poll_interval_seconds", 30))
        self.max_workers = int(self.cfg.get("max_workers", 4))
        self.retry_attempts = int(self.cfg.get("retry_attempts", 2))
        self.retry_backoff_seconds = int(self.cfg.get("retry_backoff_seconds", 60))
        self.timezone = eval(self.cfg.get("timezone", "timezone.utc"))
        self.executor = ThreadPoolExecutor(max_workers=self.max_workers)
        self._stop = False

    def start(self):
        self.logger.info("SchedulerDaemon starting up.")
        # register signals for graceful shutdown
        signal.signal(signal.SIGINT, self._handle_signal)
        signal.signal(signal.SIGTERM, self._handle_signal)

        try:
            while not self._stop:
                now = datetime.now(self.timezone)
                try:
                    schedules = self.db.get_active_schedules()
                    if schedules:
                        # find schedules that should run in this minute
                        to_run = [s for s in schedules if should_run_schedule(s, now, self.logger)]
                        if to_run:
                            self.logger.info(f"Found {len(to_run)} schedule(s) to run at {now}.")
                        futures = []
                        for schedule_row in to_run:
                            # resolve job
                            job = self.db.get_job(schedule_row["job_id"])
                            if not job:
                                self.logger.error(f"Job ID {schedule_row['job_id']} not found for schedule {schedule_row['id']}")
                                continue
                            # submit task
                            fut = self.executor.submit(
                                run_job_process,
                                self.db,
                                job,
                                schedule_row,
                                0,
                                self.retry_attempts,
                                self.retry_backoff_seconds,
                                self.logger,
                                self.timezone
                            )
                            futures.append(fut)

                        # Optionally wait for futures to complete or let them run
                        # Here we do not block the polling loop for all jobs; they run in threads
                    else:
                        self.logger.debug("No schedules found in DB.")
                except Exception as e:
                    self.logger.exception("Error while scanning schedules: %s", e)

                time.sleep(self.poll_interval)
        finally:
            self.shutdown()

    def _handle_signal(self, signum, frame):
        self.logger.info("Received signal %s. Shutting down...", signum)
        self._stop = True

    def shutdown(self):
        self.logger.info("Shutting down SchedulerDaemon: waiting for running jobs to complete.")
        self.executor.shutdown(wait=True)
        self.logger.info("Executor shut down. Exiting.")


# ---------------------------
# CLI entrypoint
# ---------------------------
def main():
    cfg_path = DEFAULT_CONFIG_PATH
    if len(sys.argv) > 1:
        cfg_path = sys.argv[1]
    daemon = SchedulerDaemon(cfg_path)
    daemon.start()


if __name__ == "__main__":
    main()
