import random
from modules.events.base_event import BaseEvent
import time

class RandomLapEvent(BaseEvent):
    """
    A class to represent a random lap event in the iRacing simulator.

    Attributes:
        start_lap (int): The start lap of the event.
    """

    def __init__(self, min_lap: int = 0, max_lap: int = 1, *args, **kwargs):
        """
        Initializes the RandomLapEvent class.

        Args:
            min_lap (int, optional): Minimum lap for the event to start. Defaults to 0.
            max_lap (int, optional): Maximum lap for the event to start. Defaults to 1.
        """
        super().__init__(*args, **kwargs)
        if self.sdk['SessionLapsRemain'] == 32767 and (min_lap < 0 or max_lap < 0):
            raise ValueError('Cannot use negative lap values for time-based races.')
        self.start_lap = random.randint(min_lap if min_lap >= 0 else int(self.sdk['SessionLapsRemain']) + min_lap,
                                        max_lap if max_lap >= 0 else int(self.sdk['SessionLapsRemain']) + max_lap)

    def is_lap_to_start(self, adjustment=0.5):
        """
        Checks if it is lap to start the event.

        Args:
            adjustment (float, optional): Number of laps to adjust the start lap by. Defaults to 0.5.

        Returns:
            bool: True if it is lap to start the event, False otherwise.
        """
        order = self.get_current_running_order()
        lap = max([car['total_completed'] for car in order])
        return lap >= self.start_lap + adjustment

    def wait_for_start(self):
        """
        Waits until it is lap to start the event.
        """
        while not self.is_lap_to_start():
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
        try:
            self.event_sequence()
        except Exception as e:
            self.logger.exception('Error in event sequence.')
            self.logger.exception(e)


class LapEvent(RandomLapEvent):
    """
    A class to represent a timed event in the iRacing simulator.
    """
    def __init__(self, event_lap, *args, **kwargs):
        """
        Initializes the TimedEvent class.

        Args:
            event_time (int): The time for the event
        """
        super().__init__(min_lap=int(event_lap), max_lap=int(event_lap)+1, *args, **kwargs)