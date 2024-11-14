import irsdk
import pywinauto
import pyperclip
import streamlit as st
import time
import logging
import threading

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
    """

    def __init__(self, sdk=None, pwa=None, cancel_event=None, busy_event=None):
        """
        Initializes the BaseEvent class.

        Args:
            sdk (irsdk.IRSDK, optional): Instance of the iRacing SDK. Defaults to None.
            pwa (pywinauto.Application, optional): Instance of the pywinauto Application. Defaults to None.
            cancel_event (threading.Event, optional): Event to signal cancellation. Defaults to None.
            busy_event (threading.Event, optional): Event to signal busy state. Defaults to None.
        """
        self.sdk = sdk or irsdk.IRSDK()
        self.pwa = pwa or pywinauto.Application()
        self.sdk.startup()
        self.pwa.connect(best_match='iRacing.com Simulator', timeout=10)
        self.thread = None
        self.killed = False
        self.task = None
        self.logger = st.session_state.get('logger', logging.getLogger(__name__))
        self.cancel_event = cancel_event
        self.busy_event = busy_event

    def sleep(self, seconds):
        """
        Sleeps for a specified number of seconds and checks for cancellation.

        Args:
            seconds (int): Number of seconds to sleep.

        Raises:
            KeyboardInterrupt: If the cancel_event is set.
        """
        time.sleep(seconds)
        if self.cancel_event.is_set():
            self.logger.info('Event cancelled.')
            raise KeyboardInterrupt

    def run(self, cancel_event=None, busy_event=None):
        """
        Runs the event sequence.

        Args:
            cancel_event (threading.Event, optional): Event to signal cancellation. Defaults to None.
            busy_event (threading.Event, optional): Event to signal busy state. Defaults to None.
        """
        self.cancel_event = cancel_event or self.cancel_event
        self.busy_event = busy_event or self.busy_event
        self.event_sequence()

    def event_sequence(self):
        """
        Defines the sequence of events. Must be implemented by subclasses.

        Raises:
            NotImplementedError: If not implemented by subclass.
        """
        raise NotImplementedError

    def _chat(self, message, enter=True, race_control=False):
        """
        Sends a chat message in the iRacing simulator.

        Args:
            message (str): The message to send.
            enter (bool, optional): Whether to press enter after the message. Defaults to True.
            race_control (bool, optional): Whether the message is from race control. Defaults to False.
        """
        if race_control:
            message = f'/all {message}'
        pyperclip.copy(message)
        self.logger.debug(f'Sending chat message: {message}')
        self.sdk.chat_command(3)
        self.sleep(0.1)
        self.sdk.chat_command(1)
        keys = ['^v']
        if enter:
            keys.append('{ENTER}')
        self.pwa['iRacing.com Simulator'].type_keys(''.join(keys))
        self.sleep(0.3)

    def wave_and_eol(self, car):
        """
        Waves around a car and sends it to the end of the line.

        Args:
            car (int): The car index.
        """
        car_number = self.sdk['DriverInfo']['Drivers'][car]['CarNumber']
        self.logger.info(f'Waving around car {car_number}')
        self._chat(f'!w {car_number}')
        self._chat(f'!eol {car_number}')

    def wave_around(self, cars):
        """
        Waves around multiple cars.

        Args:
            cars (list): List of car indices.
        """
        for car in cars:
            self.wave_and_eol(car)

    def countdown(self, seconds, message=''):
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
            self._chat(f'{message} {interval} seconds.')
            seconds = interval

    def throw_caution(self):
        """
        Throws a caution flag in the iRacing simulator.
        """
        self.logger.info('Throwing caution')
        self._chat('!y')

    def close_pits(self, warning_time=None):
        """
        Closes the pits with an optional warning time.

        Args:
            warning_time (int, optional): Time in seconds before closing the pits. Defaults to None.
        """
        self.logger.info('Beginning pit close sequence.')
        if warning_time:
            self.countdown(warning_time, 'Pits closing in ')
        self.logger.info('Closing pits.')
        self._chat('!pitclose')

    def get_cars_on_pit_lane(self):
        """
        Gets a list of cars currently on the pit lane.

        Returns:
            list: List of drivers on the pit lane.
        """
        return [driver for driver in self.sdk['DriverInfo']['Drivers']
                if driver['CarIsPaceCar'] != 1 and self.sdk['CarIdxOnPitRoad'][driver['CarIdx']]]

    def get_lap_down_cars(self):
        """
        Gets a list of cars that are a lap down.

        Returns:
            list: List of car indices that are a lap down.
        """
        laps_completed = self.sdk['CarIdxLapCompleted']
        partial_laps = self.sdk['CarIdxLapDistPct']
        distance_covered = [laps_completed[i] + partial_laps[i] for i in range(len(laps_completed))]
        max_distance_covered = max(distance_covered)
        return sorted(
            [driver['CarIdx'] for driver in self.sdk['DriverInfo']['Drivers']
             if driver['CarIsPaceCar'] != 1 and distance_covered[driver['CarIdx']] <= max_distance_covered - 1],
            key=lambda x: laps_completed[x] + partial_laps[x], reverse=True)

    def get_current_running_order(self, max_laps_behind_leader=99):
        """
        Gets the current running order of cars.

        Args:
            max_laps_behind_leader (int, optional): Maximum laps behind the leader to include. Defaults to 99.

        Returns:
            list: List of dictionaries representing the running order.
        """
        running_order = [{
            'CarIdx': car['CarIdx'],
            'CarNumber': car['CarNumber'],
            'LapCompleted': self.sdk['CarIdxLapCompleted'][car['CarIdx']],
            'LapDistPct': self.sdk['CarIdxLapDistPct'][car['CarIdx']],
            'InPits': self.sdk['CarIdxOnPitRoad'][car['CarIdx']],
            'total_completed': self.sdk['CarIdxLapCompleted'][car['CarIdx']] + self.sdk['CarIdxLapDistPct'][car['CarIdx']]
        } for car in self.sdk['DriverInfo']['Drivers'] if car['CarIsPaceCar'] != 1]
        running_order.sort(key=lambda x: x['total_completed'], reverse=True)
        return [runner for runner in running_order if runner['total_completed'] >= (running_order[0]['total_completed'] - max_laps_behind_leader)]

    def get_leader(self):
        """
        Gets the car index of the current leader.

        Returns:
            int: Car index of the leader.
        """
        return self.get_current_running_order()[0]['CarIdx']

    def is_caution_active(self):
        """
        Checks if a caution flag is active.

        Returns:
            bool: True if a caution flag is active, False otherwise.
        """
        return hex(self.sdk['SessionFlags'])[-4] in ['4', '8']