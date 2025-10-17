import streamlit as st

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