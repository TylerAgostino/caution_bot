import random

from modules.events import BaseEvent


class RandomEvent(BaseEvent):
    """
    An event that may or may not happen, determined by some likelihood percentage. It may also be scheduled by reimplementing the is_time_to_start method.
    """

    def __init__(self, likelihood=100, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.likelihood = likelihood

    def wait_for_start(self):
        """
        Waits until it is time to start the event.
        """
        while not self.is_time_to_start():
            self.sleep(1)

    def run(
        self,
        cancel_event=None,
        busy_event=None,
        chat_lock=None,
        audio_queue=None,
        broadcast_text_queue=None,
    ):
        """
        Runs the event sequence.

        Args:
            cancel_event (threading.Event, optional): Event to signal cancellation. Defaults to None.
            busy_event (threading.Event, optional): Event to signal busy state. Defaults to None.
            chat_lock (threading.Lock, optional): Lock to ensure thread-safe access to chat method. Defaults to None.
            audio_queue (queue.Queue, optional): Queue for audio events. Defaults to None.
            broadcast_text_queue (queue.Queue, optional): Queue for text events. Defaults to None.
        """
        self.cancel_event = cancel_event or self.cancel_event
        self.busy_event = busy_event or self.busy_event
        self.chat_lock = chat_lock or self.chat_lock
        self.audio_queue = audio_queue or self.audio_queue
        self.broadcast_text_queue = broadcast_text_queue or self.broadcast_text_queue
        self.wait_for_start()

        if random.randrange(0, 100) > float(self.likelihood):
            self.logger.debug(f"{type(self)} Event skipped.")
            return
        try:
            self.event_sequence()
        except Exception as e:
            self.logger.exception("Error in event sequence.")
            self.logger.exception(e)

    @staticmethod
    def is_time_to_start():
        return True
