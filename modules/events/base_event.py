import logging
import queue
import threading
import time

import irsdk
import pyperclip
import pywinauto
from pandas import DataFrame, concat


class BaseEvent:
    """
    Base class for handling events in the iRacing simulator.

    Attributes:
        sdk (irsdk.IRSDK): Instance of the iRacing SDK.
        pwa (pywinauto.Application): Instance of the pywinauto Application.
        thread (threading.Thread): Thread for running the event.
        killed (bool): Flag to indicate if the event is killed.
        task (Any): Placeholder for a task.
        logger (logging.Logger): Logger instance for logging events.
        cancel_event (threading.Event): Event to signal cancellation.
        busy_event (threading.Event): Event to signal busy state.
        chat_lock (threading.Lock): Lock to ensure thread-safe access to chat method.
        max_laps_behind_leader (int): Maximum Laps Down for cars to be considered in the field.
    """

    Flags = irsdk.Flags
    PaceFlags = irsdk.PaceFlags

    def __init__(
        self,
        sdk=None,
        pwa=None,
        cancel_event=None,
        busy_event=None,
        chat_lock=None,
        audio_queue=None,
        broadcast_text_queue=None,
        chat_consumer_queue=None,
        max_laps_behind_leader=99,
    ):
        """
        Initializes the BaseEvent class.

        Args:
            sdk (irsdk.IRSDK, optional): Instance of the iRacing SDK. Defaults to None.
            pwa (pywinauto.Application, optional): Instance of the pywinauto Application. Defaults to None.
            cancel_event (threading.Event, optional): Event to signal cancellation. Defaults to None.
            busy_event (threading.Event, optional): Event to signal busy state. Defaults to None.
            chat_lock (threading.Lock, optional): Lock to ensure thread-safe access to chat method. Defaults to None.
            audio_queue (queue.Queue, optional): Queue for audio messages. Defaults to None.
            broadcast_text_queue (queue.Queue, optional): Queue for broadcast text messages. Defaults to None.
            chat_consumer_queue (queue.Queue, optional): Queue for chat messages directed to the player. Defaults to None.
            max_laps_behind_leader (int, optional): Maximum Laps Down for cars to be considered in the field. Defaults to 99.
        """
        self.sdk = irsdk.IRSDK() if sdk is None else sdk
        if self.sdk:
            self.pwa = pwa or pywinauto.Application()
            self.sdk.shutdown()
            self.sdk.startup()
            self.pwa.connect(best_match="iRacing.com Simulator", timeout=10)
        self.thread = None
        self.killed = False
        self.task = None
        from modules.logging_context import get_logger

        lh = get_logger() if get_logger() else logging.getLogger(__name__)
        if lh is not None:
            self.logger = logging.LoggerAdapter(
                lh,
                {"event": self.__class__.__name__},
            )
        self.cancel_event = cancel_event or threading.Event()
        self.busy_event = busy_event or threading.Event()
        self.chat_lock = chat_lock or threading.Lock()
        self.audio_queue = audio_queue or queue.Queue()
        self.broadcast_text_queue = broadcast_text_queue or queue.Queue()
        self.chat_consumer_queue = chat_consumer_queue or queue.Queue()
        self.max_laps_behind_leader = int(max_laps_behind_leader)
        self.logger.debug(f"cancel: {self.cancel_event}")
        self.logger.debug(f"busy: {self.busy_event}")
        self.logger.debug(f"chat: {self.chat_lock}")
        self.logger.debug(f"broadcast: {self.broadcast_text_queue}")
        self.logger.debug(f"audio: {self.audio_queue}")
        self.logger.debug(f"chat_consumer: {self.chat_consumer_queue}")

    def sleep(self, seconds):
        """
        Sleeps for a specified number of seconds and checks for cancellation.

        Args:
            seconds (float): Number of seconds to sleep.

        Raises:
            KeyboardInterrupt: If the cancel_event is set.
        """
        time.sleep(seconds)
        if self.cancel_event.is_set():
            self.logger.info("Event cancelled.")
            raise KeyboardInterrupt

    def run(
        self,
        cancel_event=None,
        busy_event=None,
        chat_lock=None,
        audio_queue=None,
        broadcast_text_queue=None,
        chat_consumer_queue=None,
    ):
        """
        Runs the event sequence.

        Args:
            cancel_event (threading.Event, optional): Event to signal cancellation. Defaults to None.
            busy_event (threading.Event, optional): Event to signal busy state. Defaults to None.
            chat_lock (threading.Lock, optional): Lock to ensure thread-safe access to chat method. Defaults to None.
            audio_queue (queue.Queue, optional): Queue for audio commands. Defaults to None.
            broadcast_text_queue (queue.Queue, optional): Queue for broadcast text messages. Defaults to None.
            chat_consumer_queue (queue.Queue, optional): Queue for chat consumer messages. Defaults to None.
        """
        self.cancel_event = cancel_event or self.cancel_event
        self.busy_event = busy_event or self.busy_event
        self.chat_lock = chat_lock or self.chat_lock
        self.audio_queue = audio_queue or self.audio_queue
        self.broadcast_text_queue = broadcast_text_queue or self.broadcast_text_queue
        self.chat_consumer_queue = chat_consumer_queue or self.chat_consumer_queue
        try:
            self.event_sequence()
        except Exception as e:
            self.logger.exception("Error in event sequence.")
            self.logger.exception(e)

    def event_sequence(self):
        """
        Defines the sequence of events. Must be implemented by subclasses.

        Raises:
            NotImplementedError: If not implemented by subclass.
        """
        raise NotImplementedError

    @staticmethod
    def ui(ident=""):
        """
        Defines the UI for the event. Must be implemented by subclasses.
        :return:
        """
        raise NotImplementedError

    def _chat(self, message, race_control=False):
        """
        Sends a chat message in the iRacing simulator.
        Uses chat_lock to ensure thread-safe access to the chat functionality.

        Also checks if the message is a DM to the player car (e.g., /123, #123, @123)
        and if so, places it on the chat consumer queue for display in the UI.

        Args:
            message (str): The message to send.
            race_control (bool, optional): Whether the message is from race control. Defaults to False.
        """
        # Check if this is a DM to the player car
        import re

        try:
            # Get player car number
            player_car_idx = self.sdk["PlayerCarIdx"]
            driver = [
                d
                for d in self.sdk["DriverInfo"]["Drivers"]
                if d["CarIdx"] == player_car_idx
            ][0]
            player_car_number = str(driver["CarNumber"])

            # Check if message starts with /123, #123, or @123 (where 123 is the player car number)
            dm_pattern = rf"^[/@#]{player_car_number}\s+(.+)$"
            match = re.match(dm_pattern, message)

            if match:
                # Extract the message content without the prefix
                dm_content = match.group(1)
                # Put it on the chat consumer queue for UI display
                self.chat_consumer_queue.put(dm_content)
                self.logger.debug(
                    f"DM to player car detected, queued for display: {dm_content}"
                )
        except Exception as e:
            # If anything goes wrong with DM detection, just log and continue
            self.logger.debug(f"Error checking for player DM: {e}")

        # Acquire the lock - this will block if another thread holds it
        while not self.chat_lock.acquire(blocking=False):
            self.sleep(0.1)
        try:
            while self.sdk["IsGarageVisible"]:
                self.sleep(1)
            if race_control:
                message = f"/all {message}"
            pyperclip.copy(message)
            self.logger.debug(f"Sending chat message: {message}")
            self.sdk.chat_command(3)
            self.sleep(0.1)
            self.sdk.chat_command(1)
            keys = ["^v"]
            try:
                self.pwa["iRacing.com Simulator"].type_keys("".join(keys))
            except Exception as e:
                self.logger.critical("Error sending chat message.")
                self.logger.critical(e)
            else:
                self.pwa["iRacing.com Simulator"].type_keys("{ENTER}")
            self.sleep(0.1)
        finally:
            # Always release the lock, even if an error occurred
            self.chat_lock.release()

    def wave_and_eol(self, car):
        """
        Waves around a car and sends it to the end of the line.

        Args:
            car (int): The car index.
        """
        driver = [d for d in self.sdk["DriverInfo"]["Drivers"] if d["CarIdx"] == car][0]
        car_number = driver["CarNumber"]
        self.logger.info(f"Waving around car {car_number}")
        self._chat(f"!w {car_number}")
        self._chat(f"!eol {car_number}")

    def wave_around(self, cars):
        """
        Waves around multiple cars.

        Args:
            cars (list): List of car indices.
        """
        for car in cars:
            self.wave_and_eol(car)

    def countdown(self, seconds, message=""):
        """
        Sends countdown messages at specified intervals.

        Args:
            seconds (int): Total countdown time in seconds.
            message (str, optional): Message to send with the countdown. Defaults to ''.
        """
        intervals = [i for i in [30, 20, 10, 5, 3, 2, 1] if i < seconds]
        intervals.insert(0, seconds)
        for interval in intervals:
            self.sleep(seconds - interval)
            self._chat(f"{message} {interval} seconds.", race_control=True)
            seconds = interval

    def throw_caution(self):
        """
        Throws a caution flag in the iRacing simulator.
        """
        self.logger.info("Throwing caution")
        self._chat("!y")

    def close_pits(self, warning_time=None):
        """
        Closes the pits with an optional warning time.

        Args:
            warning_time (int, optional): Time in seconds before closing the pits. Defaults to None.
        """
        self.logger.info("Beginning pit close sequence.")
        if warning_time:
            self.countdown(warning_time, "Pits closing in ")
        self.logger.info("Closing pits.")
        self._chat("!pitclose")

    def get_cars_on_pit_lane(self):
        """
        Gets a list of cars currently on the pit lane.

        Returns:
            list: List of drivers on the pit lane.
        """
        return [
            driver
            for driver in self.sdk["DriverInfo"]["Drivers"]
            if driver["CarIsPaceCar"] != 1
            and self.sdk["CarIdxOnPitRoad"][driver["CarIdx"]]
        ]

    def get_lap_down_cars(self):
        """
        Gets a list of cars that are a lap down.

        Returns:
            list: List of car indices that are a lap down.
        """
        laps_completed = self.sdk["CarIdxLapCompleted"]
        partial_laps = self.sdk["CarIdxLapDistPct"]
        distance_covered = [
            laps_completed[i] + partial_laps[i] for i in range(len(laps_completed))
        ]
        max_distance_covered = max(distance_covered)
        return sorted(
            [
                driver["CarIdx"]
                for driver in self.sdk["DriverInfo"]["Drivers"]
                if driver["CarIsPaceCar"] != 1
                and max_distance_covered - 1
                >= distance_covered[driver["CarIdx"]]
                >= max_distance_covered - self.max_laps_behind_leader - 1
            ],
            key=lambda x: laps_completed[x] + partial_laps[x],
            reverse=True,
        )

    def get_current_running_order(self):
        """
        Gets the current running order of cars.

        Returns:
            list: List of dictionaries representing the running order.
        """
        running_order = [
            {
                "CarIdx": car["CarIdx"],
                "CarNumber": car["CarNumber"],
                "LapCompleted": self.sdk["CarIdxLapCompleted"][car["CarIdx"]],
                "LapDistPct": self.sdk["CarIdxLapDistPct"][car["CarIdx"]],
                "InPits": self.sdk["CarIdxOnPitRoad"][car["CarIdx"]],
                "total_completed": self.sdk["CarIdxLapCompleted"][car["CarIdx"]]
                + self.sdk["CarIdxLapDistPct"][car["CarIdx"]],
                "last_lap_time": self.sdk["CarIdxLastLapTime"][car["CarIdx"]],
                "f2time": self.sdk["CarIdxF2Time"][car["CarIdx"]],
            }
            for car in self.sdk["DriverInfo"]["Drivers"]
            if car["CarIsPaceCar"] != 1
        ]
        running_order.sort(key=lambda x: x["total_completed"], reverse=True)
        return [
            runner
            for runner in running_order
            if runner["total_completed"]
            >= (running_order[0]["total_completed"] - self.max_laps_behind_leader - 1)
        ]

    def get_leader(self):
        """
        Gets the car index of the current leader.

        Returns:
            int: Car index of the leader.
        """
        return self.get_current_running_order()[0]["CarIdx"]

    def wait_for_cars_to_clear_pit_lane(self, max_time=300):
        """
        Waits for cars to clear the pit lane.
        """
        max_time = int(max_time)
        end_time = self.sdk["SessionTimeRemain"] - max_time
        self.logger.debug(
            f"Waiting for cars to clear pit lane with a maximum of {max_time} seconds."
        )
        while (
            any(
                self.sdk["CarIdxLapCompleted"][car["CarIdx"]]
                >= max(self.sdk["CarIdxLapCompleted"]) - self.max_laps_behind_leader
                for car in self.get_cars_on_pit_lane()
            )
            and self.sdk["SessionTimeRemain"] > end_time
        ):
            self.sleep(1)
        self.logger.debug(
            f"Finished waiting for cars to clear pit lane after {end_time + max_time - self.sdk['SessionTimeRemain']} seconds."
        )

    def get_wave_around_cars(self):
        """
        Gets the list of cars eligible for wave around.

        Returns:
            list: List of car indices eligible for wave around.
        """
        lap_down_cars = [
            car
            for car in self.get_lap_down_cars()
            if self.sdk["CarIdxLapCompleted"][car]
            >= max(self.sdk["CarIdxLapCompleted"]) - self.max_laps_behind_leader
        ]
        self.logger.debug(f"Lap down cars: {lap_down_cars}")
        return lap_down_cars

    def is_caution_active(self):
        """
        Checks if a caution flag is active.

        Returns:
            bool: True if a caution flag is active, False otherwise.
        """
        if self.sdk["SessionFlags"] == 0:
            self.logger.debug("Might be a replay")
            return False
        return any(
            self.sdk["SessionFlags"] & x
            for x in [
                irsdk.Flags.caution,
                irsdk.Flags.caution_waving,
                irsdk.Flags.one_lap_to_green,
            ]
        )

    def car_has_new_last_lap_time(self, car, last_step, this_step):
        """
        Checks if a car has a new lap time.

        Args:
            car (dict): The car to check.
            last_step (list): The running order of the last step in time.
            this_step (list): The running order of the current step in time.

        Returns:
            bool: True if the car has a new lap time, False otherwise.
        """
        try:
            last_step_record = [
                record for record in last_step if record["CarIdx"] == car["CarIdx"]
            ][0]
            this_step_record = [
                record for record in this_step if record["CarIdx"] == car["CarIdx"]
            ][0]
            return (
                this_step_record["last_lap_time"] != last_step_record["last_lap_time"]
            )
        except IndexError as e:
            self.logger.error(f"Car {car['CarNumber']} not found in running order.")
            self.logger.error(e)
            return False

    def car_has_completed_lap(self, car, last_step, this_step):
        """
        Checks if a car has completed a lap.

        Args:
            car (dict): The car to check.
            last_step (list): The running order of the last step in time.
            this_step (list): The running order of the current step in time.

        Returns:
            bool: True if the car has completed their lap in the last step, False otherwise.
        """
        try:
            last_step_record = [
                record for record in last_step if record["CarIdx"] == car["CarIdx"]
            ][0]
            this_step_record = [
                record for record in this_step if record["CarIdx"] == car["CarIdx"]
            ][0]
            return (
                this_step_record["LapCompleted"] == last_step_record["LapCompleted"] + 1
            )
        except IndexError as e:
            self.logger.error(f"Car {car['CarNumber']} not found in running order.")
            self.logger.error(e)
            return False

    def car_has_left_pits(self, car, last_step, this_step):
        """
        Checks if a car has left the pits.

        Args:
            car (dict): The car to check.
            last_step (list): The running order of the last step in time.
            this_step (list): The running order of the current step in time.

        Returns:
            bool: True if the car has left the pits in the last step, False otherwise.
        """
        try:
            last_step_record = [
                record for record in last_step if record["CarIdx"] == car["CarIdx"]
            ][0]
            this_step_record = [
                record for record in this_step if record["CarIdx"] == car["CarIdx"]
            ][0]
            return (
                this_step_record["InPits"] == 0
                and last_step_record["InPits"] == 1
                and last_step_record["LapCompleted"] > 0
                and this_step_record["LapCompleted"] > 0
            )
        except IndexError as e:
            self.logger.error(f"Car {car['CarNumber']} not found in running order.")
            self.logger.error(e)
            return False

    def car_has_entered_pits(self, car, last_step, this_step):
        """
        Checks if a car has entered the pits.

        Args:
            car (dict): The car to check.
            last_step (list): The running order of the last step in time.
            this_step (list): The running order of the current step in time.

        Returns:
            bool: True if the car has entered the pits in the last step, False otherwise.
        """
        try:
            last_step_record = [
                record for record in last_step if record["CarIdx"] == car["CarIdx"]
            ][0]
            this_step_record = [
                record for record in this_step if record["CarIdx"] == car["CarIdx"]
            ][0]
            return (
                this_step_record["InPits"] == 1
                and last_step_record["InPits"] == 0
                and last_step_record["LapCompleted"] > 0
                and this_step_record["LapCompleted"] > 0
            )
        except IndexError as e:
            self.logger.error(f"Car {car['CarNumber']} not found in running order.")
            self.logger.error(e)
            return False

    def monitor_speed(self, carIdx):
        """
        Yields the speed of a car.

        Args:
            carIdx (int): The car index to monitor.
        """
        carIdx = int(carIdx)
        speeds = {
            "speed": 0,
            "last_location": self.sdk["CarIdxLapDistPct"][carIdx],
            "last_time": self.sdk["SessionTime"],
        }
        while True:
            try:
                distance_in_lap = (
                    1 + self.sdk["CarIdxLapDistPct"][carIdx] - speeds["last_location"]
                ) % 1
                time_elapsed = self.sdk["SessionTime"] - speeds["last_time"]
                km_per_lap = float(
                    str(self.sdk["WeekendInfo"]["TrackLength"]).replace(" km", "")
                )
                seconds_per_hour = 3600
                speed = distance_in_lap / time_elapsed * km_per_lap * seconds_per_hour
                speeds = {
                    "speed": speed,
                    "last_location": self.sdk["CarIdxLapDistPct"][carIdx],
                    "last_time": self.sdk["SessionTime"],
                }
                yield speeds["speed"]
            except ZeroDivisionError:
                self.logger.error("Zero division error in speed calculation.")
                yield 0

    def multi_lane_restart(
        self,
        order: list[int],
        lanes: int = 2,
        lane_names: list[str] = ["Left", "Right"],
        restart_flag: threading.Event = threading.Event(),
        reminder_frequency: int = 10,
    ):
        # make sure the lists are the same length
        if len(lane_names) != lanes:
            raise ValueError("The number of lane names must match the number of lanes")
        # split the order into lanes
        lane_order = [order[i::lanes] for i in range(lanes)]
        # send the cars to their lanes
        for i, lane in enumerate(lane_order):
            for car in lane:
                car_ahead = lane[lane.index(car) - 1] if lane.index(car) > 0 else None
                message = f"/{car} line up in the {str(lane_names[i]).upper()} lane"
                if car_ahead:
                    message += f" behind the #{car_ahead}"
                self._chat(message)

        # make sure everyone stays in position
        last_reminder = self.sdk["SessionTime"]
        last_longer_reminder = self.sdk["SessionTime"]
        while not restart_flag.is_set():
            out_of_position = []
            current_order = [c["CarNumber"] for c in self.get_current_running_order()]
            for i, lane in enumerate(lane_order):
                for car in lane:
                    cars_incorrectly_behind = [
                        c
                        for c in current_order[current_order.index(car) :]  # is behind
                        if c in lane[: lane.index(car)]  # should be in front
                    ]
                    if cars_incorrectly_behind:
                        out_of_position.append((car, cars_incorrectly_behind))

            if self.sdk["SessionTime"] - last_reminder > reminder_frequency:
                for car, cars in out_of_position:
                    self._chat(f"/{car} let the #{', '.join(cars)} by.")
                    for c in cars:
                        self._chat(f"/{c} pass the #{car}.")
                last_reminder = self.sdk["SessionTime"]

            if self.sdk["SessionTime"] - last_longer_reminder > reminder_frequency * 3:
                # remind cars what lane they're in
                for i, lane in enumerate(lane_order):
                    for car in lane:
                        self._chat(f"/{car} {str(lane_names[i]).upper()} lane.")
                last_longer_reminder = self.sdk["SessionTime"]

        return lane_order

    def get_car_class(self, carIdx=None, car_number=None):
        if carIdx is None:
            carIdx = [
                car["CarIdx"]
                for car in self.sdk["DriverInfo"]["Drivers"]
                if car["CarNumber"] == car_number
            ][0]
        car_class = self.sdk["CarIdxClass"][carIdx]
        return car_class

    def get_fastest_lap_for_class(self, car_class):
        classes = self.sdk["CarIdxClass"]
        best_laps = self.sdk["CarIdxBestLapTime"]
        best_lap = None
        for i, c in enumerate(classes):
            if c == car_class:
                if best_lap is None or best_laps[i] < best_lap:
                    best_lap = best_laps[i]
        return best_lap

    def intermittent_boolean_generator(self, n: int = 1):
        """
        A generator that yields True every n seconds and False otherwise.
        :return:
        """
        last_true = self.sdk["SessionTime"]
        while True:
            if self.sdk["SessionTime"] - last_true > n:
                yield True
                last_true = self.sdk["SessionTime"]
            else:
                yield False

    def driver_4x_generator(self, window: int = 10):
        # Initialize tracking variables
        driver_incidents_df = DataFrame(
            data=[], columns=["timestamp", "car_number", "incidents"]
        )

        this_step = self.get_current_running_order()
        cars_taken_checkers = []
        while True:
            y = []
            # Freeze the SDK buffer to get a consistent view of the data
            self.sdk.freeze_var_buffer_latest()
            last_step = this_step
            this_step = self.get_current_running_order()

            # Get current timestamp
            current_time = time.time()

            # The SDK allows dictionary-like access
            driver_info = self.sdk["DriverInfo"]
            drivers = driver_info["Drivers"]

            # Process each driver
            for driver in drivers:
                if self.sdk["SessionState"] == 5:
                    c = [c for c in this_step if c["CarNumber"] == driver["CarNumber"]]
                    if c:
                        c = c[0]
                        if (
                            self.car_has_completed_lap(c, last_step, this_step)
                            and driver["CarNumber"] not in cars_taken_checkers
                        ):
                            self.logger.debug(
                                f"Car {driver['CarNumber']} Checkered Flag"
                            )
                            cars_taken_checkers.append(driver["CarNumber"])
                        if driver["CarNumber"] in cars_taken_checkers:
                            continue

                car_number = driver["CarNumber"]
                incident_count = driver["TeamIncidentCount"]

                # Add the current incident count to the dataframe
                new_row = DataFrame(
                    {
                        "timestamp": [current_time],
                        "car_number": [car_number],
                        "incidents": [incident_count],
                    }
                )
                # Append to dataframe (using pandas v1.x style)
                driver_incidents_df = concat(
                    [driver_incidents_df, new_row], ignore_index=True
                )

            # Remove old data outside the tracking window
            cutoff_time = current_time - window
            driver_incidents_df = driver_incidents_df[
                driver_incidents_df["timestamp"] >= cutoff_time
            ]

            # Process the data for collisions
            # Get unique car numbers in the current data
            car_numbers = list(set(driver_incidents_df["car_number"]))

            for car_number in car_numbers:
                # Get incidents for this car within the tracking window
                car_data = driver_incidents_df[
                    driver_incidents_df["car_number"] == car_number
                ]

                if len(car_data) < 2:
                    continue  # Need at least two data points to check for a spread

                # Calculate the incident spread
                min_incidents = car_data["incidents"].min()
                max_incidents = car_data["incidents"].max()
                incident_spread = max_incidents - min_incidents

                # If the spread exceeds the threshold, count it as a collision
                if incident_spread >= 4:
                    # Clear the data for this car to prevent counting the same collision multiple times
                    driver_incidents_df = driver_incidents_df[
                        driver_incidents_df["car_number"] != car_number
                    ]
                    # Log the collision
                    self.logger.info(f"Collision detected for car #{car_number}.")

                    y.append(car_number)

            # Release the SDK buffer
            self.sdk.unfreeze_var_buffer_latest()
            yield y
