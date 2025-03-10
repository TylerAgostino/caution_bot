import threading

import streamlit as st
import uuid
from modules.events.random_timed_event import TimedEvent
from streamlit_autorefresh import st_autorefresh
from modules.subprocess_manager import SubprocessManager




def start_sequence():
    st.session_state.spm = SubprocessManager([SprintRaceDQEvent(st.session_state.dq_cars, event_time=st.session_state.dq_time, penalty=st.session_state.dq_penalty).run])
    st.session_state.spm.start()
    st.session_state.refresh = True

def end_sequence():
    if 'spm' in st.session_state:
        st.session_state.spm.stop()
    st.session_state.refresh = False
    st_autorefresh(limit=1)


def ui():
    st.session_state.setdefault('dq_cars', [
        {'id': uuid.uuid4(), 'car_number': 19},
        {'id': uuid.uuid4(), 'car_number': 99}
    ])
    st.session_state.setdefault('dq_time', -60)
    st.header("Disqualification Settings")

    col1, col2, col3, _ = st.columns([1, 1, 1, 3])
    for i, dq_car in enumerate(st.session_state.get("dq_cars")):
        with col1:
            st.write("Car Number")
            st.write("")
        with col2:
            st.session_state.dq_cars[i]['car_number'] = st.text_input(f"Car {i + 1}", value=dq_car['car_number'], label_visibility='collapsed', key=f"car_number_{dq_car['id']}")
        with col3:
            st.button("Remove", on_click=lambda: st.session_state.dq_cars.pop(i), key=f"remove_{dq_car['id']}")

    st.button("Add Car", on_click=lambda: st.session_state.dq_cars.append({'id': uuid.uuid4(), 'car_number': 69}))

    col1, col2, _ = st.columns([1, 1, 4])
    with col1:
        st.write("Disqualification Time")
        st.write("")

        st.write("Penalty")
        st.write("")
    with col2:
        st.session_state.dq_time = st.text_input("Disqualification Time (sec)", "-60" , label_visibility='collapsed')
        st.session_state.dq_penalty = st.text_input("Penalty", "L2", label_visibility='collapsed')

    st.write('---')

    col1, col2, _ = st.columns([1, 1, 4])

    with col1:
        st.button("Start", on_click=lambda: start_sequence())
    with col2:
        st.button("Stop", on_click=lambda: end_sequence())

sprint_race_dq = st.Page(ui, title='Sprint Race DQ', icon="🏴")