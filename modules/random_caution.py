from modules.random_timed_event import RandomTimedEvent
import time
import logging


class RandomCaution(RandomTimedEvent):
    def __init__(self,
                 pit_close_advance_warning: int = 5,
                 pit_close_max_duration: int = 90,
                 max_laps_behind_leader: int = 3,
                 wave_arounds: bool = True,
                 notify_on_skipped_caution: bool = False,
                 frequency: int = 1,
                 likelihood: int = 100,
                 minimum: int = 0,
                 *args, **kwargs):
        self.pit_close_advance_warning = int(pit_close_advance_warning)
        self.pit_close_max_duration = int(pit_close_max_duration)
        self.max_laps_behind_leader = int(max_laps_behind_leader)
        self.wave_arounds = wave_arounds
        self.notify_on_skipped_caution = notify_on_skipped_caution
        super().__init__(*args, **kwargs)

    def is_caution_active(self):
        return hex(self.sdk['SessionFlags'])[-4] in ['4', '8']

    def wait_for_cars_to_clear_pit_lane(self):
        wait = True
        self.logger.debug('Waiting for cars to clear pit lane.')
        while wait:
            cars_on_pit_lane = self.get_cars_on_pit_lane()
            awaiting_cars = [car for car in cars_on_pit_lane if self.sdk['CarIdxLapCompleted'][car['CarIdx']] >=
                             max(self.sdk['CarIdxLapCompleted']) - self.max_laps_behind_leader]
            if not awaiting_cars:
                wait = False
            else:
                self.sleep(1)
        self.logger.debug('Cars have cleared pit lane.')

    def get_wave_around_cars(self):
        lap_down_cars = [car for car in self.get_lap_down_cars() if self.sdk['CarIdxLapCompleted'][car] >=
                         max(self.sdk['CarIdxLapCompleted']) - self.max_laps_behind_leader]
        self.logger.debug(f'Lap down cars: {lap_down_cars}')
        return lap_down_cars

    def event_sequence(self):
        if self.is_caution_active():
            self.logger.debug('Additional caution skipped due to active caution.')
            if self.notify_on_skipped_caution:
                self._chat('Additional caution skipped due to active caution.')
            return

        self.close_pits(self.pit_close_advance_warning)

        self.wait_for_cars_to_clear_pit_lane()

        self.throw_caution()

        wave_around_cars = self.get_wave_around_cars()
        if self.wave_arounds:

            # Wait to give wave arounds
            pace_car = [driver for driver in self.sdk['DriverInfo']['Drivers'] if driver['CarIsPaceCar'] == 1][0]['CarIdx']
            # see what lap the pace car is starting out on
            initial_lap = self.sdk['CarIdxLapCompleted'][pace_car]
            self.logger.debug(f'Pace car starting on lap {initial_lap}')

            # first wait for the pace car to get around 40% of the track, so we know it's left the pit exit and
            # our lap counter is _somewhat_ reliable.
            while self.sdk['CarIdxLapDistPct'][pace_car] > 0.5 or self.sdk['CarIdxLapDistPct'][pace_car] < 0.4:
                self.sleep(1)

            # wait for the pace car to complete the lap
            while self.sdk['CarIdxLapCompleted'][pace_car] < 0:
                self.sleep(1)
            self.logger.debug('Pace car has completed a lap.')

            current_positions = {}
            for car in wave_around_cars:
                current_positions[car] = self.sdk['CarIdxLapDistPct'][car]

            while current_positions:
                for car in wave_around_cars:
                    # if they've already got a wave, remove them from the list
                    if int(hex(self.sdk['CarIdxPaceFlags'][car])[-1]) >= 4:
                        try:
                            del current_positions[car]
                        except KeyError:
                            pass
                        continue

                    # if they're in pits, wait for them to come out
                    if self.sdk['CarIdxOnPitRoad'][car] or self.sdk['CarIdxPaceLine'][car] == -1:
                        current_positions[car] = 0.99
                        continue

                    # if they've completed a lap, wave them around
                    if self.sdk['CarIdxLapDistPct'][car] < current_positions[car]:
                        self.wave_and_eol(car)

                self.sleep(1)

        while self.is_caution_active():
            self.sleep(1)


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--pit_close_advance_warning', type=int, default=5)
    parser.add_argument('--pit_close_max_duration', type=int, default=90)
    parser.add_argument('--max_laps_behind_leader', type=int, default=3)
    parser.add_argument('--wave_arounds', action='store_true')
    parser.add_argument('--notify_on_skipped_caution', action='store_true')
    args = parser.parse_args()
    sc = RandomCaution(**vars(args))
    sc.run()