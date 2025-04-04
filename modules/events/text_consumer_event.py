import queue
from modules.events.base_event import BaseEvent
from ws4py.client.threadedclient import WebSocketClient
import json
import time

class TextConsumerEvent(BaseEvent):
    """
    Consumes text messages to be displayed on the Broadcast through the SDKGaming Websocket
    """
    def __init__(self, password: str = '', room: str = '', sdk=None, *args, **kwargs):
        self.password = password
        self.room = room
        self.text_queue = queue.Queue()
        super().__init__(sdk=sdk, *args, **kwargs)

    @staticmethod
    def ui(ident=''):
        import streamlit as st
        col1, col2 = st.columns(2)
        return {
            'user': col1.text_input("Password", key=f'{ident}password', value=''),
            'room': col2.text_input("Room", key=f'{ident}room', value=''),
        }

    def event_sequence(self):
        """
        Consumes text messages from the queue and sends them to the SDKGaming Websocket.
        """
        self.sdk.freeze_var_buffer_latest()
        while True:
            try:
                text = self.text_queue.get(False)
                self.send_message(text)
            except queue.Empty:
                pass
            self.sleep(5)

    def send_message(self, text: dict):
        """
        Sends text to the queue.
        """
        client = WebSocketClient('ws://livetiming.sdk-gaming.co.uk/ws')
        client.connect()
        client.send(json.dumps({'role': 'spotter', 'secret': self.room}))
        client.daemon = False
        client.connect()
        time.sleep(1)
        message = {
            'raceControlMessage': {
                'title': text['title'],
                'text': text['text'],
                'type': 'information',
                'displayTime': '20',
                'password': self.password
            }
        }
        client.send(json.dumps(message))
        time.sleep(1)
        client.close()