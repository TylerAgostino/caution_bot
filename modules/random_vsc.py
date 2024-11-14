from modules.random_timed_event import RandomTimedEvent

class RandomVSC(RandomTimedEvent):
    """
    A class to represent a random Virtual Safety Car (VSC) event in the iRacing simulator.

    Attributes:
        restart_proximity (int): Proximity threshold for restarting the race.
        max_vsc_duration (int): Maximum duration for the VSC.
        max_laps_behind_leader (int): Maximum laps a car can be behind the leader.
        wave_arounds (bool): Flag to indicate if wave arounds are allowed.
        notify_on_skipped_caution (bool): Flag to indicate if notifications should be sent when a caution is skipped.
    """

    def __init__(self, restart_proximity=None, max_vsc_duration=None, max_laps_behind_leader=3, wave_arounds=False, notify_on_skipped_caution=False, *args, **kwargs):
        """
        Initializes the RandomVSC class.

        Args:
            restart_proximity (int, optional): Proximity threshold for restarting the race. Defaults to None.
            max_vsc_duration (int, optional): Maximum duration for the VSC. Defaults to None.
            max_laps_behind_leader (int, optional): Maximum laps a car can be behind the leader. Defaults to 3.
            wave_arounds (bool, optional): Flag to indicate if wave arounds are allowed. Defaults to False.
            notify_on_skipped_caution (bool, optional): Flag to indicate if notifications should be sent when a caution is skipped. Defaults to False.
        """
        self.restart_proximity = int(restart_proximity)
        self.max_vsc_duration = int(max_vsc_duration)
        self.max_laps_behind_leader = int(max_laps_behind_leader)
        self.wave_arounds = wave_arounds
        self.notify_on_skipped_caution = notify_on_skipped_caution
        super().__init__(*args, **kwargs)

    def event_sequence(self):
        """
        Executes the event sequence for a random VSC.
        """
        if self.is_caution_active() or self.busy_event.is_set():
            if self.notify_on_skipped_caution:
                self._chat('Additional caution skipped due to active caution.')
            return

        self.busy_event.set()
        self._chat('VSC will begin at the Start/Finish Line')

        restart_order = []
        last_lap = self.get_current_running_order(self.max_laps_behind_leader)
        while not self.ready_to_restart():
            this_lap = self.get_current_running_order(self.max_laps_behind_leader)
            for car in this_lap:
                if self.car_has_completed_lap(car, last_lap, this_lap) and not self.sdk['CarIdxOnPitRoad'][car['CarIdx']]:
                    restart_order.append(car)
                    self.logger.debug(f'Added {car["CarNumber"]} to restart order (completed lap).')
                if self.car_has_left_pits(car, last_lap, this_lap):
                    restart_order.append(car)
                    self.logger.debug(f'Added {car["CarNumber"]} to restart order (left pits).')
            last_lap = this_lap

        self._chat('The field has formed up and the VSC will end soon.')

        correct_order = [car['CarNumber'] for car in restart_order]
        actual_order = [car['CarNumber'] for car in self.get_current_running_order(self.max_laps_behind_leader)]

        for i in range(len(correct_order)):
            if correct_order[i] != actual_order[i]:
                message = f'Car {correct_order[i]} incorrect position. Should be behind {correct_order[i-1]} and in front of {correct_order[i+1]}.'
                self.logger.warning(message)
                self._chat(message)

        self.logger.info(f'Correct restart order: {correct_order}')
        self.logger.info(f'VSC has ended. Restart order: {actual_order}')

        self.busy_event.clear()

    def ready_to_restart(self):
        """
        Checks if the field is ready to restart.

        Returns:
            bool: True if the field is ready to restart, False otherwise.
        """
        runners = self.get_current_running_order(self.max_laps_behind_leader)
        return runners[0]['LapDistPct'] - runners[-1]['LapDistPct'] < self.restart_proximity

    def car_has_completed_lap(self, car, last_lap, this_lap):
        """
        Checks if a car has completed a lap.

        Args:
            car (dict): The car to check.
            last_lap (list): The running order of the last lap.
            this_lap (list): The running order of the current lap.

        Returns:
            bool: True if the car has completed a lap, False otherwise.
        """
        last_lap_record = next(record for record in last_lap if record['CarIdx'] == car['CarIdx'])
        this_lap_record = next(record for record in this_lap if record['CarIdx'] == car['CarIdx'])
        return this_lap_record['LapCompleted'] > last_lap_record['LapCompleted']

    def car_has_left_pits(self, car, last_lap, this_lap):
        """
        Checks if a car has left the pits.

        Args:
            car (dict): The car to check.
            last_lap (list): The running order of the last lap.
            this_lap (list): The running order of the current lap.

        Returns:
            bool: True if the car has left the pits, False otherwise.
        """
        last_lap_record = next(record for record in last_lap if record['CarIdx'] == car['CarIdx'])
        this_lap_record = next(record for record in this_lap if record['CarIdx'] == car['CarIdx'])
        return this_lap_record['InPits'] == 0 and last_lap_record['InPits'] == 1