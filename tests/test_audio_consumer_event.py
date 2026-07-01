"""
test_audio_consumer_event.py -- Unit tests for AudioConsumerEvent's
start-lights mic lock feature
=====================================================================

These tests exercise ``AudioConsumerEvent._start_lights_active()`` — the
piece of logic that decides whether the iRacing starting lights
(start_ready / start_set / start_go) are currently showing — using
``FakeFlagsSDK`` in place of a live iRacing connection. No sim needs to be
running, and ``event_sequence()`` (which connects to Discord) is never
called.
"""

import sys
import threading
from pathlib import Path

import irsdk
import pytest

# Ensure the project root (parent of this tests/ directory) is on sys.path
# so that `modules` is importable regardless of how the script is launched.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from modules.events.audio_consumer_event import AudioConsumerEvent  # noqa: E402
from tests.mock_irsdk import FakeFlagsSDK, MockPWA  # noqa: E402


def _make_event(sdk) -> AudioConsumerEvent:
    """Build an AudioConsumerEvent wired to *sdk* without touching Discord."""
    return AudioConsumerEvent(
        vc_id="123456789012345678",
        sdk=sdk,
        pwa=MockPWA(),
        cancel_event=threading.Event(),
    )


class TestStartLightsActive:
    """Unit tests for ``AudioConsumerEvent._start_lights_active()``."""

    def test_no_sdk_never_active(self) -> None:
        """
        The default constructor uses ``sdk=False`` (no real IRSDK
        connection). ``_start_lights_active()`` must short-circuit to
        False without ever touching a sim.
        """
        event = AudioConsumerEvent(vc_id="123456789012345678")
        assert event.sdk is False
        assert event._start_lights_active() is False

    def test_flags_zero_is_inactive(self) -> None:
        """SessionFlags == 0 (e.g. a replay with no flags) is inactive."""
        event = _make_event(FakeFlagsSDK(session_flags=0))
        assert event._start_lights_active() is False

    @pytest.mark.parametrize(
        "flag_name",
        ["start_ready", "start_set", "start_go"],
    )
    def test_each_start_light_flag_is_active(self, flag_name: str) -> None:
        """Each individual starting-light flag should be detected."""
        flag_value = int(getattr(irsdk.Flags, flag_name))
        event = _make_event(FakeFlagsSDK(session_flags=flag_value))
        assert event._start_lights_active() is True

    def test_unrelated_flags_are_inactive(self) -> None:
        """Flags unrelated to the starting lights should not trigger a lock."""
        unrelated = int(irsdk.Flags.green | irsdk.Flags.checkered)
        event = _make_event(FakeFlagsSDK(session_flags=unrelated))
        assert event._start_lights_active() is False

    def test_start_flag_combined_with_other_flags_is_active(self) -> None:
        """
        A starting-light flag combined (bitwise OR) with unrelated flags
        should still be detected as active.
        """
        combined = int(irsdk.Flags.start_set | irsdk.Flags.caution_waving)
        event = _make_event(FakeFlagsSDK(session_flags=combined))
        assert event._start_lights_active() is True

    def test_lock_mic_on_start_lights_defaults_true(self) -> None:
        """The mic-lock feature should be enabled by default."""
        event = AudioConsumerEvent(vc_id="123456789012345678")
        assert event.lock_mic_on_start_lights is True

    def test_lock_mic_on_start_lights_can_be_disabled(self) -> None:
        event = AudioConsumerEvent(
            vc_id="123456789012345678", lock_mic_on_start_lights=False
        )
        assert event.lock_mic_on_start_lights is False
