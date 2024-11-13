import random
import streamlit as st
import uuid
from modules.random_caution import RandomCaution
from modules.subprocess_manager import SubprocessManager
import logging
import time
from streamlit_autorefresh import st_autorefresh
logger = logging.getLogger(__name__)

if 'refresh' not in st.session_state:
    st.session_state.refresh = False


def empty_caution():
    return {
        'id': uuid.uuid4(),
        'likelihood': 75,
        'instance': None
    }


def start_sequence(*args, **kwargs):
    cautions = []
    for caution in st.session_state.cautions:
        roll = random.randrange(0, 100)
        if roll > int(caution['likelihood']):
            logger.debug(f"Caution did not hit. {caution['likelihood']} > {roll}")
            continue
        c = RandomCaution(
            pit_close_advance_warning=st.session_state.pit_close_advance_warning,
            pit_close_max_duration=st.session_state.pit_close_maximum_duration,
            max_laps_behind_leader=st.session_state.max_laps_behind_leader,
            wave_arounds=st.session_state.wave_arounds,
            min_time=int(st.session_state.caution_window_start) * 60,
            max_time=int(st.session_state.caution_window_end) * 60,
            notify_on_skipped_caution=st.session_state.notify_skipped
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
        st.session_state.caution_runner.stop()
    st.session_state.refresh = False
    st_autorefresh(limit=1)


def ui():
    if 'cautions' not in st.session_state:
        st.session_state.cautions = [empty_caution(), empty_caution()]

    if 'caution_instances' not in st.session_state:
        st.session_state.caution_instances = []

    st.header("Global Settings")
    
    # global settings
    col1, col2, col3, col4, col5, col6, col7 = st.columns((1, 1, 1, 1, 1, 1, 2))
    with col1:
        st.session_state.caution_window_start = st.text_input("Window Start (min)", "5")
    with col2:
        st.session_state.caution_window_end = st.text_input("Window End (min)", "-15")
    with col3:
        st.session_state.pit_close_advance_warning = st.text_input("Pit Close Warning (sec)", "5")
    with col4:
        st.session_state.pit_close_maximum_duration = st.text_input("Max Pit Close Time (sec)", "120")
    with col5:
        st.session_state.max_laps_behind_leader = st.text_input("Max Laps Behind Leader", "3")
    with col6:
        st.session_state.wave_arounds = st.checkbox("Wave Arounds")
    with col7:
        st.session_state.notify_skipped = st.checkbox("Notify on Skipped Caution")
    st.write('---')
    
    # Individual caution settings
    for i, caution in enumerate(st.session_state.cautions):
        col1, col2, col3, blank = st.columns((1, 1, 1, 2))
        with col1:
            st.subheader(f"Caution {i + 1}")
        with col2:
            caution['likelihood'] = st.text_input("Likelihood (%)", caution['likelihood'], key=f"likelihood_{caution['id']}")
        with col3:
            st.write(' ')
            st.write(' ')
            st.button("Remove", on_click=lambda: st.session_state.cautions.pop(i), key=f"remove_{caution['id']}")

    st.write('---')
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