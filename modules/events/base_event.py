import irsdk
import pywinauto
import pyperclip
import streamlit as st
import time
import logging
import threading
from modules.llm import generate_caution_reason, generate_black_flag_reason

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
        max_laps_behind_leader (int): Maximum Laps Down for cars to be considered in the field.
    """

    def __init__(self, sdk=None, pwa=None, cancel_event=threading.Event(), busy_event=threading.Event(), max_laps_behind_leader=99):
        """
        Initializes the BaseEvent class.

        Args:
            sdk (irsdk.IRSDK, optional): Instance of the iRacing SDK. Defaults to None.
            pwa (pywinauto.Application, optional): Instance of the pywinauto Application. Defaults to None.
            cancel_event (threading.Event, optional): Event to signal cancellation. Defaults to None.
            busy_event (threading.Event, optional): Event to signal busy state. Defaults to None.
            max_laps_behind_leader (int, optional): Maximum Laps Down for cars to be considered in the field. Defaults to 99.
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
        self.max_laps_behind_leader = int(max_laps_behind_leader)

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
        try:
            self.pwa['iRacing.com Simulator'].type_keys(''.join(keys))
        except Exception as e:
            self.logger.critical('Error sending chat message.')
            self.logger.critical(e)
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
            self._chat(f'{message} {interval} seconds.', race_control=True)
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
             if driver['CarIsPaceCar'] != 1 and max_distance_covered - 1 >= distance_covered[
                 driver['CarIdx']] >= max_distance_covered - self.max_laps_behind_leader - 1],
            key=lambda x: laps_completed[x] + partial_laps[x], reverse=True)

    def get_current_running_order(self):
        """
        Gets the current running order of cars.

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
        return [runner for runner in running_order if runner['total_completed'] >= (running_order[0]['total_completed'] - self.max_laps_behind_leader-1)]

    def get_leader(self):
        """
        Gets the car index of the current leader.

        Returns:
            int: Car index of the leader.
        """
        return self.get_current_running_order()[0]['CarIdx']

    def wait_for_cars_to_clear_pit_lane(self, max_time=300):
        """
        Waits for cars to clear the pit lane.
        """
        max_time = int(max_time)
        end_time = self.sdk['SessionTimeRemain'] - max_time
        self.logger.debug(f'Waiting for cars to clear pit lane with a maximum of {max_time} seconds.')
        while any(self.sdk['CarIdxLapCompleted'][car['CarIdx']] >= max(self.sdk['CarIdxLapCompleted']) - self.max_laps_behind_leader for car in self.get_cars_on_pit_lane())\
                and self.sdk['SessionTimeRemain'] > end_time:
            self.sleep(1)
        self.logger.debug(f'Finished waiting for cars to clear pit lane after {end_time + max_time - self.sdk['SessionTimeRemain']} seconds.')

    def get_wave_around_cars(self):
        """
        Gets the list of cars eligible for wave around.

        Returns:
            list: List of car indices eligible for wave around.
        """
        lap_down_cars = [car for car in self.get_lap_down_cars() if self.sdk['CarIdxLapCompleted'][car] >= max(self.sdk['CarIdxLapCompleted']) - self.max_laps_behind_leader]
        self.logger.debug(f'Lap down cars: {lap_down_cars}')
        return lap_down_cars

    def is_caution_active(self):
        """
        Checks if a caution flag is active.

        Returns:
            bool: True if a caution flag is active, False otherwise.
        """
        return hex(self.sdk['SessionFlags'])[-4] in ['4', '8']

    @staticmethod
    def car_has_completed_lap(car, last_step, this_step):
        """
        Checks if a car has completed a lap.

        Args:
            car (dict): The car to check.
            last_step (list): The running order of the last step in time.
            this_step (list): The running order of the current step in time.

        Returns:
            bool: True if the car has completed their lap in the last step, False otherwise.
        """
        last_step_record = [record for record in last_step if record['CarIdx'] == car['CarIdx']][0]
        this_step_record = [record for record in this_step if record['CarIdx'] == car['CarIdx']][0]
        return this_step_record['LapCompleted'] > last_step_record['LapCompleted']

    @staticmethod
    def car_has_left_pits(car, last_step, this_step):
        """
        Checks if a car has left the pits.

        Args:
            car (dict): The car to check.
            last_step (list): The running order of the last step in time.
            this_step (list): The running order of the current step in time.

        Returns:
            bool: True if the car has left the pits in the last step, False otherwise.
        """
        last_step_record = [record for record in last_step if record['CarIdx'] == car['CarIdx']][0]
        this_step_record = [record for record in this_step if record['CarIdx'] == car['CarIdx']][0]
        return this_step_record['InPits'] == 0 and last_step_record['InPits'] == 1

    @staticmethod
    def generate_random_caution_reason():
        """
        Generates a random caution reason.

        Returns:
            str: A random caution reason.
        """
        return generate_caution_reason()

    @staticmethod
    def generate_random_black_flag_reason():
        """
        Generates a random black flag reason.

        Returns:
            str: A random black flag reason.
        """
        return generate_black_flag_reason()