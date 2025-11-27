import json
import os
import queue
import time

import discord
from ws4py.client.threadedclient import WebSocketClient

from modules.events import BaseEvent


class TextConsumerEvent(BaseEvent):
    """
    Consumes text messages to be displayed on the Broadcast through the SDKGaming Websocket
    """

    def __init__(
        self, password: str = "", room: str = "", test=False, sdk=False, *args, **kwargs
    ):
        self.password = password
        self.room = room
        super().__init__(sdk=sdk, *args, **kwargs)
        if test:
            self.broadcast_text_queue.put(
                {"title": "Race Control", "text": "A test message from Race Control"}
            )

    @staticmethod
    def ui(ident=""):
        import streamlit as st

        col1, col2 = st.columns(2)
        return {
            "password": col1.text_input("Password", key=f"{ident}password", value=""),
            "room": col2.text_input("Room", key=f"{ident}room", value=""),
            "test": col1.checkbox("Test", key=f"{ident}test", value=False),
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
            self.send(json.dumps({"role": "spotter", "secret": self.event.room}))
            self.event.logger.debug("WebSocket opened")

        def closed(self, code, reason=None):
            self.event.logger.debug("WebSocket closed")

        def received_message(self, message):
            self.event.logger.debug("Received message:", message)

    def send_message(self, text: dict):
        """
        Sends text to the queue.
        """
        client = self.WSC(self, "wss://livetiming2.sdk-gaming.co.uk/ws")
        client.connect()
        time.sleep(1)
        message = {
            "raceControlMessage": {
                "title": text["title"],
                "text": text["text"],
                "type": "information",
                "displayTime": "20",
                "password": self.password,
            }
        }
        client.send(json.dumps(message))
        time.sleep(1)
        client.close()


class DiscordTextConsumerEvent(TextConsumerEvent):
    """
    Consumes text messages to be displayed in a text channel in Discord.
    """

    def send_message(self, text: dict):
        # Create a discord client
        intents = discord.Intents.default()
        client = discord.Client(intents=intents)

        # Send a message to the channel
        @client.event
        async def on_ready():
            try:
                self.logger.debug(f"Logged on as {client.user}")
                channel = client.get_channel(int(self.room))
                message = f"# {text['title']}\n\n {text['text']}"
                await channel.send(message)
                self.logger.debug("Message sent")
            except Exception as e:
                self.logger.exception(e)
            finally:
                await client.close()
                self.logger.debug("Client closed")

        token = (
            self.password
            if self.password and self.password != ""
            else os.getenv("BOT_TOKEN")
        )
        client.run(token)

    @staticmethod
    def ui(ident=""):
        import streamlit as st

        col1, col2 = st.columns(2)
        return {
            "Token": col1.text_input("Token", key=f"{ident}password", value=""),
            "Text Channel ID": col2.text_input(
                "Text Channel ID", key=f"{ident}room", value=""
            ),
            "test": col1.checkbox("Test", key=f"{ident}test", value=False),
        }


class ATVOTextConsumerEvent(TextConsumerEvent):
    from enum import Enum

    class EntryIdType(Enum):
        CarIdx = 0
        CarNumber = 1
        CustomerId = 2

    class DecisionType(Enum):
        NoDecision = 0
        Cleared = 1
        NoFurtherAction = 2
        Warning = 3
        Penalty = 4

    class PenaltyTypes(Enum):
        NoPenalty = 0
        SwapPosition = 1
        DriveThrough = 2
        StopAndGo = 3
        TimePenalty = 4
        Disqualify = 5

    class MessageTypes(Enum):
        Unknown = 0
        Info = 1
        Warning = 2
        Penalty = 3
        Investigation = 4
        NoFurtherAction = 5
        ClearPenalty = 6

    @staticmethod
    def ui(ident=""):
        import streamlit as st

        col1, col2 = st.columns(2)
        return {
            "password": col1.text_input("Password", key=f"{ident}password", value=""),
            "test": col1.checkbox("Test", key=f"{ident}test", value=False),
        }

    def send_message(self, text: dict):
        """
        Sends text to the queue.
        """
        from requests import Session
        from signalr import Connection

        self.logger.debug("Sending message to ATVO")
        # create a connection
        connection = Connection("http://localhost:1337/signalr", Session())

        # get chat hub
        chat = connection.register_hub("RaceControlHub")

        # #start a connection
        connection.start()

        chat.server.invoke(
            "sendMessage",
            {
                "source": "Better Caution Bot",
                "type": "1",
                # 'entryId': 3, # Optional entry CarIdx, leave out if not related to anyone
                "sessionName": "Race",
                "header": text["title"],
                "text": text["text"],
            },
        )
