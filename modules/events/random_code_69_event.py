from modules.events.random_timed_event import RandomTimedEvent
import threading
import enum

class RestartOrderManager:
    def __init__(self, sdk, preset_order=None):
        if preset_order is not None:
            self.order = preset_order
        else:
            self.order = []
        self.sdk = sdk
        self.class_separation = False
        self.one_meter = 1 / (float(str(self.sdk['WeekendInfo']['TrackLength']).replace(' km', '')) * 1000)
        self.wave_around_cars = []
        self.out_of_place_cars = []
        self.catchup_cars = []
        self.race_classes = self.sdk['CarIdxClass']
        self.class_lap_times = {}
        def get_fastest_lap_for_class(cc):
            classes = self.sdk['CarIdxClass']
            best_laps = self.sdk['CarIdxBestLapTime']
            best_lap = None
            for i, c in enumerate(classes):
                if c == cc:
                    if (best_lap is None or best_laps[i] < best_lap) and best_laps[i] > 0:
                        best_lap = best_laps[i]
            return best_lap
        for car_class in self.race_classes:
            if car_class not in self.class_lap_times:
                self.class_lap_times[car_class] = get_fastest_lap_for_class(car_class)

        # {'1': 'Faestest_class', '2': 'Second_fastest_class', '3': 'Third_fastest_class'}

        self.class_speed_rank = {class_: str(i+1) for i, class_ in enumerate(sorted({k:v for k,v in self.class_lap_times.items() if v is not None}, key=lambda x: self.class_lap_times[x])) }
        print(self.class_lap_times)

    def add_car_to_order(self, carIdx, wave_around=0, slower_class_catchup=0):
        if carIdx not in [car['CarIdx'] for car in self.order]:
            car_restart_record = {
                'CarIdx': carIdx,
                'CarNumber': self.sdk['DriverInfo']['Drivers'][carIdx]['CarNumber'],
                'CarClassOrder': self.class_speed_rank[self.sdk['CarIdxClass'][carIdx]],
                'BeganPacingLap': self.sdk['CarIdxLapCompleted'][carIdx],
                'BeganPacingTick': int(self.sdk['SessionTick']),
                'BeganPacingDistance': self.sdk['CarIdxLapDistPct'][carIdx],
                'WaveAround': wave_around,
                'SlowerClassCatchup': slower_class_catchup,
                'ExpectedPosition': 0,
                'ActualPosition': 0
            }
        else:
            # Don't EOL everyone here, if someone pits and comes back out they should just be added to the order
            car_restart_record = [car for car in self.order if car['CarIdx'] == carIdx][0]
            self.order.remove(car_restart_record)
            car_restart_record['BeganPacingTick'] = int(self.sdk['SessionTick'])

        self.order.append(car_restart_record)
        self.update_car_positions()

    def update_order(self):
        # check if we've separated classes
        if self.class_separation:
            self.order = sorted(self.order, key=lambda x: (x['WaveAround'] + x['SlowerClassCatchup'], x['CarClassOrder'], x['BeganPacingTick']))
        else:
            self.order = sorted(self.order, key=lambda x: (x['WaveAround'] + x['SlowerClassCatchup'], x['BeganPacingTick']))

        self.update_car_positions()
        return [car['CarNumber'] for car in self.order]

    def update_car_positions(self):
        # First update all the actual positions
        for i, car in enumerate(self.order):
            self.order[i]['ActualPosition'] = self.sdk['CarIdxLapCompleted'][car['CarIdx']] + self.sdk['CarIdxLapDistPct'][car['CarIdx']] - car['BeganPacingLap']
        # Then update the expected positions to be right behind the car in front of them
        for i, car in enumerate(self.order):
            if i == 0:
                self.order[i]['ExpectedPosition'] = self.order[i]['ActualPosition']
            else:
                car_ahead = self.order[i-1]
                # something's wrong here, getting negative numbers -- might be fixed now
                self.order[i]['ExpectedPosition'] = (min(car_ahead['ActualPosition'], car_ahead['ExpectedPosition']) - (self.one_meter * 0.1) -
                                                     car_ahead['WaveAround'] - car_ahead['SlowerClassCatchup'] +
                                                     car['WaveAround'] + car['SlowerClassCatchup']) # EOL'd car behind waved car messes this up
                # If the car ahead
        # Then find anyone out of place and tell them to get back in line
        if self.order:
            leader_position = self.order[0]['ActualPosition']
            self.out_of_place_cars = []
            self.catchup_cars = []
            self.wave_around_cars = []
            for i, car in enumerate(self.order):
                # skip the leader
                if i == 0:
                    continue
                # Identify anyone that needs to overtake the leader (they are more than a lap from where they should be)
                if car['ExpectedPosition'] - car['ActualPosition'] > ((1 + car['ExpectedPosition'] - leader_position) % 1): # this is wrong, EOL'd cars are being told to overtake
                    self.wave_around_cars.append(car)
                # Identify anyone far from the car in front of them
                elif car['ExpectedPosition'] - car['ActualPosition'] > self.one_meter * 200:
                    self.catchup_cars.append((car, self.order[i-1]))
                # Identify anyone in front of cars they should be behind
                elif car['ActualPosition'] > car['ExpectedPosition']:
                    self.out_of_place_cars.append((car, self.order[i-1]))



