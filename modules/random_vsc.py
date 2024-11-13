from modules.random_timed_event import RandomTimedEvent


class RandomVSC(RandomTimedEvent):
    def __init__(self,
                 restart_proximity: int = None,
                 max_vsc_duration: int = None,
                 max_laps_behind_leader: int = 3,
                 wave_arounds: bool = False,
                 notify_on_skipped_caution: bool = False,
                 *args, **kwargs):
        self.restart_proximity = int(restart_proximity)
        self.max_vsc_duration = int(max_vsc_duration)
        self.max_laps_behind_leader = int(max_laps_behind_leader)
        self.wave_arounds = wave_arounds
        self.notify_on_skipped_caution = notify_on_skipped_caution
        super().__init__(*args, **kwargs)

    def event_sequence(self):
        if self.is_caution_active() or self.busy_event.is_set():
            if self.notify_on_skipped_caution:
                self._chat('Additional caution skipped due to active caution.')
            return

        self.busy_event.set()

        # notify that a VSC will start at the end of the current lap
        self._chat('VSC will begin at the Start/Finish Line')
        self._chat('VSC will begin at the Start/Finish Line')
        self._chat('VSC will begin at the Start/Finish Line')

        # wait for each car to cross the timing line and note their position
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

        # announce the end of the VSC
        self._chat('The field has formed up and the VSC will end soon.')

        correct_order = [f'{car["CarNumber"]}' for car in restart_order]
        actual_order = [f'{car["CarNumber"]}' for car in self.get_current_running_order(self.max_laps_behind_leader)]

        for i in range(len(correct_order)):
            if correct_order[i] != actual_order[i]:
                message = f'Car {correct_order[i]} incorrect position. Should be behind {correct_order[i-1]} and in front of {correct_order[i+1]}.'
                self.logger.warning(message)
                self._chat(message)

        self.logger.info(f'Correct restart order: {correct_order}')
        self.logger.info(f'VSC has ended. Restart order: {actual_order}')

        self.busy_event.clear()

    def ready_to_restart(self):
        runners = self.get_current_running_order(self.max_laps_behind_leader)
        last_runner = runners[-1]
        leader = runners[0]
        if leader['LapDistPct'] - last_runner['LapDistPct'] < self.restart_proximity:
            return True

    def car_has_completed_lap(self, car, last_lap, this_lap):
        last_lap_record = [record for record in last_lap if record['CarIdx'] == car['CarIdx']][0]
        this_lap_record = [record for record in this_lap if record['CarIdx'] == car['CarIdx']][0]
        if this_lap_record['LapCompleted'] > last_lap_record['LapCompleted']:
            return True
        else:
            return False

    def car_has_left_pits(self, car, last_lap, this_lap):
        last_lap_record = [record for record in last_lap if record['CarIdx'] == car['CarIdx']][0]
        this_lap_record = [record for record in this_lap if record['CarIdx'] == car['CarIdx']][0]
        if this_lap_record['InPits'] == 0 and last_lap_record['InPits'] == 1:
            return True