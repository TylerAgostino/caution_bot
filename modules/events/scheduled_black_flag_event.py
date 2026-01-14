from modules.events import TimedEvent


class SprintRaceDQEvent(TimedEvent):
    def __init__(self, cars, penalty, *args, **kwargs):
        self.cars = cars
        self.penalty = penalty
        super().__init__(*args, **kwargs)

    def event_sequence(self):
        if isinstance(self.cars, str):
            cars = self.cars.split(",")
        else:
            cars = self.cars
        for car in cars:
            self._chat(f"!bl {car} {self.penalty}")
