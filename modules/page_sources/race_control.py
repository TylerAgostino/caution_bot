import streamlit as st
from streamlit_autorefresh import st_autorefresh
from modules.events.random_caution_event import RandomCautionEvent, LapCautionEvent
from modules.events.random_code_69_event import RandomTimedCode69Event, RandomLapCode69Event
from modules.events.clear_black_flag_event import ClearBlackFlagEvent
from modules.events.audio_consumer_event import AudioConsumerEvent
from modules.subprocess_manager import SubprocessManager
from modules.events.scheduled_message_event import ScheduledMessageEvent
import uuid

event_types = {
    "Lap Caution Event": LapCautionEvent,
    "Random Caution Event": RandomCautionEvent,
    "Random Lap Code69 Event": RandomLapCode69Event,
    "Random Timed Code69 Event": RandomTimedCode69Event,
    "Clear Black Flag Event": ClearBlackFlagEvent,
    "Discord Bot": AudioConsumerEvent,
    "Scheduled Message": ScheduledMessageEvent
}

def set_events(midway = True):
    if midway:
        for guid in st.session_state['events']:
            for key in st.session_state.keys():
                if key.startswith(f"{guid}"):
                    st.session_state[key] = st.session_state[key]
    configured_events = [{
        "type": st.session_state[f'{i}_type'],
        "args": {key.split(f"{i}")[1]: st.session_state[key] for key in st.session_state.keys() if key.startswith(f"{i}") and key != f"{i}_type"}
    } for i in st.session_state.get('events', [])]
    st.session_state.configured_events = configured_events

def start():
    event_run_methods = [
        event_types[event['type']](**event['args']).event_sequence for event in st.session_state.get('configured_events', [])
    ]
    st.session_state.subprocess_manager = SubprocessManager(event_run_methods)
    st.session_state.subprocess_manager.start()
    st.session_state.refresh = True

def stop():
    if 'subprocess_manager' in st.session_state:
        st.session_state.subprocess_manager.stop()
    st.session_state.refresh = False

def ui():
    st.title("Event Configuration")

    if 'events' not in st.session_state:
        st.session_state['events'] = []


    col1, col2, col3, _ = st.columns(4)
    if col1.button("Start"):
        start()
    if col2.button("Stop"):
        stop()
    if col3.button("Add Event"):
        st.session_state['events'].append(str(uuid.uuid4())) # ] = {"type": None, "args": {}}
    if st.session_state.get('refresh', False):
        st_autorefresh()

    st.write('---')
    n = 0
    for i in st.session_state['events']:
        n += 1
        left, right = st.columns((5, 1))
        with right:
            if st.button("Remove", key=f"remove_{i}"):
                st.session_state['events'].remove(i)
                for key in st.session_state.keys():
                    if key.startswith(f"{i}"):
                        del st.session_state[key]
                set_events()
                st.rerun()
        with left:
            st.subheader(f"Event {n}")
            st.selectbox(f"Select Event Type for Event {i}", list(event_types.keys()), key=f"{i}_type", index= list(event_types.keys()).index(st.session_state.get(f'{i}_type', 'Lap Caution Event')))
            event_type = st.session_state[f'{i}_type']
            try:
                event_types[event_type].ui(i)
            except NotImplementedError:
                st.write(f"UI for {event_type} not implemented yet.")
        st.write('---')
    set_events(False)
    st.write("Configured Events:", st.session_state.get('configured_events', []))

race_control = st.Page(ui, title='Race Control', url_path='race_control', icon='🏁')