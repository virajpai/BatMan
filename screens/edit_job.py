# screens/edit_job.py
import streamlit as st
import json
import pandas as pd
from utils.db_models import Job
from utils.db_utils import DbOps

db_ops = DbOps()

def render():
    st.title("✏️ Edit Jobs")
    st.caption("Edit job details below. You can modify name, script path, and args (JSON format).")

    # Fetch jobs
    req_cols = ["id", "name", "script_path", "args"]
    df = db_ops.select_records(Job, filters=None, columns=req_cols)

    if df.empty:
        st.info("No jobs found. Please add jobs first.")
        return
    
    # Add delete column
    df["Delete"] = False

    # Display editable DataFrame
    key = f"edit_job_table_{st.session_state.get('refresh_key', 0)}"
    edited_df = st.data_editor(
        df,
        disabled=["id"],
        width='stretch',
        num_rows="fixed",
        hide_index=True,
        key=key
    )

    # Save button
    if st.button("💾 Save Changes"):
        total_updates = 0
        errors = []

        for i, row in edited_df.iterrows():
            job_id = row["id"]
            
            # Compare with original df
            orig_row = df[df["id"] == job_id].iloc[0]
            if row["name"] == orig_row["name"] and \
            row["script_path"] == orig_row["script_path"] and \
            row["args"] == orig_row["args"]:
                continue  # Skip if nothing changed

            updates = {
                "name": row["name"],
                "script_path": row["script_path"],
                "args": row["args"],
                "modified_by": "ui_user"
            }

            try:
                updated = db_ops.update_records(Job, filters={"id": job_id}, updates=updates)
                total_updates += updated
            except Exception as e:
                errors.append(f"Job id {job_id}: failed to update → {e}")

        # Feedback
        if errors:
            st.error("Some updates failed:")
            for e in errors:
                st.write(f"- {e}")
        else:
            # --- Before rerun ---
            st.session_state["toast_msg"] = f"✅ Successfully updated {total_updates} job(s)."
            st.session_state["toast_icon"] = "💾"
            st.rerun()


    # --- DELETE SELECTED JOBS ---
    delete_rows = edited_df[edited_df["Delete"] == True]

    if not delete_rows.empty:
        if st.button("🗑️ Delete Selected"):
            deleted_count = 0
            for _, row in delete_rows.iterrows():
                try:
                    db_ops.delete_records(Job, filters={"id": row["id"]})
                    deleted_count += 1
                except Exception as e:
                    st.error(f"Failed to delete job ID {row['id']}: {e}")
            
            st.session_state["toast_msg"] = f"🗑️ Deleted {deleted_count} job(s)."
            st.session_state["toast_icon"] = "⚡"
            st.session_state["refresh_key"] = st.session_state.get("refresh_key", 0) + 1
            st.rerun()
            
    # --- Show toast if message exists ---
    if "toast_msg" in st.session_state and st.session_state["toast_msg"]:
        st.toast(st.session_state["toast_msg"], icon=st.session_state.get("toast_icon", "✅"))
        st.session_state["toast_msg"] = ""  # Clear after showing

