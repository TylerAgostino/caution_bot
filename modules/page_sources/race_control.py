import streamlit as st
from streamlit_autorefresh import st_autorefresh
from modules.events.random_caution_event import RandomCautionEvent, LapCautionEvent
from modules.events.random_code_69_event import RandomTimedCode69Event, RandomLapCode69Event
from modules.events.clear_black_flag_event import ClearBlackFlagEvent
from modules.events.audio_consumer_event import AudioConsumerEvent
import uuid

def ui():
    st.title("Event Configuration")

    if 'events' not in st.session_state:
        st.session_state['events'] = {}

    event_types = {
        "Lap Caution Event": LapCautionEvent,
        "Random Caution Event": RandomCautionEvent,
        "Random Lap Code69 Event": RandomLapCode69Event,
        "Random Timed Code69 Event": RandomTimedCode69Event,
        "Clear Black Flag Event": ClearBlackFlagEvent,
        "Discord Bot": AudioConsumerEvent
    }

    if st.button("Add Event"):
        st.session_state['events'][str(uuid.uuid4())] = {"type": None, "args": {}}

    n = 0
    for i, event in st.session_state['events'].items():
        n += 1
        left, right = st.columns((5, 1))
        with right:
            if st.button("Remove", key=f"remove_{i}"):
                st.session_state['events'].pop(i)
                st.rerun()
        with left:
            st.subheader(f"Event {n}")
            event_type = st.selectbox(f"Select Event Type for Event {i}", list(event_types.keys()), key=f"type_{i}", index=list(event_types.keys()).index(event['type']) if event['type'] else 1)
            st.session_state['events'][i]['type'] = event_type

            try:
                st.session_state['events'][i]['args'] = event_types[event_type].ui(i)
            except NotImplementedError:
                st.write(f"UI for {event_type} not implemented yet.")

    st.write("Configured Events:", st.session_state['events'])

race_control = st.Page(ui, title='Race Control', url_path='race_control', icon='🏁')