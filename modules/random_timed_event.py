import random
from modules.base_event import BaseEvent
import time


class RandomTimedEvent(BaseEvent):
    def __init__(self, min_time: int = 0, max_time: int = 1, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if max_time < 0:
            max_time = int(self.sdk['SessionTimeTotal']) + max_time
        self.start_time = random.randrange(min_time, max_time)

    def is_time_to_start(self, adjustment=0):
        total_session_time = self.sdk['SessionTimeTotal']
        time_remaining = self.sdk['SessionTimeRemain']
        is_time = (total_session_time - time_remaining >= self.start_time - adjustment)
        return is_time and time_remaining > 1

    def wait_for_start(self):
        while not self.is_time_to_start():
            self.sleep(1)

    def run(self, cancel_event=None, busy_event=None):
        if cancel_event is not None:
            self.cancel_event = cancel_event
        if busy_event is not None:
            self.busy_event = busy_event
        self.wait_for_start()
        self.event_sequence()