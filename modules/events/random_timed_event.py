import random
from modules.events.random_event import RandomEvent
import time

class RandomTimedEvent(RandomEvent):
    """
    A class to represent a random timed event in the iRacing simulator.

    Attributes:
        start_time (int): The start time of the event.
    """

    def __init__(self, min: float = 0, max: float = 1, *args, **kwargs):
        """
        Initializes the RandomTimedEvent class.

        Args:
            min (int, optional): Minimum time for the event to start. Defaults to 0.
            max (int, optional): Maximum time for the event to start. Defaults to 1.
        """
        super().__init__(*args, **kwargs)
        min = float(min)
        max = float(max)
        self.start_time = random.randint(min*60 if min >= 0 else int(self.sdk['SessionTimeTotal']) + min*60,
                                         max*60 if max >= 0 else int(self.sdk['SessionTimeTotal']) + max*60)

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
        return (total_session_time - time_remaining >= self.start_time + adjustment) and time_remaining > 1 and self.sdk['SessionState'] == 4




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