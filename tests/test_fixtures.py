"""
test_fixtures.py -- Parameterized replay fixture tests
=======================================================

Each ``.meta.json`` file discovered in ``tests/fixtures/`` becomes one test
case via the ``pytest_generate_tests`` hook in ``conftest.py``.

To add a new scenario:

1.  Capture telemetry during a real race or replay::

        python tests/capture_telemetry.py --output tests/fixtures/my_race.json

2.  Create a sidecar at ``tests/fixtures/my_race.meta.json``::

        {
            "description": "Wave arounds at Bathurst",
            "event_kwargs": {
                "wave_arounds": true,
                "extra_lanes": false,
                "max_speed_km": 69,
                "restart_speed_pct": 125
            },
            "expected_restart_order": [
                ["11", "22", "33"]
            ]
        }

3.  Run this file with the "Test: Replay Fixtures" Zed debug profile, or::

        pytest tests/test_fixtures.py -v

The test will automatically pick up the new fixture — no code changes needed.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from tests.conftest import ReplayFixture  # noqa: E402
from tests.replay_runner import ReplayRunner  # noqa: E402

# ---------------------------------------------------------------------------
# How long to wait for a single fixture run before declaring a timeout.
# Real-race telemetry files are longer than the synthetic ones used in
# test_replay.py, so we allow a generous budget.
# ---------------------------------------------------------------------------
_TIMEOUT_SECONDS = 120.0


class TestFixtureRestartOrder:
    """Runs every discovered ReplayFixture and asserts the restart order."""

    def test_fixture_restart_order(self, replay_fixture: ReplayFixture) -> None:
        """
        Load the telemetry file, run the Code 69 event sequence against it,
        and assert that the restart order at the green flag matches the
        expected order declared in the ``.meta.json`` sidecar.

        Failure modes surfaced by this test
        ------------------------------------
        * ``result.timed_out`` — the event never reached the green flag within
          the timeout.  Usually means the telemetry file ended too early, or a
          bug caused the event to hang.
        * ``result.completed is False`` — ``event_sequence()`` raised an
          unhandled exception.  ``result.exception`` will contain it.
        * ``result.final_restart_order != expected`` — the bot computed a
          different order than what was recorded in the sidecar.  This is the
          primary regression signal.
        """
        sdk = replay_fixture.build_sdk()
        event = replay_fixture.build_event(sdk)
        runner = ReplayRunner(sdk, event)

        result = runner.run(timeout=_TIMEOUT_SECONDS)

        # ------------------------------------------------------------------
        # 1. The event must have run to completion.
        # ------------------------------------------------------------------
        if result.exception is not None:
            raise AssertionError(
                f"[{replay_fixture.description}] event_sequence() raised an "
                f"unhandled exception: {result.exception!r}"
            ) from result.exception

        assert not result.timed_out, (
            f"[{replay_fixture.description}] Timed out after {_TIMEOUT_SECONDS}s. "
            f"The event did not reach the green flag. "
            f"Frames consumed: {result.frames_consumed}. "
            f"Last chat messages: {result.chat_messages[-5:]}"
        )

        assert result.completed, (
            f"[{replay_fixture.description}] event_sequence() did not complete. "
            f"Last chat messages: {result.chat_messages[-5:]}"
        )

        # ------------------------------------------------------------------
        # 2. A green flag must have been thrown.
        # ------------------------------------------------------------------
        green_flag_messages = [m for m in result.chat_messages if "Green Flag" in m]
        assert green_flag_messages, (
            f"[{replay_fixture.description}] No 'Green Flag' message was sent. "
            f"All chat messages:\n" + "\n".join(f"  {m}" for m in result.chat_messages)
        )

        # ------------------------------------------------------------------
        # 3. The restart order must match the expected order exactly.
        #
        #    We compare lane-by-lane.  The number of lanes in the result must
        #    match the number declared in expected_restart_order.
        # ------------------------------------------------------------------
        expected = replay_fixture.expected_restart_order
        actual = result.final_restart_order

        assert actual, (
            f"[{replay_fixture.description}] final_restart_order is empty — "
            f"the event completed but never populated the order. "
            f"This is a bug in the event or the runner."
        )

        assert len(actual) == len(expected), (
            f"[{replay_fixture.description}] Lane count mismatch.\n"
            f"  Expected {len(expected)} lane(s): {expected}\n"
            f"  Got      {len(actual)} lane(s):   {actual}"
        )

        for lane_idx, (actual_lane, expected_lane) in enumerate(zip(actual, expected)):
            assert actual_lane == expected_lane, (
                f"[{replay_fixture.description}] Lane {lane_idx + 1} mismatch.\n"
                f"  Expected : {expected_lane}\n"
                f"  Got      : {actual_lane}\n"
                f"\n"
                f"  Full expected order : {expected}\n"
                f"  Full actual order   : {actual}\n"
                f"\n"
                f"  All chat messages:\n"
                + "\n".join(f"    {m}" for m in result.chat_messages)
            )
