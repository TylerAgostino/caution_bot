import threading
import modules.race_control as rc
import datetime
import os
import logging
from logging.config import dictConfig
import asyncio
import streamlit
import uuid
from streamlit.runtime.scriptrunner import add_script_run_ctx
import streamlit_autorefresh
active_caution = False

LOGLEVEL = 'ERROR'

counter = streamlit_autorefresh.st_autorefresh()

os.makedirs('logs', exist_ok=True)
if 'LOGFILE' not in streamlit.session_state:
    streamlit.session_state.LOGFILE = f'logs/{datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")}.log'
    streamlit.session_state.DEBUG_LOGFILE = f'logs/{datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")}_debug.log'

LOGFILE = streamlit.session_state.LOGFILE
DEBUG_LOGFILE = streamlit.session_state.DEBUG_LOGFILE
# LOGFILE = f'logs/{datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")}.log'
# DEBUG_LOGFILE = f'logs/{datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")}_debug.log'

if 'log_level' not in streamlit.session_state:
    streamlit.session_state.log_level = 'INFO'

if 'kill' not in streamlit.session_state:
    streamlit.session_state.kill = False

def set_log_level(level=None):
    if level is None:
        level = streamlit.session_state.log_level
    logger.handlers[0].setLevel(level)
    # maybe start a new log file here?


async def start_bot(caution_window_start, caution_window_end, caution_likelihood, caution_frequency, minimum_cautions,
                    pit_close_advance_warning, pit_close_maximum_duration, max_laps_behind_leader, wave_arounds,
                    caution_class=rc.Caution):
    try:
        bot = rc.Bot(
            caution_window_start=int(float(caution_window_start) * 60),
            caution_window_end=int(float(caution_window_end) * 60),
            caution_likelihood=float(caution_likelihood) / 100,
            caution_frequency=int(caution_frequency),
            minimum_cautions=int(minimum_cautions),
            pit_close_advance_warning=int(pit_close_advance_warning),
            pit_close_maximum_duration=int(pit_close_maximum_duration),
            max_laps_behind_leader=int(max_laps_behind_leader),
            caution_class=caution_class,
            wave_arounds=wave_arounds
        )
    except Exception as e:
        logging.error(f'Error initializing bot: {e}')
        logging.debug(f'Caution window start: {caution_window_start}')
        logging.debug(f'Caution window end: {caution_window_end}')
        logging.debug(f'Caution likelihood: {caution_likelihood}')
        logging.debug(f'Caution frequency: {caution_frequency}')
        logging.debug(f'Minimum cautions: {minimum_cautions}')
        logging.debug(f'Pit close advance warning: {pit_close_advance_warning}')
        logging.debug(f'Pit close maximum duration: {pit_close_maximum_duration}')
        logging.debug(f'Max laps behind leader: {max_laps_behind_leader}')
        return

    while not bot.is_in_valid_session():
        logging.info("Not in a valid session.")
        await asyncio.sleep(10)

    for caution in bot.cautions:
        logging.debug(f"Caution at {caution.caution_time} seconds.")
    await asyncio.gather(*[caution.run() for caution in bot.cautions])


async def start_task(**kwargs):
    task = asyncio.create_task(start_bot(**kwargs))
    while not streamlit.session_state.kill and not task.done():
        await asyncio.sleep(1)
    logging.info("Done.")
    # start_button.config(text="Start", command=start_bot_thread)


def stop_task():
    logger.info("Cancelling.")
    streamlit.session_state.kill = True


def ui_random_cautions():

    def empty_caution():
        return {
            'id': uuid.uuid4(),
            'frequency': 1,
            'likelihood': 75,
            'minimum': 0
        }

    def start_bot_thread():
        streamlit.session_state.kill = False
        for caution in streamlit.session_state.cautions:
            caution_frequency = int(caution['frequency'])
            caution_likelihood = int(caution['likelihood'])
            caution_minimum = int(caution['minimum'])
            t = threading.Thread(target=asyncio.run, args=(start_task(
                caution_window_start=caution_window_start,
                caution_window_end=caution_window_end,
                caution_likelihood=caution_likelihood,
                caution_frequency=caution_frequency,
                minimum_cautions=caution_minimum,
                pit_close_advance_warning=pit_close_advance_warning,
                pit_close_maximum_duration=pit_close_maximum_duration,
                max_laps_behind_leader=max_laps_behind_leader,
                wave_arounds=wave_arounds
            ),))
            add_script_run_ctx(t)
            t.start()

    streamlit.write(f'Kill: {streamlit.session_state.kill}')

    if 'cautions' not in streamlit.session_state:
        streamlit.session_state.cautions = [empty_caution()]

    streamlit.header("Global Settings")

    # global settings
    col1, col2, col3, col4, col5, col6 = streamlit.columns(6)
    with col1:
        caution_window_start = streamlit.text_input("Window Start (minutes)", "5")
    with col2:
        caution_window_end = streamlit.text_input("Window End (minutes)", "-15")
    with col3:
        pit_close_advance_warning = streamlit.text_input("Pit Close Warning (Seconds)", "5")
    with col4:
        pit_close_maximum_duration = streamlit.text_input("Max Pit Close Time (Seconds)", "120")
    with col5:
        max_laps_behind_leader = streamlit.text_input("Max Laps Behind Leader", "3")
    with col6:
        wave_arounds = streamlit.checkbox("Wave Arounds", key='wave_arounds')

    # Individual caution settings
    for i, caution in enumerate(streamlit.session_state.cautions):
        streamlit.subheader(f"Caution {i + 1}")
        col1, col2, col3, col4 = streamlit.columns(4)
        with col1:
            caution['frequency'] = streamlit.text_input("Maximum Cautions", caution['frequency'], key=f"frequency_{caution['id']}", disabled=streamlit.session_state.kill)
        with col2:
            caution['minimum'] = streamlit.text_input("Minimum Cautions", caution['minimum'], key=f"minimum_{caution['id']}", disabled=streamlit.session_state.kill)
        with col3:
            caution['likelihood'] = streamlit.text_input("Likelihood (%)", caution['likelihood'], key=f"likelihood_{caution['id']}", disabled=streamlit.session_state.kill)
        with col4:
            streamlit.button("Remove", on_click=lambda: streamlit.session_state.cautions.pop(i), key=f"remove_{caution['id']}", disabled=streamlit.session_state.kill)

    streamlit.button("Add Caution", on_click=lambda: streamlit.session_state.cautions.append(empty_caution()), disabled=streamlit.session_state.kill)


    col1, col2, col3 = streamlit.columns(3)
    with col1:
        streamlit.button("Start", on_click=start_bot_thread, disabled=streamlit.session_state.kill)
    with col2:
        streamlit.button("Stop", on_click=stop_task, disabled=not streamlit.session_state.kill)
    with col3:
        log_level = streamlit.selectbox("Log Level",
                                    ['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'],
                                    on_change=set_log_level,
                                    key='log_level')
    log_box = streamlit.text_area("Log", value='\n'.join(open(LOGFILE).read().split('\n')[::-1]), height=500, key='log_box')



