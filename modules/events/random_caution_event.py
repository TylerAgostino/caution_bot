from modules.events.random_timed_event import RandomTimedEvent

class RandomCautionEvent(RandomTimedEvent):
    """
    A class to represent a random caution event in the iRacing simulator.

    Attributes:
        pit_close_advance_warning (int): Advance warning time before pits close.
        pit_close_max_duration (int): Maximum duration for pits to be closed.
        wave_arounds (bool): Flag to indicate if wave arounds are allowed.
        notify_on_skipped_caution (bool): Flag to indicate if notifications should be sent when a caution is skipped.
    """

    def __init__(self, pit_close_advance_warning=5, pit_close_max_duration=90, wave_arounds=True, notify_on_skipped_caution=False, full_sequence=True, *args, **kwargs):
        """
        Initializes the RandomCaution class.

        Args:
            pit_close_advance_warning (int, optional): Advance warning time before pits close. Defaults to 5.
            pit_close_max_duration (int, optional): Maximum duration for pits to be closed. Defaults to 90.
            wave_arounds (bool, optional): Flag to indicate if wave arounds are allowed. Defaults to True.
            notify_on_skipped_caution (bool, optional): Flag to indicate if notifications should be sent when a caution is skipped. Defaults to False.
        """
        self.pit_close_advance_warning = int(pit_close_advance_warning)
        self.pit_close_max_duration = int(pit_close_max_duration)
        self.wave_arounds = wave_arounds
        self.notify_on_skipped_caution = notify_on_skipped_caution
        self.full_sequence = full_sequence
        super().__init__(*args, **kwargs)

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
        if self.full_sequence:
            self.close_pits(self.pit_close_advance_warning)
            self.wait_for_cars_to_clear_pit_lane(self.pit_close_max_duration)
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

            current_positions = self.get_wave_around_cars()

            last_step = self.get_current_running_order()

            while current_positions:
                this_step = self.get_current_running_order()
                for car in current_positions:
                    args = [{'CarIdx': car}, last_step, this_step]
                    if int(hex(self.sdk['CarIdxPaceFlags'][car])[-1]) >= 4:
                        current_positions.pop(current_positions.index(car))
                    if self.car_has_completed_lap(*args) or self.car_has_left_pits(*args):
                        if self.sdk['CarIdxOnPitRoad'][car]:
                            self.logger.debug(f'{car} is on pit road.')
                            continue
                        self.wave_and_eol(car)
                last_step = this_step
                self.sleep(1)

            self.logger.info('Wave arounds complete.')

        while self.is_caution_active():
            self.sleep(1)

        self.logger.debug('Caution has ended.')

        self.busy_event.clear()