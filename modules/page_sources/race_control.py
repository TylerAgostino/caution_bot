import streamlit as st
from streamlit_autorefresh import st_autorefresh
from modules.events.random_caution_event import RandomCautionEvent, LapCautionEvent
from modules.events.random_code_69_event import RandomTimedCode69Event, RandomLapCode69Event
from modules.events.clear_black_flag_event import ClearBlackFlagEvent
from modules.events.audio_consumer_event import AudioConsumerEvent
from modules.subprocess_manager import SubprocessManager
from modules.events.scheduled_message_event import ScheduledMessageEvent
from modules.events.scheduled_black_flag_event import SprintRaceDQEvent
from modules.events.incident_penalty_event import IncidentPenaltyEvent
from modules.events.text_consumer_event import TextConsumerEvent, DiscordTextConsumerEvent, ATVOTextConsumerEvent
import uuid
from streamlit.errors import StreamlitAPIException
import os
import json

event_types = {
    "Lap Caution Event": LapCautionEvent,
    "Random Caution Event": RandomCautionEvent,
    "Random Lap Code69 Event": RandomLapCode69Event,
    "Random Timed Code69 Event": RandomTimedCode69Event,
    "Clear Black Flag Event": ClearBlackFlagEvent,
    "Discord Bot": AudioConsumerEvent,
    "Scheduled Message": ScheduledMessageEvent,
    "Sprint DQ": SprintRaceDQEvent,
    "Incident Penalty": IncidentPenaltyEvent,
    "Broadcast Text": TextConsumerEvent,
    "Discord Text": DiscordTextConsumerEvent,
    "ATVO Text": ATVOTextConsumerEvent,
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
        "guid": i,
        "type": st.session_state[f'{i}_type'],
        "args": {key.split(f"{i}")[1]: st.session_state[key] for key in st.session_state.keys() if key.startswith(f"{i}") and key != f"{i}_type"}
    } for i in st.session_state.get('events', [])]
    st.session_state.configured_events = configured_events

def update_events():
    if 'event_classes' in st.session_state:
        for guid, event in st.session_state['event_classes'].items():
            properties = {key: st.session_state[key] for key in st.session_state.keys() if key.startswith(guid) and key != f"{guid}_type"}
            for key, value in properties.items():
                de_guid_key = key.split(guid)[1]
                if hasattr(event, de_guid_key):
                    setattr(event, de_guid_key, value)
                else:
                    pass

def save_preset(name):
    file = open(f"presets/{name}.json", "w")
    file.write(json.dumps(st.session_state.get('configured_events', [])))
    file.close()

def load_presets():
    presets = []
    for file in os.listdir("presets"):
        if file.endswith(".json"):
            with open(f"presets/{file}", "r") as f:
                presets.append((file[:-5], json.loads(f.read())))
    return presets

def start():
    st.session_state.event_classes = {event['guid']: event_types[event['type']](**event['args']) for event in st.session_state.get('configured_events', [])}
    event_run_methods = [
        event.run for guid, event in st.session_state.event_classes.items()
    ]
    st.session_state.subprocess_manager = SubprocessManager(event_run_methods)
    st.session_state.subprocess_manager.start()
    st.session_state.refresh = True

def stop():
    if 'subprocess_manager' in st.session_state:
        st.session_state.subprocess_manager.stop()
    st.session_state.refresh = False
    st_autorefresh(limit=1)

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
    presets = load_presets()
    columns = st.columns(min(len(presets)+2, 7))
    for i, (name, preset) in enumerate(presets):
        with columns[i%5]:
            if st.button(name):
                apply_preset(preset)
    col1 = columns[-2]
    col2 = columns[-1]
    new_preset_name = col1.text_input("New Preset Name", "")
    if col2.button("Save Preset"):
        if new_preset_name:
            save_preset(new_preset_name)
            st.success(f"Preset {new_preset_name} saved!")
        else:
            st.error("Please enter a name for the preset.")
    st.write('---')

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
    update_events()
    st.write("Configured Events:", st.session_state.get('configured_events', []))

race_control = st.Page(ui, title='Race Control', url_path='race_control', icon='🏁')