"""
test_replay.py -- Replay-based pytest tests for caution_bot events
==================================================================

This module contains:

1.  ``sample_telemetry_path`` fixture
    Generates a synthetic, self-contained telemetry JSON file in pytest's
    ``tmp_path`` directory.  No live iRacing session is required.

    Scenario
    --------
    * Track : 2.0 km loop
    * 4 car slots (CarIdx 0–3)
        - CarIdx 0 : pace car   (CarIsPaceCar=1)
        - CarIdx 1 : car "11"   (lead-lap car, race leader)
        - CarIdx 2 : car "22"   (lead-lap car, P2)
        - CarIdx 3 : car "33"   (lead-lap car, P3)
    * All racers are in the same class (class ID 1)
    * Session is a *racing* session (SessionState=4)
    * No caution is active (SessionFlags=0)
    * All cars start at ~lap 2 (LapCompleted=1) with small LapDistPct offsets
      so they are clearly in running order 11 > 22 > 33.

    Frame sequence (phases)
    -----------------------
    Phase A – "waiting for lap completion"  (~60 frames)
        Cars advance around the track.  On frame 40 every racer's
        LapCompleted flips from 1 → 2, which satisfies the
        ``car["LapCompleted"] > lead_lap`` condition in event_sequence()
        and ends the waiting-loop.

    Phase B – "pacing / building restart order"  (~120 frames)
        After the caution is thrown, cars continue around the track at a
        slow pacing pace (LapDistPct advancing by ~0.005 per frame).
        On frame 10 of this phase each car's LapCompleted ticks to 2 and
        LapDistPct resets to a small positive value so add_car_to_order()
        will fire for each car via car_has_completed_lap().
        ActualPosition (= LapCompleted + LapDistPct - BeganPacingLap) grows
        with every frame; once it reaches >= auto_restart_form_lanes_position
        (0.5 in the test) restart_ready is set.

    Phase C – "lane formation / restart"  (~120 frames)
        Cars advance far enough that the lane-formation loop's speed check
        fires (speed > restart_speed_pct * pacing_speed_km / 100) which
        triggers the "Green Flag!" sequence and ends event_sequence().

    Total frames: ~300, well within any reasonable timeout.

2.  ``test_replay_sdk_frame_advance``
    Unit-tests ``ReplaySDK`` in isolation: verifies frame indexing and that
    ``StopIteration`` is raised when frames are exhausted.

3.  ``test_code69_restart_order_simple``
    End-to-end test: builds a ``RandomTimedCode69Event`` with the synthetic
    telemetry, runs it through ``ReplayRunner``, and asserts:
    - The event completed without a timeout.
    - At least one chat message contains "Green Flag".
    - At least one audio event equals "code69begin".
"""

from __future__ import annotations

import json
import queue
import sys
import threading
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Ensure the project root (parent of tests/) is on sys.path so that `modules`
# is importable regardless of how pytest discovers / runs this file.
# ---------------------------------------------------------------------------
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

# ---------------------------------------------------------------------------
# Bootstrap logging (BaseEvent.__init__ calls get_logger() at import time)
# ---------------------------------------------------------------------------
from modules.logging_configuration import init_logging  # noqa: E402
from modules.logging_context import set_logger  # noqa: E402

_logger, _logfile = init_logging()
set_logger(_logger, _logfile)

# ---------------------------------------------------------------------------
# Now safe to import project modules
# ---------------------------------------------------------------------------
from modules.events.random_code_69_event import RandomTimedCode69Event  # noqa: E402
from tests.mock_irsdk import MockPWA, ReplaySDK  # noqa: E402
from tests.replay_runner import ReplayRunner  # noqa: E402

# ---------------------------------------------------------------------------
# Telemetry-generation helpers
# ---------------------------------------------------------------------------

_TRACK_LENGTH_KM = 2.0
_TRACK_LENGTH_STR = f"{_TRACK_LENGTH_KM} km"

# iRacing class IDs used in the synthetic session
_PACE_CAR_CLASS = 0  # iRacing uses 0 for the pace car
_RACE_CLASS = 1  # single racing class for all racers

