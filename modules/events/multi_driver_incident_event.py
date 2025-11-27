import time

from typing_extensions import override

from modules.events.random_caution_event import RandomCautionEvent


class MultiDriverTimedIncidentEvent(RandomCautionEvent):
    """
    An event that throws a caution when a certain number of drivers (or more)
    earn a 4x incident within a configurable time window.
    """

    def __init__(
        self,
        drivers_threshold: int = 3,
        incident_window_seconds: int = 10,
        overall_driver_window: int = 30,
        auto_increase: bool = False,
        increase_by: int = 1,
        *args,
        **kwargs,
    ):
        """
        Initialize the MultiDriverIncidentEvent.

        :param drivers_threshold: Number of drivers required to trigger a caution.
        :param individual_4x_window: Time window (in seconds) to monitor individual driver 4x incidents.
        :param overall_driver_window: Time window (in seconds) to count drivers with recent 4x incidents.
        :param auto_increase: Whether to automatically increase the drivers threshold after each caution.
        :param increase_by: Amount to increase the drivers threshold by when auto_increase is enabled.
        :param sound: Whether to play a sound when the caution is triggered.
        """
        self.drivers_threshold = drivers_threshold
        self.incident_window_seconds = incident_window_seconds
        self.overall_driver_window = overall_driver_window
        self.auto_increase = auto_increase
        self.increase_by = increase_by
        self.driver_incident_timestamps = {}
        super().__init__(*args, **kwargs)
        self.start_time = kwargs.get("min", 0)
        self.start_lap = kwargs.get("min", 0)
        self.end_time = kwargs.get("max", 0)

    @staticmethod
    def ui(ident=""):
        """
        UI for the MultiDriverIncidentEvent.
        """
        import streamlit as st

        col1, col2, col3, col4 = st.columns([1, 1, 1, 1])
        return {
            "drivers_threshold": col1.number_input(
                "Drivers Threshold",
                value=3,
                key=f"{ident}drivers_threshold",
                help="Number of cars receiving 4x in the window to trigger a caution",
            ),
            "overall_driver_window": col2.number_input(
                "Incident Window (s)",
                value=30,
                key=f"{ident}overall_driver_window",
                help="Number of seconds between drivers' 4xs counted as the same incident",
            ),
            "auto_increase": col3.checkbox(
                "Auto Raise Threshold",
                value=False,
                key=f"{ident}auto_increase",
                help="Raise the threshold after every caution",
            ),
            "increase_by": col4.number_input(
                "Increase By",
                value=1,
                min_value=1,
                key=f"{ident}increase_by",
                help="Raises the threshold by this number of drivers after every caution",
            ),
            **super(MultiDriverTimedIncidentEvent, MultiDriverTimedIncidentEvent).ui(
                ident
            ),
        }

    @override
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
        self.logger.debug("Starting MultiDriverTimedIncidentEvent run loop.")
        iterator = self.driver_4x_generator(self.incident_window_seconds)
        threshold = self.drivers_threshold

        while not self.is_time_to_end():
            current_time = time.time()
            cars_with_4x = iterator.__next__()
            for car in cars_with_4x:
                self.logger.debug(f"Driver {car} triggered a 4x incident.")
                self.logger.debug(self.driver_incident_timestamps)
                if car not in self.driver_incident_timestamps:
                    self.driver_incident_timestamps[car] = []
                self.driver_incident_timestamps[car].append(current_time)

            # Clean up old timestamps outside the individual 4x window
            for car_no, timestamps in list(self.driver_incident_timestamps.items()):
                self.driver_incident_timestamps[car_no] = [
                    t
                    for t in timestamps
                    if current_time - t <= self.overall_driver_window
                ]
                if not self.driver_incident_timestamps[car_no]:
                    del self.driver_incident_timestamps[car_no]

            if len(list(self.driver_incident_timestamps.items())) >= threshold:
                # if we're already in caution, don't throw another one
                if self.is_caution_active():
                    self.logger.debug("Caution already active, not throwing another.")
                    self.driver_incident_timestamps.clear()
                    continue
                self.logger.info(
                    f"Throwing caution: {len(self.driver_incident_timestamps)} drivers triggered a 4x"
                )
                self.event_sequence()
                self.driver_incident_timestamps.clear()  # Reset after caution

                # Auto-increase the drivers threshold if enabled
                if self.auto_increase:
                    threshold += self.increase_by
                    self.logger.info(
                        f"Auto-increase enabled: drivers threshold increased to {threshold}"
                    )
            self.sleep(1)

    def is_time_to_end(self):
        total_session_time = self.sdk["SessionTimeTotal"]
        time_remaining = self.sdk["SessionTimeRemain"]
        end_time = self.end_time * 60
        end_time = end_time if end_time > 0 else int(total_session_time) + end_time

        time_until_end = end_time - (total_session_time - time_remaining)
        return time_until_end < 0


from modules.events import RandomLapEvent


class MultiDriverLapIncidentEvent(RandomLapEvent, MultiDriverTimedIncidentEvent):
    @override
    def is_time_to_end(self):
        order = self.get_current_running_order()
        lap = max([car["total_completed"] for car in order]) + 1
        end_lap = (
            self.end_time
            if self.end_time > 0
            else self.sdk["SessionLapsTotal"] + self.end_time
        )
        return lap >= end_lap

    def __init__(self, *args, **kwargs):
        MultiDriverTimedIncidentEvent.__init__(self, *args, **kwargs)
