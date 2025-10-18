import streamlit as st
from screens import dashboard, add_job, edit_job, run_job, schedule_job, view_logs

st.set_page_config(page_title="JobGoblin", page_icon="🧙‍♂️", layout="wide")

menu = {
    "🏠 Dashboard": dashboard.render,
    "➕ Add Job": add_job.render,
    "✏️ Edit Jobs": edit_job.render,
    "⚡ Run Job": run_job.render,
    "🕒 Schedule Job": schedule_job.render,
    "📜 View Logs": view_logs.render,
}

choice = st.sidebar.radio("Navigation", list(menu.keys()))
menu[choice]()
