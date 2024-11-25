from modules.events.random_timed_event import RandomTimedEvent
import threading

class RandomCode60Event(RandomTimedEvent):
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

    def __init__(self, wave_arounds=False, notify_on_skipped_caution=False, max_speed_km = 60, restart_speed_pct=150,
                 restart_lanes=2, separate_classes=False, *args, **kwargs):
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
        self.double_file = False
        self.reminder_frequency = 8
        self.restart_speed = self.max_speed_km * (int(restart_speed_pct) / 100)
        super().__init__(*args, **kwargs)
        self.reason = self.generate_random_caution_reason()

    def event_sequence(self):
        """
        Executes the event sequence for a random Code 60.
        """
        if self.is_caution_active() or self.busy_event.is_set():
            if self.notify_on_skipped_caution:
                self._chat('Additional caution skipped due to active caution.', race_control=True)
            return

        self.busy_event.set()
        self.restart_ready.clear()
        # self._chat(self.reason, race_control=True)
        self._chat('Code 60 will begin at the Start/Finish Line', race_control=True)

        last_step = self.get_current_running_order()
        session_time = self.sdk['SessionTimeRemain']

        # wait for someone to start the next lap
        lead_lap = max([car['LapCompleted'] for car in last_step])
        while not any([car['LapCompleted'] > lead_lap for car in self.get_current_running_order()]):
            if session_time - self.sdk['SessionTimeRemain'] > self.reminder_frequency:
                self._chat('Code 60 will begin at the Start/Finish Line', race_control=True)
                session_time = self.sdk['SessionTimeRemain']
            self.sleep(1)

        self._chat('Double Yellow Flags in Sector 1', race_control=True)

        leader = None
        speed_km_per_hour = 0
        leader_speed_generator = None
        restart_order_generator = self.generate_restart_order()
        correct_order = []

        while not self.ready_to_restart():
            correct_order = restart_order_generator.__next__()

            running_order_uncorrected = self.get_current_running_order()
            running_order_lap_down_corrected = sorted(running_order_uncorrected, key=lambda x: int(2 if x['total_completed']>max([l['total_completed']-1 for l in running_order_uncorrected]) else 1) + x['total_completed']/1000, reverse=True)
            actual_order = [car['CarNumber'] for car in running_order_lap_down_corrected if car['CarNumber'] in correct_order]

            # Check the leader's speed
            if len(correct_order) > 0 and (leader_speed_generator is None or leader != correct_order[0]):
                # New leader
                leader = correct_order[0]
                leader_speed_generator = self.monitor_speed(leader)
            if leader_speed_generator is not None:
                speed_km_per_hour = leader_speed_generator.__next__()

            # Send reminders
            if session_time - self.sdk['SessionTimeRemain'] > self.reminder_frequency:
                # Update the wrong positions
                # Gives a map of car number to a list of cars that should be in front of it but are behind it
                wrong_positions = {car: [c for c in actual_order[actual_order.index(car) + 1:] if car in correct_order[:correct_order.index(car)]] for car in actual_order}

                for car, cars_incorrectly_behind in wrong_positions.items():
                    if cars_incorrectly_behind:
                        session_time = self.sdk['SessionTimeRemain']
                        self.logger.warning(f'Car {car} ahead of cars {cars_incorrectly_behind} when they should be behind.')
                        self._chat(f'/{car} let the {", ".join(cars_incorrectly_behind)} car{'s' if len(cars_incorrectly_behind)>1 else ''} by.')
                        for passed_car in cars_incorrectly_behind:
                            self._chat(f'/{passed_car} pass the {car} car.')

                if speed_km_per_hour > self.max_speed_km:
                    session_time = self.sdk['SessionTimeRemain']
                    self._chat(f'/{leader} Slow down to {self.max_speed_km} kph / {int(self.max_speed_km*0.621371)} mph.')

            self.sleep(1)

        if self.double_file:
            self.restart_ready.clear()
            self._chat('Double File Restart', race_control=True)
            restart_order_lanes = self.multi_lane_restart(correct_order, lanes=2, lane_names=['LEFT', 'RIGHT'],
                                    restart_flag=self.restart_ready, reminder_frequency=self.reminder_frequency)
        else:
            restart_order_lanes = [correct_order]

        self._chat('Get Ready, Code 60 will end soon.', race_control=True)
        self._chat('Get Ready, Code 60 will end soon.', race_control=True)
        throwaway_speed = leader_speed_generator.__next__() # Make sure we aren't using an average from a while ago
        self.sleep(0.5)
        while True:
            self._chat(f'/{leader} you control the field, go when ready')
            speed_km_per_hour = leader_speed_generator.__next__()
            if speed_km_per_hour > self.restart_speed:
                break
            self.sleep(0.5)

        order_at_green = self.get_current_running_order()

        self._chat('Green Flag!', race_control=True)
        self._chat('Green Flag!', race_control=True)
        self._chat('Green Flag!', race_control=True)


        for lane in restart_order_lanes:
            for car in lane:
                cars_incorrectly_behind = [car['CarNumber'] for car in order_at_green[order_at_green.index(car)] if car['CarNumber'] in lane[lane.index(car)+1:]]
                if cars_incorrectly_behind:
                    self.logger.error(f'Car {car} restarted ahead of cars {cars_incorrectly_behind}.')
                    self._chat(f'/{car} Restart violation will be investigated after the race.')

        self.busy_event.clear()

    def ready_to_restart(self):
        """
        Checks if the field is ready to restart.

        Returns:
            bool: True if the field is ready to restart, False otherwise.
        """
        return self.restart_ready.is_set()

