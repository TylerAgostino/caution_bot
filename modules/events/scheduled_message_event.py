from modules.events import TimedEvent


class ScheduledMessageEvent(TimedEvent):
    """
    A class to represent a scheduled message event in the iRacing simulator.
    """

    def __init__(
        self,
        message: str,
        race_control: bool = False,
        broadcast: bool = False,
        *args,
        **kwargs,
    ):
        """
        Initializes the ScheduledMessageEvent class.

        Args:
            message (str): The message to send.
        """
        super().__init__(*args, **kwargs)
        self.message = message
        self.race_control = race_control
        self.broadcast = broadcast

    def event_sequence(self):
        """
        Sends the message.
        """
        self._chat(self.message, race_control=self.race_control)
        if self.broadcast:
            msg = {
                "title": "Race Control",
                "text": self.message,
            }
            self.broadcast_text_queue.put(msg)
