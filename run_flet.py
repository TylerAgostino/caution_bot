import logging

import flet as ft

from modules import init_logging, set_logger
from modules.flet_pages.race_control import main


def main_wrapper(page: ft.Page):
    """
    Wrapper function to initialize logging before starting the Flet app.
    """
    # Initialize logging for Flet application
    logger, logfile = init_logging()

    # Store logger in global context that BaseEvent can access
    set_logger(logger, logfile)

    # Log startup message
    logging.LoggerAdapter(logger, {"event": "init"}).info("Flet application started")

    # Start the main application
    main(page)


if __name__ == "__main__":
    ft.app(target=main_wrapper, view=ft.AppView.FLET_APP)
