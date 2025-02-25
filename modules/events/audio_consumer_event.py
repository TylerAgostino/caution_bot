import queue
from modules.events.base_event import BaseEvent
import discord
from discord.ext import tasks
import os
import asyncio
from imageio_ffmpeg import get_ffmpeg_exe

# Replace with the path to your FFmpeg executable
module_path = os.path.dirname(os.path.dirname(os.path.dirname(os.path.realpath(__file__))))
FFMPEG_PATH = get_ffmpeg_exe()

class AudioConsumerEvent(BaseEvent):
    def __init__(self, vc_id, volume=1, sdk=None, *args, **kwargs):
        self.vc_id = int(vc_id)
        self.vc = None
        self.volume = volume
        super().__init__(sdk=sdk, *args, **kwargs)
        self.logger.debug(f'Voice Channel ID: {self.vc_id}')

    @staticmethod
    def ui(ident=''):
        import streamlit as st
        col1, col2, col3 = st.columns(3)
        return {
            'vc_id': col1.text_input("Discord Voice Channel ID", "1057329833278976160", key=f'{ident}discord_vc_id'),
            'volume': col2.slider("Discord Volume", 0.0, 2.0, 1.5, key=f'{ident}discord_volume')
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
            source = discord.PCMVolumeTransformer(discord.FFmpegPCMAudio(fname, executable=FFMPEG_PATH), volume=self.volume)
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
