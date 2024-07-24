from tkinter import *
from tkinter import ttk
import threading
import datetime
import os
import logging
import irsdk
import random
import asyncio
import pywinauto
import time
import pyperclip
from idlelib.tooltip import Hovertip
from tkinter.scrolledtext import ScrolledText
kill = False
active_caution = False

LOGLEVEL = 'INFO'

os.makedirs('logs', exist_ok=True)
LOGFILE = f'logs/{datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")}.log'
DEBUG_LOGFILE = f'logs/{datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")}_debug.log'


class Bot:
    def __init__(self,
                 caution_window_start=5,
                 caution_window_end=-10,
                 caution_likelihood=0.75,
                 caution_frequency=2,
                 minimum_cautions=0,
                 allowed_session_types=None,
                 **kwargs
                 ):
        if allowed_session_types is None:
            allowed_session_types = [4]
        logging.info('Initializing bot.')
        self.sdk = irsdk.IRSDK()
        self.sdk.startup()
        race_duration = self.sdk['SessionTimeTotal']

        self.caution_window_start = caution_window_start
        if caution_window_end < 0:
            logging.debug('Setting caution window end relative')
            self.caution_window_end = race_duration + caution_window_end
        else:
            self.caution_window_end = caution_window_end
        logging.debug(f'Caution window end: {self.caution_window_end}')
        self.caution_likelihood = caution_likelihood
        self.caution_frequency = caution_frequency

        self.caution_window = (int(self.caution_window_start), int(self.caution_window_end))
        self.cautions = []

        self.allowed_session_types = allowed_session_types

        for i in range(self.caution_frequency):
            if random.random() < self.caution_likelihood:
                caution_time = random.randint(*self.caution_window)
                caution = Caution(caution_time, self.sdk, **kwargs)
                self.cautions.append(caution)
            else:
                logging.debug('Caution did not hit.')

        if len(self.cautions) < minimum_cautions:
            logging.debug('Adding more cautions to meet minimum.')
            for i in range(minimum_cautions - len(self.cautions)):
                caution_time = random.randint(*self.caution_window)
                caution = Caution(caution_time, self.sdk, **kwargs)
                self.cautions.append(caution)

    def is_in_valid_session(self):
        return self.sdk['SessionState'] in self.allowed_session_types


