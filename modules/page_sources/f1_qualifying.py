from math import isnan
import streamlit as st
from modules.subprocess_manager import SubprocessManager
from modules.events.f1_qualifying_event import F1QualifyingEvent
from streamlit_autorefresh import st_autorefresh

def ui():
    st.title("F1 Qualifying")

    session_lengths = st.text_input("Session Lengths (comma-separated)", "1, 1, 1")
    advancing_cars = st.text_input("Advancing Cars (comma-separated)", "8, 5, 0")
    wait_between_sessions = st.number_input("Wait Between Sessions (seconds)", value=120)

    if st.button("Stop"):
        if 'f1_subprocess_manager' in st.session_state:
            st.session_state.f1_subprocess_manager.stop()
        st.session_state.refresh = False

    if st.button("Start"):
        st.session_state.event = F1QualifyingEvent(session_lengths, advancing_cars, wait_between_sessions=wait_between_sessions)
        st.session_state.f1_subprocess_manager = SubprocessManager([st.session_state.event.run])
        st.session_state.f1_subprocess_manager.start()
        st.session_state.refresh = True

    if 'event' in st.session_state:
        st.header(st.session_state.event.subsession_time_remaining)
        leaderboard = st.session_state.event.leaderboard_df
        for col in leaderboard.columns:
            if col == 'DriverName':
                continue
            leaderboard[col] = leaderboard[col].apply(lambda x: f"{int(x // 60):02}:{int(x % 60):02}.{int((x % 1) * 1000):03}" if isinstance(x, (int, float)) and not isnan(x) else x)
        st.dataframe(leaderboard,width=600, height=1000, use_container_width=False)

    if st.session_state.get('refresh', False):
        st_autorefresh()
    else:
        st_autorefresh(limit=1)

f1_qualifying = st.Page(ui, title='F1 Qualifying', url_path='f1_qualifying')