from modules.events import BaseEvent
import pandas as pd
import time
import threading
import queue
import irsdk


class CollisionPenaltyEvent(BaseEvent):
    """
    An event which monitors driver incidents over time and penalizes drivers for
    collision patterns.

    This event continuously tracks the incident count for each driver and maintains
    a rolling window of data for the last 10 seconds. If there is more than a 4 incident
    spread for a driver in that window, a collision is recorded. After a specified
    number of collisions, a penalty is applied.
    """

    def __init__(
        self,
        collisions_per_penalty: int = 3,
        penalty: str = "d",
        tracking_window_seconds: int = 10,
        incident_threshold: int = 4,
        sdk=irsdk.IRSDK(),
        pwa=None,
        cancel_event=threading.Event(),
        busy_event=threading.Event(),
        audio_queue=queue.Queue(),
        broadcast_text_queue=queue.Queue(),
        max_laps_behind_leader=99,
    ):
        """
        Initialize the CollisionPenaltyEvent class.

        Args:
            collisions_per_penalty (int, optional): Number of collisions before applying a penalty. Defaults to 3.
            penalty (str, optional): The penalty to apply. Defaults to 'd' (drive through).
            tracking_window_seconds (int, optional): The time window in seconds to track incidents. Defaults to 10.
            incident_threshold (int, optional): The incident spread threshold to count as a collision. Defaults to 4.
        """
        self.collisions_per_penalty = collisions_per_penalty
        self.penalty = penalty
        self.tracking_window_seconds = tracking_window_seconds
        self.incident_threshold = incident_threshold

        # Initialize dataframes and tracking variables
        self.driver_incidents_df = pd.DataFrame()
        self.driver_collision_counts = {}

        super().__init__(
            sdk=sdk,
            pwa=pwa,
            cancel_event=cancel_event,
            busy_event=busy_event,
            audio_queue=audio_queue,
            broadcast_text_queue=broadcast_text_queue,
            max_laps_behind_leader=max_laps_behind_leader,
        )

    @staticmethod
    def ui(ident=""):
        """
        UI for the CollisionPenaltyEvent.
        """
        import streamlit as st  # Import here to avoid circular imports

        col1, col2, col3, col4 = st.columns([1, 1, 1, 1])
        return {
            "collisions_per_penalty": col1.number_input(
                "Collisions Per Penalty",
                value=3,
                min_value=1,
                key=f"{ident}collisions_per_penalty",
            ),
            "penalty": col2.text_input("Penalty", key=f"{ident}penalty", value="d"),
            "tracking_window_seconds": col1.number_input(
                "Tracking Window (seconds)",
                value=10,
                min_value=1,
                key=f"{ident}tracking_window_seconds",
            ),
            "incident_threshold": col2.number_input(
                "Incident Threshold",
                value=4,
                min_value=1,
                key=f"{ident}incident_threshold",
            ),
        }

    def event_sequence(self):
        """
        Monitors incidents over time and applies penalties when collisions are detected.
        """
        self.logger.info("Starting collision monitoring")

        # Initialize tracking variables
        self.driver_incidents_df = pd.DataFrame(
            data=[], columns=["timestamp", "car_number", "incidents"]
        )
        self.driver_collision_counts = {}

        this_step = self.get_current_running_order()
        cars_taken_checkers = []

        while not self.cancel_event.is_set():
            try:
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
                        c = [
                            c
                            for c in this_step
                            if c["CarNumber"] == driver["CarNumber"]
                        ]
                        if c:
                            c = c[0]
                            if (
                                self.car_has_completed_lap(c, last_step, this_step)
                                and driver["CarNumber"] not in cars_taken_checkers
                            ):
                                self.logger.debug(
                                    f'Car {driver["CarNumber"]} Checkered Flag'
                                )
                                cars_taken_checkers.append(driver["CarNumber"])
                            if driver["CarNumber"] in cars_taken_checkers:
                                continue

                    car_number = driver["CarNumber"]
                    incident_count = driver["TeamIncidentCount"]

                    # Add the current incident count to the dataframe
                    new_row = pd.DataFrame(
                        {
                            "timestamp": [current_time],
                            "car_number": [car_number],
                            "incidents": [incident_count],
                        }
                    )
                    # Append to dataframe (using pandas v1.x style)
                    self.driver_incidents_df = pd.concat(
                        [self.driver_incidents_df, new_row], ignore_index=True
                    )

                # Remove old data outside the tracking window
                cutoff_time = current_time - self.tracking_window_seconds
                self.driver_incidents_df = self.driver_incidents_df[
                    self.driver_incidents_df["timestamp"] >= cutoff_time
                ]

                # Process the data for collisions
                self.check_for_collisions()

                # Release the SDK buffer
                self.sdk.unfreeze_var_buffer_latest()

                # Log the current state periodically
                if current_time % 60 < 1:  # Log approximately once every minute
                    self.logger.debug(
                        f"Current collision counts: {self.driver_collision_counts}"
                    )

                # Wait a short time before the next check
                self.sleep(0.5)

            except Exception as e:
                self.logger.exception(f"Error in collision monitoring: {e}")
                self.sleep(5)  # Sleep longer after an error

    def check_for_collisions(self):
        """
        Check the incident data for each driver to detect collisions.
        """
        # Get unique car numbers in the current data
        car_numbers = list(set(self.driver_incidents_df["car_number"]))

        for car_number in car_numbers:
            # Get incidents for this car within the tracking window
            car_data = self.driver_incidents_df[
                self.driver_incidents_df["car_number"] == car_number
            ]

            if len(car_data) < 2:
                continue  # Need at least two data points to check for a spread

            # Calculate the incident spread
            min_incidents = car_data["incidents"].min()
            max_incidents = car_data["incidents"].max()
            incident_spread = max_incidents - min_incidents

            # If the spread exceeds the threshold, count it as a collision
            if incident_spread >= self.incident_threshold:
                # Update collision count for this driver
                if car_number not in self.driver_collision_counts:
                    self.driver_collision_counts[car_number] = 0

                # Add a collision
                self.driver_collision_counts[car_number] += 1
                collision_count = self.driver_collision_counts[car_number]
                # Log the collision
                self.logger.info(
                    f"Collision detected for car #{car_number}. Total: {collision_count}"
                )

                self.taunt(car_number, collision_count)

                # Check if penalty should be applied
                if collision_count % self.collisions_per_penalty == 0:
                    self.apply_penalty(car_number, collision_count)

                # Clear the data for this car to prevent counting the same collision multiple times
                self.driver_incidents_df = self.driver_incidents_df[
                    self.driver_incidents_df["car_number"] != car_number
                ]

    def apply_penalty(self, car_number, collision_count):
        """
        Applies the configured penalty to the specified car number.
        Args:
            car_number (str): The car number to penalize
            collision_count (int): The current collision count
        """

        self.logger.info(
            f"Applying penalty to car #{car_number} after {collision_count} collisions"
        )

        # Send the penalty command to the race
        self._chat(f"!bl {car_number} {self.penalty} ({collision_count} collisions)")

        # Format the penalty message for broadcast
        penalty_text = (
            "Drive Through" if self.penalty == "d" else f"{self.penalty}s Hold"
        )

        # Send message to broadcast queue
        self.broadcast_text_queue.put(
            {
                "title": "Race Control",
                "text": f"Car #{car_number} - {penalty_text} - {collision_count} Collisions",
            }
        )

    def taunt(self, car_number, collision_count):
        """
        Reminds a driver how many collisions they've had.

        Args:
            car_number (str): The car number to penalize
            collision_count (int): The current collision count
        """
        next_penalty_threshold = (
            (collision_count // self.collisions_per_penalty) + 1
        ) * self.collisions_per_penalty

        options = [
            "Way to go, bozo!",
            "Smooth. Real subtle. Nobody saw that.",
            "Don’t worry, insurance will totally cover that.",
            "What a gentle love tap. True sportsmanship.",
            "Wow, didn’t know demolition derby was part of the schedule.",
            "Well, at least you aimed at something.",
            "Subtle as a sledgehammer, my guy.",
            "Elegant. Graceful. Catastrophic.",
            "Real NASCAR highlight reel material right there.",
            "Look at you, single-handedly funding the body shop industry.",
            "Well, you sure made an impression — literally.",
        ]
        random_option = options[
            hash(car_number + str(collision_count) + str(time.time())) % len(options)
        ]
        self._chat(
            f"/{car_number} {random_option} ({collision_count}/{next_penalty_threshold} collisions)"
        )