# Car slot layout
#   idx 0 → pace car
#   idx 1 → car "11"  (race P1 / leader)
#   idx 2 → car "22"  (race P2)
#   idx 3 → car "33"  (race P3)
_DRIVERS = [
    {"CarIdx": 0, "CarNumber": "0", "CarIsPaceCar": 1, "TeamIncidentCount": 0},
    {"CarIdx": 1, "CarNumber": "11", "CarIsPaceCar": 0, "TeamIncidentCount": 0},
    {"CarIdx": 2, "CarNumber": "22", "CarIsPaceCar": 0, "TeamIncidentCount": 0},
    {"CarIdx": 3, "CarNumber": "33", "CarIsPaceCar": 0, "TeamIncidentCount": 0},
]

_N_SLOTS = 4  # total car-index slots (0..3)


def _make_driver_info() -> dict:
    return {"Drivers": list(_DRIVERS)}


def _make_weekend_info() -> dict:
    return {"TrackLength": _TRACK_LENGTH_STR}


def _base_frame(
    *,
    tick: int,
    session_time: float,
    session_time_remain: float,
    session_flags: int = 0,  # 0 = no caution (is_caution_active() returns False)
    is_garage_visible: int = 0,
    player_car_idx: int = 1,
    weather_declared_wet: int = 0,
    lap_completed: list[int] | None = None,
    lap_dist_pct: list[float] | None = None,
    on_pit_road: list[int] | None = None,
    session_flags_per_car: list[int] | None = None,
    last_lap_time: list[float] | None = None,
    f2_time: list[float] | None = None,
) -> dict:
    """Return a dynamic-keys-only telemetry frame dict with sensible defaults.

    Static keys (WeekendInfo, DriverInfo, CarIdxClass, CarIdxBestLapTime) are
    NOT included here — they live in meta.static and are merged in by ReplaySDK.
    """
    if lap_completed is None:
        lap_completed = [0, 1, 1, 1]
    if lap_dist_pct is None:
        lap_dist_pct = [-1.0, 0.9, 0.85, 0.8]
    if on_pit_road is None:
        on_pit_road = [0, 0, 0, 0]
    if session_flags_per_car is None:
        session_flags_per_car = [0, 0, 0, 0]
    if last_lap_time is None:
        last_lap_time = [-1.0, 72.0, 72.5, 73.0]
    if f2_time is None:
        f2_time = [0.0, 0.0, 0.0, 0.0]

    # WeekendInfo, DriverInfo, CarIdxClass, and CarIdxBestLapTime are static
    # and live in meta.static — omit them from individual frames.
    return {
        "SessionTime": round(session_time, 4),
        "SessionTick": tick,
        "SessionTimeRemain": round(session_time_remain, 4),
        "SessionFlags": session_flags,
        "IsGarageVisible": is_garage_visible,
        "PlayerCarIdx": player_car_idx,
        "WeatherDeclaredWet": weather_declared_wet,
        "CarIdxLastLapTime": list(last_lap_time),
        "CarIdxLapCompleted": list(lap_completed),
        "CarIdxLapDistPct": list(lap_dist_pct),
        "CarIdxOnPitRoad": list(on_pit_road),
        "CarIdxSessionFlags": list(session_flags_per_car),
        "CarIdxF2Time": list(f2_time),
    }


