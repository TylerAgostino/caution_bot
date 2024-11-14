from modules import logging_configuration  # noqa
import streamlit as st
from pages.random_caution_bot import random_caution_bot
from pages.random_vsc_bot import random_vsc_bot

# List of available pages for navigation
PAGES = [random_caution_bot, random_vsc_bot]

def main():
    """
    Main function to set up the Streamlit page configuration, handle page navigation,
    display log content, and provide a log level selection box.
    """
    st.set_page_config(layout='wide')  # Set the page layout to wide
    pages = st.navigation(PAGES)  # Initialize navigation with the list of pages
    pages.run()  # Run the selected page

    # Read and reverse the log content for display
    log_content = '\n'.join(open(st.session_state.logfile).read().split('\n')[::-1])
    st.text_area("Log", value=log_content, height=500, key='log_box')  # Display the log content in a text area

    # Provide a dropdown to select the log level and update the logger's level
    st.selectbox("Log Level", ['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'],
                 on_change=lambda: st.session_state.logger.handlers[0].setLevel(st.session_state.log_level),
                 key='log_level')

if __name__ == '__main__':
    main()  # Run the main function if the script is executed directly