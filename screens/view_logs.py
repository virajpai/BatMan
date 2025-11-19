import streamlit as st
import pandas as pd
import base64
from utils.db_utils import DbOps
from utils.db_models import Run, Job, Schedule
from st_aggrid import AgGrid, GridOptionsBuilder, GridUpdateMode
from datetime import datetime
import os


# --------------------------------------------------------
# Load and Join Data
# --------------------------------------------------------
@st.cache_data(ttl=300)
def load_run_data():
    dbo = DbOps()

    runs = dbo.select_records(
        Run,
        columns=[
            "id",
            "schedule_id",
            "job_id",
            "run_type",
            "status",
            "start_time",
            "end_time",
            "log_path"
        ]
    )
    if runs is None or runs.empty:
        return pd.DataFrame()

    runs.rename(columns={"id": "run_id"}, inplace=True)

    jobs = dbo.select_records(Job, columns=["id", "name"])
    jobs.rename(columns={"id": "job_id", "name": "job_name"}, inplace=True)

    schedules = dbo.select_records(Schedule, columns=["id", "schedule_name"])
    schedules.rename(columns={"id": "schedule_id"}, inplace=True)

    df = runs.merge(jobs, on="job_id", how="left")
    df = df.merge(schedules, on="schedule_id", how="left")

    df["start_time"] = pd.to_datetime(df["start_time"])
    df["end_time"] = pd.to_datetime(df["end_time"])

    return df


# --------------------------------------------------------
# Convert log file → base64
# --------------------------------------------------------
@st.cache_data(ttl=300)
def file_to_base64(path):
    try:
        with open(path, "rb") as f:
            return base64.b64encode(f.read()).decode()
    except:
        return None


# --------------------------------------------------------
# MAIN UI
# --------------------------------------------------------
def render():
    st.set_page_config(page_title="JobGoblin - ViewLogs", page_icon="🧙‍♂️", layout="wide")
    st.title("📜 JobGoblin — Scheduler Run Logs")

    df = load_run_data()

    if df.empty:
        st.info("No logs available yet.")
        return

    # --------------------------------------------------------
    # SEARCH BAR
    # --------------------------------------------------------
    search_query = st.text_input("🔍 Search logs", placeholder="Search by job, schedule, type, status...")

    if search_query:
        df = df[df.apply(lambda row: row.astype(str).str.contains(search_query, case=False).any(), axis=1)]

    # --------------------------------------------------------
    # Build the Download Link column
    # --------------------------------------------------------
    download_col = []
    for _, row in df.iterrows():
        log_path = row["log_path"]
        b64 = file_to_base64(log_path) if log_path else None

        if b64:
            filename = os.path.basename(log_path)
            html_btn = (
                f'<a href="data:file/plain;base64,{b64}" '
                f'download="{filename}" '
                f'style="padding:4px 8px; background:#265ad1; color:white; '
                f'border-radius:4px; text-decoration:none; font-size:12px;">'
                f'Download</a>'
            )
        else:
            html_btn = "<span style='color:#aaa;'>—</span>"

        download_col.append(html_btn)

    df["Download Log"] = download_col

    # --------------------------------------------------------
    # Display dataframe must include log_path for selection
    # --------------------------------------------------------
    df_display = df[
        [
            "run_id",
            "job_name",
            "schedule_name",
            "run_type",
            "status",
            "start_time",
            "end_time",
            "log_path",
            "Download Log"
        ]
    ].copy()

    # --------------------------------------------------------
    # AG-GRID with Pagination (compatible mode)
    # --------------------------------------------------------
    gb = GridOptionsBuilder.from_dataframe(df_display)
    gb.configure_default_column(filter=True, sortable=True, resizable=True, editable=False)

    gb.configure_column("job_name", filter="agSetColumnFilter")
    gb.configure_column("schedule_name", filter="agSetColumnFilter")
    gb.configure_column("run_type", filter="agSetColumnFilter")
    gb.configure_column("status", filter="agSetColumnFilter")
    gb.configure_column("start_time", type=["dateColumnFilter","customDateTimeFormat"], custom_format_string='yyyy-MM-dd HH:mm:ss', pivot=True)
    gb.configure_column("end_time", type=["dateColumnFilter","customDateTimeFormat"], custom_format_string='yyyy-MM-dd HH:mm:ss', pivot=True)
    # Hide but keep available for downloads
    gb.configure_column("log_path", hide=True)

    # Enable HTML buttons
    gb.configure_column("Download Log", dangerously_allow_html=True, hide=True)

    # 🔥 Use older-version-safe pagination syntax
    gb.configure_grid_options(
        pagination=True,
        paginationPageSize=15,
    )

    grid_opts = gb.build()
    grid_opts["rowSelection"] = "single"

    grid_response = AgGrid(
        df_display,
        gridOptions=grid_opts,
        update_mode=GridUpdateMode.SELECTION_CHANGED,
        allow_unsafe_jscode=True,
        height=520,
        fit_columns_on_grid_load=True,
    )

    # --------------------------------------------------------
    # Process selected row
    # --------------------------------------------------------
    selected_rows = grid_response.get("selected_rows", [])

    if selected_rows is not None and len(selected_rows) > 0:
        sel = selected_rows.reset_index(drop=True).to_dict(orient="records")[0]
        log_path = sel.get("log_path")

        if log_path and os.path.exists(log_path):
            with open(log_path, "rb") as f:
                file_bytes = f.read()

            st.download_button(
                label=f"📥 Download Log: {os.path.basename(log_path)}",
                data=file_bytes,
                file_name=os.path.basename(log_path),
                mime="text/plain"
            )
        else:
            st.info("Selected run has no log file available.")
    else:
        st.info("Select a row to enable download.")
