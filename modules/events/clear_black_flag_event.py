from modules.events import BaseEvent

class ClearBlackFlagEvent(BaseEvent):
    def __init__(self, interval: int = 5):
        super().__init__()
        self.interval = int(interval)

    @staticmethod
    def ui(ident=''):
        import streamlit as st
        col1, col2, col3, _ = st.columns([1, 1, 1, 3])
        return {
            'interval': col1.number_input(label="Interval", key=f'{ident}interval', value=1)
        }

    def event_sequence(self):
        while True:
            flags = [any(flag & x for x in [self.Flags.black, self.Flags.furled, self.Flags.disqualify]) for flag in self.sdk['CarIdxSessionFlags']]
            if any(flags):
                self._chat('!clearall')
            self.sleep(self.interval)
