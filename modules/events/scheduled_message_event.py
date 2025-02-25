from modules.events.random_timed_event import TimedEvent

class ScheduledMessageEvent(TimedEvent):
    """
    A class to represent a scheduled message event in the iRacing simulator.
    """

    def __init__(self, message: str, *args, **kwargs):
        """
        Initializes the ScheduledMessageEvent class.

        Args:
            message (str): The message to send.
        """
        super().__init__(*args, **kwargs)
        self.message = message

    def event_sequence(self):
        """
        Sends the message.
        """
        self._chat(self.message)

    @staticmethod
    def ui(ident=''):
        import streamlit as st
        return {
            'event_time': st.number_input("Event Time (min)", value=5, key=f'{ident}event_time') * 60,
            'message': st.text_input('Message', key=f'{ident}message', value=''),
        }
