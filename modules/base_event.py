import irsdk
import pywinauto
import pyperclip
import streamlit as st
import time
import logging
import threading


class BaseEvent:
    def __init__(self,
                 sdk: irsdk.IRSDK = None,
                 pwa: pywinauto.Application = None,
                 cancel_event: threading.Event = None,
                 busy_event: threading.Event = None
                 ):
        if sdk is None:
            self.sdk = irsdk.IRSDK()
        else:
            self.sdk = sdk
        if pwa is None:
            self.pwa = pywinauto.Application()
        else:
            self.pwa = pwa
        self.sdk.startup()
        self.pwa.connect(best_match='iRacing.com Simulator', timeout=10)
        self.thread = None
        self.killed = False
        self.task = None
        if 'logger' not in st.session_state:
            self.logger = logging.getLogger(__name__)
        else:
            self.logger = st.session_state.logger
        self.cancel_event = cancel_event
        self.busy_event = busy_event

    def sleep(self, seconds):
        time.sleep(seconds)
        if self.cancel_event.is_set():
            self.logger.info('Event cancelled.')
            raise KeyboardInterrupt

    def run(self, cancel_event=None, busy_event=None):
        if cancel_event is not None:
            self.cancel_event = cancel_event
        if busy_event is not None:
            self.busy_event = busy_event
        self.event_sequence()

    def event_sequence(self):
        raise NotImplementedError

    def _chat(self, message, enter=True, race_control=False):
        if race_control:
            message = f'/all {message}'
        pyperclip.copy(message)
        self.logger.debug(f'Sending chat message: {message}')
        self.sdk.chat_command(3)  # Close any chat in progress
        self.sleep(0.1)  # Wait a beat
        self.sdk.chat_command(1)  # Open a new chat
        keys = ['^v']
        if enter:
            keys.append('{ENTER}')
        self.pwa['iRacing.com Simulator'].type_keys(''.join(keys))
        self.sleep(0.3)  # Wait a beat again

    def wave_and_eol(self, car):
        car_number = self.sdk['DriverInfo']['Drivers'][car]['CarNumber']
        self.logger.info(f'Waving around car {car_number}')
        self._chat(f'!w {car_number}')
        self._chat(f'!eol {car_number}')

    def wave_around(self, cars):
        for car in cars:
            self.wave_and_eol(car)

    def countdown(self, seconds, message=''):
        intervals = [30, 20, 10, 5, 3, 2, 1]
        intervals = [interval for interval in intervals if interval < seconds]
        intervals.insert(0, seconds)

        for interval in intervals:
            self.sleep(seconds - interval)
            self._chat(f'{message} {interval} seconds.')
            seconds = interval

    def throw_caution(self):
        self.logger.info('Throwing caution')
        self._chat('!y')

    def close_pits(self, warning_time: int = None):
        self.logger.info('Beginning pit close sequence.')
        if warning_time:
            self.countdown(warning_time, 'Pits closing in ')
        self.logger.info('Closing pits.')
        self._chat('!pitclose')

    def get_cars_on_pit_lane(self):
        pit_lane_cars = [driver for driver in self.sdk['DriverInfo']['Drivers']
                         if driver['CarIsPaceCar'] != 1
                         and self.sdk['CarIdxOnPitRoad'][driver['CarIdx']]
                         ]
        return pit_lane_cars

    def get_lap_down_cars(self):
        wave_around_cars = []
        laps_completed = self.sdk['CarIdxLapCompleted']
        partial_laps = self.sdk['CarIdxLapDistPct']
        distance_covered = [laps_completed[i] + partial_laps[i] for i in range(len(laps_completed))]
        max_distance_covered = max(distance_covered)
        for driver in self.sdk['DriverInfo']['Drivers']:
            if driver['CarIsPaceCar'] != 1 and \
                    distance_covered[driver['CarIdx']] <= max_distance_covered - 1:
                wave_around_cars.append(driver['CarIdx'])
        wave_around_cars.sort(key=lambda x: laps_completed[x] + partial_laps[x], reverse=True)
        return wave_around_cars

    def get_current_running_order(self, max_laps_behind_leader=99):
        running_order = []
        for car in self.sdk['DriverInfo']['Drivers']:
            if car['CarIsPaceCar'] != 1:
                pos = {
                    'CarIdx': car['CarIdx'],
                    'CarNumber': car['CarNumber'],
                    'LapCompleted': self.sdk['CarIdxLapCompleted'][car['CarIdx']],
                    'LapDistPct': self.sdk['CarIdxLapDistPct'][car['CarIdx']],
                    'InPits': self.sdk['CarIdxOnPitRoad'][car['CarIdx']]
                }
                pos['total_completed'] = pos['LapCompleted'] + pos['LapDistPct']
                running_order.append(pos)
        running_order.sort(key=lambda x: x['total_completed'], reverse=True)
        running_order = [runner for runner in running_order if
                         runner['total_completed'] >= (running_order[0]['total_completed'] - max_laps_behind_leader)]
        return running_order

    def get_leader(self):
        return self.get_current_running_order()[0]['CarIdx']

    def is_caution_active(self):
        return hex(self.sdk['SessionFlags'])[-4] in ['4', '8']