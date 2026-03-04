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
        play_audio: bool = False,
        audio_file: str = "",
        *args,
        **kwargs,
    ):
        """
        Initializes the ScheduledMessageEvent class.

        Args:
            message (str): The message to send.
            race_control (bool): Whether to send the message to race control.
            broadcast (bool): Whether to send the message to the broadcast overlay.
            play_audio (bool): Whether to queue an audio file for playback via the audio consumer.
            audio_file (str): The filename (without path/extension) to supply to the audio consumer.
        """
        super().__init__(*args, **kwargs)
        self.message = message
        self.race_control = race_control
        self.broadcast = broadcast
        self.play_audio = play_audio
        self.audio_file = audio_file

    def event_sequence(self):
        """
        Sends the message and optionally queues an audio file for playback.
        """
        self._chat(self.message, race_control=self.race_control)
        if self.broadcast:
            msg = {
                "title": "Race Control",
                "text": self.message,
            }
            self.broadcast_text_queue.put(msg)
        if self.play_audio and self.audio_file:
            self.audio_queue.put(self.audio_file)
