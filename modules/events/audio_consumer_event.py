import queue
from modules.events import BaseEvent
import discord
from discord.ext import tasks
import os
import asyncio
from imageio_ffmpeg import get_ffmpeg_exe

# Replace with the path to your FFmpeg executable
module_path = os.path.dirname(os.path.dirname(os.path.dirname(os.path.realpath(__file__))))
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
        self.logger.debug(f'Voice Channel ID: {self.vc_id}')

    @staticmethod
    def ui(ident=''):
        import streamlit as st
        col1, col2 = st.columns(2)
        return {
            'vc_id': col1.text_input("Discord Voice Channel ID", key=f'{ident}vc_id', value='420037391882125313'),
            'volume': col2.slider("Discord Volume", min_value=0.0, max_value=2.0, key=f'{ident}volume'),
            'token': col1.text_input("Bot Token (optional)", key=f'{ident}token', value=''),
            'hello': col2.checkbox("Play Hello on Connect", key=f'{ident}hello', value=True),
        }

    def event_sequence(self):
        # Set up the bot
        self.logger.debug('Setting up the bot.')
        intents = discord.Intents.default()
        intents.message_content = True
        bot = discord.Client(intents=intents)

        self.logger.debug('Setting methods.')

        async def play(message=None):
            fname = os.path.join(module_path, 'audio', f'{message}.mp3')
            # if it's a directory, grab a random file
            if os.path.isdir(fname.removesuffix('.mp3')):
                import random
                files = os.listdir(fname.removesuffix('.mp3'))
                fname = os.path.join(fname.removesuffix('.mp3'), random.choice(files))
            if not os.path.exists(fname):
                self.logger.error(f'File {fname} does not exist.')
                return

            source = discord.PCMVolumeTransformer(discord.FFmpegPCMAudio(fname, executable=FFMPEG_PATH), volume=float(self.volume))
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
                await play('hello')

            auto_play.start()

        self.logger.debug('Running bot.')

        token = self.token if self.token and self.token != '' else os.getenv('BOT_TOKEN')
        bot.run(token)
