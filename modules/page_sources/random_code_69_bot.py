import streamlit as st
import uuid
from streamlit_autorefresh import st_autorefresh
import random
from modules.events.random_code_69_event import RandomTimedCode69Event, RandomLapCode69Event
from modules.subprocess_manager import SubprocessManager
from modules.events.audio_consumer_event import AudioConsumerEvent


logger = st.session_state.logger


def empty_vsc():
    return {'id': uuid.uuid4(), 'likelihood': 75, 'instance': None}

def start_sequence():
    window_type = st.session_state.get('vsc_type', '')
    if window_type == 'Time':
        cautions = [
            RandomTimedCode69Event(
                wave_arounds=st.session_state.wave_arounds,
                min_time=int(st.session_state.vsc_window_start) * 60,
                max_time=int(st.session_state.vsc_window_end) * 60,
                notify_on_skipped_caution=st.session_state.notify_skipped,
                reminder_frequency=st.session_state.reminder_frequency,
                max_speed_km=st.session_state.vsc_maximum_speed,
                restart_speed_pct=st.session_state.vsc_restart_speed_pct,
                lane_names=st.session_state.restart_lane_names.split(','),
                auto_restart_form_lanes=st.session_state.auto_restart_lanes,
                auto_restart_form_lanes_position=float(st.session_state.lanes_position),
                auto_restart_get_ready=st.session_state.auto_restart,
                auto_restart_get_ready_position=float(st.session_state.auto_restart_position),
                extra_lanes = len(st.session_state.restart_lane_names.split(',')) > 1
            )
            for caution in st.session_state.vsc
            if random.randrange(0, 100) <= int(caution['likelihood'])
        ]
    elif window_type == 'Lap':
        cautions = [
            RandomLapCode69Event(
                wave_arounds=st.session_state.wave_arounds,
                min_lap=int(st.session_state.vsc_window_start),
                max_lap=int(st.session_state.vsc_window_end),
                notify_on_skipped_caution=st.session_state.notify_skipped,
                reminder_frequency=st.session_state.reminder_frequency,
                max_speed_km=st.session_state.vsc_maximum_speed,
                restart_speed_pct=st.session_state.vsc_restart_speed_pct,
                lane_names=st.session_state.restart_lane_names.split(','),
                auto_restart_form_lanes=st.session_state.auto_restart_lanes,
                auto_restart_form_lanes_position=float(st.session_state.lanes_position),
                auto_restart_get_ready=st.session_state.auto_restart,
                auto_restart_get_ready_position=float(st.session_state.auto_restart_position),
                extra_lanes = len(st.session_state.restart_lane_names.split(',')) > 1
            )
            for caution in st.session_state.vsc
            if random.randrange(0, 100) <= int(caution['likelihood'])
        ]
    else:
        raise ValueError('Invalid caution window type.')
    discord_voice = AudioConsumerEvent(vc_id=int(st.session_state.discord_vc_id))

    st.session_state.vsc_runner = cautions
    all_events = [discord_voice.run, *[c.run for c in cautions]] if st.session_state.use_discord else [c.run for c in cautions]
    st.session_state.vsc_spm = SubprocessManager(all_events)
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
    col0, col1, col2, col3, col4 = st.columns(5)
    st.session_state.vsc_type = col0.radio("VSC Type", ['Time', 'Lap'], index=0, help='The type of window to trigger the VSC.')
    st.session_state.use_discord = col0.checkbox("Use Discord Voice", value=False, help='Use Discord voice chat for the VSC. Requires the BOT_TOKEN environment variable to be set.')
    st.session_state.discord_volume = col0.slider("Discord Volume", 0.0, 2.0, 1.5, disabled=not st.session_state.use_discord)
    st.session_state.vsc_window_start = col1.text_input("Window Start (min/lap)", "5", help='Start of the window in minutes.')
    st.session_state.vsc_window_end = col1.text_input("Window End (min/lap)", "-15", help='End of the window in minutes. Negative values are subtracted from the end of the session.')
    st.session_state.auto_restart_lanes = col1.checkbox("Auto Form Lanes", value=True, help='Automatically form multiple restart lanes.')
    st.session_state.reminder_frequency = col2.text_input("Reminder Frequency", "10", help='How often to send reminders in chat. If this is too low, the bot may spam the chat and be unresponsive.')
    st.session_state.vsc_maximum_speed = col2.text_input("Max VSC Speed (kph)", "69", help='Pesters the leader to stay below this speed.')
    st.session_state.auto_restart = col2.checkbox("Auto Restart", value=True, help='Automatically restart the race after the VSC ends.')
    st.session_state.vsc_restart_speed_pct = col3.text_input("Restart Speed (% of Max)", "125", help='Green flag when the leader reaches this speed after the \'End Code 69\' button is pressed.')
    st.session_state.wave_arounds = col3.checkbox("Wave Arounds", value=True, help='Automatically let cars unlap themselves at the start of the event.')
    st.session_state.restart_lane_names = col4.text_input("Restart Lane Names", "Right,Left", help="A comma-separated list of lane names. Length must be equal to the number of restart lanes. Primary/Lead lane is the first in the list.")
    st.session_state.notify_skipped = col4.checkbox("Notify on Skipped Caution", help='Send a message to the chat if a caution is skipped.')

    col0, col1, col2, col3, col4 = st.columns(5)
    st.session_state.discord_vc_id = col0.text_input("Discord Voice Channel ID", "1057329833278976160", disabled=not st.session_state.use_discord)
    st.session_state.lanes_position = col1.text_input("Form Lanes Position", "1.5", help='Laps of pacing before forming the restart lanes.', disabled=not st.session_state.auto_restart_lanes)
    st.session_state.auto_restart_position = col2.text_input("Auto Restart Position", "1.85", help='Laps of pacing before restarting.', disabled=not st.session_state.auto_restart)
    st.write('---')

    for i, caution in enumerate(st.session_state.vsc):
        col1, col2, col3, _ = st.columns((1, 1, 1, 2))
        col1.subheader(f"Code 69 #{i + 1}")
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
    col5.button("End Active Code 69", on_click=end_sequence, disabled=not active_caution)

    if st.session_state.refresh:
        st_autorefresh()
    if 'vsc_spm' in st.session_state and not any(c.is_alive() for c in st.session_state.vsc_spm.threads):
        st.session_state.refresh = False
        st_autorefresh(limit=1)

random_code_69_bot = st.Page(ui, title='Random Code 69 Bot', url_path='random_code_69_bot', icon='🐢')