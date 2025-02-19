import queue

from modules.events.base_event import BaseEvent
import random
import pytchat
from yapper import PiperSpeaker, PiperVoiceUS
import discord
from discord.ext import tasks
import os
import asyncio
import time
from tempfile import NamedTemporaryFile

# Replace with the path to your FFmpeg executable
FFMPEG_PATH = "C:\\Users\\sniff\\miniconda3\\Lib\\site-packages\\imageio_ffmpeg\\binaries\\ffmpeg-win64-v4.2.2.exe"

class AudioConsumerEvent(BaseEvent):
    def __init__(self, vc_id, sdk=None, *args, **kwargs):
        self.vc_id = vc_id
        self.vc = None
        super().__init__(sdk=sdk, *args, **kwargs)
        self.logger.debug(f'Voice Channel ID: {self.vc_id}')

    def event_sequence(self):
        # Set up the bot
        self.logger.debug('Setting up the bot.')
        intents = discord.Intents.default()
        intents.message_content = True
        bot = discord.Client(intents=intents)

        self.logger.debug('Setting methods.')

        async def play(message=None):
            fname = f"C:\\Users\\sniff\\IdeaProjects\\Better Caution Bot\\audio\\{message}.mp3"
            source = discord.PCMVolumeTransformer(discord.FFmpegPCMAudio(fname, executable=FFMPEG_PATH), volume=2.0)
            self.vc.play(source)
            while self.vc.is_playing():
                await asyncio.sleep(1)

        @tasks.loop(seconds=1)
        async def auto_play():
            try:
                text = self.audio_queue.get(False)
                await play(text)
            except queue.Empty:
                pass
            self.sleep(1)

        @bot.event
        async def on_ready():
            voice_channel = bot.get_channel(self.vc_id)
            if not voice_channel.guild.voice_client:
                self.vc = await voice_channel.connect()
            else:
                self.vc = voice_channel.guild.voice_client
            print(f"Logged in as {bot.user}")

            await play('hello')

            auto_play.start()

        self.logger.debug('Running bot.')

        bot.run(os.getenv('BOT_TOKEN'))
