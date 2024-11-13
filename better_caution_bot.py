import streamlit as st
from pages.random_caution_bot import random_caution_bot
from pages.random_vsc_bot import random_vsc_bot
import logging
import datetime
from logging.config import dictConfig
import os


if 'logger' not in st.session_state:
    st.session_state.log_level = 'INFO'
    os.makedirs('logs', exist_ok=True)
    LOGFILE = f'logs/{datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")}.log'
    DEBUG_LOGFILE = f'logs/debug_{datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")}.log'
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
                'level': st.session_state.log_level
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
    logger.info(f'Logging to {LOGFILE} and {DEBUG_LOGFILE}')
    st.session_state.logger = logger
    st.session_state.logfile = LOGFILE

if __name__ == '__main__':
    log_file = st.session_state.logfile
    st.set_page_config(layout='wide')
    pages = st.navigation([random_caution_bot, random_vsc_bot])
    pages.run()
    log_box = st.text_area("Log", value='\n'.join(open(log_file).read().split('\n')[::-1]), height=500, key='log_box')
    log_level = st.selectbox("Log Level",
                             ['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'],
                             on_change=lambda: st.session_state.logger.handlers[0].setLevel(st.session_state.log_level),
                             key='log_level')
