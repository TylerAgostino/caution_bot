import random
import time

from modules.events import RandomEvent


class RandomLapEvent(RandomEvent):
    """
    A class to represent a random lap event in the iRacing simulator.

    Attributes:
        start_lap (int): The start lap of the event.
    """

    def __init__(
        self, min: int = 0, max: int = 1, quickie_window: int = 5, *args, **kwargs
    ):
        """
        Initializes the RandomLapEvent class.

        Args:
            min (int, optional): Minimum lap for the event to start. Defaults to 0.
            max (int, optional): Maximum lap for the event to start. Defaults to 1.
        """
        super().__init__(*args, **kwargs)
        self.quickie = False
        self.quickie_window = quickie_window
        if self.sdk["SessionLapsRemain"] == 32767 and (min < 0 or max < 0):
            raise ValueError("Cannot use negative lap values for time-based races.")
        self.start_lap = random.randint(
            min if min >= 0 else int(self.sdk["SessionLapsRemain"]) + min,
            max if max >= 0 else int(self.sdk["SessionLapsRemain"]) + max,
        )

    def is_time_to_start(self, adjustment=0):
        """
        Checks if it is lap to start the event.

        Args:
            adjustment (float, optional): Number of laps to adjust the start lap by. Defaults to 0.5.

        Returns:
            bool: True if it is lap to start the event, False otherwise.
        """
        order = self.get_current_running_order()
        lap = max([car["total_completed"] for car in order])
        valid_session = lap >= 1 and self.sdk["SessionState"] == 4
        if valid_session:
            self.check_and_set_quickie_flag()
        return lap >= self.start_lap + adjustment

    def check_and_set_quickie_flag(self):
        total_session_time = self.sdk["SessionTimeTotal"]
        time_remaining = self.sdk["SessionTimeRemain"]
        order = self.get_current_running_order()
        lap = max([car["total_completed"] for car in order])

        # if we're within 5 minutes of the start time, and there is another event processing, set the quickie flag
        if (
            (lap >= self.start_lap - self.quickie_window)
            and (
                self.is_caution_active()
                or self.busy_event.is_set()
                or (self.start_lap <= self.quickie_window)
            )
            and not self.quickie
        ):
            self.logger.debug(f"{self} will be a quickie event.")
            self.quickie = True


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
        super().__init__(min=int(event_lap), max=int(event_lap), *args, **kwargs)
