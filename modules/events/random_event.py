from modules.events.base_event import BaseEvent
import random

class RandomEvent(BaseEvent):
    """
    An event that may or may not happen, determined by some likelihood percentage. It may also be scheduled by reimplementing the is_time_to_start method.
    """
    def __init__(self, likelihood=100):
        super().__init__()
        self.likelihood = likelihood

    def wait_for_start(self):
        """
        Waits until it is time to start the event.
        """
        while not self.is_time_to_start():
            self.sleep(1)

    def run(self, cancel_event=None, busy_event=None, audio_queue=None):
        """
        Runs the event sequence.

        Args:
            cancel_event (threading.Event, optional): Event to signal cancellation. Defaults to None.
            busy_event (threading.Event, optional): Event to signal busy state. Defaults to None.
            audio_queue (queue.Queue, optional): Queue for audio events. Defaults to None.
        """
        self.cancel_event = cancel_event or self.cancel_event
        self.busy_event = busy_event or self.busy_event
        self.audio_queue = audio_queue or self.audio_queue
        self.wait_for_start()

        if random.randrange(0, 100) > self.likelihood:
            self.logger.debug(f'{type(self)} Event skipped.')
            return
        try:
            self.event_sequence()
        except Exception as e:
            self.logger.exception('Error in event sequence.')
            self.logger.exception(e)

    @staticmethod
    def is_time_to_start():
        return True