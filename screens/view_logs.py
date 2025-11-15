import streamlit as st
import pandas as pd
from datetime import date
from utils.db_utils import DbOps
from utils.db_models import Run, Schedule


# ------------------------------------------
# Helper load functions
# ------------------------------------------
@st.cache_data
def load_runs():
    db = DbOps()
    df = db.select_records(Run)
    if df.empty:
        return df

    df["start_time"] = pd.to_datetime(df["start_time"])
    df["end_time"] = pd.to_datetime(df["end_time"])
    return df


@st.cache_data
def load_schedules():
    db = DbOps()
    df = db.select_records(Schedule)
    if df.empty:
        return df
    return df[["id", "schedule_name"]]


# ------------------------------------------
# Main Render Function
# ------------------------------------------
def render():
    st.set_page_config(
        page_title="JobGoblin - ViewLogs",
        page_icon="🧙‍♂️",
        layout="wide"
    )

    st.title("📜 JobGoblin — Scheduler Run Logs")

    # ------------------ Load Data ------------------
    runs_df = load_runs()
    schedule_df = load_schedules()

    if runs_df.empty:
        st.warning("No logs found in the system yet.")
        return

    # ------------------ Join Schedule Names ------------------
    runs_df = runs_df.merge(schedule_df, left_on="schedule_id", right_on="id", how="left")
    runs_df.rename(columns={"name": "schedule_name"}, inplace=True)
    runs_df.drop(columns=["id_y"], errors="ignore", inplace=True)
    runs_df.rename(columns={"id_x": "run_id"}, inplace=True)

    # ------------------ Sidebar Filters ------------------
    st.sidebar.header("🔍 Filter Logs")

    schedule_filter = st.sidebar.multiselect(
        "Schedule Name",
        options=sorted(runs_df["schedule_name"].dropna().unique().tolist()),
        default=sorted(runs_df["schedule_name"].dropna().unique().tolist()),
    )

    run_type_filter = st.sidebar.multiselect(
        "Run Type",
        options=sorted(runs_df["run_type"].unique().tolist()),
        default=sorted(runs_df["run_type"].unique().tolist()),
    )

    status_filter = st.sidebar.multiselect(
        "Status",
        options=sorted(runs_df["status"].unique().tolist()),
        default=sorted(runs_df["status"].unique().tolist()),
    )

    start_date = st.sidebar.date_input(
        "Start Date",
        value=runs_df["start_time"].min().date() if not runs_df.empty else date.today(),
    )

    end_date = st.sidebar.date_input(
        "End Date",
        value=runs_df["end_time"].max().date() if not runs_df.empty else date.today(),
    )

    # ------------------ Apply Filters ------------------
    filtered_df = runs_df[
        (runs_df["schedule_name"].isin(schedule_filter)) &
        (runs_df["run_type"].isin(run_type_filter)) &
        (runs_df["status"].isin(status_filter)) &
        (runs_df["start_time"].dt.date >= start_date) &
        (runs_df["end_time"].dt.date <= end_date)
    ]

    # ------------------ Add Log File Hyperlinks ------------------
    # def make_log_link(path):
    #     print(path)
    #     if not path or pd.isna(path):
    #         return ""
    #     # Allow clicking inside Streamlit
    #     # return f"<a href='{path}' target='_blank'>Open Log</a>"
    #     return f"[Open Log]({path})"

    # filtered_df["log_file"] = filtered_df["log_path"].apply(make_log_link)

    # Final columns to display
    display_df = filtered_df[[
        "run_id",
        "schedule_name",
        "run_type",
        "status",
        "start_time",
        "end_time",
        "log_path",
    ]]

    # ------------------ Display Table with Download Buttons ------------------
    st.markdown("### 📄 Run History")

    # Prepare rows for UI
    ui_rows = []
    for _, row in filtered_df.iterrows():
        log_path = row["log_path"]

        if log_path and isinstance(log_path, str):
            try:
                with open(log_path, "r", encoding="utf-8") as f:
                    log_data = f.read()
            except Exception:
                log_data = "Error reading log file."

            download_widget = st.download_button(
                label="📥 Download",
                data=log_data,
                file_name=log_path.split("/")[-1],
                mime="text/plain",
                key=f"download_{row['run_id']}"
            )
        else:
            download_widget = "—"

        ui_rows.append({
            "Run ID": row["run_id"],
            "Schedule Name": row["schedule_name"],
            "Run Type": row["run_type"],
            "Status": row["status"],
            "Start Time": row["start_time"],
            "End Time": row["end_time"],
            "Download Log": download_widget
        })

    # Show as non-editable grid
    st.data_editor(
        ui_rows,
        use_container_width=True,
        hide_index=True,
        disabled=True,
    )