class Caution:
    def __init__(self, caution_time, sdk, **kwargs):
        logging.debug(f'Creating caution at {caution_time} seconds.')
        self.caution_time = caution_time
        self.pit_close_advance_warning = kwargs['pit_close_advance_warning']
        self.pit_close_maximum_duration = kwargs['pit_close_maximum_duration']
        self.max_laps_behind_leader = kwargs['max_laps_behind_leader']
        self.sdk = sdk
        self.pwa = pywinauto.Application()
        self.pwa.connect(best_match='iRacing.com Simulator')

    async def run(self):
        global active_caution
        logging.info(f'Running caution')
        logging.debug(f'Caution time: {self.caution_time}')
        while not self.is_caution_time():
            await asyncio.sleep(1)
        if active_caution:
            self._chat('Additional caution skipped due to active caution.')
            return
        active_caution = True
        await self.warn_pits_closing(self.pit_close_advance_warning)
        self.close_pits()
        start_time = self.sdk['SessionTime']
        while self.pit_lane_has_cars():
            await asyncio.sleep(1)
            if self.sdk['SessionTime'] - start_time > self.pit_close_maximum_duration:
                logging.debug('Pit lane has cars for too long.')
                break
        self.throw()

        # Check for lap down cars
        wave_around_cars = self.get_wave_around_cars()

        # Wait to give wave arounds
        pace_car = [driver for driver in self.sdk['DriverInfo']['Drivers'] if driver['CarIsPaceCar'] == 1][0]['CarIdx']
        # see what lap the pace car is starting out on
        initial_lap = self.sdk['CarIdxLapCompleted'][pace_car]
        # wait for the pace car to complete the lap
        while self.sdk['CarIdxLapCompleted'][pace_car] - initial_lap < 1:
            await asyncio.sleep(1)

        while len(wave_around_cars) > 0:
            # now wait for the waved car to pass the pit commit line.
            # checking for this using the lap distance percentage.
            # if this percentage is set too high, we might wave cars
            # before they've actually caught the field and decided whether to pit
            # if they're very far behind. if its set too low, the sdk might 'miss'
            # the frame where the car crosses the line and not wave them around
            while self.sdk['CarIdxLapDistPct'][wave_around_cars[0]] > 0.1 and \
                    not self.sdk['CarIdxOnPitRoad'][wave_around_cars[0]]:
                await asyncio.sleep(1)

            # if they pitted, then skip them for now
            if self.sdk['CarIdxOnPitRoad'][wave_around_cars[0]]:
                # move to the back of the array
                wave_around_cars.append(wave_around_cars.pop(0))
            else:
                # otherwise wave them around
                self.wave_and_eol(wave_around_cars.pop(0))
            await asyncio.sleep(1)

        # then wait for green flag
        while self.sdk['SessionState'] != 4:
            await asyncio.sleep(1)
        active_caution = False



    def get_wave_around_cars(self):
        wave_around_cars = []
        laps_completed = self.sdk['CarIdxLapCompleted']
        partial_laps = self.sdk['CarIdxLapDistPct']
        distance_covered = [laps_completed[i] + partial_laps[i] for i in range(len(laps_completed))]
        max_distance_covered = max(distance_covered)
        for driver in self.sdk['DriverInfo']['Drivers']:
            if driver['CarIsPaceCar'] != 1 and \
                    distance_covered[driver['CarIdx']] <= max_distance_covered - 1 and \
                    self.sdk['CarIdxLapCompleted'][driver['CarIdx']] >= \
                    max(self.sdk['CarIdxLapCompleted']) - self.max_laps_behind_leader:
                wave_around_cars.append(driver['CarIdx'])
        wave_around_cars.sort(key=lambda x: laps_completed[x] + partial_laps[x])
        return wave_around_cars

    def pit_lane_has_cars(self):
        for driver in self.sdk['DriverInfo']['Drivers']:
            if driver['CarIsPaceCar'] != 1 and \
                    self.sdk['CarIdxOnPitRoad'][driver['CarIdx']] and \
                    self.sdk['CarIdxLapCompleted'][driver['CarIdx']] >= \
                    max(self.sdk['CarIdxLapCompleted']) - self.max_laps_behind_leader:
                logging.debug(f'Car {driver["CarNumber"]} is on pit road.')
                return True
        logging.debug('No cars on pit road.')
        return False

    def is_caution_time(self):
        total_session_time = self.sdk['SessionTimeTotal']
        time_remaining = self.sdk['SessionTimeRemain']
        return total_session_time - time_remaining >= self.caution_time - self.pit_close_advance_warning

    async def warn_pits_closing(self, warning_time):
        message = f'Pits closing in {self.pit_close_advance_warning} seconds.'
        logging.info(message)
        self._chat(message, race_control=True)

        for interval in [30, 20, 10, 5, 3, 2, 1]:
            if warning_time > interval:
                await asyncio.sleep(warning_time - interval)
                warning_time = interval
                self._chat(f'Pits closing in {interval} seconds.', race_control=True)

    def close_pits(self):
        logging.info('Closing pits.')
        self._chat('!pitclose')

    def throw(self):
        logging.info('Throwing caution.')
        self._chat('!pitopen')
        self._chat('!y')

    def _chat(self, message, enter=True, race_control=False):
        if race_control:
            message = f'/all {message}'
        pyperclip.copy(message)
        logging.debug(f'Sending chat message: {message}')
        self.sdk.chat_command(3)  # Close any chat in progress
        time.sleep(0.1)  # Wait a beat
        self.sdk.chat_command(1)  # Open a new chat
        keys = ['^v']
        if enter:
            keys.append('{ENTER}')
        self.pwa['iRacing.com Simulator'].type_keys(''.join(keys))
        time.sleep(1)  # Wait a beat again

    def wave_around(self, cars):
        for car in cars:
            self.wave_and_eol(car)

    def wave_and_eol(self, car):
        car_number = self.sdk['DriverInfo']['Drivers'][car]['CarNumber']
        logging.info(f'Waving around car {car_number}')
        self._chat(f'!w {car_number}')
        self._chat(f'!eol {car_number}')