def _build_synthetic_frames() -> list[dict]:
    """
    Build a list of telemetry frames that will drive a full Code 69 cycle.

    Design notes
    ------------
    We test with these event constructor knobs:
      - auto_restart_form_lanes_position = 0.5
      - auto_restart_get_ready_position  = 0.85
      - extra_lanes = False  (single-file restart; avoids the multi-lane loop)
      - wave_arounds = False
      - end_of_lap_safety_margin = 0
      - restart_speed_pct = 125
      - max_speed_km = 69
      - reminder_frequency = 8   (seconds; with patched sleep/time this just
                                   means every 8 "SDK seconds")

    Event flow we must satisfy
    --------------------------

    [Step 1]  is_caution_active() must return False on the very first frame.
              SessionFlags = 0 → is_caution_active() short-circuits to False. ✓

    [Step 2]  get_current_running_order() is called; lead_lap = max LapCompleted
              for racers.  We start cars at LapCompleted=1, so lead_lap = 1.

    [Step 3]  Safety margin check:
              max_total_completed = max(LapCompleted + LapDistPct)
              If that is >= 1 - 0 = 1.0 the margin triggers.
              We start the leader at LapDistPct = 0.02 so total_completed = 1.02.
              1.02 - 1 = 0.02 which is < 1.0, so NO margin trigger. ✓
              (end_of_lap_safety_margin=0, so threshold is 1-0=1.0)

    [Step 4]  "Wait for lap completion" loop.
              Loop condition: not any(car["LapCompleted"] > lead_lap for car in this_step)
              → we need LapCompleted to flip from 1 → 2 for at least one racer.
              We do this at frame index 40 by incrementing LapCompleted for all
              racers and resetting LapDistPct to near 0.

    [Step 5]  After the lap completes, the main pacing loop starts.
              RestartOrderManager is constructed.  Cars are added via
              car_has_completed_lap() (LapCompleted[n] > LapCompleted[n-1]).
              We arrange for each racer to cross the lap boundary once (frame 40
              already does this).  After that, cars advance at pacing speed.

              car_has_completed_lap detects: this_step[LapCompleted] == last_step[LapCompleted]+1
              So at the frame where LapCompleted ticks from 1→2 the car is added.

    [Step 6]  ActualPosition in RestartOrderManager:
              ActualPosition = sdk["CarIdxLapCompleted"][carIdx]
                             + sdk["CarIdxLapDistPct"][carIdx]
                             - car["BeganPacingLap"]
              BeganPacingLap = LapCompleted at the moment the car was added (=2).
              So ActualPosition = 2 + LapDistPct - 2 = LapDistPct.
              We need ActualPosition >= auto_restart_form_lanes_position = 0.5
              So we need LapDistPct >= 0.5 for the leader.
              Cars advance at 0.005 per frame → need 0.5/0.005 = 100 frames.
              We start pacing at LapDistPct ≈ 0.02, so need ~96 more frames.

    [Step 7]  Once restart_ready is set (extra_lanes=False → goes to the single
              file restart path), the event calls:
                - 3× "Get Ready …" chat
                - sleep(2)
                - then enters the restart-speed while-loop.
              The restart speed threshold is:
                restart_speed = 69 * (125/100) = 86.25 kph
              monitor_speed() computes:
                speed = distance_delta / time_delta * track_km * 3600
              For speed > 86.25 we need the leader to be moving quickly.
              We make cars advance by 0.05 per frame in the restart phase and
              SessionTime advances by 1/60 per frame.
              speed = 0.05 / (1/60) * 2.0 * 3600 = 21600 kph  (much > 86.25) ✓

    [Step 8]  After the speed check fires, "Green Flag!" is sent 3 times. ✓

    Total frames needed: ~40 (wait) + 10 (pacing warmup) + 100 (pacing) + 30 (restart) + padding
    We generate 400 frames for safety.
    """
    frames: list[dict] = []
    tick = 1000
    session_time = 120.0  # 2 minutes into the session
    session_time_remain = 3480.0  # ~58 minutes remain
    session_time_total = 3600.0

    FPS = 60.0
    dt = 1.0 / FPS  # ~0.01667 s per frame
    session_time_total = (
        3600.0  # noqa: F841 — kept for readability, not passed to _base_frame
    )

    # ---- initial car state -----------------------------------------------
    # LapCompleted for slots [pace, car11, car22, car33]
    laps = [0, 1, 1, 1]

    # LapDistPct — leader a bit ahead
    # We start deliberately low so the safety-margin check does NOT trigger.
    # total_completed for leader = 1 + 0.02 = 1.02; threshold = 1.0 → no trigger.
    dist = [-1.0, 0.02, 0.01, 0.005]

    # Speed of advancement per frame for each car slot (fraction of lap)
    # These values mimic ~40 kph on a 2 km track:
    #   40 kph → 40/3600 km/s → 40/3600/2.0 lap/s → ~0.00556 lap/frame at 60Hz
    advance_slow = 0.0055  # pacing speed per frame
    advance_fast = 0.05  # restart-speed burst per frame (>> threshold)

    # Track which phase we are in so we can vary the advancement rate.
    # Phases:
    #   0 = waiting for lap completion (frames 0-39)
    #   1 = pacing / building order    (frames 40-199)
    #   2 = restart burst              (frames 200+)
    #
    # We signal phase transitions with a simple counter.
    LAP_COMPLETE_FRAME = 40  # frame index where LapCompleted flips 1→2

    for frame_idx in range(400):
        # ------------------------------------------------------------------
        # Advance car positions
        # ------------------------------------------------------------------
        if frame_idx < LAP_COMPLETE_FRAME:
            # Phase 0: slow running order approach to lap boundary
            for slot in [1, 2, 3]:
                dist[slot] = round(dist[slot] + advance_slow, 6)

        elif frame_idx == LAP_COMPLETE_FRAME:
            # Phase transition: every racer crosses the start/finish line.
            # LapCompleted goes 1 → 2, LapDistPct resets to a tiny positive value.
            # We stagger by slot so P1 > P2 > P3 in LapDistPct.
            for slot in [1, 2, 3]:
                laps[slot] = 2
            dist[1] = 0.02  # P1 crosses first
            dist[2] = 0.01  # P2 a tiny bit behind
            dist[3] = 0.005  # P3 further back

        elif frame_idx < 200:
            # Phase 1: pacing.  Cars advance slowly.
            for slot in [1, 2, 3]:
                new_dist = round(dist[slot] + advance_slow, 6)
                if new_dist >= 1.0:
                    # Car completes another lap — this shouldn't happen in our
                    # window but handle it defensively.
                    laps[slot] += 1
                    new_dist = round(new_dist - 1.0, 6)
                dist[slot] = new_dist

        else:
            # Phase 2: restart burst — cars floor it.
            for slot in [1, 2, 3]:
                new_dist = round(dist[slot] + advance_fast, 6)
                if new_dist >= 1.0:
                    laps[slot] += 1
                    new_dist = round(new_dist - 1.0, 6)
                dist[slot] = new_dist

        frame = _base_frame(
            tick=tick,
            session_time=session_time,
            session_time_remain=session_time_remain,
            lap_completed=list(laps),
            lap_dist_pct=list(dist),
        )
        frames.append(frame)

        tick += 1
        session_time = round(session_time + dt, 6)
        session_time_remain = round(session_time_remain - dt, 6)

    return frames


