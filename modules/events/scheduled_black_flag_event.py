from modules.events import TimedEvent


class SprintRaceDQEvent(TimedEvent):
    def __init__(self, cars, penalty, *args, **kwargs):
        self.cars = cars
        self.penalty = penalty
        self.reason = self.generate_random_black_flag_reason()
        super().__init__(*args, **kwargs)

    def event_sequence(self):
        self._chat(f"Black Flag: {self.reason}", race_control=True)
        if isinstance(self.cars, str):
            cars = self.cars.split(",")
        else:
            cars = self.cars
        for car in cars:
            self._chat(f"!bl {car} {self.penalty}")