def ui():
    async def start_task(**kwargs):
        global kill
        kill = False
        task = asyncio.create_task(start_bot(**kwargs))
        while not kill and not task.done():
            await asyncio.sleep(1)
        logging.info("Done.")
        start_button.config(text="Start", command=start_bot_thread)

    def stop_task():
        global kill
        logger.info("Cancelling.")
        kill = True

    def start_bot_thread():
        t = threading.Thread(target=asyncio.run, args=(start_task(
            caution_window_start=caution_window_start.get(),
            caution_window_end=caution_window_end.get(),
            caution_likelihood=caution_likelihood.get(),
            caution_frequency=caution_frequency.get(),
            minimum_cautions=caution_minimum.get(),
            pit_close_advance_warning=pit_close_advance_warning.get(),
            pit_close_maximum_duration=pit_close_maximum_duration.get(),
            max_laps_behind_leader=max_laps_behind_leader.get()
        ),))
        t.start()
        start_button.config(text="Cancel", command=stop_task)

    def update_log():
        while True:
            try:
                log.config(state=NORMAL)
                log.delete(1.0, END)
                with open(LOGFILE, 'r') as f:
                    text = f.read()
                    text = '\n'.join(text.split('\n')[-20:])
                    log.insert(1.0, text)
                log.config(state=DISABLED)
                time.sleep(1)
            except RuntimeError:
                break

    master = Tk()
    master.title("Caution Bot")

    Label(master, text="Window Start (minutes)", justify=RIGHT, anchor=E).grid(row=0, sticky=E)
    caution_window_start = Entry(master)
    Hovertip(caution_window_start, "Caution-free period at the start of the session in minutes. Negative values are relative to the end of the session")
    caution_window_start.insert(0, "5")
    caution_window_start.grid(row=0, column=1)

    Label(master, text="Window End (minutes)").grid(row=1, sticky=E)
    caution_window_end = Entry(master)
    Hovertip(caution_window_end, "Caution-free period at the end of the session in minutes. Negative values are relative to the end of the session")
    caution_window_end.insert(0, "-15")
    caution_window_end.grid(row=1, column=1)

    Label(master, text="Caution likelihood (%)").grid(row=2, sticky=E)
    caution_likelihood = Entry(master)
    Hovertip(caution_likelihood, "The chance of each caution being thrown.")
    caution_likelihood.insert(0, "75")
    caution_likelihood.grid(row=2, column=1)

    Label(master, text="Max Number of Cautions").grid(row=3, sticky=E)
    caution_frequency = Entry(master)
    Hovertip(caution_frequency, "The maximum number of cautions to throw.")
    caution_frequency.insert(0, "2")
    caution_frequency.grid(row=3, column=1)

    Label(master, text="Min Number of Cautions").grid(row=4, sticky=E)
    caution_minimum = Entry(master)
    Hovertip(caution_minimum, "The minimum number of cautions to throw.")
    caution_minimum.insert(0, "0")
    caution_minimum.grid(row=4, column=1)

    Label(master, text="Pit Close Warning (Seconds)").grid(row=5, sticky=E)
    pit_close_advance_warning = Entry(master)
    Hovertip(pit_close_advance_warning, "The time in seconds to warn drivers that the pits are closing.")
    pit_close_advance_warning.insert(0, "5")
    pit_close_advance_warning.grid(row=5, column=1)

    Label(master, text="Max Pit Close Time (Seconds)").grid(row=6, sticky=E)
    pit_close_maximum_duration = Entry(master)
    Hovertip(pit_close_maximum_duration, "The maximum time to wait for drivers to exit the pits")
    pit_close_maximum_duration.insert(0, "120")
    pit_close_maximum_duration.grid(row=6, column=1)

    Label(master, text="Max Laps Behind Leader").grid(row=7, sticky=E)
    max_laps_behind_leader = Entry(master)
    Hovertip(max_laps_behind_leader, "Only wait for drivers to exit the pits if they're within this many laps of the leader.")
    max_laps_behind_leader.insert(0, "3")
    max_laps_behind_leader.grid(row=7, column=1)





    Label(master, text="Log Level").grid(row=9, sticky=E)
    log_level = OptionMenu(master, StringVar(master, LOGLEVEL),'DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL', command=set_log_level)
    log_level.grid(row=9, column=1)

    start_button = Button(master, text='Start', command=start_bot_thread)
    start_button.grid(row=10, columnspan=2)


    frame = ttk.Frame(master)
    frame.grid(row=11, columnspan=2)
    log = ScrolledText(frame, wrap=WORD, state=DISABLED, height=20)
    log.grid(row=0, column=0)
    log.configure(font='TkFixedFont')
    log_thread = threading.Thread(target=update_log)
    log_thread.start()
    mainloop()

