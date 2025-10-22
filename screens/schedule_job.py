import streamlit as st
import pandas as pd
from utils.db_models import Job, Schedule
from utils.db_utils import DbOps
from utils.job_helper import resolve_date_placeholders, save_schedule

db_ops = DbOps()


def safe_index(options, val, default=0):
    """Return index of val in options if present, else default (0)."""
    try:
        if val is None:
            return default
        return options.index(val)
    except ValueError:
        return default


def render():
    st.title("🕒 Job Schedules")
    st.caption("View, add, or edit job schedules from a single page.")

    # --- Session defaults ---
    st.session_state.setdefault("show_modal", False)
    st.session_state.setdefault("edit_mode", False)
    st.session_state.setdefault("selected_schedule", None)

    # --- Fetch schedules from DB ---
    try:
        schedule_df = db_ops.select_records(Schedule, None, [
            "id", "schedule_name", "job_id", "schedule_type",
            "run_option", "hour", "minute"
        ])
    except Exception as e:
        st.error(f"Error loading schedules: {e}")
        schedule_df = pd.DataFrame()

    # --- Map job_id → job_name for display ---
    job_df = db_ops.select_records(Job, None, ["id", "name"])
    job_map = {row["id"]: row["name"] for _, row in job_df.iterrows()}

    if not schedule_df.empty:
        schedule_df["job_name"] = schedule_df["job_id"].map(job_map)
        schedule_df["time"] = schedule_df["hour"].astype(str).str.zfill(2) + ":" + schedule_df["minute"].astype(str).str.zfill(2)
    else:
        st.info("No schedules found. Add a new one below.")
        schedule_df = pd.DataFrame(columns=["id", "schedule_name", "job_name", "schedule_type", "run_option", "time"])

    # --- Header row ---
    st.markdown("#### 📋 Scheduled Jobs")
    header_cols = st.columns([1, 2, 2, 2, 2, 1])
    header_cols[0].write("**ID**")
    header_cols[1].write("**Schedule Name**")
    header_cols[2].write("**Job Name**")
    header_cols[3].write("**Type**")
    header_cols[4].write("**Run Option**")
    header_cols[5].write("**Action**")

    # --- Data rows ---
    for _, row in schedule_df.iterrows():
        cols = st.columns([1, 2, 2, 2, 2, 1])
        cols[0].write(row["id"])
        cols[1].write(row["schedule_name"])
        cols[2].write(row["job_name"])
        cols[3].write(row["schedule_type"])
        cols[4].write(row["run_option"])

        if cols[5].button("✏️", key=f"edit_{row['id']}"):
            st.session_state.show_modal = True
            st.session_state.edit_mode = True
            st.session_state.selected_schedule = row.to_dict()
            st.rerun()
        if cols[5].button("🗑️", key=f"delete_{row['id']}"):
            deleted = db_ops.delete_records(model_class=Schedule, filters={"id": row["id"]})
            if deleted > 0:
                st.toast(f"🗑️ Schedule '{row['schedule_name']}' deleted.", icon="⚡")
                st.rerun()
            else:
                st.error(f"Failed to delete schedule ID {row['id']}.")


    # --- Add Schedule Button ---
    st.divider()
    if st.button("➕ Add Schedule"):
        st.session_state.show_modal = True
        st.session_state.edit_mode = False
        st.session_state.selected_schedule = None
        st.rerun()

    # --- Modal form ---
    if st.session_state.show_modal:
        st.markdown("---")
        st.markdown("### 🗓️ Job Schedule Form")

        selected = st.session_state.selected_schedule or {}

        schedule_name = st.text_input(
            "Schedule Name",
            value=selected.get("schedule_name", "")
        )

        # --- Job dropdown ---
        job_df = db_ops.select_records(Job, None, ["id", "name", "script_path", "args"])
        job_map_name_to_id = {row["name"]: row["id"] for _, row in job_df.iterrows()}
        job_list = list(job_map_name_to_id.keys())
        default_index = (
            job_list.index(selected["job_name"])
            if st.session_state.edit_mode and selected.get("job_name") in job_list
            else 0
        )

        job_name = st.selectbox("Select Job", job_list, index=default_index)

        if job_df.empty:
            st.warning("⚠️ No jobs found in the system. Please add a job first.")
            st.stop()  # prevent form from continuing
        else:
            filtered_job = job_df[job_df["name"] == job_name]
            if filtered_job.empty:
                st.error("Selected job not found. Please refresh and try again.")
                st.stop()
            else:
                selected_job = filtered_job.iloc[0]
                job_command = (
                    f"python {selected_job['script_path']} {resolve_date_placeholders(selected_job['args'])}"
                    if selected_job["script_path"].endswith(".py")
                    else selected_job["script_path"]
                )
                st.code(job_command, language="bash")
                st.info("The script will run from the parent directory of the script file.")


        # --- Schedule type and options ---
        schedule_type = st.selectbox(
            "Schedule Type",
            ["Monthly", "Weekly", "Daily"],
            index=["Monthly", "Weekly", "Daily"].index(selected.get("schedule_type", "Monthly"))
        )

        prev_option = selected.get("run_option") if selected else None

        if schedule_type == "Monthly":
            monthly_options = ["Month-end", "Month-start"] + [f"BD{i}" for i in range(1, 21)]
            run_option = st.selectbox("Run Option", monthly_options,
                                      index=safe_index(monthly_options, prev_option, default=0))
        elif schedule_type == "Weekly":
            weekly_options = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"]
            run_option = st.selectbox("Run Option", weekly_options,
                                      index=safe_index(weekly_options, prev_option, default=0))
        else:  # Daily
            daily_options = ["Weekdays Only", "All Days"]
            run_option = st.selectbox("Run Option", daily_options,
                                      index=safe_index(daily_options, prev_option, default=0))

        # --- Time selection ---
        col1, col2 = st.columns(2)
        hour = col1.selectbox("Hour (00-23)", [f"{i:02d}" for i in range(24)],
                              index=[f"{i:02d}" for i in range(24)].index(selected.get("time", "00:00").split(":")[0]))
        minute = col2.selectbox("Minute (00,15,30,45)", ["00", "15", "30", "45"],
                                index=["00", "15", "30", "45"].index(selected.get("time", "00:00").split(":")[1]))
        run_time = f"{hour}:{minute}"

        # --- Buttons ---
        c1, c2 = st.columns(2)
        
        if c1.button("💾 Save Schedule"):
            schedule_id = selected.get("id") if st.session_state.edit_mode else None
            resp = save_schedule(
                schedule_id=schedule_id,
                schedule_name=schedule_name,
                job_id=job_map_name_to_id[job_name],
                schedule_type=schedule_type,
                run_option=run_option,
                run_time=run_time,
            )

            if resp["status"] == "success":
                st.toast(resp["message"], icon="✅")
            else:
                st.toast(resp["message"], icon="⚠️")

            st.session_state.show_modal = False
            st.rerun()


        if c2.button("❌ Cancel"):
            st.session_state.show_modal = False
            st.rerun()
