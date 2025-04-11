from modules.events.random_timed_event import TimedEvent

class SprintRaceDQEvent(TimedEvent):
    def __init__(self, cars, penalty, *args, **kwargs):
        self.cars = cars
        self.penalty = penalty
        self.reason = self.generate_random_black_flag_reason()
        super().__init__(*args, **kwargs)

    def event_sequence(self):
        self._chat(f'Black Flag: {self.reason}', race_control=True)
        if isinstance(self.cars, str):
            cars = self.cars.split(',')
        else:
            cars = self.cars
        for car in cars:
            self._chat(f'!bl {car} {self.penalty}')

    @staticmethod
    def ui(ident=''):
        import streamlit as st
        import uuid
        return {
            'event_time': st.number_input("Event Time (min)", value=-1, key=f'{ident}event_time'),
            'cars': st.text_input('Car # (comma separated)', key=f'{ident}dq_cars', value='19,99'),
            'penalty': st.text_input('Penalty', key=f'{ident}dq_penalty', value='L2')
        }