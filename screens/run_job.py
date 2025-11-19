import streamlit as st
from utils.db_utils import DbOps
from utils.db_models import Job
from utils.job_helper import resolve_date_placeholders, run  # dummy run
from services.scheduler_demon import run_job_process, load_config, DB
from datetime import timezone
import os

# ---------------------------
# Utility / Config
# ---------------------------
DEFAULT_CONFIG_PATH = os.path.join("services", "config.yaml")
cfg = load_config(DEFAULT_CONFIG_PATH)
# print(cfg)
timezone = eval(cfg.get("timezone", "timezone.utc"))

db_ops = DbOps()
db = DB(cfg.get("db_path", "sqlite:///data/scheduler.db"))


def render():
    st.title("▶️ Run Job")
    st.caption("Select a job to view its command and run it with optional overridden arguments.")

    # --- Fetch Jobs ---
    jobs_df = db_ops.select_records(Job, filters=None, columns=["id", "name", "script_path", "script_type", "args"])
    if jobs_df.empty:
        st.info("No jobs found. Please add jobs first.")
        return

    # --- Job Selection ---
    job_options = {f"{row['id']} - {row['name']}": row["id"] for _, row in jobs_df.iterrows()}
    selected = st.selectbox("Select Job", options=list(job_options.keys()))

    job_id = job_options[selected]
    job_row = jobs_df[jobs_df["id"] == job_id].iloc[0]

    # --- Build Job Command ---
    cmd_args = job_row["args"]
    if cmd_args:
        cmd_args = resolve_date_placeholders(str(cmd_args))

    if job_row["script_type"].lower() == "py":
        cmd = f"python {job_row['script_path']} {cmd_args}"
    else:
        cmd = f"{job_row['script_path']} {cmd_args}"

    st.subheader("Job Command")
    st.code(cmd)

    st.info("ℹ️ The script will be run from the **parent directory of the script**.")

    # --- Override CMD ---
    override_script = st.checkbox("Override script")
    user_script = job_row["script_path"]
    if override_script:
        user_script = st.text_input("Script", value=cmd)
        cmd = f"{user_script}"

    # --- Run Button ---
    if st.button("🏃 Run Job"):
        try:
            # Call dummy run (to be implemented later)
            # job_status = run(job_row["script_path"], cmd)

            # Call actual run function from scheduler_demon
            job_result = run_job_process(db, job_row.to_dict(), {}, _timezone=timezone)
            job_status = job_result.get("status", "failed")

            # Toast notification
            st.session_state["toast_msg"] = f"✅ Job '{job_row['name']}' executed with status {job_status}."
            st.session_state["toast_icon"] = "▶️"
            st.rerun()

        except Exception as e:
            st.session_state["toast_msg"] = f"❌ Failed to run job: {e}"
            st.session_state["toast_icon"] = "⚡"
            st.rerun()

    # --- Show toast if message exists ---
    if "toast_msg" in st.session_state and st.session_state["toast_msg"]:
        st.toast(st.session_state["toast_msg"], icon=st.session_state.get("toast_icon", "✅"))
        st.session_state["toast_msg"] = ""  # Clear after showing