def ui_virtual_safety_car():
    def start_bot_thread():
        streamlit.session_state.kill = False
        for caution in streamlit.session_state.vscs:
            caution_frequency = int(caution['frequency'])
            caution_likelihood = int(caution['likelihood'])
            caution_minimum = int(caution['minimum'])
            t = threading.Thread(target=asyncio.run, args=(start_task(
                caution_window_start=caution_window_start,
                caution_window_end=caution_window_end,
                caution_likelihood=caution_likelihood,
                caution_frequency=caution_frequency,
                minimum_cautions=caution_minimum,
                caution_class=rc.VirtualSafetyCar,
                pit_close_advance_warning=None,
                pit_close_maximum_duration=None,
                max_laps_behind_leader=None
            ),))
            add_script_run_ctx(t)
            t.start()

    def empty_caution():
        return {
            'id': uuid.uuid4(),
            'frequency': 1,
            'likelihood': 75,
            'minimum': 0
        }

    if 'vscs' not in streamlit.session_state:
        streamlit.session_state.vscs = [empty_caution()]

    streamlit.header("Global Settings")

    # global settings
    col1, col2 = streamlit.columns(2)
    with col1:
        caution_window_start = streamlit.text_input("Window Start (minutes)", "5")
    with col2:
        caution_window_end = streamlit.text_input("Window End (minutes)", "-15")

    # Individual caution settings
    for i, caution in enumerate(streamlit.session_state.vscs):
        streamlit.subheader(f"Caution {i + 1}")
        col1, col2, col3, col4 = streamlit.columns(4)
        with col1:
            caution['frequency'] = streamlit.text_input("Maximum Cautions", caution['frequency'], key=f"frequency_{caution['id']}", disabled=streamlit.session_state.kill)
        with col2:
            caution['minimum'] = streamlit.text_input("Minimum Cautions", caution['minimum'], key=f"minimum_{caution['id']}", disabled=streamlit.session_state.kill)
        with col3:
            caution['likelihood'] = streamlit.text_input("Likelihood (%)", caution['likelihood'], key=f"likelihood_{caution['id']}", disabled=streamlit.session_state.kill)
        with col4:
            streamlit.button("Remove", on_click=lambda: streamlit.session_state.vscs.pop(i), key=f"remove_{caution['id']}", disabled=streamlit.session_state.kill)

    streamlit.button("Add Caution", on_click=lambda: streamlit.session_state.vscs.append(empty_caution()), disabled=streamlit.session_state.streamlit.session_state.kill)

    col1, col2, col3 = streamlit.columns(3)

    with col1:
        streamlit.button("Start", on_click=start_bot_thread, disabled=streamlit.session_state.kill)
    with col2:
        streamlit.button("Stop", on_click=stop_task, disabled=not streamlit.session_state.kill)
    with col3:
        level = streamlit.selectbox("Log Level",
                                    ['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'],
                                    on_change=set_log_level,
                                    key='log_level')

    log_box = streamlit.text_area("Log", value='\n'.join(open(LOGFILE).read().split('\n')[::-1]), height=500, key='log_box')


if __name__ == '__main__':
    dictConfig({
        'version': 1,
        'formatters': {
            'default': {
                'format': '%(levelname)s - %(message)s'
            }
        },
        'handlers': {
            'file': {
                'class': 'logging.FileHandler',
                'filename': LOGFILE,
                'mode': 'a+',
                'formatter': 'default',
                'level': streamlit.session_state.log_level
            },
            'debug': {
                'class': 'logging.FileHandler',
                'filename': DEBUG_LOGFILE,
                'mode': 'a+',
                'formatter': 'default',
                'level': 'DEBUG'
            }
        },
        'loggers': {
            '': {
                'handlers': ['file', 'debug'],
                'level': 'DEBUG'
            }
        }
    })
    logger = logging.getLogger()
    pages = streamlit.navigation([streamlit.Page(ui_random_cautions, title='Better Caution Bot'), streamlit.Page(ui_virtual_safety_car, title='Virtual Safety Car Bot')])
    # streamlit_ui()
    pages.run()
