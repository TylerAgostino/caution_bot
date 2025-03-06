import streamlit as st
from streamlit_autorefresh import st_autorefresh
from modules.events.random_caution_event import RandomCautionEvent, LapCautionEvent
from modules.events.random_code_69_event import RandomTimedCode69Event, RandomLapCode69Event
from modules.events.clear_black_flag_event import ClearBlackFlagEvent
from modules.events.audio_consumer_event import AudioConsumerEvent
from modules.subprocess_manager import SubprocessManager
from modules.events.scheduled_message_event import ScheduledMessageEvent
from modules.events.scheduled_black_flag_event import SprintRaceDQEvent
import uuid
from streamlit.errors import StreamlitAPIException

event_types = {
    "Lap Caution Event": LapCautionEvent,
    "Random Caution Event": RandomCautionEvent,
    "Random Lap Code69 Event": RandomLapCode69Event,
    "Random Timed Code69 Event": RandomTimedCode69Event,
    "Clear Black Flag Event": ClearBlackFlagEvent,
    "Discord Bot": AudioConsumerEvent,
    "Scheduled Message": ScheduledMessageEvent,
    "Sprint DQ": SprintRaceDQEvent
}

def touch_all_state():
    for guid in st.session_state.get('events', []):
        for key in st.session_state.keys():
            if key.startswith(f"{guid}"):
                try:
                    st.session_state[key] = st.session_state[key]
                except StreamlitAPIException:
                    pass

touch_all_state()

def set_events(midway = True):
    configured_events = [{
        "type": st.session_state[f'{i}_type'],
        "args": {key.split(f"{i}")[1]: st.session_state[key] for key in st.session_state.keys() if key.startswith(f"{i}") and key != f"{i}_type"}
    } for i in st.session_state.get('events', [])]
    st.session_state.configured_events = configured_events

def start():
    event_run_methods = [
        event_types[event['type']](**event['args']).run for event in st.session_state.get('configured_events', [])
    ]
    st.session_state.subprocess_manager = SubprocessManager(event_run_methods)
    st.session_state.subprocess_manager.start()
    st.session_state.refresh = True

def stop():
    if 'subprocess_manager' in st.session_state:
        st.session_state.subprocess_manager.stop()
    st.session_state.refresh = False

def apply_preset(default_events):
    st.session_state.events = [str(uuid.uuid4()) for _ in default_events]
    for i, event in enumerate(default_events):
        for key, value in event['args'].items():
            st.session_state[f"{st.session_state['events'][i]}{key}"] = value
        st.session_state[f"{st.session_state['events'][i]}_type"] = event['type']
    set_events()
    st.rerun()


def ui():
    st.title("Event Configuration")
    col1, col2, col3, col4 = st.columns(4)
    if col1.button("Beer League Race"):
        default_events = [
            {
                "type": "Discord Bot",
                "args": {
                    'vc_id': '1057329833278976160',
                    'volume': 2.0
                }
            },
            {
                "type": "Random Timed Code69 Event",
                "args": {}
            },
            {
                "type": "Random Timed Code69 Event",
                "args": {}
            },
            {
                "type": "Scheduled Message",
                "args": {
                    "message": "The Code 69 Window is now open.",
                    "event_time": 5,
                    "race_control": True
                }
            },
            {
                "type": "Scheduled Message",
                "args": {
                    "message": "The Code 69 Window is now closed.",
                    "event_time": -15,
                    "race_control": True
                }
            },
            {
                "type": "Scheduled Message",
                "args": {
                    "message": "HALFWAY",
                    "event_time": 30,
                    "race_control": True
                }
            }
        ]
        apply_preset(default_events)
    if col2.button("Beer League Sprint"):
        default_events = [
            {
                "type": "Sprint DQ",
                "args": {}
            },
            {
                "type": "Scheduled Message",
                "args": {
                    "message": "HALFWAY",
                    "event_time": 7.5,
                    "race_control": True
                }
            }
        ]
        apply_preset(default_events)
    if col3.button("Nurb"):
        default_events = [
            {
                "type": "Discord Bot",
                "args": {
                    'vc_id': '1057329833278976160',
                    'volume': 2.0
                }
            },
            {
                "type": "Random Lap Code69 Event",
                "args": {
                    'min': 1,
                    'max': 6,
                    'auto_class_separate': False,
                    'auto_restart_form_lanes': False,
                    'auto_restart_get_ready': True,
                    'auto_restart_get_ready_position': 0.24,
                    'wave_arounds': False
                }
            },
            {
                "type": "Random Lap Code69 Event",
                "args": {
                    'min': 1,
                    'max': 6,
                    'auto_class_separate': False,
                    'auto_restart_form_lanes': False,
                    'auto_restart_get_ready': True,
                    'auto_restart_get_ready_position': 0.24,
                    'wave_arounds': False
                }
            }
        ]
        apply_preset(default_events)
    if col4.button("Test"):
        default_events = [
            {
                "type": "Random Timed Code69 Event",
                "args": {
                    'min': 1,
                    'max': 2
                }
            }
        ]
        apply_preset(default_events)

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
                touch_all_state()
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
    set_events()
    st.write("Configured Events:", st.session_state.get('configured_events', []))

race_control = st.Page(ui, title='Race Control', url_path='race_control', icon='🏁')