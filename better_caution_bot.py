import logging
import streamlit as st
from modules import init_logging, STARTUP_LOGO
from logging import INFO, DEBUG, WARNING, ERROR, CRITICAL

levels = {
    INFO: 'INFO',
    DEBUG: 'DEBUG',
    WARNING: 'WARNING',
    ERROR: 'ERROR',
    CRITICAL: 'CRITICAL'
}

if 'logger' not in st.session_state:
    st.session_state.logger, st.session_state.logfile = init_logging()
    for handler in st.session_state.logger.handlers:
        handler.doRollover()
    st.session_state.base_logger = logging.LoggerAdapter(st.session_state.logger, {'event': 'base'})
    st.session_state.base_logger.info(STARTUP_LOGO)
    st.session_state.base_logger.info('---')


def main():
    """
    Main function to set up the Streamlit page configuration, handle page navigation,
    display log content, and provide a log level selection box.
    """
    from modules.page_sources import race_control, beer_goggles, f1_qualifying

    # List of available pages for navigation
    page_list = [
        race_control,
        beer_goggles,
        f1_qualifying
    ]

    st.set_page_config(layout='wide')  # Set the page layout to wide
    st.logo("https://osyu.sh/thonk.svg")
    pages = st.navigation(page_list)  # Initialize navigation with the list of pages
    pages.run()  # Run the selected page

    with st.sidebar:

        # Provide a dropdown to select the log level and update the logger's level
        log_levels = ['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL']
        st.session_state.log_level = st.selectbox("Log Level", log_levels,
                                                  index=log_levels.index(levels[st.session_state.logger.handlers[0].level]),
                                                  )
        st.session_state.logger.handlers[0].setLevel(st.session_state.log_level)  # Update the logger's level
        with st.container(height=450):
            # Read and reverse the log content for display
            log_lines = open(st.session_state.logfile).read().split('\f')[::-1]
            if len(log_lines) > 1000:
                log_lines = log_lines[:1000]
            log_content = '\n'.join(log_lines)
            st.code(log_content, language='log', wrap_lines=False)  # Display the log content in a text area

if __name__ == '__main__':
    main()  # Run the main function if the script is executed directly