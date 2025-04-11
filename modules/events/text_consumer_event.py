import queue
from modules.events.base_event import BaseEvent
from ws4py.client.threadedclient import WebSocketClient
import json
import time

class TextConsumerEvent(BaseEvent):
    """
    Consumes text messages to be displayed on the Broadcast through the SDKGaming Websocket
    """
    def __init__(self, password: str = '', room: str = '', test=False, sdk=None, *args, **kwargs):
        self.password = password
        self.room = room
        super().__init__(sdk=sdk, *args, **kwargs)
        if test:
            self.broadcast_text_queue.put({
                'title': 'Race Control',
                'text': 'A'
            })

    @staticmethod
    def ui(ident=''):
        import streamlit as st
        col1, col2 = st.columns(2)
        return {
            'password': col1.text_input("Password", key=f'{ident}password', value=''),
            'room': col2.text_input("Room", key=f'{ident}room', value=''),
            'test': col1.checkbox("Test", key=f'{ident}test', value=False)
        }

    def event_sequence(self):
        """
        Consumes text messages from the queue and sends them to the SDKGaming Websocket.
        """
        while True:
            try:
                text = self.broadcast_text_queue.get(False)
                self.send_message(text)
            except queue.Empty:
                pass
            self.sleep(5)

    class WSC(WebSocketClient):
        """
        WebSocket client for the SDKGaming Websocket.
        """
        def __init__(self, event, *args, **kwargs):
            self.event = event
            super().__init__(*args, **kwargs)
        def opened(self):
            self.send(json.dumps({'role': 'spotter', 'secret': self.event.room}))
            self.event.logger.debug('WebSocket opened')

        def closed(self, code, reason=None):
            self.event.logger.debug("WebSocket closed")

        def received_message(self, message):
            self.event.logger.debug("Received message:", message)

    def send_message(self, text: dict):
        """
        Sends text to the queue.
        """
        client = self.WSC(self, 'wss://livetiming2.sdk-gaming.co.uk/ws')
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