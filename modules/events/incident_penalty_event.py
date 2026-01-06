from modules.events import BaseEvent


class IncidentPenaltyEvent(BaseEvent):
    """
    An event which penalizes the driver for incidents.
    """

    def __init__(
        self,
        initial_penalty_incidents: int = 0,
        recurring_peanlty_every_incidents: int = 0,
        end_recurring_incidents: int = 0,
        initial_penalty: str = "",
        recurring_penalty: str = "",
        end_recurring_penalty: str = "",
        sound: bool = False,
    ):
        self.initial_penalty = initial_penalty
        self.recurring_penalty = recurring_penalty
        self.end_recurring_penalty = end_recurring_penalty
        self.initial_penalty_incidents = initial_penalty_incidents
        self.recurring_penalty_incidents = recurring_peanlty_every_incidents
        self.end_recurring_incidents = end_recurring_incidents
        self.sound = sound
        if not (
            self.initial_penalty_incidents
            or self.recurring_penalty_incidents
            or self.end_recurring_incidents
        ):
            raise ValueError("You must set at least one of the penalty incidents")
        if self.initial_penalty_incidents and not self.initial_penalty:
            raise ValueError("You must set the initial penalty")
        if self.recurring_penalty_incidents and not self.recurring_penalty:
            raise ValueError("You must set the recurring penalty")
        super().__init__()

    def event_sequence(self):
        """
        Applies penalties to any driver who has more than the specified number of incidents.
        """
        self.sdk.freeze_var_buffer_latest()
        this_step = self.sdk["DriverInfo"]["Drivers"]
        this_driver_positions = self.get_current_running_order()
        cars_taken_checkers = []
        while True:
            self.sdk.freeze_var_buffer_latest()
            last_step = this_step
            this_step = self.sdk["DriverInfo"]["Drivers"]
            last_driver_positions = this_driver_positions
            this_driver_positions = self.get_current_running_order()
            for car in this_step:
                try:
                    if self.sdk["SessionState"] == 5:
                        c = [
                            c
                            for c in this_driver_positions
                            if c["CarNumber"] == car["CarNumber"]
                        ]
                        if c:
                            c = c[0]
                            if (
                                self.car_has_completed_lap(
                                    c, last_driver_positions, this_driver_positions
                                )
                                and car["CarNumber"] not in cars_taken_checkers
                            ):
                                self.logger.debug(
                                    f"Car {car['CarNumber']} Checkered Flag"
                                )
                                cars_taken_checkers.append(car["CarNumber"])
                            if car["CarNumber"] in cars_taken_checkers:
                                continue
                except Exception as e:
                    self.logger.exception(f"Error in post race detection: {e}")

                car_no = car["CarNumber"]
                try:
                    prev_inc = [x for x in last_step if x["CarNumber"] == car_no][0][
                        "TeamIncidentCount"
                    ]
                except IndexError:
                    self.logger.debug(f"Car {car_no} not found in last step")
                    continue
                this_inc = car["TeamIncidentCount"]
                if this_inc > prev_inc:
                    self.logger.debug(f"Car {car_no} has {this_inc} incidents")
                if (
                    self.initial_penalty_incidents
                    and prev_inc < self.initial_penalty_incidents <= this_inc
                ):
                    self.penalize(
                        car_no, self.initial_penalty, self.initial_penalty_incidents
                    )
                    continue
                if (
                    self.recurring_penalty_incidents
                    and (this_inc > prev_inc)
                    and (
                        (this_inc - self.initial_penalty_incidents)
                        % self.recurring_penalty_incidents
                        <= (prev_inc - self.initial_penalty_incidents)
                        % self.recurring_penalty_incidents
                    )
                    and (
                        self.end_recurring_incidents == 0
                        or this_inc < self.end_recurring_incidents
                    )
                    and (this_inc > self.initial_penalty_incidents)
                ):
                    n = (
                        this_inc - self.initial_penalty_incidents
                    ) // self.recurring_penalty_incidents
                    x = self.initial_penalty_incidents + (
                        n * self.recurring_penalty_incidents
                    )
                    self.penalize(car_no, self.recurring_penalty, x)
                    continue

                if (
                    self.end_recurring_incidents
                    and this_inc >= self.end_recurring_incidents > prev_inc
                ):
                    self.penalize(
                        car_no, self.end_recurring_penalty, self.end_recurring_incidents
                    )
            self.sdk.unfreeze_var_buffer_latest()
            self.sleep(5)

    def penalize(self, car_no, penalty, threshold):
        self._chat(f"!bl {car_no} {penalty} ({threshold}x)")
        if self.sound:
            self.audio_queue.put("penalty")
        penalty = "Drive Through" if penalty == "d" else f"{penalty}s Hold"
        self.broadcast_text_queue.put(
            {
                "title": "Race Control",
                "text": f"Car #{car_no} - {penalty} - {threshold}x Incident Limit",
            }
        )
