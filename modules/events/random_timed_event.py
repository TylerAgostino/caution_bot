import random
from modules.events.random_event import RandomEvent
import time

class RandomTimedEvent(RandomEvent):
    """
    A class to represent a random timed event in the iRacing simulator.

    Attributes:
        start_time (int): The start time of the event.
    """

    def __init__(self, min_time: int = 0, max_time: int = 1, *args, **kwargs):
        """
        Initializes the RandomTimedEvent class.

        Args:
            min_time (int, optional): Minimum time for the event to start. Defaults to 0.
            max_time (int, optional): Maximum time for the event to start. Defaults to 1.
        """
        super().__init__(*args, **kwargs)
        self.start_time = random.randrange(min_time if min_time >= 0 else int(self.sdk['SessionTimeTotal']) + min_time,
                                           max_time if max_time >= 0 else int(self.sdk['SessionTimeTotal']) + max_time)

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
        super().__init__(min_time=int(event_time), max_time=int(event_time)+1, *args, **kwargs)