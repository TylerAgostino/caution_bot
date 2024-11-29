import streamlit as st
import uuid
from streamlit_autorefresh import st_autorefresh
import random
from modules.events.random_code_60_event import RandomCode60Event
from modules.subprocess_manager import SubprocessManager


logger = st.session_state.logger


def empty_vsc():
    return {'id': uuid.uuid4(), 'likelihood': 75, 'instance': None}

def start_sequence():
    cautions = [
        RandomCode60Event(
            wave_arounds=st.session_state.wave_arounds,
            min_time=int(st.session_state.vsc_window_start) * 60,
            max_time=int(st.session_state.vsc_window_end) * 60,
            notify_on_skipped_caution=st.session_state.notify_skipped,
            max_laps_behind_leader=st.session_state.vsc_laps_behind,
            max_speed_km=st.session_state.vsc_maximum_speed,
            restart_speed_pct=st.session_state.vsc_restart_speed_pct,
            restart_lanes=int(st.session_state.restart_lanes),
            lane_names=st.session_state.restart_lane_names.split(',')
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
        st.session_state.vsc_runner = []
    st.session_state.refresh = False
    st_autorefresh(limit=1)

def end_sequence():
    if 'vsc_runner' in st.session_state:
        for caution in st.session_state.vsc_runner:
            caution.restart_ready.set()

def form_lanes():
    if 'vsc_runner' in st.session_state:
        for caution in st.session_state.vsc_runner:
            if caution.busy_event.is_set():
                caution.extra_lanes = True
                caution.restart_lanes = int(st.session_state.restart_lanes)
                caution.lane_names = st.session_state.restart_lane_names.split(',')
                caution.restart_ready.set()

def class_separation():
    if 'vsc_runner' in st.session_state:
        for caution in st.session_state.vsc_runner:
            if caution.busy_event.is_set():
                caution.class_separation = True

def ui():
    st.session_state.setdefault('vsc', [empty_vsc(), empty_vsc()])
    st.session_state.setdefault('vsc_instances', [])
    st.session_state.setdefault('refresh', False)

    st.header("Global Settings")
    col1, col2, col3, col4 = st.columns(4)
    st.session_state.vsc_window_start = col1.text_input("Window Start (min)", "5", help='Start of the window in minutes.')
    st.session_state.vsc_window_end = col1.text_input("Window End (min)", "-15", help='End of the window in minutes. Negative values are subtracted from the end of the session.')
    st.session_state.vsc_laps_behind = col2.text_input("Max Laps Behind Leader", "4", help='Ignore cars more than this number of laps behind the leader.')
    st.session_state.vsc_maximum_speed = col2.text_input("Max VSC Speed (kph)", "60", help='Pesters the leader to stay below this speed.')
    st.session_state.vsc_restart_speed_pct = col3.text_input("Restart Speed (% of Max)", "150", help='Green flag when the leader reaches this speed after the \'End Code 60\' button is pressed.')
    st.session_state.wave_arounds = col3.checkbox("Wave Arounds", value=True, help='Automatically let cars unlap themselves at the start of the event.')
    st.session_state.notify_skipped = col3.checkbox("Notify on Skipped Caution", help='Send a message to the chat if a caution is skipped.')
    st.session_state.restart_lanes = col4.text_input("Restart Lanes", "2", help='How many lanes to form when the button is clicked.')
    st.session_state.restart_lane_names = col4.text_input("Restart Lane Names", "Inside,Outside", help="A comma-separated list of lane names. Length must be equal to the number of restart lanes. Primary/Lead lane is the first in the list.")
    st.write('---')

    for i, caution in enumerate(st.session_state.vsc):
        col1, col2, col3, _ = st.columns((1, 1, 1, 2))
        col1.subheader(f"Code 60 #{i + 1}")
        st.session_state.vsc[i]['likelihood'] = col2.text_input("Likelihood (%)", caution['likelihood'], key=f"likelihood_{caution['id']}")
        col3.button("Remove", on_click=lambda: st.session_state.vsc.pop(i), key=f"remove_{caution['id']}")

    st.button("Add", on_click=lambda: st.session_state.vsc.append(empty_vsc()))
    st.write('---')

    col1, col2, col3, col4, col5 = st.columns(5)
    active_caution = any(c.busy_event.is_set() for c in st.session_state.vsc_runner) if 'vsc_runner' in st.session_state else False
    can_separate_classes = any(c.busy_event.is_set() and c.can_separate_classes for c in st.session_state.vsc_runner) if 'vsc_runner' in st.session_state else False
    col1.button("Start", on_click=start_sequence)
    col2.button("Cancel", on_click=stop_sequence)
    col3.button("Class Separation", on_click=class_separation, disabled=not can_separate_classes)
    col4.button("Form Multiple Lanes", on_click=form_lanes, disabled=not active_caution)
    col5.button("End Active Code 60", on_click=end_sequence, disabled=not active_caution)

    if st.session_state.refresh:
        st_autorefresh()
    if 'spm' in st.session_state and not any(c.is_alive() for c in st.session_state.spm.threads):
        st.session_state.refresh = False
        st_autorefresh(limit=1)

random_code_60_bot = st.Page(ui, title='Random Code 60 Bot', url_path='random_code_60_bot', icon='🐢')