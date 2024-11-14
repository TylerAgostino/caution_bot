from modules.random_timed_event import RandomTimedEvent

class RandomCaution(RandomTimedEvent):
    """
    A class to represent a random caution event in the iRacing simulator.

    Attributes:
        pit_close_advance_warning (int): Advance warning time before pits close.
        pit_close_max_duration (int): Maximum duration for pits to be closed.
        max_laps_behind_leader (int): Maximum laps a car can be behind the leader.
        wave_arounds (bool): Flag to indicate if wave arounds are allowed.
        notify_on_skipped_caution (bool): Flag to indicate if notifications should be sent when a caution is skipped.
    """

    def __init__(self, pit_close_advance_warning=5, pit_close_max_duration=90, max_laps_behind_leader=3, wave_arounds=True, notify_on_skipped_caution=False, *args, **kwargs):
        """
        Initializes the RandomCaution class.

        Args:
            pit_close_advance_warning (int, optional): Advance warning time before pits close. Defaults to 5.
            pit_close_max_duration (int, optional): Maximum duration for pits to be closed. Defaults to 90.
            max_laps_behind_leader (int, optional): Maximum laps a car can be behind the leader. Defaults to 3.
            wave_arounds (bool, optional): Flag to indicate if wave arounds are allowed. Defaults to True.
            notify_on_skipped_caution (bool, optional): Flag to indicate if notifications should be sent when a caution is skipped. Defaults to False.
        """
        self.pit_close_advance_warning = int(pit_close_advance_warning)
        self.pit_close_max_duration = int(pit_close_max_duration)
        self.max_laps_behind_leader = int(max_laps_behind_leader)
        self.wave_arounds = wave_arounds
        self.notify_on_skipped_caution = notify_on_skipped_caution
        super().__init__(*args, **kwargs)

    def wait_for_cars_to_clear_pit_lane(self):
        """
        Waits for cars to clear the pit lane.
        """
        self.logger.debug('Waiting for cars to clear pit lane.')
        while any(self.sdk['CarIdxLapCompleted'][car['CarIdx']] >= max(self.sdk['CarIdxLapCompleted']) - self.max_laps_behind_leader for car in self.get_cars_on_pit_lane()):
            self.sleep(1)
        self.logger.debug('Cars have cleared pit lane.')

    def get_wave_around_cars(self):
        """
        Gets the list of cars eligible for wave around.

        Returns:
            list: List of car indices eligible for wave around.
        """
        lap_down_cars = [car for car in self.get_lap_down_cars() if self.sdk['CarIdxLapCompleted'][car] >= max(self.sdk['CarIdxLapCompleted']) - self.max_laps_behind_leader]
        self.logger.debug(f'Lap down cars: {lap_down_cars}')
        return lap_down_cars

    def event_sequence(self):
        """
        Executes the event sequence for a random caution.
        """
        if self.is_caution_active() or self.busy_event.is_set():
            self.logger.debug('Additional caution skipped due to active caution.')
            if self.notify_on_skipped_caution:
                self._chat('Additional caution skipped due to active caution.')
            return

        self.busy_event.set()
        self.close_pits(self.pit_close_advance_warning)
        self.wait_for_cars_to_clear_pit_lane()
        self.throw_caution()

        if self.wave_arounds:
            pace_car = next(driver for driver in self.sdk['DriverInfo']['Drivers'] if driver['CarIsPaceCar'] == 1)['CarIdx']
            initial_lap = self.sdk['CarIdxLapCompleted'][pace_car]
            self.logger.debug(f'Pace car starting on lap {initial_lap}')

            while not (0.4 <= self.sdk['CarIdxLapDistPct'][pace_car] <= 0.5):
                self.sleep(1)

            while self.sdk['CarIdxLapCompleted'][pace_car] < initial_lap + 1:
                self.sleep(1)
            self.logger.debug('Pace car has completed a lap.')

            current_positions = {car: self.sdk['CarIdxLapDistPct'][car] for car in self.get_wave_around_cars()}

            while current_positions:
                for car in list(current_positions):
                    if int(hex(self.sdk['CarIdxPaceFlags'][car])[-1]) >= 4:
                        current_positions.pop(car, None)
                    elif self.sdk['CarIdxOnPitRoad'][car] or self.sdk['CarIdxPaceLine'][car] == -1:
                        current_positions[car] = 0.99
                    elif self.sdk['CarIdxLapDistPct'][car] < current_positions[car]:
                        self.wave_and_eol(car)
                        current_positions.pop(car, None)
                self.sleep(1)

        while self.is_caution_active():
            self.sleep(1)

        self.busy_event.clear()