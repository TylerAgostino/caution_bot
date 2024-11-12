import streamlit as st
import uuid
from modules.random_caution import RandomCaution
from modules.subprocess_manager import SubprocessManager
import logging
import time
from streamlit_autorefresh import st_autorefresh

if 'refresh' not in st.session_state:
    st.session_state.refresh = False


def empty_caution():
    return {
        'id': uuid.uuid4(),
        'frequency': 1,
        'likelihood': 75,
        'minimum': 0,
        'instance': None
    }


def start_sequence(*args, **kwargs):
    cautions = []
    for caution in st.session_state.cautions:
        c = RandomCaution(
            frequency=caution['frequency'],
            likelihood=caution['likelihood'],
            minimum=caution['minimum'],
            pit_close_advance_warning=st.session_state.pit_close_advance_warning,
            pit_close_max_duration=st.session_state.pit_close_maximum_duration,
            max_laps_behind_leader=st.session_state.max_laps_behind_leader,
            wave_arounds=st.session_state.wave_arounds,
            min_time=int(st.session_state.caution_window_start) * 60,
            max_time=int(st.session_state.caution_window_end) * 60,
            notify_on_skipped_caution=False
        )
        cautions.append(c)

    st.session_state.caution_runner = cautions

    processes = [c.run for c in cautions]
    st.session_state.spm = SubprocessManager(processes)
    st.session_state.spm.start()
    # while any([c.is_alive() for c in spm.threads]):
    #     time.sleep(1)
    st.session_state.refresh = True


def stop_sequence():
    if 'caution_runner' in st.session_state:
        for c in st.session_state.caution_runner:
            c.killed = True
    st.session_state.refresh = False
    st_autorefresh(limit=1)


def ui():
    if 'kill' not in st.session_state:
        st.session_state.kill = True

    if 'cautions' not in st.session_state:
        st.session_state.cautions = [empty_caution()]

    if 'caution_instances' not in st.session_state:
        st.session_state.caution_instances = []

    st.header("Global Settings")
    
    # global settings
    col1, col2, col3, col4, col5, col6 = st.columns(6)
    with col1:
        st.session_state.caution_window_start = st.text_input("Window Start (minutes)", "5")
    with col2:
        st.session_state.caution_window_end = st.text_input("Window End (minutes)", "-15")
    with col3:
        st.session_state.pit_close_advance_warning = st.text_input("Pit Close Warning (Seconds)", "5")
    with col4:
        st.session_state.pit_close_maximum_duration = st.text_input("Max Pit Close Time (Seconds)", "120")
    with col5:
        st.session_state.max_laps_behind_leader = st.text_input("Max Laps Behind Leader", "3")
    with col6:
        st.session_state.wave_arounds = st.checkbox("Wave Arounds")
    
    # Individual caution settings
    for i, caution in enumerate(st.session_state.cautions):
        st.subheader(f"Caution {i + 1}")
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            caution['frequency'] = st.text_input("Maximum Cautions", caution['frequency'], key=f"frequency_{caution['id']}")
        with col2:
            caution['minimum'] = st.text_input("Minimum Cautions", caution['minimum'], key=f"minimum_{caution['id']}")
        with col3:
            caution['likelihood'] = st.text_input("Likelihood (%)", caution['likelihood'], key=f"likelihood_{caution['id']}")
        with col4:
            st.button("Remove", on_click=lambda: st.session_state.cautions.pop(i), key=f"remove_{caution['id']}")
    
    st.button("Add Caution", on_click=lambda: st.session_state.cautions.append(empty_caution()))
    
    col1, col2 = st.columns(2)
    with col1:
        st.button("Start", on_click=start_sequence)
    with col2:
        st.button("Stop", on_click=stop_sequence)

    if 'refresh' in st.session_state and st.session_state.refresh:
        st_autorefresh()
    if 'spm' in st.session_state:
        if not any([c.is_alive() for c in  st.session_state.spm.threads]):
            st.session_state.refresh = False
            st_autorefresh(limit=1)


random_caution_bot = st.Page(ui, title='Random Caution Bot', url_path='random_caution_bot')