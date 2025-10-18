import streamlit as st
from datetime import datetime, timedelta
import calendar
import re
import os

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

def run(script_path: str, command: str):
    """
    Run a job with the given job ID.
    """
    
    print(rf"Executing script at: {script_path} with command: {command}")
    
    # Save current working directory
    # parent_dir = os.path.dirname(rf"{script_path}")
    cwd = os.getcwd()
    # os.chdir(parent_dir)  # run from parent directory
    try:
        # Dummy implementation of job execution
        st.write(f"Running job... --> {command}")
        # Here you would add the actual job execution logic
    finally:
        # Restore working directory
        os.chdir(cwd)
        
    return "success"