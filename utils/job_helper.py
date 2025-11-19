import streamlit as st
from datetime import datetime, timedelta
import calendar
import re
import os

from utils.db_utils import DbOps
from utils.db_models import Schedule, Run
import subprocess

def format_arg(key, value, arg_type=None):
    """Return formatted CLI argument string like -f data.csv or --file data.csv."""
    prefix = f"-{key}" if len(key) == 1 else f"--{key}"
    formatted = f"{prefix} ##{value}##" if arg_type and arg_type=='date' else f"{prefix} {value}"
    return formatted

def get_arg_value(arg_type):
    """Render and return value field and optional date format."""
    if arg_type == "str":
        return st.text_input("Value", placeholder="e.g., report.csv"), ""
    elif arg_type == "number":
        return st.number_input("Value", value=0), ""
    elif arg_type == "date":
        date_format = st.selectbox("Date Format", ["YYYYMMDD", "YYYYMM"])
        format_display = f"({date_format})"
        if date_format == "YYYYMM":
            option = st.selectbox("Date Option", ["Previous Month", "Current Month"])
        else:
            option = st.selectbox("Date Option", ["Previous Month End", "T - n"])
            if option == "T - n":
                n = st.number_input("n (days before today)", min_value=1, max_value=365, value=1)
                option = f"T - {n}"
        return option, format_display
    return None, ""

def resolve_date_placeholders(text: str) -> str:
    """
    Replaces all supported date placeholders inside a string with actual date values.

    Supported placeholders (case-sensitive):
    ----------------------------------------
    ##Previous Month##      → 'YYYYMM' (last month)
    ##Current Month##       → 'YYYYMM' (current month)
    ##Previous Month End##  → 'YYYYMMDD' (last day of previous month)
    ##T - N##               → 'YYYYMMDD' (today minus N days)

    Example:
    --------
    "--save --date ##Previous Month## --params file.json"
    → "--save --date 202509 --params file.json"
    """
    today = datetime.today()

    def replace_placeholder(match):
        placeholder = match.group(0)

        if placeholder == "##Previous Month##":
            year = today.year if today.month > 1 else today.year - 1
            month = today.month - 1 if today.month > 1 else 12
            return f"{year}{month:02d}"

        elif placeholder == "##Current Month##":
            return today.strftime("%Y%m")

        elif placeholder == "##Previous Month End##":
            year = today.year if today.month > 1 else today.year - 1
            month = today.month - 1 if today.month > 1 else 12
            last_day = calendar.monthrange(year, month)[1]
            return f"{year}{month:02d}{last_day:02d}"

        elif placeholder.startswith("##T -"):
            n_match = re.search(r"T\s*-\s*(\d+)", placeholder)
            if n_match:
                n = int(n_match.group(1))
                target_date = today - timedelta(days=n)
                return target_date.strftime("%Y%m%d")

        return placeholder  # Leave unmodified if pattern not recognized

    # Pattern to match all supported placeholders
    pattern = r"##(?:Previous Month End|Previous Month|Current Month|T\s*-\s*\d+)##"
    return re.sub(pattern, replace_placeholder, text)

# def run(script_path: str, command: str):
#     """
#     Run a job with the given job ID.
#     """
    
#     print(rf"Executing script at: {script_path} with command: {command}")
    
#     # Save current working directory
#     parent_dir = os.path.dirname(rf"{script_path}")
#     cwd = os.getcwd()
#     try:
#         # Change to the script's parent directory
#         print('Chaning working directory to:', parent_dir)
#         os.chdir(parent_dir)  # run from parent directory
#         st.write(f"Running job... --> {command}")
#         os.system(command)
#         print("Job execution completed.")
#     finally:
#         # Restore working directory
#         os.chdir(cwd)
        
#     return "success"

def run(script_path: str, command: str):
    """
    Run a job with the given job ID.
    Minimal changes:
    - capture stdout into log file
    - insert run entry into DB
    """

    print(rf"Executing script at: {script_path} with command: {command}")

    # ------------------------------
    # Setup log file
    # ------------------------------
    os.makedirs("logs/run_logs", exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    job_name = os.path.splitext(os.path.basename(script_path))[0]
    log_file = f"logs/run_logs/{job_name}_{timestamp}.log"

    # ------------------------------
    # Insert DB start record
    # ------------------------------
    dbo = DbOps()
    run_id = dbo.insert_record(
        "runs",
        {
            "schedule_name": job_name,
            "run_type": "manual",
            "status": "running",
            "start_time": datetime.now(),
            "end_time": None,
            "log_file": log_file
        }
    )

    # Save current working directory
    parent_dir = os.path.dirname(rf"{script_path}")
    cwd = os.getcwd()

    try:
        print('Chaning working directory to:', parent_dir)
        os.chdir(parent_dir)  # run from parent directory

        # ------------------------------
        # Run and stream logs
        # ------------------------------
        with open(log_file, "w") as logf:
            logf.write(f"=== Job Started at {timestamp} ===\n")
            logf.write(f"Command: {command}\n\n")

            process = subprocess.Popen(
                command,
                shell=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True
            )

            for line in process.stdout:
                logf.write(line)

            process.wait()

            if process.returncode == 0:
                status = "success"
                logf.write("\nJob completed successfully.\n")
            else:
                status = "failed"
                logf.write(f"\nJob failed with exit code {process.returncode}\n")

    except Exception as e:
        status = "failed"
        with open(log_file, "a") as logf:
            logf.write(f"\nERROR: {str(e)}\n")

    finally:
        # Restore working directory
        os.chdir(cwd)

        # ------------------------------
        # Update DB end record
        # ------------------------------
        dbo.update_records(
            "runs",
            run_id,
            {
                "status": status,
                "end_time": datetime.now()
            }
        )

    print("Job execution completed.")
    return "success"



def save_schedule(schedule_id: int | None, schedule_name: str, job_id: int, schedule_type: str, run_option: str, run_time: str, created_by: str = "system"):
    """
    Save or update a job schedule.
    If schedule_id is provided → update the record, else insert new.
    """
    db = DbOps()
    hour, minute = run_time.split(":")

    data = {
        "schedule_name": schedule_name,
        "job_id": job_id,
        "schedule_type": schedule_type,
        "run_option": run_option,
        "hour": hour,
        "minute": minute,
        "modified_at": datetime.utcnow(),
        "modified_by": created_by,
    }

    if schedule_id:
        updated = db.update_records(Schedule, filters={"id": schedule_id}, updates=data)
        if updated > 0:
            return {"status": "success", "message": f"✅ Schedule '{schedule_name}' updated successfully."}
        else:
            return {"status": "error", "message": "⚠️ Failed to update schedule."}
    else:
        data["created_at"] = datetime.utcnow()
        data["created_by"] = created_by
        inserted = db.insert_record(Schedule, data)
        if inserted > 0:
            return {"status": "success", "message": f"✅ Schedule '{schedule_name}' added successfully."}
        else:
            return {"status": "error", "message": "⚠️ Failed to add schedule."}
