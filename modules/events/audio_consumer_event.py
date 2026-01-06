import asyncio
import os
import queue

import discord
from discord.ext import tasks
from imageio_ffmpeg import get_ffmpeg_exe

from modules.events import BaseEvent

FFMPEG_PATH = get_ffmpeg_exe()


class AudioConsumerEvent(BaseEvent):
    def __init__(
        self, vc_id, volume=1, token="", hello=True, sdk=False, *args, **kwargs
    ):
        self.vc_id = int(vc_id)
        self.vc = None
        self.volume = volume
        self.hello = hello
        self.token = token
        super().__init__(sdk=sdk, *args, **kwargs)
        self.logger.debug(f"Voice Channel ID: {self.vc_id}")

    def event_sequence(self):
        # Set up the bot
        self.logger.debug("Setting up the bot.")
        intents = discord.Intents.default()
        intents.message_content = True
        bot = discord.Client(intents=intents)

        self.logger.debug("Setting methods.")

        async def play(message=None):
            fname = os.path.join(os.getcwd(), "audio", f"{message}.mp3")
            # if it's a directory, grab a random file
            if os.path.isdir(fname.removesuffix(".mp3")):
                import random

                files = os.listdir(fname.removesuffix(".mp3"))
                fname = os.path.join(fname.removesuffix(".mp3"), random.choice(files))
            if not os.path.exists(fname):
                self.logger.error(f"File {fname} does not exist.")
                return

            source = discord.PCMVolumeTransformer(
                discord.FFmpegPCMAudio(fname, executable=FFMPEG_PATH),
                volume=float(self.volume),
            )
            self.vc.play(source)
            while self.vc.is_playing():
                await asyncio.sleep(0.01)

        @tasks.loop(seconds=0.1)
        async def auto_play():
            try:
                text = self.audio_queue.get(False)
                await play(text)
            except queue.Empty:
                pass
            self.sleep(0)

        @bot.event
        async def on_ready():
            voice_channel = bot.get_channel(int(self.vc_id))
            if not voice_channel.guild.voice_client:
                self.vc = await voice_channel.connect()
            else:
                self.vc = voice_channel.guild.voice_client
            print(f"Logged in as {bot.user}")

            if self.hello:
                await play("hello")

            auto_play.start()

        self.logger.debug("Running bot.")

        token = (
            self.token if self.token and self.token != "" else os.getenv("BOT_TOKEN")
        )
        bot.run(token)
