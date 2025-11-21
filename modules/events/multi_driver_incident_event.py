from typing_extensions import override
import time

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
        *args,
        **kwargs,
    ):
        """
        Initialize the MultiDriverIncidentEvent.

        :param drivers_threshold: Number of drivers required to trigger a caution.
        :param individual_4x_window: Time window (in seconds) to monitor individual driver 4x incidents.
        :param overall_driver_window: Time window (in seconds) to count drivers with recent 4x incidents.
        :param sound: Whether to play a sound when the caution is triggered.
        """
        self.drivers_threshold = drivers_threshold
        self.incident_window_seconds = incident_window_seconds
        self.overall_driver_window = overall_driver_window
        self.driver_incident_timestamps = {}
        super().__init__(*args, **kwargs)
        self.start_time = kwargs.get('min', 0)
        self.end_time = kwargs.get('max', 0)

    @staticmethod
    def ui(ident=""):
        """
        UI for the MultiDriverIncidentEvent.
        """
        import streamlit as st

        col1, col2, col3 = st.columns([1, 1, 1])
        return {
            "drivers_threshold": col1.number_input(
                "Drivers Threshold", value=3, key=f"{ident}drivers_threshold"
            ),
            "incident_window_seconds": col2.number_input(
                "Incident Window (s)", value=10, key=f"{ident}incident_window_seconds"
            ),
            "overall_driver_window": col3.number_input(
                "Overall Driver Window (s)",
                value=30,
                key=f"{ident}overall_driver_window",
            ),
            **super(MultiDriverTimedIncidentEvent, MultiDriverTimedIncidentEvent).ui(ident),
        }

    @override
    def run(
        self,
        cancel_event=None,
        busy_event=None,
        audio_queue=None,
        broadcast_text_queue=None,
    ):
        """
        Runs the event sequence.

        Args:
            cancel_event (threading.Event, optional): Event to signal cancellation. Defaults to None.
            busy_event (threading.Event, optional): Event to signal busy state. Defaults to None.
            audio_queue (queue.Queue, optional): Queue for audio events. Defaults to None.
            broadcast_text_queue (queue.Queue, optional): Queue for text events. Defaults to None.
        """
        self.cancel_event = cancel_event or self.cancel_event
        self.busy_event = busy_event or self.busy_event
        self.audio_queue = audio_queue or self.audio_queue
        self.broadcast_text_queue = broadcast_text_queue or self.broadcast_text_queue
        self.wait_for_start()

        self.sdk.freeze_var_buffer_latest()
        this_step = self.sdk["DriverInfo"]["Drivers"]
        while not self.is_time_to_end():
            self.sdk.freeze_var_buffer_latest()
            last_step = this_step
            this_step = self.sdk["DriverInfo"]["Drivers"]

            current_time = time.time()
            triggered_drivers = []
            for car in this_step:
                car_no = car["CarNumber"]
                try:
                    prev_inc = [x for x in last_step if x["CarNumber"] == car_no][0][
                        "TeamIncidentCount"
                    ]
                except IndexError:
                    self.logger.debug(f"Car {car_no} not found in last step")
                    continue

                this_inc = car["TeamIncidentCount"]
                if this_inc - prev_inc >= 4:  # Detect a 4x incident
                    self.logger.debug(f"Car {car_no} earned a 4x incident")
                    if car_no not in self.driver_incident_timestamps:
                        self.driver_incident_timestamps[car_no] = []
                    self.driver_incident_timestamps[car_no].append(current_time)

            # Clean up old timestamps outside the individual 4x window
            for car_no, timestamps in list(self.driver_incident_timestamps.items()):
                self.driver_incident_timestamps[car_no] = [
                    t
                    for t in timestamps
                    if current_time - t <= self.incident_window_seconds
                ]
                if not self.driver_incident_timestamps[car_no]:
                    del self.driver_incident_timestamps[car_no]

            # Count drivers with recent 4x incidents within the overall driver window
            triggered_drivers = [
                car_no
                for car_no, timestamps in self.driver_incident_timestamps.items()
                if any(
                    current_time - t <= self.overall_driver_window for t in timestamps
                )
            ]

            if len(triggered_drivers) >= self.drivers_threshold:
                self.logger.info(
                    f"Throwing caution: {len(triggered_drivers)} drivers triggered a 4x"
                )
                self.event_sequence()
                self.driver_incident_timestamps.clear()  # Reset after caution

            self.sdk.unfreeze_var_buffer_latest()
            self.sleep(1)

    def is_time_to_end(self):
        total_session_time = self.sdk['SessionTimeTotal']
        time_remaining = self.sdk['SessionTimeRemain']
        end_time = self.end_time * 60
        end_time = end_time if end_time > 0 else int(total_session_time) + end_time

        time_until_end = end_time - (total_session_time - time_remaining)
        return time_until_end < 0

from modules.events import LapCautionEvent
class MultiDriverLapIncidentEvent(LapCautionEvent, MultiDriverTimedIncidentEvent):
    @override
    def is_time_to_end(self):
        order = self.get_current_running_order()
        lap = max([car['total_completed'] for car in order]) + 1
        end_lap = self.end_time if self.end_time > 0 else self.sdk['SessionLapsTotal'] + self.end_time
        return lap >= end_lap
