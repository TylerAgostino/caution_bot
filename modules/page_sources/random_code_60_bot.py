import streamlit as st
import uuid
from streamlit_autorefresh import st_autorefresh
import random
from modules.events.random_code_60_event import RandomCode60Event
from modules.subprocess_manager import SubprocessManager


logger = st.session_state.logger


def empty_vsc():
    return {'id': uuid.uuid4(), 'likelihood': 100, 'instance': None}

def start_sequence():
    cautions = [
        RandomCode60Event(
            restart_proximity=st.session_state.vsc_restart_proximity,
            max_vsc_duration=st.session_state.vsc_maximum_duration,
            wave_arounds=st.session_state.wave_arounds,
            min_time=int(st.session_state.vsc_window_start) * 60,
            max_time=int(st.session_state.vsc_window_end) * 60,
            notify_on_skipped_caution=st.session_state.notify_skipped,
            max_laps_behind_leader=st.session_state.vsc_laps_behind
        )
        for caution in st.session_state.vsc
        if random.randrange(0, 100) <= int(caution['likelihood'])
    ]

    st.session_state.vsc_runner = cautions
    st.session_state.vsc_spm = SubprocessManager([c.run for c in cautions])
    st.session_state.vsc_spm.start()
    st.session_state.refresh = True

def stop_sequence():
    if 'vsc_runner' in st.session_state:
        st.session_state.vsc_spm.stop()
    st.session_state.refresh = False
    st_autorefresh(limit=1)

def end_sequence():
    if 'vsc_runner' in st.session_state:
        for caution in st.session_state.vsc_runner:
            caution.restart_ready.set()

def end_double_file():
    if 'vsc_runner' in st.session_state:
        for caution in st.session_state.vsc_runner:
            caution.double_file = True
            caution.restart_ready.set()

def ui():
    st.session_state.setdefault('vsc', [empty_vsc()])
    st.session_state.setdefault('vsc_instances', [])
    st.session_state.setdefault('refresh', False)

    st.header("Global Settings")
    col1, col2, col3, col4, col5, col6, col7 = st.columns(7)
    st.session_state.vsc_window_start = col1.text_input("Window Start (min)", "5")
    st.session_state.vsc_window_end = col2.text_input("Window End (min)", "-15")
    st.session_state.vsc_laps_behind = col3.text_input("Max Laps Behind Leader", "4")
    st.session_state.vsc_maximum_duration = col4.text_input("Max VSC duration (sec)", "120", disabled=True)
    st.session_state.vsc_restart_proximity = col5.text_input("Restart Proximity (Lap%)", "5", disabled=True)
    st.session_state.wave_arounds = col6.checkbox("Wave Arounds", value=True)
    st.session_state.notify_skipped = col7.checkbox("Notify on Skipped Caution")
    st.write('---')

    for i, caution in enumerate(st.session_state.vsc):
        col1, col2, col3, _ = st.columns((1, 1, 1, 2))
        col1.subheader(f"Code 60 #{i + 1}")
        st.session_state.vsc[i]['likelihood'] = col2.text_input("Likelihood (%)", caution['likelihood'], key=f"likelihood_{caution['id']}")
        col3.button("Remove", on_click=lambda: st.session_state.vsc.pop(i), key=f"remove_{caution['id']}")

    st.write('---')
    st.button("Add", on_click=lambda: st.session_state.vsc.append(empty_vsc()))

    col1, col2, col3, col4, _ = st.columns(5)
    col1.button("Start", on_click=start_sequence)
    col2.button("Cancel", on_click=stop_sequence)
    col3.button("Line Up Double File", on_click=end_double_file)
    col4.button("End Active Code 60", on_click=end_sequence)

    if st.session_state.refresh:
        st_autorefresh()
    if 'spm' in st.session_state and not any(c.is_alive() for c in st.session_state.spm.threads):
        st.session_state.refresh = False
        st_autorefresh(limit=1)

random_code_60_bot = st.Page(ui, title='Random Code 60 Bot', url_path='random_code_60_bot', icon='🐢')