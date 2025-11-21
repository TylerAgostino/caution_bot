from modules.events import RandomTimedEvent
import threading

class RestartOrderManager:
    def __init__(self, sdk, preset_order=None):
        """
        Initialize the RestartOrderManager.
        
        Args:
            sdk: The iRacing SDK instance.
            preset_order (list, optional): A preset order of cars. Defaults to None.
        """
        if preset_order is not None:
            self.order = preset_order
        else:
            self.order = []
        self.sdk = sdk
        self.class_separation = False
        self.one_meter = 1 / (float(str(self.sdk['WeekendInfo']['TrackLength']).replace(' km', '')) * 1000)
        self.wave_around_cars = []
        self.out_of_place_cars = []
        self.displaced_cars = []
        self.race_classes = self.sdk['CarIdxClass']
        self.class_lap_times = {}
        def get_fastest_lap_for_class(cc):
            classes = self.sdk['CarIdxClass']
            best_laps = self.sdk['CarIdxBestLapTime'] or self.sdk['CarIdxLastLapTime']
            best_lap = None
            for i, c in enumerate(classes):
                if c == cc:
                    if (best_lap is None or best_laps[i] < best_lap) and best_laps[i] > 0:
                        best_lap = best_laps[i]

            if best_lap is None:
                return 999999
            return best_lap
        for car_class in self.race_classes:
            if car_class not in self.class_lap_times:
                self.class_lap_times[car_class] = get_fastest_lap_for_class(car_class)

        # {'1': 'Faestest_class', '2': 'Second_fastest_class', '3': 'Third_fastest_class'}

        self.class_speed_rank = {class_: str(i+1) for i, class_ in enumerate(sorted({k:v for k,v in self.class_lap_times.items() if v is not None}, key=lambda x: self.class_lap_times[x])) }
        print(self.class_lap_times)

    def add_car_to_order(self, carIdx, wave_around=0, slower_class_catchup=0):
        """
        Add a car to the restart order.
        
        Args:
            carIdx (int): The index of the car to add.
            wave_around (int, optional): Whether this car gets a wave around. Defaults to 0.
            slower_class_catchup (int, optional): Whether this car gets a waved around to not be split from the rest of their class. Defaults to 0.
        """
        began_pacing_distance = self.sdk['CarIdxLapDistPct'][carIdx]
        if carIdx not in [car['CarIdx'] for car in self.order]:
            driver = [d for d in self.sdk['DriverInfo']['Drivers'] if d['CarIdx']==carIdx][0]
            car_number = driver['CarNumber']
            car_restart_record = {
                'CarIdx': carIdx,
                'CarNumber': car_number,
                'CarClassOrder': self.class_speed_rank[self.sdk['CarIdxClass'][carIdx]],
                'BeganPacingLap': self.sdk['CarIdxLapCompleted'][carIdx],
                'BeganPacingTick': int(self.sdk['SessionTick']),
                'BeganPacingDistance': began_pacing_distance,
                'WaveAround': wave_around,
                'SlowerClassCatchup': slower_class_catchup,
                'ExpectedPosition': 0,
                'ActualPosition': 0,
                'LatePit': 0,
                'IncorrectOvertakes': [],
                'IncorrectlyOvertakenBy': [],
                'WavesRemain': False
            }
        else:
            car_restart_record = [car for car in self.order if car['CarIdx'] == carIdx][0]
            self.order.remove(car_restart_record)
            car_restart_record['BeganPacingTick'] = int(self.sdk['SessionTick'])
            car_restart_record['LatePit'] = 1 #if car_restart_record['ActualPosition'] >= 0.25 else 0

        self.order.append(car_restart_record)
        self.update_order()

    def update_order(self):
        """
        Sort the order of cars based on current rules and parameters.
        
        Returns:
            list: A list of car numbers in the correct order.
        """
        # check if we've separated classes
        if self.class_separation:
            self.order = sorted(self.order, key=lambda x: (x['LatePit'], x['WaveAround'] + x['SlowerClassCatchup'], x['CarClassOrder'], x['BeganPacingTick'], -x['BeganPacingDistance']))
        else:
            self.order = sorted(self.order, key=lambda x: (x['LatePit'], x['WaveAround'] + x['SlowerClassCatchup'], x['BeganPacingTick'], -x['BeganPacingDistance']))
        self.update_car_positions()
        return [car['CarNumber'] for car in self.order]

    def update_car_positions(self):
        """
        Update the actual and expected positions of cars in the order.
        
        This method checks for cars that are out of position, have been overtaken incorrectly,
        or need to perform wave arounds.
        """
        # First update all the actual positions
        self.sdk.freeze_var_buffer_latest()
        for i, car in enumerate(self.order):
            self.order[i]['ActualPosition'] = self.sdk['CarIdxLapCompleted'][car['CarIdx']] + self.sdk['CarIdxLapDistPct'][car['CarIdx']] - car['BeganPacingLap']
        self.sdk.unfreeze_var_buffer_latest()
        # Then update the expected positions to be right behind the car in front of them
        for i, car in enumerate(self.order):
            self.order[i]['IncorrectOvertakes'] = []
            self.order[i]['IncorrectlyOvertakenBy'] = []
            for car_ahead in self.order[:i]:
                wave_adjusted_car_ahead_position = car_ahead['ActualPosition'] - car_ahead['WaveAround'] - car_ahead['SlowerClassCatchup'] + car['WaveAround'] + car['SlowerClassCatchup']
                if (car['ActualPosition'] > wave_adjusted_car_ahead_position and
                        not self.sdk['CarIdxOnPitRoad'][car_ahead['CarIdx']] and
                        not self.sdk['CarIdxOnPitRoad'][car['CarIdx']] and
                        not self.sdk['CarIdxLapDistPct'][car_ahead['CarIdx']] == -1 and
                        not self.sdk['CarIdxLapDistPct'][car['CarIdx']] == -1):
                    self.order[i]['IncorrectOvertakes'].append(car_ahead['CarNumber'])
            for car_behind in self.order[i+1:]:
                wave_adjusted_car_behind_position = car_behind['ActualPosition'] - car_behind['WaveAround'] - car_behind['SlowerClassCatchup'] + car['WaveAround'] + car['SlowerClassCatchup']
                if (car['ActualPosition'] < wave_adjusted_car_behind_position and
                        not self.sdk['CarIdxOnPitRoad'][car_behind['CarIdx']] and
                        not self.sdk['CarIdxOnPitRoad'][car['CarIdx']] and
                        not self.sdk['CarIdxLapDistPct'][car_behind['CarIdx']] == -1 and
                        not self.sdk['CarIdxLapDistPct'][car['CarIdx']] == -1):
                    self.order[i]['IncorrectlyOvertakenBy'].append(car_behind['CarNumber'])

            self.order[i]['WavesRemain'] = car['ActualPosition'] - (car['WaveAround'] + car['SlowerClassCatchup']) < self.leader()['ActualPosition'] - 1

        if self.order:
            self.out_of_place_cars = []
            self.displaced_cars = []
            self.wave_around_cars = []
            for i, car in enumerate(self.order):
                # skip the leader
                if i == 0:
                    continue
                if car['WavesRemain']:
                    self.wave_around_cars.append(car)
                if car['IncorrectOvertakes']:
                    self.out_of_place_cars.append(car)
                if car['IncorrectlyOvertakenBy']:
                    self.displaced_cars.append(car)

    def leader(self):
        """
        Get the current leader car.
        
        Returns:
            dict: The car data for the current leader, or None if no leader is found.
        """
        return next((car for car in self.order if self.sdk['CarIdxLapDistPct'][car['CarIdx']] != -1), None)