def _build_telemetry_json(frames: list[dict]) -> dict:
    """Wrap a frame list in the standard telemetry JSON envelope.

    Static keys that never change during a session are stored once in
    meta.static rather than being repeated in every frame, matching the format
    produced by capture_telemetry.py.
    """
    from datetime import datetime, timezone

    track_length_km = _TRACK_LENGTH_KM
    static_data = {
        "WeekendInfo": _make_weekend_info(),
        "DriverInfo": _make_driver_info(),
        "CarIdxClass": [_PACE_CAR_CLASS, _RACE_CLASS, _RACE_CLASS, _RACE_CLASS],
        # ~72 seconds for a 2 km lap at 100 kph
        "CarIdxBestLapTime": [-1.0, 72.0, 72.5, 73.0],
    }
    return {
        "meta": {
            "captured_at": datetime.now(tz=timezone.utc).isoformat(),
            "frame_count": len(frames),
            "tick_rate_hz": 4.0,
            "track_length_km": track_length_km,
            "static": static_data,
        },
        "frames": frames,
    }


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def sample_telemetry_path(tmp_path: Path) -> Path:
    """Write synthetic telemetry to ``tmp_path/test_telemetry.json`` and return the path."""
    frames = _build_synthetic_frames()
    data = _build_telemetry_json(frames)
    out = tmp_path / "test_telemetry.json"
    out.write_text(json.dumps(data, separators=(",", ":")), encoding="utf-8")
    return out


# ---------------------------------------------------------------------------
# Helpers for constructing the event under test
# ---------------------------------------------------------------------------


