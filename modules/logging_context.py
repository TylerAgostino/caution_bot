"""
Global logging context for sharing logger instances across the application.

This module provides a central place to store and retrieve logger instances,
which is especially important for Flet applications that don't have
Streamlit's session state.
"""

import logging
from typing import Optional

# Global logger instance
_global_logger: Optional[logging.Logger] = None
_global_logfile: Optional[str] = None


def set_logger(logger: logging.Logger, logfile: str = None):
    """
    Set the global logger instance.

    Args:
        logger: The logger instance to store globally
        logfile: Optional path to the log file
    """
    global _global_logger, _global_logfile
    _global_logger = logger
    _global_logfile = logfile


def get_logger() -> Optional[logging.Logger]:
    """
    Get the global logger instance.

    Returns:
        The global logger instance, or None if not set
    """
    return _global_logger


def get_logfile() -> Optional[str]:
    """
    Get the global log file path.

    Returns:
        The log file path, or None if not set
    """
    return _global_logfile


def has_logger() -> bool:
    """
    Check if a logger has been initialized.

    Returns:
        True if logger is set, False otherwise
    """
    return _global_logger is not None
