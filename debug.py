import streamlit as st

def log(msg: str):
    """Přidá zprávu do session debug logu (s novým řádkem)."""
    if 'debug_history' not in st.session_state:
        st.session_state.debug_history = ""
    st.session_state.debug_history += f"\n{msg}"
