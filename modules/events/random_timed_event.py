import random
from modules.events.random_event import RandomEvent
import time

class RandomTimedEvent(RandomEvent):
    """
    A class to represent a random timed event in the iRacing simulator.

    Attributes:
        start_time (int): The start time of the event.
    """

    def __init__(self, min: float = 0, max: float = 1, quickie_window: float = 300, *args, **kwargs):
        """
        Initializes the RandomTimedEvent class.

        Args:
            min (int, optional): Minimum time for the event to start. Defaults to 0.
            max (int, optional): Maximum time for the event to start. Defaults to 1.
        """
        super().__init__(*args, **kwargs)
        min = int(float(min) * 60)
        max = int(float(max) * 60)
        self.quickie = False
        self.quickie_window = quickie_window
        self.start_time = random.randint(min if min >= 0 else int(self.sdk['SessionTimeTotal']) + min,
                                         max if max >= 0 else int(self.sdk['SessionTimeTotal']) + max)

    def is_time_to_start(self, adjustment=0):
        """
        Checks if it is time to start the event.

        Args:
            adjustment (int, optional): Number of seconds to adjust the start time by. Defaults to 0.

        Returns:
            bool: True if it is time to start the event, False otherwise.
        """
        total_session_time = self.sdk['SessionTimeTotal']
        time_remaining = self.sdk['SessionTimeRemain']

        time_until_trigger = self.start_time - (total_session_time - time_remaining) + adjustment
        valid_session =  time_remaining > 1 and self.sdk['SessionState'] == 4

        if valid_session:
            self.check_and_set_quickie_flag()
        return time_until_trigger < 0 and valid_session

    def check_and_set_quickie_flag(self):
        total_session_time = self.sdk['SessionTimeTotal']
        time_remaining = self.sdk['SessionTimeRemain']

        # if we're within 5 minutes of the start time, and there is another event processing, set the quickie flag
        if (total_session_time - time_remaining >= self.start_time - self.quickie_window*60) and (
                self.is_caution_active() or self.busy_event.is_set() or (self.start_time <= self.quickie_window*60)
        ) and not self.quickie:
            self.logger.debug(f'{self} will be a quickie event.')
            self.quickie = True


class TimedEvent(RandomTimedEvent):
    """
    A class to represent a timed event in the iRacing simulator.
    """
    def __init__(self, event_time, *args, **kwargs):
        """
        Initializes the TimedEvent class.

        Args:
            event_time (int): The time for the event
        """
        super().__init__(min=float(event_time), max=float(event_time), *args, **kwargs)