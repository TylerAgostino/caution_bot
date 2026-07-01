"""
test_audio_consumer_permissions_live.py -- Live Discord integration test for
AudioConsumerEvent's start-lights mic lock
=============================================================================

Unlike ``test_audio_consumer_event.py`` (which mocks the iRacing SDK so no
sim is needed), this test exercises the *Discord permission* side of the
feature against a **real** voice channel. It logs in with a real bot token,
snapshots the channel's current permission overwrites, calls
``AudioConsumerEvent.lock_voice_channel()`` / ``unlock_voice_channel()``
directly (bypassing ``event_sequence()`` / iRacing entirely), and asserts
that:

  * Locking denies ``speak`` for ``@everyone`` (and every other existing
    overwrite) while leaving ``connect`` untouched.
  * Unlocking restores the channel's permission overwrites to exactly what
    they were before locking.

Requirements to run this test
------------------------------
This test is **skipped by default** because it needs real credentials and a
real channel to operate on. To run it, set these environment variables
before invoking pytest:

    DISCORD_TEST_BOT_TOKEN   A bot token with "Manage Roles" (or
                              "Manage Permissions") on the target channel.
                              Falls back to BOT_TOKEN if unset.
    DISCORD_TEST_VC_ID       The ID of a voice channel the bot can see and
                              manage permissions for. Use a disposable/test
                              channel -- while this test cleans up after
                              itself, an aborted run could leave the channel
                              muted for everyone until manually restored.

Example::

    DISCORD_TEST_BOT_TOKEN=... DISCORD_TEST_VC_ID=123456789012345678 \\
        python -m pytest tests/test_audio_consumer_permissions_live.py -v
"""

import asyncio
import os
import sys
from pathlib import Path

import discord
import pytest

# Ensure the project root (parent of this tests/ directory) is on sys.path
# so that `modules` is importable regardless of how the script is launched.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from modules.events.audio_consumer_event import AudioConsumerEvent  # noqa: E402

TOKEN = os.getenv("DISCORD_TEST_BOT_TOKEN") or os.getenv("BOT_TOKEN")
VC_ID_RAW = os.getenv("DISCORD_TEST_VC_ID")

pytestmark = pytest.mark.skipif(
    not TOKEN or not VC_ID_RAW,
    reason=(
        "Live Discord permissions test requires DISCORD_TEST_BOT_TOKEN "
        "(or BOT_TOKEN) and DISCORD_TEST_VC_ID environment variables "
        "pointing at a real bot/voice channel with Manage Roles access."
    ),
)


class _ChannelFetcher(discord.Client):
    """Minimal client used only to log in and grab one channel by ID."""

    def __init__(self, target_vc_id: int, **kwargs):
        super().__init__(**kwargs)
        self.target_vc_id = target_vc_id
        self.channel = None
        self.ready_event = asyncio.Event()

    async def on_ready(self):
        self.channel = self.get_channel(self.target_vc_id)
        self.ready_event.set()


async def _connect_and_fetch_channel(token: str, vc_id: int):
    """Log in with *token* and return ``(client, task, channel)``.

    The caller is responsible for calling ``client.close()`` and awaiting
    ``task`` when finished.
    """
    intents = discord.Intents.default()
    client = _ChannelFetcher(vc_id, intents=intents)
    task = asyncio.create_task(client.start(token))
    ready_wait = asyncio.create_task(client.ready_event.wait())
    done, _pending = await asyncio.wait(
        {ready_wait, task}, timeout=30, return_when=asyncio.FIRST_COMPLETED
    )

    if ready_wait not in done:
        ready_wait.cancel()
        if task in done:
            exc = task.exception()
            await client.close()
            if exc is not None:
                raise RuntimeError(f"Discord client failed to start: {exc}") from exc
            raise RuntimeError("Discord client exited before becoming ready.")
        task.cancel()
        await client.close()
        raise RuntimeError("Timed out waiting for the Discord bot to become ready.")

    if client.channel is None:
        await client.close()
        await task
        raise RuntimeError(
            f"Voice channel {vc_id} was not found (or is not visible to the bot)."
        )
    if not isinstance(client.channel, discord.channel.VocalGuildChannel):
        await client.close()
        await task
        raise RuntimeError(f"Channel {vc_id} is not a voice channel.")

    return client, task, client.channel


def _snapshot_overwrites(channel) -> dict:
    """Return a comparable snapshot of a channel's permission overwrites."""
    return {
        target.id: overwrite.pair() for target, overwrite in channel.overwrites.items()
    }


async def _lock_unlock_roundtrip():
    assert TOKEN is not None and VC_ID_RAW is not None  # enforced by skipif above
    client, task, channel = await _connect_and_fetch_channel(TOKEN, int(VC_ID_RAW))
    event = None
    try:
        # sdk=False -- no iRacing SDK/sim interaction needed for this test.
        event = AudioConsumerEvent(vc_id=VC_ID_RAW, sdk=False)
        event.voice_channel = channel

        original_snapshot = _snapshot_overwrites(channel)

        # ------------------------------------------------------------
        # Lock: speak should be denied for @everyone and connect must
        # remain untouched (members can stay in the call).
        # ------------------------------------------------------------
        locked_channel = await event.lock_voice_channel()
        assert event._mic_locked is True

        everyone = locked_channel.guild.default_role
        everyone_overwrite = locked_channel.overwrites_for(everyone)
        assert everyone_overwrite.speak is False
        assert everyone_overwrite.connect is not False

        for target, overwrite in locked_channel.overwrites.items():
            assert overwrite.speak is False, (
                f"Expected speak=False to be applied to overwrite for {target!r}"
            )

        # ------------------------------------------------------------
        # Unlock: permissions should be restored to exactly what they
        # were before locking.
        # ------------------------------------------------------------
        restored_channel = await event.unlock_voice_channel()
        assert event._mic_locked is False

        restored_snapshot = _snapshot_overwrites(restored_channel)
        assert restored_snapshot == original_snapshot
    finally:
        # Safety net: if an assertion above failed mid-test, make sure we
        # don't leave the real channel muted.
        if event is not None and event._mic_locked:
            await event.unlock_voice_channel()
        await client.close()
        await task


def test_lock_and_unlock_real_voice_channel():
    """
    Full round-trip against a real Discord voice channel: lock denies
    ``speak`` for everyone (connect stays allowed), unlock restores the
    exact original permission overwrites.
    """
    asyncio.run(_lock_unlock_roundtrip())
