import queue
import threading
import time

import irsdk
import pandas as pd

from modules.events import BaseEvent


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
        sdk=None,
        pwa=None,
        max_laps_behind_leader=99,
    ):
        """
        Initialize the CollisionPenaltyEvent class.

        Args:
            collisions_per_penalty (int, optional): Number of collisions before applying a penalty. Defaults to 3.
            penalty (str, optional): The penalty to apply. Defaults to 'd' (drive through).
            tracking_window_seconds (int, optional): The time window in seconds to track incidents. Defaults to 10.
        """
        self.collisions_per_penalty = collisions_per_penalty
        self.penalty = penalty
        self.tracking_window_seconds = tracking_window_seconds

        self.driver_collision_counts = {}

        super().__init__(
            sdk=sdk or irsdk.IRSDK(),
            pwa=pwa,
            max_laps_behind_leader=max_laps_behind_leader,
        )

    def event_sequence(self):
        """
        Monitors incidents over time and applies penalties when collisions are detected.
        """
        self.logger.info("Starting collision monitoring")

        self.driver_collision_counts = {}

        iterator = self.driver_4x_generator(self.tracking_window_seconds)

        while not self.cancel_event.is_set():
            try:
                cars = iterator.__next__()
                for car in cars:
                    if car not in self.driver_collision_counts:
                        self.driver_collision_counts[car] = 0
                    # Add a collision
                    self.driver_collision_counts[car] += 1
                    collision_count = self.driver_collision_counts[car]
                    # Log the collision
                    self.logger.info(
                        f"Collision detected for car #{car}. Total: {collision_count}"
                    )

                    # Check if penalty should be applied
                    if collision_count % self.collisions_per_penalty == 0:
                        self.apply_penalty(car, collision_count)
                    else:
                        self.taunt(car, collision_count)

                if cars:
                    self.audio_queue.put("quack")
                self.sleep(1)

            except Exception as e:
                self.logger.exception(f"Error in collision monitoring: {e}")
                self.sleep(5)  # Sleep longer after an error

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

        self.audio_queue.put("penalty")

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

        self._chat(
            f"/{car_number} {collision_count}/{next_penalty_threshold} collisions before penalty."
        )
