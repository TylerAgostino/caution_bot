import streamlit as st
from modules.logging_configuration import init_logging
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
    st.session_state.logger.info('Application started.')


def main():
    """
    Main function to set up the Streamlit page configuration, handle page navigation,
    display log content, and provide a log level selection box.
    """
    from pages.random_caution_bot import random_caution_bot
    from pages.random_vsc_bot import random_vsc_bot
    from pages.sprint_race_dq import sprint_race_dq

    # List of available pages for navigation
    PAGES = [random_caution_bot, random_vsc_bot, sprint_race_dq]

    st.set_page_config(layout='wide')  # Set the page layout to wide
    pages = st.navigation(PAGES)  # Initialize navigation with the list of pages
    pages.run()  # Run the selected page

    # Read and reverse the log content for display
    log_content = '\n'.join(open(st.session_state.logfile).read().split('\n')[::-1])
    st.text_area("Log", value=log_content, height=500)  # Display the log content in a text area

    # Provide a dropdown to select the log level and update the logger's level
    log_levels = ['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL']
    st.session_state.log_level = st.selectbox("Log Level", log_levels,
                                              index=log_levels.index(levels[st.session_state.logger.handlers[0].level]),
                 )
    st.session_state.logger.handlers[0].setLevel(st.session_state.log_level)  # Update the logger's level

if __name__ == '__main__':
    main()  # Run the main function if the script is executed directly