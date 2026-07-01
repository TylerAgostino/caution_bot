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
        self,
        vc_id,
        volume=1,
        token="",
        hello=True,
        lock_mic_on_start_lights=True,
        sdk=False,
        *args,
        **kwargs,
    ):
        self.vc_id = int(vc_id)
        self.vc = None
        self.voice_channel = None
        self.volume = volume
        self.hello = hello
        self.token = token
        # When enabled, the bot will deny the "speak" permission for everyone
        # in the voice channel while the iRacing starting lights are showing
        # (start_ready, start_set, start_go), then restore the original
        # permissions once the starting sequence is over. Members can still
        # stay connected; they simply can't transmit audio (open mic or PTT).
        self.lock_mic_on_start_lights = lock_mic_on_start_lights
        self._mic_locked = False
        self._original_overwrites = None
        super().__init__(sdk=sdk, *args, **kwargs)
        self.logger.debug(f"Voice Channel ID: {self.vc_id}")

    def _start_lights_active(self):
        """
        Checks whether the iRacing starting lights are currently showing
        (start_ready, start_set, or start_go).

        Returns:
            bool: True if one of the starting-light flags is active.
        """
        if not self.sdk:
            return False
        flags = self.sdk["SessionFlags"]
        if not flags:
            self.logger.debug("Might be a replay")
            return False
        return any(
            flags & flag  # pyright: ignore[reportOperatorIssue]
            for flag in (
                self.Flags.start_ready,
                self.Flags.start_set,
                self.Flags.start_go,
            )
        )

    async def lock_voice_channel(self, channel=None):
        """
        Notes the given voice channel's current permission overwrites, then
        denies the "speak" permission for everyone so nobody can transmit
        audio (whether using open mic or push-to-talk) while still allowing
        them to remain connected to the call.

        Args:
            channel: The voice channel to lock. Defaults to
                ``self.voice_channel`` (the channel the bot is connected to).

        Returns:
            The channel object reflecting the post-edit state (or the
            original channel if no edit was made).
        """
        channel = channel or self.voice_channel  # pyright: ignore[reportAttributeAccessIssue]
        if self._mic_locked or channel is None:
            return channel
        try:
            original_overwrites = channel.overwrites
            muted_overwrites = {
                target: discord.PermissionOverwrite.from_pair(*overwrite.pair())
                for target, overwrite in original_overwrites.items()
            }
            everyone = channel.guild.default_role
            everyone_overwrite = muted_overwrites.setdefault(
                everyone, discord.PermissionOverwrite()
            )
            for overwrite in muted_overwrites.values():
                overwrite.speak = False
            everyone_overwrite.speak = False

            self._original_overwrites = original_overwrites
            edited = await channel.edit(
                overwrites=muted_overwrites,
                reason="iRacing starting lights active: muting voice channel.",
            )
            channel = edited or channel
            if self.voice_channel is not None:
                self.voice_channel = channel
            self._mic_locked = True
            self.logger.info(
                f"Starting lights active. Muted speak permission in "
                f"'{channel.name}'."
            )
        except discord.Forbidden:
            self.logger.error(
                "Missing permissions to update voice channel permissions "
                "for the start-lights mic lock."
            )
        except Exception:
            self.logger.exception(
                "Failed to lock voice channel permissions for start lights."
            )
        return channel

    async def unlock_voice_channel(self, channel=None):
        """
        Restores the given voice channel's original permission overwrites
        that were noted before the mic lock was applied.

        Args:
            channel: The voice channel to unlock. Defaults to
                ``self.voice_channel`` (the channel the bot is connected to).

        Returns:
            The channel object reflecting the post-edit state (or the
            original channel if no edit was made).
        """
        channel = channel or self.voice_channel  # pyright: ignore[reportAttributeAccessIssue]
        if not self._mic_locked or channel is None:
            return channel
        try:
            edited = await channel.edit(
                overwrites=self._original_overwrites or {},
                reason="iRacing starting lights over: restoring voice channel permissions.",
            )
            channel = edited or channel
            if self.voice_channel is not None:
                self.voice_channel = channel
            self.logger.info(
                f"Starting lights over. Restored permissions in "
                f"'{channel.name}'."
            )
        except discord.Forbidden:
            self.logger.error(
                "Missing permissions to restore voice channel permissions "
                "after the start-lights mic lock."
            )
        except Exception:
            self.logger.exception(
                "Failed to restore voice channel permissions after start lights."
            )
        finally:
            self._mic_locked = False
            self._original_overwrites = None
        return channel

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
            self.vc.play(source)  # pyright: ignore[reportAttributeAccessIssue]
            while self.vc.is_playing():  # pyright: ignore[reportAttributeAccessIssue]
                await asyncio.sleep(0.01)

        @tasks.loop(seconds=0.1)
        async def auto_play():
            try:
                self.sleep(0)
                text = self.audio_queue.get(False)
                await play(text)
            except queue.Empty:
                pass
            except KeyboardInterrupt:
                await bot.close()
                raise

        @tasks.loop(seconds=0.25)
        async def monitor_start_lights():
            try:
                self.sleep(0)
                if self._start_lights_active():
                    await self.lock_voice_channel()
                elif self._mic_locked:
                    await self.unlock_voice_channel()
            except KeyboardInterrupt:
                if self._mic_locked:
                    await self.unlock_voice_channel()
                await bot.close()
                raise

        @bot.event
        async def on_ready():
            voice_channel = bot.get_channel(int(self.vc_id))
            if voice_channel is None:
                self.logger.error(f"Voice channel with ID {self.vc_id} not found.")
                return
            if not isinstance(voice_channel, discord.channel.VocalGuildChannel):
                self.logger.error(
                    f"Channel with ID {self.vc_id} is not a voice channel."
                )
                return
            self.voice_channel = voice_channel
            if not voice_channel.guild.voice_client:
                self.vc = await voice_channel.connect()
            else:
                self.vc = voice_channel.guild.voice_client
            print(f"Logged in as {bot.user}")

            if self.hello:
                await play("hello")

            auto_play.start()

            if self.lock_mic_on_start_lights:
                monitor_start_lights.start()

        self.logger.debug("Running bot.")

        token = (
            self.token
            if self.token and self.token != ""
            else os.getenv("BOT_TOKEN", "")
        )
        bot.run(token)
