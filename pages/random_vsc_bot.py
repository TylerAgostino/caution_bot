import streamlit as st
import uuid
from streamlit_autorefresh import st_autorefresh
import random
from modules.events.random_vsc_event import RandomVSCEvent
from modules.subprocess_manager import SubprocessManager


logger = st.session_state.logger


def empty_vsc():
    return {'id': uuid.uuid4(), 'likelihood': 100, 'instance': None}

def start_sequence():
    cautions = [
        RandomVSCEvent(
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

def ui():
    st.session_state.setdefault('vsc', [empty_vsc()])
    st.session_state.setdefault('vsc_instances', [])
    st.session_state.setdefault('refresh', False)

    st.header("Global Settings")
    col1, col2, col3, col4, col5, col6, col7 = st.columns(7)
    st.session_state.vsc_window_start = col1.text_input("Window Start (min)", "5")
    st.session_state.vsc_window_end = col2.text_input("Window End (min)", "-15")
    st.session_state.vsc_laps_behind = col3.text_input("Max Laps Behind Leader", "4")
    st.session_state.vsc_maximum_duration = col4.text_input("Max VSC duration (sec)", "120")
    st.session_state.vsc_restart_proximity = col5.text_input("Restart Proximity (Lap%)", "5")
    st.session_state.wave_arounds = col6.checkbox("Wave Arounds")
    st.session_state.notify_skipped = col7.checkbox("Notify on Skipped Caution")
    st.write('---')

    for i, caution in enumerate(st.session_state.vsc):
        col1, col2, col3, _ = st.columns((1, 1, 1, 2))
        col1.subheader(f"VSC {i + 1}")
        st.session_state.vsc[i]['likelihood'] = col2.text_input("Likelihood (%)", caution['likelihood'], key=f"likelihood_{caution['id']}")
        col3.button("Remove", on_click=lambda: st.session_state.vsc.pop(i), key=f"remove_{caution['id']}")

    st.write('---')
    st.button("Add Caution", on_click=lambda: st.session_state.vsc.append(empty_vsc()))

    col1, col2, col3 = st.columns(3)
    col1.button("Start", on_click=start_sequence)
    col2.button("Stop", on_click=stop_sequence)
    col3.button("End Active VSC", on_click=end_sequence)

    if st.session_state.refresh:
        st_autorefresh()
    if 'spm' in st.session_state and not any(c.is_alive() for c in st.session_state.spm.threads):
        st.session_state.refresh = False
        st_autorefresh(limit=1)

random_vsc_bot = st.Page(ui, title='Random VSC Bot', url_path='random_vsc_bot')