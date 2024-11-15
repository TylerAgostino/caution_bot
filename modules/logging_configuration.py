import logging
from logging.config import dictConfig
import streamlit as st
import datetime
import os

def init_logging(level='INFO'):
    """
    Initializes the logging configuration for the Streamlit application.
    """
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
                'level': level
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
    return logger, LOGFILE