def set_log_level(level):
    logger.handlers[1].setLevel(level)
    # maybe start a new log file here?

async def start_bot(caution_window_start, caution_window_end, caution_likelihood, caution_frequency, minimum_cautions,
                    pit_close_advance_warning, pit_close_maximum_duration, max_laps_behind_leader):
    try:
        bot = Bot(
            caution_window_start=int(float(caution_window_start) * 60),
            caution_window_end=int(float(caution_window_end) * 60),
            caution_likelihood=float(caution_likelihood) / 100,
            caution_frequency=int(caution_frequency),
            minimum_cautions=int(minimum_cautions),
            pit_close_advance_warning=int(pit_close_advance_warning),
            pit_close_maximum_duration=int(pit_close_maximum_duration),
            max_laps_behind_leader=int(max_laps_behind_leader)
        )
    except Exception as e:
        logging.error(f'Error initializing bot: {e}')
        logging.debug(f'Caution window start: {caution_window_start}')
        logging.debug(f'Caution window end: {caution_window_end}')
        logging.debug(f'Caution likelihood: {caution_likelihood}')
        logging.debug(f'Caution frequency: {caution_frequency}')
        logging.debug(f'Minimum cautions: {minimum_cautions}')
        logging.debug(f'Pit close advance warning: {pit_close_advance_warning}')
        logging.debug(f'Pit close maximum duration: {pit_close_maximum_duration}')
        logging.debug(f'Max laps behind leader: {max_laps_behind_leader}')
        return

    while not bot.is_in_valid_session():
        logging.info("Not in a valid session.")
        await asyncio.sleep(10)

    for caution in bot.cautions:
        logging.debug(f"Caution at {caution.caution_time} seconds.")
    await asyncio.gather(*[caution.run() for caution in bot.cautions])


if __name__ == '__main__':
    logger = logging.getLogger()
    logging.basicConfig(level=LOGLEVEL, format='%(levelname)s - %(message)s')
    filelogger = logging.FileHandler(LOGFILE, mode='w')
    filelogger.setFormatter(logging.Formatter('%(levelname)s - %(message)s'))
    logger.addHandler(filelogger)
    debuglogger = logging.FileHandler(DEBUG_LOGFILE, mode='w')
    debuglogger.setLevel(logging.DEBUG)
    debuglogger.setFormatter(logging.Formatter('%(levelname)s - %(message)s'))
    logger.addHandler(debuglogger)
    logging.info("Hello.")
    ui()
    logging.info("Exiting.")