def _make_event(sdk: ReplaySDK) -> RandomTimedCode69Event:
    """Construct a ``RandomTimedCode69Event`` wired to *sdk* for replay testing.

    We use settings designed to make the event complete quickly on the
    synthetic frames:

    * ``extra_lanes=False``   → single-file restart; no lane-formation loop.
    * ``auto_restart_form_lanes_position=0.5``
                              → restart_ready fires when ActualPosition >= 0.5.
    * ``auto_restart_get_ready_position=0.85``
                              → "get ready" threshold (above form_lanes for
                                 this test so only the form_lanes path fires).
    * ``restart_speed_pct=125``  → restart when speed > 69 * 1.25 = 86.25 kph.
    * ``max_speed_km=69``
    * ``reminder_frequency=1``  → send reminder every 1 SDK second.  With
                                   SessionTime advancing at 1/60 s per frame,
                                   the ~160-frame pacing phase spans ~2.67 SDK
                                   seconds, which is enough for the generator
                                   to fire at least twice and initialize
                                   ``leader_speed_generator``.
    * ``likelihood=100``         → always fires (though we call event_sequence()
                                   directly, bypassing the likelihood roll).
    * ``end_of_lap_safety_margin=0`` → simpler safety margin logic.
    * ``wave_arounds=False``     → no wave-around sub-logic to worry about.
    """
    cancel_event = threading.Event()
    busy_event = threading.Event()
    chat_lock = threading.Lock()
    audio_queue = queue.Queue()
    broadcast_text_queue = queue.Queue()
    chat_consumer_queue = queue.Queue()

    return RandomTimedCode69Event(
        # Timing: min=0, max=1 → start_time in [0, 60].  The synthetic frames
        # have SessionTimeRemain well above 1 s so is_time_to_start() would
        # return True immediately — but we bypass it and call event_sequence()
        # directly, so this only matters for __init__ (RandomTimedEvent reads
        # sdk["SessionTimeTotal"] if min/max are negative; both are positive
        # here so no SDK read is needed for start_time).
        min=0,
        max=1,
        likelihood=100,
        wave_arounds=False,
        notify_on_skipped_caution=False,
        max_speed_km=69,
        restart_speed_pct=125,
        lane_names=["Right", "Left"],
        reminder_frequency=1,
        extra_lanes=False,  # single-file restart
        auto_restart_get_ready_position=0.85,
        auto_restart_form_lanes_position=0.5,
        auto_class_separate_position=-1,  # disabled
        quickie_auto_restart_get_ready_position=0.85,
        quickie_auto_restart_form_lanes_position=0.5,
        quickie_auto_class_separate_position=-1,
        quickie_window=-1,
        quickie_invert_lanes=False,
        end_of_lap_safety_margin=0,
        # BaseEvent knobs
        sdk=sdk,
        pwa=MockPWA(),
        cancel_event=cancel_event,
        busy_event=busy_event,
        chat_lock=chat_lock,
        audio_queue=audio_queue,
        broadcast_text_queue=broadcast_text_queue,
        chat_consumer_queue=chat_consumer_queue,
        max_laps_behind_leader=99,
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestReplaySDKFrameAdvance:
    """Unit-tests for ``ReplaySDK`` in isolation."""

    def test_initial_frame_is_zero(self, tmp_path: Path) -> None:
        """The SDK starts on frame 0 and returns the correct values."""
        frames = [
            _base_frame(
                tick=100,
                session_time=10.0,
                session_time_remain=3590.0,
                lap_completed=[0, 1, 1, 1],
                lap_dist_pct=[-1.0, 0.1, 0.05, 0.02],
            ),
            _base_frame(
                tick=101,
                session_time=10.0167,
                session_time_remain=3589.98,
                lap_completed=[0, 1, 1, 1],
                lap_dist_pct=[-1.0, 0.11, 0.06, 0.03],
            ),
            _base_frame(
                tick=102,
                session_time=10.0334,
                session_time_remain=3589.97,
                lap_completed=[0, 1, 1, 1],
                lap_dist_pct=[-1.0, 0.12, 0.07, 0.04],
            ),
        ]
        path = tmp_path / "minimal.json"
        path.write_text(json.dumps(_build_telemetry_json(frames)), encoding="utf-8")

        sdk = ReplaySDK(path)
        assert sdk.current_frame_index == 0
        assert sdk["SessionTick"] == 100
        assert sdk["CarIdxLapDistPct"][1] == pytest.approx(0.1)

    def test_freeze_advances_frame(self, tmp_path: Path) -> None:
        """``freeze_var_buffer_latest()`` moves to the next frame."""
        frames = [
            _base_frame(tick=100, session_time=10.0, session_time_remain=3590.0),
            _base_frame(tick=101, session_time=10.0167, session_time_remain=3589.98),
            _base_frame(tick=102, session_time=10.0334, session_time_remain=3589.97),
        ]
        path = tmp_path / "advance.json"
        path.write_text(json.dumps(_build_telemetry_json(frames)), encoding="utf-8")

        sdk = ReplaySDK(path)

        # Frame 0
        assert sdk["SessionTick"] == 100

        # Advance to frame 1
        sdk.freeze_var_buffer_latest()
        assert sdk.current_frame_index == 1
        assert sdk["SessionTick"] == 101

        # Advance to frame 2
        sdk.freeze_var_buffer_latest()
        assert sdk.current_frame_index == 2
        assert sdk["SessionTick"] == 102

    def test_stop_iteration_on_exhaustion(self, tmp_path: Path) -> None:
        """``freeze_var_buffer_latest()`` raises ``StopIteration`` after the last frame."""
        frames = [
            _base_frame(tick=100, session_time=10.0, session_time_remain=3590.0),
            _base_frame(tick=101, session_time=10.0167, session_time_remain=3589.98),
            _base_frame(tick=102, session_time=10.0334, session_time_remain=3589.97),
        ]
        path = tmp_path / "exhaustion.json"
        path.write_text(json.dumps(_build_telemetry_json(frames)), encoding="utf-8")

        sdk = ReplaySDK(path)

        # Consume frame 0 → 1
        sdk.freeze_var_buffer_latest()
        # Consume frame 1 → 2
        sdk.freeze_var_buffer_latest()
        # Past the last frame → StopIteration
        with pytest.raises(StopIteration):
            sdk.freeze_var_buffer_latest()

    def test_is_replay_exhausted(self, tmp_path: Path) -> None:
        """``is_replay_exhausted`` reflects the frame pointer correctly."""
        frames = [
            _base_frame(tick=1, session_time=0.0, session_time_remain=60.0),
            _base_frame(tick=2, session_time=0.0167, session_time_remain=59.98),
        ]
        path = tmp_path / "exhausted.json"
        path.write_text(json.dumps(_build_telemetry_json(frames)), encoding="utf-8")

        sdk = ReplaySDK(path)
        assert not sdk.is_replay_exhausted

        sdk.freeze_var_buffer_latest()
        assert not sdk.is_replay_exhausted  # still on frame 1, which is valid

        with pytest.raises(StopIteration):
            sdk.freeze_var_buffer_latest()
        assert sdk.is_replay_exhausted

    def test_reset_rewinds_to_frame_zero(self, tmp_path: Path) -> None:
        """``reset()`` brings the index back to 0."""
        frames = [
            _base_frame(tick=5, session_time=0.0, session_time_remain=60.0),
            _base_frame(tick=6, session_time=0.0167, session_time_remain=59.98),
        ]
        path = tmp_path / "reset.json"
        path.write_text(json.dumps(_build_telemetry_json(frames)), encoding="utf-8")

        sdk = ReplaySDK(path)
        sdk.freeze_var_buffer_latest()
        assert sdk["SessionTick"] == 6

        sdk.reset()
        assert sdk.current_frame_index == 0
        assert sdk["SessionTick"] == 5

    def test_peek_next_does_not_advance(self, tmp_path: Path) -> None:
        """``peek_next()`` returns the next frame without moving the pointer."""
        frames = [
            _base_frame(tick=10, session_time=0.0, session_time_remain=60.0),
            _base_frame(tick=11, session_time=0.0167, session_time_remain=59.98),
        ]
        path = tmp_path / "peek.json"
        path.write_text(json.dumps(_build_telemetry_json(frames)), encoding="utf-8")

        sdk = ReplaySDK(path)
        peeked = sdk.peek_next()
        assert peeked is not None
        assert peeked["SessionTick"] == 11
        # Pointer must NOT have moved
        assert sdk.current_frame_index == 0
        assert sdk["SessionTick"] == 10

    def test_meta_loaded(self, tmp_path: Path) -> None:
        """``sdk.meta`` is populated from the JSON envelope."""
        frames = [_base_frame(tick=1, session_time=0.0, session_time_remain=60.0)]
        data = _build_telemetry_json(frames)
        path = tmp_path / "meta.json"
        path.write_text(json.dumps(data), encoding="utf-8")

        sdk = ReplaySDK(path)
        assert sdk.meta["frame_count"] == 1
        assert sdk.meta["track_length_km"] == pytest.approx(_TRACK_LENGTH_KM)


class TestCode69RestartOrder:
    """End-to-end replay tests for ``RandomTimedCode69Event``."""

    def test_code69_restart_order_simple(self, sample_telemetry_path: Path) -> None:
        """
        Full Code 69 cycle on synthetic telemetry.

        Verifies:
        - The event completes normally (no timeout, no exception).
        - At least one chat message contains "Green Flag".
        - At least one audio event equals "code69begin".
        - The broadcast queue received at least one message.
        - No unhandled exception was raised inside event_sequence().
        """
        sdk = ReplaySDK(sample_telemetry_path)
        event = _make_event(sdk)

        runner = ReplayRunner(sdk, event)
        result = runner.run(timeout=30)

        # Diagnostics on failure
        if not result.completed or result.timed_out:
            print("\n--- chat_messages ---")
            for msg in result.chat_messages:
                print(" ", msg)
            print("--- audio_events ---")
            for ev in result.audio_events:
                print(" ", ev)
            if result.exception:
                raise result.exception

        assert not result.timed_out, (
            "event_sequence() did not finish within the timeout.  "
            f"Frames consumed: {result.frames_consumed}.  "
            f"Chat so far: {result.chat_messages}"
        )
        assert result.completed, (
            f"event_sequence() did not complete cleanly.  "
            f"Exception: {result.exception}"
        )
        assert (
            result.exception is None
        ), f"event_sequence() raised an exception: {result.exception}"

        # The "Green Flag!" message should appear at least once.
        green_flag_messages = [m for m in result.chat_messages if "Green Flag" in m]
        assert len(green_flag_messages) >= 1, (
            f"Expected at least one 'Green Flag' message but got none.\n"
            f"Chat messages: {result.chat_messages}"
        )

        # The "code69begin" audio cue must have been queued.
        assert (
            "code69begin" in result.audio_events
        ), f"Expected 'code69begin' audio event but got: {result.audio_events}"

        # At least one broadcast message was sent.
        assert (
            len(result.broadcast_messages) >= 1
        ), "Expected at least one broadcast message but got none."

    def test_code69_skips_when_caution_active(self, tmp_path: Path) -> None:
        """
        When ``SessionFlags`` indicates an active caution the event should
        return immediately without sending any messages.
        """
        import irsdk

        # Build frames with the caution flag set
        caution_flag_value = int(irsdk.Flags.caution)
        frames = [
            _base_frame(
                tick=1,
                session_time=0.0,
                session_time_remain=3600.0,
                session_flags=caution_flag_value,
            )
        ] * 10  # a few identical frames so the SDK doesn't exhaust immediately

        path = tmp_path / "caution_active.json"
        path.write_text(json.dumps(_build_telemetry_json(frames)), encoding="utf-8")

        sdk = ReplaySDK(path)
        event = _make_event(sdk)

        runner = ReplayRunner(sdk, event)
        result = runner.run(timeout=5)

        # Event should return immediately (no Green Flag, no code69begin)
        assert result.completed
        assert "code69begin" not in result.audio_events
        assert not any("Green Flag" in m for m in result.chat_messages)

    def test_code69_skips_when_busy(self, tmp_path: Path) -> None:
        """
        When ``busy_event`` is already set the event should return immediately.
        """
        frames = [
            _base_frame(tick=1, session_time=0.0, session_time_remain=3600.0)
        ] * 10

        path = tmp_path / "busy.json"
        path.write_text(json.dumps(_build_telemetry_json(frames)), encoding="utf-8")

        sdk = ReplaySDK(path)
        event = _make_event(sdk)
        event.busy_event.set()  # Pre-set the busy flag

        runner = ReplayRunner(sdk, event)
        result = runner.run(timeout=5)

        assert result.completed
        assert "code69begin" not in result.audio_events

    def test_frames_consumed_increases(self, sample_telemetry_path: Path) -> None:
        """``result.frames_consumed`` reflects how many frames were read."""
        sdk = ReplaySDK(sample_telemetry_path)
        event = _make_event(sdk)

        runner = ReplayRunner(sdk, event)
        result = runner.run(timeout=30)

        assert result.frames_consumed > 0, "Expected at least one frame to be consumed."
