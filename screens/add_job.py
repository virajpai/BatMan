import streamlit as st
import os
from utils.job_helper import get_arg_value, format_arg
from utils.db_utils import DbOps
from utils.db_models import Job

def render():
    st.title("➕ Add Job")
    st.caption("Define a new script job with configurable arguments.")

    # Initialize session
    st.session_state.setdefault("job_args", [])
    st.session_state.setdefault("arg_inputs", {"key": "", "type": "str", "value": None, "format": ""})

    # --- Basic Info ---
    job_name = st.text_input("Job Name", placeholder="e.g., Daily_Sales_Extract")

    uploaded_file = st.file_uploader("Select Script File", type=["py", "bat"])
    file_path = uploaded_file.name if uploaded_file else None
    if file_path:
        file_path = os.path.abspath(file_path)
        st.info(f"📁 File path: {file_path}")

    st.divider()

    # --- Arguments Section ---
    with st.expander("Add Arguments"):
        col1, col2, col3 = st.columns([1, 1, 2])
        with col1:
            st.session_state.arg_inputs["key"] = st.text_input("Key", placeholder="e.g., f or file", value=st.session_state.arg_inputs["key"])
        with col2:
            st.session_state.arg_inputs["type"] = st.selectbox("Type", ["str", "number", "date"], index=["str", "number", "date"].index(st.session_state.arg_inputs["type"]))
        with col3:
            val, fmt = get_arg_value(st.session_state.arg_inputs["type"])
            st.session_state.arg_inputs["value"] = val
            st.session_state.arg_inputs["format"] = fmt

        if st.button("➕ Add Argument"):
            key = st.session_state.arg_inputs["key"]
            arg_type = st.session_state.arg_inputs["type"]
            arg_value = st.session_state.arg_inputs["value"]
            date_format = st.session_state.arg_inputs["format"]

            if key and arg_value is not None:
                formatted = format_arg(key, arg_value, arg_type=arg_type)
                st.session_state.job_args.append({
                    "key": key,
                    "type": arg_type,
                    "value": arg_value,
                    "format": date_format if date_format else "",
                    "formatted": formatted,
                })

                # Clear input fields
                st.session_state.arg_inputs = {"key": "", "type": "str", "value": None, "format": ""}
                st.rerun()
            else:
                st.warning("Please fill both key and value before adding.")

    # --- Display Added Arguments (as table) ---
    if st.session_state.job_args:
        st.subheader("Added Arguments")

        # Header row
        cols = st.columns([1, 1, 2, 2, 1])
        cols[0].write("**Key**")
        cols[1].write("**Type**")
        cols[2].write("**Value**")
        cols[3].write("**Format**")
        cols[4].write("**Delete**")

        # Data rows
        for idx, arg in enumerate(st.session_state.job_args):
            col1, col2, col3, col4, col5 = st.columns([1, 1, 2, 2, 1])
            col1.write(arg["key"])
            col2.write(arg["type"])
            val_display = f"{arg['value']} {arg['format']}" if arg['format'] else arg['value']
            col3.write(val_display)
            col4.write(arg["format"])
            if col5.button("❌", key=f"del_{idx}"):
                st.session_state.job_args.pop(idx)
                st.rerun()

    # --- Save Job ---
    if st.button("💾 Save Job"):
        if not job_name:
            st.error("Please enter a job name.")
        elif not file_path:
            st.error("Please select a file.")
        else:
            args_str = " ".join([arg.get("formatted") for arg in st.session_state.job_args])
            dbops = DbOps()
            num_rec = dbops.insert_record(Job, {
                "name": job_name,
                "script_path": file_path,
                "script_type": str(file_path).split(".", maxsplit=-1)[-1],
                "args": args_str
            })
            
            if num_rec and num_rec == 1:
                st.success(f"✅ Job '{job_name}' saved successfully.")
            else:
                st.error('Error is saving the job!')
                
            st.json({
                "name": job_name,
                "script_path": file_path,
                "args": args_str,
            })
            st.session_state.job_args = []
