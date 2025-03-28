from modules.events.base_event import BaseEvent
from pandas import DataFrame

class F1QualifyingEvent(BaseEvent):
    """
    An event that handles F1 qualifying sessions.
    """
    def __init__(self, session_minutes, session_advancing_cars, send_dq, *args, **kwargs):
        super().__init__(*args, **kwargs)
        lengths = session_minutes.split(',')
        num_drivers_remain = session_advancing_cars.split(',')
        self.session_minutes = [int(length) for length in lengths]
        self.session_advancing_cars = [int(num) for num in num_drivers_remain]
        if self.session_advancing_cars[-1] != 0:
            self.session_advancing_cars.append(0)
            self.session_minutes.append(self.session_minutes[-1])
        if len(self.session_minutes) != len(self.session_advancing_cars):
            raise ValueError("session_minutes and session_advancing_cars must have the same length.")
        self.send_dq = send_dq
        self.leaderboard = {}
        for n in range(len(self.session_minutes)):
            self.leaderboard[f'Q{n+1}'] = {}
        self.leaderboard_df = DataFrame(self.leaderboard)

    def event_sequence(self):
        # [(length, num_drivers_remain), ...]
        session_info = list(zip(self.session_minutes, self.session_advancing_cars))
        advancing_drivers = None
        for session_number, details in enumerate(session_info, start=1):
            length, num_drivers_remain = details
            advancing_drivers = self.subsession(5, length, num_drivers_remain, session_number, advancing_drivers)


    def apply_new_laptime(self, laps, carNumber, laptime):
        """
        Applies the new lap time to the car run order object.

        Args:
            laps (dict): Dictionary of car numbers and their fastest laps.
            carNumber (int): Car number.
            laptime (float): New lap time.
        """
        if laptime > 1 and (carNumber not in laps or laptime < laps[carNumber]):
            laps[carNumber] = laptime
            # format seconds to mm:ss.sss
            laptime = f"{int(laptime // 60):02}:{int(laptime % 60):02}.{int((laptime % 1) * 1000):03}"
            #check if it's the fastest lap of the session
            if laptime == min(laps.values()):
                self._chat(f"FASTEST LAP for car {carNumber}: {laptime}!", race_control=True)
            else:
                self._chat(f"New personal best for car {carNumber}: {laptime}!", race_control=True)
        return laps

    def update_leaderboard(self, fastest_laps, session_number, send_msg=True):
        """
        Updates the leaderboard with the fastest laps.

        Args:
            fastest_laps (dict): Dictionary of car numbers and their fastest laps.
        """
        sorted_laps = sorted(fastest_laps.items(), key=lambda x: x[1])
        overall_best = sorted_laps[0]
        for car, lap in sorted_laps:
            if car == overall_best[0]:
                self._chat(f'/{car} you are currently P1')
            else:
                car_ahead = sorted_laps[sorted_laps.index((car, lap)) - 1][1]
                gap = lap - overall_best[1]
                formatted_gap = f"{gap:.3f}"
                interval = lap - car_ahead
                formatted_interval = f"{interval:.3f}"
                msg = f'/{car} Pos: {sorted_laps.index((car, lap)) + 1}, Gap: {formatted_gap}s, Int: {formatted_interval}s'
                elimination = self.session_advancing_cars[session_number - 1]
                if 0 < elimination < len(sorted_laps):
                    gap_to_elim = lap - sorted_laps[elimination][1]
                    msg += f', Elim: {gap_to_elim:.3f}s'
                if send_msg:
                    self._chat(msg)
            self.leaderboard[f'Q{session_number}'][car] = lap

        self.leaderboard_df = DataFrame(self.leaderboard)
        #sort the df by lap times, highest qualifying session first
        sessions = [f'Q{n+1}' for n in range(len(self.session_minutes))]
        sessions.reverse()
        self.leaderboard_df = self.leaderboard_df.sort_values(by=sessions, ascending=True)

    def subsession(self, delay_start, length, num_drivers_remain, session_number, subset_of_drivers=None):
        """
        Runs a single subsession of the qualifying event.

        Args:
            delay_start (int): Delay before starting the session.
            length (int): Length of the session.
            num_drivers_remain (int): Number of drivers remaining in the session.
            session_number (int): Session number.
            subset_of_drivers (list, optional): List of drivers to include in the session. Defaults to None.
        """
        self._chat(f'Q{session_number} will begin shortly.', race_control=True)
        self._chat(f'Pit Exit is CLOSED.', race_control=True)

        # count down to session start
        self.countdown(delay_start, f"Q{session_number} will begin in")
        self._chat(f'Pit Exit is OPEN.', race_control=True)

        session_time_at_start = self.sdk['SessionTime']
        fastest_laps = {}
        this_step = self.get_current_running_order()
        sent_one_minute_warning = False

        while True:
            # main loop for the session until the checkered flag comes out
            self.sdk.unfreeze_var_buffer_latest()
            self.sdk.freeze_var_buffer_latest()
            last_step = this_step
            this_step = self.get_current_running_order()

            session_elapsed_time = self.sdk['SessionTime'] - session_time_at_start
            for car in this_step:
                driver_info_record = [c for c in self.sdk['DriverInfo']['Drivers'] if c['CarNumber'] == car['CarNumber']]
                if driver_info_record and car['CarNumber'] in subset_of_drivers if subset_of_drivers else True:
                    if self.car_has_completed_lap(car, last_step, this_step):
                        car_idx = driver_info_record[0]['CarIdx']
                        last_lap = self.sdk['CarIdxLastLapTime'][car_idx]
                        fastest_laps = self.apply_new_laptime(fastest_laps, car['CarNumber'], last_lap)

            if length * 60 - session_elapsed_time < 60 and not sent_one_minute_warning:
                self._chat(f"1 minute remaining in Q{session_number}!", race_control=True)
                sent_one_minute_warning = True

            if session_elapsed_time > length * 60:
                self._chat(f"Checkered flag is out for Q{session_number}!", race_control=True)
                self.sdk.unfreeze_var_buffer_latest()
                break

            self.sleep(1)

        self.update_leaderboard(fastest_laps, session_number)

        # allow any cars that are on track to finish their lap
        remaining_cars = subset_of_drivers if subset_of_drivers else [car['CarNumber'] for car in this_step]
        while remaining_cars:
            self.sdk.unfreeze_var_buffer_latest()
            self.sdk.freeze_var_buffer_latest()
            last_step = this_step
            this_step = self.get_current_running_order()
            for car in this_step:
                if car['CarNumber'] in remaining_cars:
                    if car['CarNumber'] not in fastest_laps: # todo: if you don't have a valid lap when time expires, you don't get the extra lap
                        remaining_cars.remove(car['CarNumber'])
                        self._chat(f'/{car['CarNumber']} The session is over.')
                    else:
                        driver_info_record = [c for c in self.sdk['DriverInfo']['Drivers'] if c['CarNumber'] == car['CarNumber']]
                        if driver_info_record and car['CarNumber'] in subset_of_drivers if subset_of_drivers else True:
                            if self.car_has_completed_lap(car, last_step, this_step):
                                car_idx = driver_info_record[0]['CarIdx']
                                last_lap = self.sdk['CarIdxLastLapTime'][car_idx]
                                fastest_laps = self.apply_new_laptime(fastest_laps, car['CarNumber'], last_lap)
                                remaining_cars.remove(car['CarNumber'])
                                self._chat(f'/{car['CarNumber']} The session is over, please return to the pits.')
                                continue

                            carIdx = driver_info_record[0]['CarIdx']
                            if self.sdk['CarIdxOnPitRoad'][carIdx] == 1:
                                remaining_cars.remove(car['CarNumber'])
                                self._chat(f'/{car['CarNumber']} The session is over.')

            self.sleep(1)

        self.sdk.unfreeze_var_buffer_latest()

        self.update_leaderboard(fastest_laps, session_number)
        if num_drivers_remain > 0:
            advancing_drivers = [c for c,n in sorted(fastest_laps.items(), key=lambda x: x[1])[:num_drivers_remain]]
            eliminated_drivers = [car for car in [c['CarNumber'] for c in last_step] if car not in advancing_drivers]
            eliminated_drivers.reverse()
            for car in eliminated_drivers:
                car_idx = [c for c in self.sdk['DriverInfo']['Drivers'] if c['CarNumber'] == car]
                if car_idx:
                    flags = self.sdk['CarIdxSessionFlags'][car_idx[0]['CarIdx']]
                    if not flags & 0x020000:
                        self._chat(f'/{car} you have been eliminated from Q{session_number}!')
                        if self.send_dq:
                            self._chat(f'!dq {car}')
            for car in advancing_drivers:
                self._chat(f'/{car} you have advanced to Q{session_number + 1}!')

        else:
            advancing_drivers = [c for c,n in sorted(fastest_laps.items(), key=lambda x: x[1])]
            for car in advancing_drivers:
                self._chat(f'/{car} Thats the end of Qualifying!')
            if self.send_dq:
                advancing_drivers.reverse()
                for car in advancing_drivers:
                    self._chat(f'!dq {car}')

        return advancing_drivers