class RandomCode69Event(RandomTimedEvent):
    """
    A class to represent a random Virtual Safety Car (VSC) event in the iRacing simulator.

    Attributes:
        restart_proximity (int): Proximity threshold for restarting the race.
        max_vsc_duration (int): Maximum duration for the VSC.
        max_laps_behind_leader (int): Maximum laps a car can be behind the leader.
        wave_arounds (bool): Flag to indicate if wave arounds are allowed.
        notify_on_skipped_caution (bool): Flag to indicate if notifications should be sent when a caution is skipped.
        reason (str): The reason for the VSC.
    """

    def __init__(self, wave_arounds=False, notify_on_skipped_caution=False, max_speed_km = 69, restart_speed_pct=125,
                 restart_lanes=2, lane_names=None, reminder_frequency=8, *args, **kwargs):
        """
        Initializes the RandomVSC class.

        Args:
            restart_proximity (int, optional): Proximity threshold for restarting the race. Defaults to None.
            max_vsc_duration (int, optional): Maximum duration for the VSC. Defaults to None.
            max_laps_behind_leader (int, optional): Maximum laps a car can be behind the leader. Defaults to 3.
            wave_arounds (bool, optional): Flag to indicate if wave arounds are allowed. Defaults to False.
            notify_on_skipped_caution (bool, optional): Flag to indicate if notifications should be sent when a caution is skipped. Defaults to False.
        """
        self.wave_arounds = wave_arounds
        self.notify_on_skipped_caution = notify_on_skipped_caution
        self.restart_ready = threading.Event()
        self.max_speed_km = int(max_speed_km)
        self.extra_lanes = False
        self.class_separation = False
        self.can_separate_classes = True
        self.can_separate_lanes = True
        self.reminder_frequency = int(reminder_frequency)
        self.restart_speed = self.max_speed_km * (int(restart_speed_pct) / 100)
        if lane_names is not None:
            self.lane_names = lane_names
        else:
            self.lane_names = ['LEFT', 'RIGHT']
        self.restart_lanes = int(restart_lanes)
        super().__init__(*args, **kwargs)
        self.max_laps_behind_leader = 99999
        # self.reason = self.generate_random_caution_reason()

    def send_reminders(self, order_generator):
        # Instructions to cars that are out of place
        for car in order_generator.wave_around_cars:
            self._chat(f'/{car["CarNumber"]} Safely overtake the leader and join at the back of the pack.')
        for car, car_ahead in order_generator.catchup_cars:
            self._chat(f'/{car["CarNumber"]} Catch the {car_ahead["CarNumber"]} car.')
        for car, car_ahead in order_generator.out_of_place_cars:
            self._chat(f'/{car["CarNumber"]} Let the {car_ahead["CarNumber"]} car by.')
            self._chat(f'/{car_ahead["CarNumber"]} Pass the {car["CarNumber"]} car.')

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
        self._chat('Code 69 will begin at the Start/Finish Line', race_control=True)

        last_step = self.get_current_running_order()
        session_time = self.sdk['SessionTime']

        # wait for someone to start the next lap
        lead_lap = max([car['LapCompleted'] for car in last_step])
        this_step = last_step
        while not any([car['LapCompleted'] > lead_lap for car in this_step]):
            for car in this_step:
                if (self.car_has_completed_lap(car, last_step, this_step) and not self.sdk['CarIdxOnPitRoad'][car['CarIdx']]) \
                        or self.car_has_left_pits(car, last_step, this_step):
                    self._chat(f'/{car["CarNumber"]} YOU ARE STILL RACING FOR AN ADDITIONAL LAP')
            if self.sdk['SessionTime'] - session_time > self.reminder_frequency:
                self._chat('Code 69 will begin at the Start/Finish Line', race_control=True)
                session_time = self.sdk['SessionTime']
            last_step = this_step
            this_step = self.get_current_running_order()

        self._chat('Double Yellow Flags in Sector 1', race_control=True)

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
                if ((car['CarIdx'] not in [c['CarIdx'] for c in restart_order_generator.order] and
                    self.car_has_completed_lap(car, last_step, this_step) and not self.sdk['CarIdxOnPitRoad'][car['CarIdx']])
                        or (
                    self.car_has_left_pits(car, last_step, this_step)
                )):
                    car_class = self.get_car_class(carIdx=car['CarIdx'])
                    class_leader = leaders[car_class]
                    gets_catch_up = 1 if class_leader['CarIdx'] not in [c['CarIdx'] for c in restart_order_generator.order] and class_leader['CarIdx'] != car['CarIdx'] and not class_leader['InPits'] else 0
                    gets_wave_around = 1 if car['LapCompleted'] < class_leader['LapCompleted'] or (class_leader['InPits'] and car['total_completed'] + 0.5 < class_leader['total_completed']) else 0
                    restart_order_generator.add_car_to_order(car['CarIdx'], wave_around=gets_wave_around, slower_class_catchup=gets_catch_up)
                    if len(restart_order_generator.order) > 1:
                        self._chat(f'/{car["CarNumber"]} Catch the field and look for further instructions')
                    else:
                        self._chat(f'/{car["CarNumber"]} Slow down and look for further instructions')
                    self.logger.debug(f'Adding car {car["CarNumber"]} to order (completed lap)')
                    self.logger.debug(f'Wave Around: {gets_wave_around}, Catch Up: {gets_catch_up}')
                    self.logger.debug(f'Correct order: {restart_order_generator.order}')
                    if gets_wave_around or gets_catch_up:
                        self.logger.info(f'{car["CarNumber"]} gets wave around: {gets_wave_around}, catch up: {gets_catch_up}')
                    continue

            correct_order = restart_order_generator.update_order()

            # Send reminders
            if self.sdk['SessionTime'] - session_time > self.reminder_frequency:
                # Check the leader's speed
                if len(correct_order) > 0 and (leader_speed_generator is None or leader != restart_order_generator.order[0]['CarNumber'] or leader not in [car['CarNumber'] for car in restart_order_generator.order]):
                    # New leader, we need a new speed generator
                    leader = restart_order_generator.order[0]['CarNumber']
                    leader_speed_generator = self.monitor_speed(leader)
                if leader_speed_generator is not None:
                    speed_km_per_hour = leader_speed_generator.__next__()

                self.send_reminders(restart_order_generator)

                if speed_km_per_hour > self.max_speed_km:
                    self._chat(f'/{leader} Slow down to {self.max_speed_km} kph / {int(self.max_speed_km*0.621371)} mph.')
                session_time = self.sdk['SessionTime']
            self.sleep(0.1)

            if self.class_separation:
                if self.can_separate_classes:
                    self._chat(f'Performing class separation. Faster classes overtake on the {self.lane_names[0]}', race_control=True)
                restart_order_generator.class_separation = True
                self.can_separate_classes = False
                self.logger.debug(restart_order_generator.order)
            last_step = this_step

        if self.extra_lanes:
            self.restart_ready.clear()
            self._chat(f'Forming {self.restart_lanes} restart lanes, leader in the {self.lane_names[0]} lane.', race_control=True)
            lanes_raw = [[] for _ in range(self.restart_lanes)]
            lane_order_generators = []
            i = 0
            for car in restart_order_generator.order:
                lanes_raw[i % self.restart_lanes].append(car)
                self._chat(f'/{car["CarNumber"]} Line up in the {str(self.lane_names[i % self.restart_lanes]).upper()} lane.')
                i += 1
            for lane_cars in lanes_raw:
                lane_order_generators.append(RestartOrderManager(self.sdk, preset_order=lane_cars))
                self.logger.debug(f'Lane {lanes_raw.index(lane_cars)}: {lane_cars}')
            self.can_separate_lanes = False

        else:
            lane_order_generators = [restart_order_generator]

        while not self.restart_ready.is_set():
            if self.sdk['SessionTime'] - session_time > self.reminder_frequency:
                if len(lane_order_generators[0].order) > 0 and (leader_speed_generator is None or leader != lane_order_generators[0].order[0]['CarNumber'] or leader not in [car['CarNumber'] for car in lane_order_generators[0].order]):
                    # New leader, we need a new speed generator
                    leader = lane_order_generators[0].order[0]['CarNumber']
                    leader_speed_generator = self.monitor_speed(leader)
                if leader_speed_generator is not None:
                    speed_km_per_hour = leader_speed_generator.__next__()
                for i in range(self.restart_lanes):
                    lane_order_generators[i].update_car_positions()
                    self.send_reminders(lane_order_generators[i])
                if speed_km_per_hour > self.max_speed_km:
                    self._chat(f'/{leader} Slow down to {self.max_speed_km} kph / {int(self.max_speed_km*0.621371)} mph.')
                session_time = self.sdk['SessionTime']
            self.sleep(0.1)


        self._chat('Get Ready, Code 69 will end soon.', race_control=True)
        self._chat('Get Ready, Code 69 will end soon.', race_control=True)
        throwaway_speed = leader_speed_generator.__next__() # Make sure we aren't using an average from a while ago
        while True:
            self._chat(f'/{leader} you control the field, go when ready')
            speed_km_per_hour = leader_speed_generator.__next__()
            if speed_km_per_hour > self.restart_speed:
                break
            self.sleep(0.5)

        for i in range(len(lane_order_generators)):
            lane_order_generators[i].update_order()
            self.logger.debug(lane_order_generators[i].order)

        self._chat('Green Flag!', race_control=True)
        self._chat('Green Flag!', race_control=True)
        self._chat('Green Flag!', race_control=True)

        for i in range(len(lane_order_generators)):
            if lane_order_generators[i].out_of_place_cars:
                for car, car_ahead in lane_order_generators[i].out_of_place_cars:
                    self._chat(f'/{car["CarNumber"]} RESTART VIOLATION will be investigated after the race.')

        self.busy_event.clear()
