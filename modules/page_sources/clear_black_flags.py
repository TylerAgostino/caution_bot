import threading

import streamlit as st
import uuid
from modules.events.random_timed_event import TimedEvent
from streamlit_autorefresh import st_autorefresh
from modules.subprocess_manager import SubprocessManager
from modules.events.clear_black_flag_event import ClearBlackFlagEvent


def start_sequence():
    st.session_state.spm = SubprocessManager([ClearBlackFlagEvent(interval=st.session_state.interval).run])
    st.session_state.spm.start()
    st.session_state.refresh = True

def end_sequence():
    if 'spm' in st.session_state:
        st.session_state.spm.stop()
    st.session_state.refresh = False
    st_autorefresh(limit=1)


def ui():
    st.session_state.setdefault('interval', 5)
    st.header("Clear Black Flags")

    col1, col2, col3, _ = st.columns([1, 1, 1, 3])
    with col1:
        st.write("Interval")
        st.write("")
    with col2:
        st.session_state.interval = st.text_input(label_visibility='collapsed', label="interval", value=st.session_state.interval)

    st.write('---')

    col1, col2, _ = st.columns([1, 1, 4])

    with col1:
        st.button("Start", on_click=lambda: start_sequence())
    with col2:
        st.button("Stop", on_click=lambda: end_sequence())

clear_black_flags = st.Page(ui, title='Clear Black Flags', icon="🏴‍☠️", url_path='clear_black_flags')