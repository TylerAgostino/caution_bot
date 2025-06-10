import logging
from logging.config import dictConfig
import os
import re

class CustomFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        arg_pattern = re.compile(r'%\((\w+)\)')
        arg_names = [x.group(1) for x in arg_pattern.finditer(self._fmt)]
        for field in arg_names:
            if field not in record.__dict__:
                record.__dict__[field] = None

        return super().format(record)


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
                'format': '%(asctime)s - %(event)s - %(levelname)s - %(message)s \f',
                'class': 'modules.logging_configuration.CustomFormatter',
            },
            'minimal': {
                'format': '%(message)s',
                'class': 'modules.logging_configuration.CustomFormatter',
            }
        },
        'handlers': {
            'file': {
                'class': 'logging.handlers.RotatingFileHandler',
                'filename': LOGFILE,
                'formatter': 'minimal',
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


