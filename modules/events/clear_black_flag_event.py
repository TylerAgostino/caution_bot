from modules.events.base_event import BaseEvent

class ClearBlackFlagEvent(BaseEvent):
    def __init__(self, interval: int = 5, audio: bool = False):
        super().__init__()
        self.interval = int(interval)
        self.audio = audio

    @staticmethod
    def ui(ident='', defaults=None):
        import streamlit as st
        col1, col2, col3, _ = st.columns([1, 1, 1, 3])
        if not defaults or defaults == {}:
            defaults = {
                'interval': 5,
                'audio': False
            }
        return {
            'interval': st.text_input(label_visibility='collapsed', label="interval", key=f'{ident}interval', value=defaults['interval']),
            'audio': st.checkbox('Audio', key=f'{ident}audio', value=defaults['audio'])
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