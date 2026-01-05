import queue

from modules.events import BaseEvent


class ChatConsumerEvent(BaseEvent):
    """
    Consumes chat messages directed to the player to be displayed in the UI for the driver.
    This consumer is specifically designed to show messages (like lane assignments) directed to the player
    that might otherwise be missed in busy chat windows when they're also racing.
    """

    def __init__(self, test=False, sdk=False, *args, **kwargs):
        super().__init__(sdk=sdk, *args, **kwargs)
        if test:
            self.chat_consumer_queue.put("Test message for driver display")

    @staticmethod
    def ui(ident=""):
        import streamlit as st

        col1, col2 = st.columns(2)
        return {
            "test": col1.checkbox("Test", key=f"{ident}test", value=False),
        }

    def event_sequence(self):
        """
        Consumes chat messages from the queue.
        The actual display is handled by the UI layer.
        This event just keeps the queue active and prevents it from blocking.
        """
        while True:
            try:
                # Just check if there are messages, but don't consume them
                # The UI will consume them for display
                if not self.chat_consumer_queue.empty():
                    self.logger.debug(
                        f"Chat consumer queue has {self.chat_consumer_queue.qsize()} message(s)"
                    )
            except queue.Empty:
                pass
            self.sleep(1)
