from modules.events.base_event import BaseEvent
from pandas import DataFrame

class F1QualifyingEvent(BaseEvent):
    """
    An event that handles F1 qualifying sessions with multiple elimination rounds.
    
    Implements a Formula 1 style qualifying format with:
    - Multiple timed sessions (Q1, Q2, Q3, etc.)
    - Progressive elimination of drivers
    - Tracking of lap times and position updates
    - Leaderboard management
    """
    def __init__(self, session_minutes, session_advancing_cars, wait_between_sessions, *args, **kwargs):
        """
        Initialize the F1 qualifying event.
        
        Args:
            session_minutes (str): Comma-separated string of session lengths in minutes (e.g. "18,15,12")
            session_advancing_cars (str): Comma-separated string of cars advancing from each session (e.g. "15,10,0"). If the last number is not 0, an additional final round is added automatically.
            *args, **kwargs: Additional arguments passed to BaseEvent
        """
        super().__init__(*args, **kwargs)
        
        # Parse session configuration
        lengths = session_minutes.split(',')
        num_drivers_remain = session_advancing_cars.split(',')
        self.session_minutes = [int(length) for length in lengths]
        self.session_advancing_cars = [int(num) for num in num_drivers_remain]
        self.wait_between_sessions = wait_between_sessions
        self.subsession_time_remaining = 0
        
        # Ensure the final session properly terminates by adding a 0-advancing session if needed
        if self.session_advancing_cars[-1] != 0:
            self.session_advancing_cars.append(0)
            self.session_minutes.append(self.session_minutes[-1])
            
        # Validate configuration
        if len(self.session_minutes) != len(self.session_advancing_cars):
            raise ValueError("session_minutes and session_advancing_cars must have the same length.")
        
        # Initialize leaderboard structure
        self.leaderboard = {}
        for n in range(len(self.session_minutes)):
            self.leaderboard[f'Q{n+1}'] = {}
        self.leaderboard_df = DataFrame(self.leaderboard)

    def event_sequence(self):
        """
        Main event sequence that runs the entire qualifying session.
        
        Process flow:
        1. Create session information from configuration
        2. Run each qualifying session in sequence (Q1, Q2, Q3...)
        3. Track advancing drivers between sessions
        4. Terminate after final session
        """
        # Create list of tuples: [(session_length, cars_advancing), ...]
        session_info = list(zip(self.session_minutes, self.session_advancing_cars))
        advancing_drivers = None
        
        # Run each qualifying session
        for session_number, details in enumerate(session_info, start=1):
            length, num_drivers_remain = details
            advancing_drivers = self.subsession(self.wait_between_sessions, length, num_drivers_remain, session_number, advancing_drivers)

    def apply_new_laptime(self, laps, carNumber, laptime):
        """
        Applies a new lap time to the car run order object if it's an improvement.
        
        Args:
            laps (dict): Dictionary of car numbers and their fastest laps in this subsession.
            carNumber (int): Car number.
            laptime (float): New lap time in seconds.
            
        Returns:
            dict: Updated dictionary of fastest laps in this subsession
        """
        # Only update if the lap is valid (>1 sec) and faster than previous best
        if laptime > 1 and (carNumber not in laps or laptime < laps[carNumber]):
            laps[carNumber] = laptime
            
            # Format seconds to mm:ss.sss for display
            formatted_time = f"{int(laptime // 60):02}:{int(laptime % 60):02}.{int((laptime % 1) * 1000):03}"
            
            # Check if it's the fastest lap of the session
            if laptime == min(laps.values()):
                self._chat(f"FASTEST LAP for car {carNumber}: {formatted_time}!", race_control=True)
            else:
                self._chat(f"New personal best for car {carNumber}: {formatted_time}!", race_control=True)
                
        return laps

    def update_leaderboard(self, fastest_laps, session_number, send_msg=True):
        """
        Updates the leaderboard with the fastest laps and sends position updates.
        
        Args:
            fastest_laps (dict): Dictionary of car numbers and their fastest laps in this subsession.
            session_number (int): Current qualifying session number (1, 2, 3...)
            send_msg (bool): Whether to send position messages to drivers
        """
        # Sort laps by time (fastest first)
        sorted_laps = sorted(fastest_laps.items(), key=lambda x: x[1])
        
        if not sorted_laps:
            return
            
        overall_best = sorted_laps[0]
        
        # Process each car's position
        for car, lap in sorted_laps:
            if car == overall_best[0]:
                # Leader notification
                if send_msg:
                    self._chat(f'/{car} you are currently P1')
            else:
                # Get car ahead's time for interval calculation
                car_ahead = sorted_laps[sorted_laps.index((car, lap)) - 1][1]
                
                # Calculate gap to leader and interval to car ahead
                gap = lap - overall_best[1]
                formatted_gap = f"{gap:.3f}"
                interval = lap - car_ahead
                formatted_interval = f"{interval:.3f}"
                
                # Build position message
                msg = f'/{car} Pos: {sorted_laps.index((car, lap)) + 1}, Gap: {formatted_gap}s, Int: {formatted_interval}s'
                
                # Add elimination zone info if applicable
                elimination = self.session_advancing_cars[session_number - 1]
                if 0 < elimination < len(sorted_laps):
                    gap_to_elim = lap - sorted_laps[elimination - 1][1]
                    msg += f', Elim: {gap_to_elim:.3f}s'
                    
                if send_msg:
                    self._chat(msg)
                    
            # Update session leaderboard
            self.leaderboard[f'Q{session_number}'][car] = lap

        # Update the dataframe representation of the leaderboard
        self.leaderboard_df = DataFrame(self.leaderboard)
        
        # Sort the dataframe by lap times, prioritizing higher qualifying sessions
        sessions = [f'Q{n+1}' for n in range(len(self.session_minutes))]
        sessions.reverse()
        self.leaderboard_df = self.leaderboard_df.sort_values(by=sessions, ascending=True)

    def subsession(self, delay_start, length, num_drivers_remain, session_number, subset_of_drivers=None):
        """
        Runs a single qualifying subsession (Q1, Q2, Q3, etc.).
        
        Process flow:
        1. Announce session start and close pit exit
        2. Countdown to session start
        3. Open pit exit and begin session timing
        4. Track lap times during session
        5. Announce checkered flag when session time expires
        6. Allow cars to complete final laps
        7. Process results and determine advancing drivers
        8. Notify drivers of their status (advancing/eliminated)
        
        Args:
            delay_start (int): Delay in seconds before starting the session.
            length (int): Length of the session in minutes.
            num_drivers_remain (int): Number of drivers advancing to next session.
            session_number (int): Session number (1 for Q1, 2 for Q2, etc.)
            subset_of_drivers (list, optional): List of drivers eligible for this session.
            
        Returns:
            list: List of drivers advancing to the next session
        """
        # ----- SESSION PREPARATION PHASE -----
        self._chat(f'Q{session_number} will begin shortly.', race_control=True)
        self._chat(f'Pit Exit is CLOSED.', race_control=True)

        # Count down to session start
        self.countdown(delay_start, f"Q{session_number} will begin in")
        self._chat(f'Pit Exit is OPEN.', race_control=True)

        # ----- SESSION RUNNING PHASE -----
        session_time_at_start = self.sdk['SessionTime']
        fastest_laps = {}
        this_step = self.get_current_running_order()
        sent_one_minute_warning = False

        every_minute_update = self.intermittent_boolean_generator(60)

        # Main session loop
        out_of_time = False
        while True:
            # Update sim data
            self.sdk.unfreeze_var_buffer_latest()
            self.sdk.freeze_var_buffer_latest()
            
            # Track changes between steps since the last time this loop ran
            last_step = this_step
            this_step = self.get_current_running_order()

            # Calculate elapsed time since session start
            session_elapsed_time = self.sdk['SessionTime'] - session_time_at_start
            self.subsession_time_remaining = length * 60 - session_elapsed_time
            #format as time
            self.subsession_time_remaining = f"{int(self.subsession_time_remaining // 60):02}:{int(self.subsession_time_remaining % 60):02}"

            # Session time expired - show checkered flag after this iteration of the loop
            if session_elapsed_time > length * 60:
                out_of_time = True

            # if anyone has completed a lap, wait a few seconds to make sure the last lap data updates
            # before we check for lap times
            if any([self.car_has_completed_lap(c, last_step, this_step) for c in this_step]):
                self.sleep(5)
                self.sdk.unfreeze_var_buffer_latest()
                self.sdk.freeze_var_buffer_latest()

            # Process lap times for each car
            for car in this_step:
                driver_info_record = [c for c in self.sdk['DriverInfo']['Drivers'] if c['CarNumber'] == car['CarNumber']]
                
                # Only process eligible cars (either all cars or the subset for this session)
                is_eligible = car['CarNumber'] in subset_of_drivers if subset_of_drivers else True
                
                if driver_info_record and is_eligible:
                    if self.car_has_completed_lap(car, last_step, this_step):
                        car_idx = driver_info_record[0]['CarIdx']
                        last_lap = self.sdk['CarIdxLastLapTime'][car_idx]
                        fastest_laps = self.apply_new_laptime(fastest_laps, car['CarNumber'], last_lap)
                        self.update_leaderboard(fastest_laps, session_number, send_msg=False)

            # One minute warning
            if length * 60 - session_elapsed_time < 60 and not sent_one_minute_warning:
                self._chat(f"1 minute remaining in Q{session_number}!", race_control=True)
                sent_one_minute_warning = True

            if every_minute_update.__next__():
                # Update leaderboard every minute
                self.update_leaderboard(fastest_laps, session_number, send_msg=True)

            if out_of_time:
                self._chat(f"Checkered flag is out for Q{session_number}!", race_control=True)
                self.sdk.unfreeze_var_buffer_latest()
                break
            self.sleep(1)

        # ----- FINAL LAP COMPLETION PHASE -----
        self.update_leaderboard(fastest_laps, session_number)

        # Allow any cars on track to finish their in-progress lap
        remaining_cars = subset_of_drivers.copy() if subset_of_drivers else [car['CarNumber'] for car in this_step]

        longest_lap_time = max(fastest_laps.values()) if fastest_laps else 120
        wait_timeout = self.intermittent_boolean_generator(longest_lap_time*1.1)
        
        while remaining_cars:
            out_of_time = wait_timeout.__next__()
            self.sdk.unfreeze_var_buffer_latest()
            self.sdk.freeze_var_buffer_latest()
            
            last_step = this_step
            this_step = self.get_current_running_order()

            # if anyone has completed a lap, wait a few seconds to make sure the last lap data updates
            # before we check for lap times
            if any([self.car_has_completed_lap(c, last_step, this_step) for c in this_step]):
                self.sleep(5)
                self.sdk.unfreeze_var_buffer_latest()
                self.sdk.freeze_var_buffer_latest()
            
            for car in this_step:
                if car['CarNumber'] in remaining_cars:
                    driver_info_record = [c for c in self.sdk['DriverInfo']['Drivers']
                                        if c['CarNumber'] == car['CarNumber']]

                    is_eligible = car['CarNumber'] in subset_of_drivers if subset_of_drivers else True

                    if driver_info_record and is_eligible:
                        # Check if car has completed a lap
                        if self.car_has_completed_lap(car, last_step, this_step):
                            car_idx = driver_info_record[0]['CarIdx']
                            last_lap = self.sdk['CarIdxLastLapTime'][car_idx]
                            fastest_laps = self.apply_new_laptime(fastest_laps, car['CarNumber'], last_lap)
                            self.update_leaderboard(fastest_laps, session_number, send_msg=False)
                            remaining_cars.remove(car['CarNumber'])
                            self._chat(f'/{car["CarNumber"]} The session is over, please return to the pits.')
                            continue

                        # Check if car has returned to pits
                        carIdx = driver_info_record[0]['CarIdx']
                        if self.sdk['CarIdxOnPitRoad'][carIdx] == 1:
                            remaining_cars.remove(car['CarNumber'])
                            self._chat(f'/{car["CarNumber"]} The session is over.')

            self.sleep(1)
            if out_of_time:
                break

        self.sdk.unfreeze_var_buffer_latest()

        # ----- RESULTS PROCESSING PHASE -----
        self.update_leaderboard(fastest_laps, session_number)
        
        # Process advancing or elimination based on session configuration
        if num_drivers_remain > 0:
            # Get advancing drivers (sorted by fastest time)
            advancing_drivers = [c for c, n in sorted(fastest_laps.items(), key=lambda x: x[1])[:num_drivers_remain]]
            
            # Get eliminated drivers
            eliminated_drivers = [car for car in [c['CarNumber'] for c in last_step] if car not in advancing_drivers and (car in subset_of_drivers if subset_of_drivers else True)]
            
            # Notify eliminated drivers
            for car in eliminated_drivers:
                self._chat(f'/{car} you have been eliminated from Q{session_number}!')
            
            # Notify advancing drivers
            for car in advancing_drivers:
                self._chat(f'/{car} you have advanced to Q{session_number + 1}!')
        else:
            # Final session - nothing left to advance to
            advancing_drivers = [c for c, n in sorted(fastest_laps.items(), key=lambda x: x[1])]
            
            # Notify end of qualifying
            for car in advancing_drivers:
                self._chat(f'/{car} Thats the end of Qualifying! You are P{advancing_drivers.index(car) + 1}!')

        return advancing_drivers
