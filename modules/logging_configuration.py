import logging
from logging.config import dictConfig
import os

def init_logging(level='INFO'):
    """
    Initializes the logging configuration for the Streamlit application.
    """
    os.makedirs('logs', exist_ok=True)
    LOGFILE = f'logs/better_caution_bot.log'
    DEBUG_LOGFILE = f'logs/better_caution_bot_debug.log'
    dictConfig({
        'version': 1,
        'formatters': {
            'default': {
                'format': '%(asctime)s - %(event)s - %(levelname)s - %(message)s \f'
            }
        },
        'handlers': {
            'file': {
                'class': 'logging.handlers.RotatingFileHandler',
                'filename': LOGFILE,
                'formatter': 'default',
                'level': level,
                # 'when': 'D',
                'backupCount': 7,
            },
            'debug': {
                'class': 'logging.handlers.RotatingFileHandler',
                'filename': DEBUG_LOGFILE,
                'formatter': 'default',
                'level': 'DEBUG',
                # 'when': 'D',
                'backupCount': 7,
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
    logging.LoggerAdapter(logger, {'event': 'init'}).debug(f'Logging to {LOGFILE} and {DEBUG_LOGFILE}')
    return logger, LOGFILE