class RandomTimedCode69Event(RandomTimedEvent):
    """
    A class to represent a random Code 69 event in the iRacing simulator.
    
    This event slows down the field to a specific speed (default 69 kph) and coordinates
    an organized restart with options for wave arounds, class separation, and lane formation.

    Attributes:
        wave_arounds (bool): Flag to indicate if wave arounds are allowed.
        notify_on_skipped_caution (bool): Flag to indicate if notifications should be sent when a caution is skipped.
        restart_ready (Event): Threading event to signal when restart is ready.
        max_speed_km (int): Maximum speed in kilometers per hour for pacing.
        extra_lanes (bool): Flag to indicate if multiple restart lanes should be used.
        class_separation (bool): Flag indicating if classes are currently separated.
        can_separate_classes (bool): Flag indicating if class separation is permitted.
        can_separate_lanes (bool): Flag indicating if lane separation is permitted.
        reminder_frequency (int): How often to send reminder messages in chat.
        restart_speed_pct (int): Speed percentage threshold for restart.
        lane_names (list): Names of restart lanes (e.g. 'Left', 'Right').
        max_laps_behind_leader (int): Maximum laps a car can be behind the leader.
    """

    def __init__(self, wave_arounds=False, notify_on_skipped_caution=False, max_speed_km=69, restart_speed_pct=125,
                 lane_names=None, reminder_frequency=8, auto_restart_get_ready_position=1.85, wet_speed_km=69,
                 auto_restart_form_lanes_position=1.5, extra_lanes=True, auto_class_separate_position=1.0,
                 quickie_auto_restart_get_ready_position=0.85, quickie_auto_restart_form_lanes_position=0.5,
                 quickie_auto_class_separate_position=-1, quickie_invert_lanes=False, end_of_lap_safety_margin=0.1,
                 *args, **kwargs):
        """
        Initializes the RandomTimedCode69Event class.

        Args:
            wave_arounds (bool, optional): Flag to indicate if wave arounds are allowed. Defaults to False.
            notify_on_skipped_caution (bool, optional): Flag to indicate if notifications should be sent when a caution is skipped. Defaults to False.
            max_speed_km (int, optional): Maximum speed in kilometers per hour for pacing. Defaults to 69.
            restart_speed_pct (int, optional): Speed percentage threshold for restart. Defaults to 125.
            lane_names (list, optional): Names of restart lanes. Defaults to None.
            reminder_frequency (int, optional): How often to send reminder messages in chat. Defaults to 8.
            auto_restart_get_ready_position (float, optional): Laps of pacing before restarting. Defaults to 1.85.
            auto_restart_form_lanes_position (float, optional): Laps of pacing before forming lanes. Defaults to 1.5.
            extra_lanes (bool, optional): Flag to indicate if multiple restart lanes should be used. Defaults to True.
            auto_class_separate_position (float, optional): Laps of pacing before separating classes. Defaults to 1.0.
            quickie_auto_restart_get_ready_position (float, optional): Quickie laps before restarting. Defaults to 0.85.
            quickie_auto_restart_form_lanes_position (float, optional): Quickie laps before forming lanes. Defaults to 0.5.
            quickie_auto_class_separate_position (float, optional): Quickie laps before separating classes. Defaults to -1.
            quickie_invert_lanes (bool, optional): Whether to invert lanes in quickie events. Defaults to False.
            end_of_lap_safety_margin (float, optional): Safety margin at end of lap. Defaults to 0.1.
        """
        self.wave_arounds = wave_arounds
        self.wave_arounds_active = wave_arounds
        self.notify_on_skipped_caution = notify_on_skipped_caution
        self.restart_ready = threading.Event()
        self.max_speed_km = max_speed_km
        self.wet_speed_km = wet_speed_km
        self.extra_lanes = extra_lanes
        self.class_separation = False
        self.can_separate_classes = True
        self.can_separate_lanes = True
        self.reminder_frequency = reminder_frequency
        self.restart_speed_pct = restart_speed_pct
        # self.restart_speed = self.max_speed_km * (int(restart_speed_pct) / 100)
        self.auto_class_separate_position = auto_class_separate_position
        self.auto_restart_get_ready_position = auto_restart_get_ready_position
        self.auto_restart_form_lanes_position = auto_restart_form_lanes_position
        self.lane_names = lane_names
        self.quickie_auto_restart_get_ready_position = quickie_auto_restart_get_ready_position
        self.quickie_auto_restart_form_lanes_position = quickie_auto_restart_form_lanes_position
        self.quickie_auto_class_separate_position = quickie_auto_class_separate_position
        self.quickie_invert_lanes = quickie_invert_lanes
        self.end_of_lap_safety_margin = end_of_lap_safety_margin
        super().__init__(*args, **kwargs)
        self.max_laps_behind_leader = 99999
        self.pacing_speed_km = lambda: self.wet_speed_km if self.sdk['WeatherDeclaredWet'] else self.max_speed_km

    @staticmethod
    def ui(ident = ''):
        """
        Create a Streamlit UI for configuring the Code69 event parameters.
        
        Args:
            ident (str, optional): Identifier prefix for UI elements. Defaults to ''.
            
        Returns:
            dict: A dictionary containing the user-configured parameters.
        """
        import streamlit as st
        col1, col2, col3, col4, col5 = st.columns(5)
        advanced_options = st.expander("Advanced Options", expanded=False)
        aa_col1, aa_col2, aa_col3 = advanced_options.columns(3)
        return {
            'min': col1.number_input(f"Window Start", value=5, key=f'{ident}min', help="Minutes/Laps before the start of the window. Negative values are relative to the end of the race."),
            'max': col1.number_input("Window End", value=-15, key=f'{ident}max', help="Minutes/Laps before the end of the window. Negative values are relative to the end of the race"),
            'reminder_frequency': aa_col1.number_input("Reminder Frequency", value=8, help='How often to send reminders in chat. If this is too low, the bot may spam the chat and be unresponsive.', key=f'{ident}reminder_frequency'),

            'likelihood': col2.number_input(f'% Chance', key=f'{ident}likelihood', value=75, help="The likelihood of the event happening. 100% means it will happen every time."),
            'max_speed_km': aa_col2.number_input("Pace Speed (kph)", value=69, help='Pesters the leader to stay below this speed.', key=f'{ident}max_speed_km'),
            'wet_speed_km': aa_col3.number_input("Wet Pace Speed (kph)", value=69, help='Pesters the leader to stay below this speed when the track is wet.', key=f'{ident}wet_speed_km'),

            'auto_class_separate_position': col3.number_input("Class Separation Position", value=-1.00, help='Laps of pacing before separating classes. -1 to disable auto class separation', key=f'{ident}auto_class_separate_position'),
            'wave_arounds': col3.checkbox(f'Wave Arounds', key=f'{ident}wave_arounds', value=True),

            'auto_restart_form_lanes_position': col4.number_input("Lanes Form Position", value=1.63, help='Laps of pacing before forming the restart lanes. -1 to disable auto lane forming', key=f'{ident}auto_restart_form_lanes_position'),
            'lane_names': col4.text_input("Lane Names", "Right,Left", help="A comma-separated list of lane names. Length must be equal to the number of restart lanes. Primary/Lead lane is the first in the list.", key=f'{ident}lane_names').split(','),

            'auto_restart_get_ready_position': col5.number_input("Restart Position", value=1.79, help='Laps of pacing before restarting. -1 to disable auto restart', key=f'{ident}auto_restart_get_ready_position'),
            'restart_speed_pct': aa_col2.number_input("Restart Speed %", value=125, help='After the leader receives the "You control the field" message, show the green flag when they reach this % of the pacing speed', key=f'{ident}restart_speed_pct'),
            #quickie stuff
            'quickie_window': aa_col1.number_input("Quickie Window", value=5, help='If within this many minutes of another event, make this a quickie 69. -1 to disable', key=f'{ident}quickie_window'),
            'quickie_auto_class_separate_position': aa_col3.number_input("Quickie Class Separation Position", value=-1, help='Laps of pacing before separating classes (during Quickie 69)', key=f'{ident}quickie_auto_class_separate_position'),
            'quickie_auto_restart_form_lanes_position': aa_col3.number_input("Quickie Lanes Form Position", value=0.63, help='Laps of pacing before forming the restart lanes (during Quickie 69)', key=f'{ident}quickie_auto_restart_form_lanes_position'),
            'quickie_auto_restart_get_ready_position': aa_col3.number_input("Quickie Restart Position", value=0.79, help='Laps of pacing before restarting (during Quickie 69)', key=f'{ident}quickie_auto_restart_get_ready_position'),
            'quickie_invert_lanes': aa_col1.checkbox(f'Invert Quickie Lanes', key=f'{ident}quickie_invert_lanes', value=False, help='Inverts the lane names for the quickie event.'),
            'notify_on_skipped_caution': aa_col1.checkbox(f'Notify on Skip', key=f'{ident}notify_on_skipped_caution', value=False, help='Send a message to the chat if the event is triggered and skipped while another event is in progress.'),
            'end_of_lap_safety_margin': aa_col2.number_input("End of Lap Safety Margin", value=0.1, help='If the leader is within this lap percent of the S/F when the code69 is triggered, extend by another lap', key=f'{ident}end_of_lap_safety_margin'),
        }

    def send_reminders(self, order_generator):
        """
        Send reminder messages to cars that are out of position.
        
        Args:
            order_generator (RestartOrderManager): The restart order manager instance.
        """
        self.logger.debug(order_generator.order)
        # Instructions to cars that are out of place
        for car in order_generator.wave_around_cars:
            if self.wave_arounds_active:
                self._chat(f'/{car["CarNumber"]} Safely overtake the leader and join at the back of the pack.')
        for car in order_generator.out_of_place_cars:
            self._chat(f'/{car["CarNumber"]} Let the {", ".join(car["IncorrectOvertakes"])} car{"s" if len(car["IncorrectOvertakes"]) > 1 else ""} by.')
        for car in order_generator.displaced_cars:
            self._chat(f'/{car["CarNumber"]} Pass the {", ".join(car["IncorrectlyOvertakenBy"])} car{"s" if len(car["IncorrectlyOvertakenBy"]) > 1 else ""}.')

    def event_sequence(self):
        """
        Executes the event sequence for a random Code 69.
        """
        if self.is_caution_active() or self.busy_event.is_set():
            if self.notify_on_skipped_caution:
                self._chat('Additional caution skipped due to active caution.', race_control=True)
            return

        self.busy_event.set()
        self.restart_ready.clear()
        # self._chat(self.reason, race_control=True)
        self.audio_queue.put('quickiesoon' if self.quickie else 'code69beginsoon')


        last_step = self.get_current_running_order()
        send_message_indicator = self.intermittent_boolean_generator(self.reminder_frequency)

        # wait for someone to start the next lap
        lead_lap = max([car['LapCompleted'] for car in last_step])
        max_total_completed = max([car['total_completed'] for car in last_step])
        if max_total_completed - lead_lap >= 1 - self.end_of_lap_safety_margin:
            self.logger.warn('Safety margin triggered, extending notification phase by 1 lap')
            lead_lap += 1
        this_step = last_step
        msg = f'{"Quickie" if self.quickie else "Code"} 69 will begin at the end of lap {lead_lap + 1}'
        self._chat(msg, race_control=True)
        broadcast_msg = {
            'title': 'Race Control',
            'text': f'Code 69 Beginning at the end of lap {lead_lap + 1}',
        }
        self.broadcast_text_queue.put(broadcast_msg)
        while not any([car['LapCompleted'] > lead_lap for car in this_step]):
            self.sdk.unfreeze_var_buffer_latest()
            self.sdk.freeze_var_buffer_latest()
            last_step = this_step
            this_step = self.get_current_running_order()
            if any([car['LapCompleted'] > lead_lap for car in this_step]):
                break
            for car in this_step:
                if (self.car_has_completed_lap(car, last_step, this_step) and not self.sdk['CarIdxOnPitRoad'][car['CarIdx']]) \
                        or (self.car_has_left_pits(car, last_step, this_step) and self.sdk['CarIdxLapDistPct'][car['CarIdx']] < 0.5):
                    self._chat(f'/{car["CarNumber"]} YOU ARE STILL RACING FOR AN ADDITIONAL LAP')
            if send_message_indicator.__next__():
                self._chat(msg, race_control=True)

        self._chat('Double Yellow Flags in Sector 1', race_control=True)
        self.audio_queue.put('code69begin')
        if self.quickie:
            self._chat('The sequence will be shortened')
            self.audio_queue.put('quickiebegin')

        speed_km_per_hour = 0
        leader_speed_generator = None
        restart_order_generator = RestartOrderManager(self.sdk)
        leader = -1

        while not self.restart_ready.is_set():
            this_step = self.get_current_running_order()
            # Get the class leaders
            leaders = {}
            classes = set(self.get_car_class(carIdx=car['CarIdx']) for car in this_step)
            for class_ in classes:
                cars_in_class_on_track = [car for car in this_step if self.get_car_class(carIdx=car['CarIdx']) == class_ and not car['InPits']]
                cars_in_class_in_pits = [car for car in this_step if self.get_car_class(carIdx=car['CarIdx']) == class_ and car['InPits']]
                if cars_in_class_on_track:
                    leader_on_track = cars_in_class_on_track[0]
                    leader_in_pits = cars_in_class_in_pits[0] if cars_in_class_in_pits else None
                    if leader_in_pits and leader_in_pits['LapCompleted'] > leader_on_track['LapCompleted']:
                            leader_for_class = leader_in_pits
                    else:
                        leader_for_class = leader_on_track
                    leaders[class_] = leader_for_class

            for car in this_step:
                existing_restart_record = [c for c in restart_order_generator.order if c['CarIdx'] == car['CarIdx']]
                car_flags = self.sdk['CarIdxSessionFlags'][car['CarIdx']]
                if ( existing_restart_record
                         and
                        self.car_has_entered_pits(car, last_step, this_step) and
                        existing_restart_record[0]['ActualPosition'] < 0.5
                ):
                    # welcome to Bathurst
                    self.logger.debug(f'Car {car["CarNumber"]} has entered pits immediately after S/F, removing from order')
                    restart_order_generator.order = [c for c in restart_order_generator.order if c['CarIdx'] != car['CarIdx']]

                if ((car['CarIdx'] not in [c['CarIdx'] for c in restart_order_generator.order] and
                    self.car_has_completed_lap(car, last_step, this_step) and not self.sdk['CarIdxOnPitRoad'][car['CarIdx']])
                or (
                    self.car_has_left_pits(car, last_step, this_step) and self.sdk['CarIdxLapDistPct'][car['CarIdx']] < 0.5
                )
                or (car['CarIdx'] in [c['CarIdx'] for c in restart_order_generator.order] and
                    (self.car_has_entered_pits(car, last_step, this_step) or car_flags & self.Flags.black)
                        )
                ):
                    try:
                        last_step_record = [c for c in last_step if c['CarIdx'] == car['CarIdx']][0]
                        if last_step_record['LapCompleted'] == car['LapCompleted'] + 1 and last_step_record['LapDistPct'] <= car['LapDistPct']:
                            # fix issue where lap completed increments before the lap distance percentage resets to 0
                            car['LapDistPct'] = 0
                        # if the car has a slowdown, delay adding them to the order until they are clear
                        if car_flags & self.Flags.furled:
                            # overwrite the this_step record with the last step record to prevent re-adding them
                            self.logger.debug(f'Car {car["CarNumber"]} has a furled flag, delaying adding to order until clear')
                            this_step = [last_step_record if c['CarIdx'] == car['CarIdx'] else c for c in this_step]
                            continue
                        if car['CarIdx'] in [c['CarIdx'] for c in restart_order_generator.order] and car_flags & self.Flags.black:
                            self.logger.debug(f'Car {car["CarNumber"]} has a black flag, converting to EOL')
                            self._chat(f'!clear {car["CarNumber"]} Converted to EOL')

                    except IndexError:
                        pass

                    car_class = self.get_car_class(carIdx=car['CarIdx'])
                    class_leader = leaders[car_class]

                    distance_completed = car['total_completed']
                    class_leader_distance_completed = class_leader['total_completed']
                    class_leader_in_pits = class_leader['InPits']

                    gets_catch_up = 1 if class_leader['CarIdx'] not in [c['CarIdx'] for c in restart_order_generator.order] and class_leader['CarIdx'] != car['CarIdx'] and not class_leader_in_pits else 0
                    gets_wave_around = 1 if car['LapCompleted'] <= lead_lap else 0 # todo: this won't work for multiclass... I think?
                    gets_wave_around = gets_wave_around if self.wave_arounds and not self.quickie else 0
                    if gets_wave_around:
                        self.logger.debug(f'Laps Completed: {distance_completed}')
                        self.logger.debug(f'Class Leader Laps Completed: {class_leader_distance_completed}')

                        self.logger.debug(f'Class Leader in pits: {class_leader_in_pits}')

                    restart_order_generator.add_car_to_order(car['CarIdx'], wave_around=gets_wave_around, slower_class_catchup=gets_catch_up)
                    if len(restart_order_generator.order) > 1 and not self.sdk['CarIdxOnPitRoad'][car['CarIdx']]:
                        self._chat(f'/{car["CarNumber"]} Catch the field and look for further instructions')
                    else:
                        self._chat(f'/{car["CarNumber"]} Slow down and look for further instructions')
                    self.logger.debug(f'Adding car {car["CarNumber"]} to order (completed lap)')
                    self.logger.debug(f'Wave Around: {gets_wave_around}, Catch Up: {gets_catch_up}')
                    self.logger.debug(f'Correct order: {restart_order_generator.order}')
                    if gets_wave_around or gets_catch_up:
                        self.logger.info(f'{car["CarNumber"]} gets wave around: {gets_wave_around}, catch up: {gets_catch_up}')
                    continue
            self.sdk.unfreeze_var_buffer_latest()
            self.sdk.freeze_var_buffer_latest()
            if not restart_order_generator.leader():
                continue

            correct_order = restart_order_generator.update_order()

            # Send reminders
            if send_message_indicator.__next__():
                # Check the leader's speed
                if len(correct_order) > 0 and (leader_speed_generator is None or leader['CarNumber'] != restart_order_generator.leader()['CarNumber'] or leader['CarNumber'] not in [car['CarNumber'] for car in restart_order_generator.order]):
                    # New leader, we need a new speed generator
                    leader = restart_order_generator.leader()
                    leader_speed_generator = self.monitor_speed(leader['CarIdx'])
                if leader_speed_generator is not None:
                    speed_km_per_hour = leader_speed_generator.__next__()

                self.send_reminders(restart_order_generator)

                if speed_km_per_hour > self.pacing_speed_km():
                    self._chat(f'/{leader["CarNumber"]} Slow down to {self.pacing_speed_km()} kph / {int(self.pacing_speed_km()*0.621371)} mph.')
            self.sleep(0.1)

            if (self.class_separation
                    or (
                        0 < (
                self.quickie_auto_class_separate_position if self.quickie else self.auto_class_separate_position) <=
                        restart_order_generator.leader()['ActualPosition']
                        and len(restart_order_generator.order) > 1
                        and self.can_separate_classes
                    )
            ) and len([i for i, v in restart_order_generator.class_lap_times.items() if v is not None]) > 1:
                if self.can_separate_classes:
                    self._chat(f'Performing class separation.', race_control=True)
                restart_order_generator.class_separation = True
                self.can_separate_classes = False
                self.logger.debug(restart_order_generator.order)
            last_step = this_step

            if 0 < (
            self.quickie_auto_restart_form_lanes_position if self.quickie else self.auto_restart_form_lanes_position) <= \
                    restart_order_generator.leader()['ActualPosition'] and restart_order_generator.order:
                self.restart_ready.set()
            elif 0 < (
            self.quickie_auto_restart_get_ready_position if self.quickie else self.auto_restart_get_ready_position) <= \
                    restart_order_generator.leader()['ActualPosition'] and restart_order_generator.order:
                self.extra_lanes = False
                self.restart_ready.set()

        ln = self.lane_names
        if ln is not None:
            if isinstance(ln, str):
                lane_names = ln.split(',')
            else:
                lane_names = ln
        else:
            lane_names = ['LEFT', 'RIGHT']

        lane_names = lane_names[::-1] if self.quickie and self.quickie_invert_lanes else lane_names
        this_step = self.get_current_running_order()

        broadcast_msg = {
            'title': 'Race Control',
            'text': 'Code 69 Ending Soon',
        }
        self.broadcast_text_queue.put(broadcast_msg)

        if self.extra_lanes:
            number_of_lanes = len(lane_names)
            self.restart_ready.clear()
            self.audio_queue.put('lanes')
            self._chat(f'Forming {number_of_lanes} restart lanes.', race_control=True)
            lanes_raw = [[] for _ in range(number_of_lanes)]
            lane_order_generators = []
            i = 0
            for car in restart_order_generator.order:
                lanes_raw[i % number_of_lanes].append(car)
                self._chat(f'/{car["CarNumber"]} Line up {number_of_lanes} wide in the {str(lane_names[i % number_of_lanes]).upper()} lane.')
                try:
                    if car['CarIdx'] == self.sdk['PlayerCarIdx']:
                        self.logger.warn(f"{str(lane_names[i % number_of_lanes]).upper()} lane for player car")
                except:
                    pass
                i += 1
            for lane_cars in lanes_raw:
                lane_order_generators.append(RestartOrderManager(self.sdk, preset_order=lane_cars))
                self.logger.debug(f'Lane {lanes_raw.index(lane_cars)}: {lane_cars}')
            self.can_separate_lanes = False

        else:
            number_of_lanes = 1
            lane_order_generators = [restart_order_generator]
        self.wave_arounds_active = False  # no wave arounds during lane formation
        less_frequent_messages = self.intermittent_boolean_generator(self.reminder_frequency * 2)
        while not self.restart_ready.is_set():
            self.sdk.unfreeze_var_buffer_latest()
            self.sdk.freeze_var_buffer_latest()
            last_step = this_step
            this_step = self.get_current_running_order()
            for i in range(number_of_lanes):
                lane_order_generators[i].update_order()
                for car in this_step:
                    if (
                            self.car_has_left_pits(car, last_step, this_step) or self.car_has_entered_pits(car, last_step, this_step)
                    ) and car['CarIdx'] in [lane['CarIdx'] for lane in lane_order_generators[i].order]:
                        lane_order_generators[i].add_car_to_order(car['CarIdx'])

            if lane_order_generators[0].leader()['ActualPosition'] >= (self.quickie_auto_restart_get_ready_position if self.quickie else self.auto_restart_get_ready_position):
                self.restart_ready.set()

            if send_message_indicator.__next__():
                if len(lane_order_generators[0].order) > 0 and (leader_speed_generator is None or leader['CarNumber'] != lane_order_generators[0].leader()['CarNumber'] or leader['CarNumber'] not in [car['CarNumber'] for car in lane_order_generators[0].order]):
                    # New leader, we need a new speed generator
                    leader = lane_order_generators[0].leader()
                    leader_speed_generator = self.monitor_speed(leader['CarIdx'])
                if leader_speed_generator is not None:
                    speed_km_per_hour = leader_speed_generator.__next__()
                for i in range(number_of_lanes):
                    lane_order_generators[i].update_car_positions()
                    self.send_reminders(lane_order_generators[i])
                    if lane_order_generators[i].leader() is None:
                        continue
                    if lane_order_generators[i].leader()['ActualPosition'] > lane_order_generators[0].leader()['ActualPosition']:
                        self._chat(f'/{lane_order_generators[i].leader()["CarNumber"]} DO NOT PASS THE {lane_order_generators[0].leader()["CarNumber"]} CAR.')
                if speed_km_per_hour > self.pacing_speed_km():
                    self._chat(f'/{leader["CarNumber"]} Slow down to {self.pacing_speed_km()} kph / {int(self.pacing_speed_km()*0.621371)} mph.')
            if less_frequent_messages.__next__():
                for i in range(number_of_lanes):
                    for car in lane_order_generators[i].order:
                        self._chat(f'/{car["CarNumber"]} Line up {number_of_lanes} wide in the {str(lane_names[i]).upper()} lane.')
            self.sdk.unfreeze_var_buffer_latest()
            self.sdk.freeze_var_buffer_latest()

            self.sleep(0.1)
        self.sdk.unfreeze_var_buffer_latest()


        self.audio_queue.put('code69end')
        self._chat('Get Ready, Code 69 will end soon.', race_control=True)
        self._chat('Get Ready, Code 69 will end soon.', race_control=True)
        self._chat('Get Ready, Code 69 will end soon.', race_control=True)
        self.sleep(2)
        throwaway_speed = leader_speed_generator.__next__() # Make sure we aren't using an average from a while ago
        immediate_throw = True
        restart_speed = self.pacing_speed_km() * (int(self.restart_speed_pct) / 100)
        while True:
            self._chat(f'/{leader["CarNumber"]} you control the field, go when ready')
            speed_km_per_hour = leader_speed_generator.__next__()
            if speed_km_per_hour > restart_speed:
                break
            self.sleep(0.5)
            self.sdk.unfreeze_var_buffer_latest()
            self.sdk.freeze_var_buffer_latest()
            immediate_throw = False

        for i in range(len(lane_order_generators)):
            lane_order_generators[i].update_order()
            self.logger.debug(lane_order_generators[i].order)

        self._chat('Green Flag!', race_control=True)
        self._chat('Green Flag!', race_control=True)
        self.audio_queue.put('green')
        self._chat('Green Flag!', race_control=True)
        violation_message = "RESTART VIOLATION will be investigated"
        if immediate_throw:
            self._chat(f'/{leader["CarNumber"]} {violation_message} - Accelerated too early')

        for i in range(len(lane_order_generators)):
            if lane_order_generators[i].leader() is None:
                continue
            if lane_order_generators[i].leader()['ActualPosition'] > lane_order_generators[0].leader()['ActualPosition']:
                self._chat(f'/{lane_order_generators[i].leader()["CarNumber"]} {violation_message} - Passed the Leader')

            for car in lane_order_generators[i].out_of_place_cars:
                self._chat(f'/{car["CarNumber"]} {violation_message} - Passed the {", ".join(car["IncorrectOvertakes"])} car{"s" if len(car["IncorrectOvertakes"]) > 1 else ""}.')

        self.sdk.unfreeze_var_buffer_latest()
        self.busy_event.clear()


from modules.events import RandomLapEvent
class RandomLapCode69Event(RandomLapEvent, RandomTimedCode69Event):
    """
    A class to represent a lap-based Code 69 event in the iRacing simulator.
    
    This class combines the lap-based triggering mechanism of RandomLapEvent
    with the Code 69 functionality of RandomTimedCode69Event. It allows for
    Code 69 events that are triggered at specific lap milestones rather than
    time-based intervals.
    """
    pass