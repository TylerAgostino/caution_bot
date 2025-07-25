from modules.events import BaseEvent

class ClearBlackFlagEvent(BaseEvent):
    def __init__(self, interval: int = 5, audio: bool = False):
        super().__init__()
        self.interval = int(interval)
        self.audio = audio

    @staticmethod
    def ui(ident=''):
        import streamlit as st
        col1, col2, col3, _ = st.columns([1, 1, 1, 3])
        return {
            'interval': col1.number_input(label="Interval", key=f'{ident}interval', value=5),
            'audio': col2.checkbox('Audio', key=f'{ident}audio', value=False)
        }

    def event_sequence(self):
        while True:
            flags = [hex(flag)[-5:-4] != '4' and hex(flag)[-5:-4] != '0' and flag!=0 for flag in self.sdk['CarIdxSessionFlags']]
            if any(flags):
                self.logger.debug(flags)
                self._chat('!clearall')
                if self.audio:
                    self.audio_queue.put('clearall')
            self.sleep(self.interval)
