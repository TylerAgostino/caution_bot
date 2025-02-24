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

    def __init__(self, pit_close_advance_warning=5, pit_close_max_duration=90, wave_arounds=True, pre_extend_laps = 1,
                 notify_on_skipped_caution=False, full_sequence=True, wave_around_lap = 1,  extend_laps = 0,
                 *args, **kwargs):
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
        self.wave_around_lap = int(wave_around_lap)
        self.extend_laps = int(extend_laps)
        self.pre_extend_laps = int(pre_extend_laps)
        super().__init__(*args, **kwargs)

    @staticmethod
    def ui(ident = ''):
        import streamlit as st
        col1, col2, col3, col4, col5 = st.columns(5)
        return {
            'window_start': col1.text_input("Window Start (min/lap)", "5", key=f'{ident}window_start'),
            'window_end': col2.text_input("Window End (min/lap)", "10", key=f'{ident}window_end'),
            'pit_close_advance_warning': col1.number_input(f'Pit Close Advance Warning', key=f'{ident}pit_close_advance_warning', min_value=0, max_value=30, value=5),
            'pit_close_max_duration': col2.number_input(f'Pit Close Max Duration', key=f'{ident}pit_close_max_duration', min_value=0, max_value=300, value=90),
            'max_laps_behind_leader': col3.number_input(f'Max Laps Behind Leader', key=f'{ident}max_laps_behind_leader', min_value=0, value=0),
            'wave_arounds': col3.checkbox(f'Wave Arounds', key=f'{ident}wave_arounds', value=True),
            'notify_on_skipped_caution': col4.checkbox(f'Notify on Skipped Caution', key=f'{ident}notify_on_skipped_caution', value=False),
            'full_sequence': col5.checkbox(f'Full Pit Close Sequence', key=f'{ident}full_sequence', value=True),
            'wave_around_lap': col1.number_input(f'Wave Around Lap', key=f'{ident}wave_around_lap', min_value=1, value=1),
            'extend_laps': col2.number_input(f'Extend Laps', key=f'{ident}extend_laps', min_value=0, value=0),
            'pre_extend_laps': col3.number_input(f'Pre-Extend Laps', key=f'{ident}pre_extend_laps', min_value=0, value=1),
            'likelihood': col5.text_input(f'Likelihood (%)', key=f'{ident}likelihood', value='100')
        }


    def event_sequence(self):
        """
        Executes the event sequence for a random caution.
        """
        if self.is_caution_active() or self.busy_event.is_set():
            self.logger.debug('Additional caution skipped due to active caution.')
            if self.notify_on_skipped_caution:
                import random
                self.sleep(random.randint(1, 5))
                self._chat('Additional caution skipped due to active caution.')
            return

        self.busy_event.set()
        if self.full_sequence:
            self.close_pits(self.pit_close_advance_warning)
            self.wait_for_cars_to_clear_pit_lane(self.pit_close_max_duration)
        self.throw_caution()
        self.audio_queue.put('caution')

        pace_car = next(driver for driver in self.sdk['DriverInfo']['Drivers'] if driver['CarIsPaceCar'] == 1)['CarIdx']

        def await_pace_car_lap():
            while not (0.4 <= self.sdk['CarIdxLapDistPct'][pace_car] <= 0.5):
                self.sleep(1)
            initial_lap = self.sdk['CarIdxLapCompleted'][pace_car]

            while self.sdk['CarIdxLapCompleted'][pace_car] < initial_lap + 1:
                self.sleep(1)
            self.logger.debug('Pace car has completed a lap.')

        if self.extend_laps > 0:
            for _ in range(self.pre_extend_laps):
                await_pace_car_lap()
            self._chat(f'!p +{self.extend_laps}')

        if self.wave_arounds:
            self.audio_queue.put('wavesoon')
            laps_completed = self.pre_extend_laps
            while laps_completed < self.wave_around_lap:
                await_pace_car_lap()
                laps_completed += 1
            self.logger.debug('Ready for Wave Arounds.')
            self.audio_queue.put('wavenow')
            current_positions = self.get_wave_around_cars()

            last_step = self.get_current_running_order()

            overridden = False
            while current_positions:
                this_step = self.get_current_running_order()
                to_remove = []
                for car in current_positions:
                    args = [{'CarIdx': car}, last_step, this_step]
                    if int(hex(self.sdk['CarIdxPaceFlags'][car])[-1]) >= 4:
                        to_remove.append(car)
                    if self.car_has_completed_lap(*args) or self.car_has_left_pits(*args):
                        if self.sdk['CarIdxOnPitRoad'][car]:
                            self.logger.debug(f'{car} is on pit road.')
                            continue
                        self.wave_and_eol(car)
                for car in to_remove:
                    current_positions.pop(current_positions.index(car))
                last_step = this_step
                self.sleep(1)
                if not self.is_caution_active():
                    self.logger.warn('Caution ended during wave arounds.')
                    overridden = True
                    break
            if not overridden:
                self._chat('!p 3')
                self.audio_queue.put('wavecomplete')
                self.logger.info('Wave arounds complete.')

        while self.is_caution_active():
            self.sleep(1)

        self.logger.debug('Caution has ended.')
        self.audio_queue.put('open')

        self.busy_event.clear()

from modules.events.random_lap_event import RandomLapEvent
class LapCautionEvent(RandomLapEvent, RandomCautionEvent):
    """
    A class to represent a lap caution event in the iRacing simulator.
    """
    def __init__(self, *args, **kwargs):
        """
        Initializes the LapCautionEvent class.
        """
        super().__init__(*args, **kwargs)

    def event_sequence(self):
        """
        Executes the event sequence for a lap caution.
        """
        super().event_sequence()