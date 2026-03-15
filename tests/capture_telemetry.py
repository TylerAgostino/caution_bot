"""
capture_telemetry.py -- iRacing Telemetry Capture Tool (gzip-compressed output)
=======================================================

WORKFLOW
--------
1.  Start iRacing and load a session or open a replay.

2.  Run this script, passing the same Code 69 settings you use in the bot::

        python tests/capture_telemetry.py \\
            --output tests/fixtures/my_race.json.gz \\
            --wave-arounds \\
            --extra-lanes \\
            --max-speed-km 69 \\
            --lane-names "Right,Left"

3.  The script connects to iRacing via irsdk.IRSDK and does two things in
    parallel:

    RECORDING THREAD (main thread)
        Loops at ~4 Hz, snapshotting the dynamic SDK keys into a frame dict
        on every tick.  Static keys that never change (WeekendInfo, DriverInfo,
        CarIdxClass, CarIdxBestLapTime) are captured once at startup and stored
        in meta.static rather than being repeated in every frame.

    EVENT THREAD (background daemon)
        Runs RandomTimedCode69Event.event_sequence() against the live SDK,
        exactly as the bot would in production.  The event drives itself — it
        calls freeze/unfreeze, monitors speeds, builds the RestartOrderManager,
        sends reminders, and eventually throws the green flag.

4.  Recording stops automatically the moment event_sequence() returns (which
    happens right after the green flag is thrown and busy_event is cleared).
    Press Ctrl-C at any point to abort and still write whatever was captured.

5.  On completion two files are written side-by-side:

        my_race.json.gz         gzip-compressed telemetry frames (for ReplaySDK)
        my_race.meta.json       sidecar with event_kwargs + expected_restart_order

    The .meta.json is immediately usable with test_fixtures.py — no manual
    editing of the restart order is needed.

    ReplaySDK transparently decompresses .json.gz files on load, so the test
    suite needs no changes when consuming these fixtures.

SIZE NOTES
----------
  - 4 Hz (not 60 Hz)             :  15× fewer frames than the naïve approach
  - Static keys hoisted out       :  removes ~70 % of per-frame payload
  - Compact JSON (no indent)      :  2–3× smaller than indented JSON
  - gzip compression (level 9)   :  typically 5–11× further reduction
  A 5-minute Code 69 sequence typically produces < 1 MB compressed.

COMMAND-LINE ARGUMENTS
----------------------
  --output PATH               Output telemetry file path.
                              Defaults to tests/fixtures/telemetry_<timestamp>.json.gz
                              Plain .json is also accepted; ReplaySDK reads both.
  --description TEXT          Human-readable label for the .meta.json sidecar.
                              Defaults to the output filename stem.

  Code 69 behaviour (mirror the bot UI settings exactly):
  --wave-arounds              Enable wave arounds (default: off)
  --extra-lanes               Enable multi-lane restart (default: off)
  --max-speed-km N            Pacing speed in kph (default: 69)
  --wet-speed-km N            Pacing speed in kph when wet (default: 69)
  --restart-speed-pct N       Speed % of max_speed_km that triggers green (default: 125)
  --reminder-frequency N      Reminder interval in seconds (default: 8)
  --lane-names NAMES          Comma-separated lane names (default: "Right,Left")
  --auto-restart-get-ready-position F     (default: 1.79)
  --auto-restart-form-lanes-position F    (default: 1.63)
  --auto-class-separate-position F        (default: -1.0)
  --quickie-auto-restart-get-ready-position F   (default: 0.79)
  --quickie-auto-restart-form-lanes-position F  (default: 0.63)
  --quickie-auto-class-separate-position F      (default: -1.0)
  --quickie-window N          Quickie window in laps, -1 to disable (default: -1)
  --quickie-invert-lanes      Invert lanes for quickie restart (default: off)
  --end-of-lap-safety-margin F            (default: 0.1)
  --max-laps-behind-leader N              (default: 99)
  --notify-on-skipped-caution             (default: off)

STATIC KEYS (captured once, stored in meta.static)
---------------------------------------------------
  WeekendInfo, DriverInfo, CarIdxClass, CarIdxBestLapTime

DYNAMIC KEYS (captured every tick, stored per-frame)
-----------------------------------------------------
  SessionTime, SessionTick, SessionTimeRemain, SessionFlags,
  IsGarageVisible, PlayerCarIdx, WeatherDeclaredWet,
  CarIdxLastLapTime, CarIdxLapCompleted, CarIdxLapDistPct,
  CarIdxOnPitRoad, CarIdxSessionFlags, CarIdxF2Time
"""

from __future__ import annotations

import argparse
import gzip
import json
import queue
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

# ---------------------------------------------------------------------------
# Ensure project root is on sys.path so ``modules`` is importable when the
# script is run from any working directory.
# ---------------------------------------------------------------------------
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

try:
    import irsdk
except ImportError:
    print("[ERROR] The 'irsdk' package is not installed.  Run: pip install pyirsdk")
    sys.exit(1)

try:
    import pywinauto
except ImportError:
    print(
        "[ERROR] The 'pywinauto' package is not installed.  Run: pip install pywinauto"
    )
    sys.exit(1)

from modules.events.random_code_69_event import RandomTimedCode69Event
from modules.logging_configuration import init_logging
from modules.logging_context import set_logger

_logger, _logfile = init_logging()
set_logger(_logger, _logfile)

# ---------------------------------------------------------------------------
# Key lists
# ---------------------------------------------------------------------------

# Captured once at startup; do not change during a session.
STATIC_KEYS: list[str] = [
    "WeekendInfo",
    "DriverInfo",
    "CarIdxClass",
    "CarIdxBestLapTime",
]

# Captured on every tick.
DYNAMIC_KEYS: list[str] = [
    "SessionTime",
    "SessionTick",
    "SessionTimeRemain",
    "SessionFlags",
    "IsGarageVisible",
    "PlayerCarIdx",
    "WeatherDeclaredWet",
    "CarIdxLastLapTime",
    "CarIdxLapCompleted",
    "CarIdxLapDistPct",
    "CarIdxOnPitRoad",
    "CarIdxSessionFlags",
    "CarIdxF2Time",
]

# 4 Hz — matches the caution_bot event loop's effective polling rate.
TICK_INTERVAL_S: float = 1.0 / 4.0


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _parse_track_length_km(weekend_info: dict | None) -> float | None:
    """Extract a float km value from WeekendInfo['TrackLength'] ("4.023 km")."""
    if not weekend_info:
        return None
    raw = weekend_info.get("TrackLength", "")
    try:
        return float(str(raw).replace(" km", "").strip())
    except (ValueError, TypeError):
        return None


def _read_keys(sdk: "irsdk.IRSDK", keys: list[str]) -> dict:
    """Snapshot a list of SDK keys into a plain dict, storing None on error."""
    out: dict = {}
    for key in keys:
        try:
            value = sdk[key]
            if isinstance(value, (list, dict, str, int, float, bool, type(None))):
                out[key] = value
            else:
                out[key] = str(value)
        except Exception as exc:
            out[key] = None
            print(f"[WARN] Could not read '{key}': {exc}")
    return out


def _format_bytes(n: float) -> str:
    """Return a human-readable byte count string."""
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} TB"


def _build_event_kwargs(args: argparse.Namespace) -> dict:
    """Convert parsed CLI args into the kwargs dict for RandomTimedCode69Event."""
    return {
        "wave_arounds": args.wave_arounds,
        "notify_on_skipped_caution": args.notify_on_skipped_caution,
        "max_speed_km": args.max_speed_km,
        "wet_speed_km": args.wet_speed_km,
        "restart_speed_pct": args.restart_speed_pct,
        "reminder_frequency": args.reminder_frequency,
        "lane_names": [n.strip() for n in args.lane_names.split(",")],
        "extra_lanes": args.extra_lanes,
        "auto_restart_get_ready_position": args.auto_restart_get_ready_position,
        "auto_restart_form_lanes_position": args.auto_restart_form_lanes_position,
        "auto_class_separate_position": args.auto_class_separate_position,
        "quickie_auto_restart_get_ready_position": args.quickie_auto_restart_get_ready_position,
        "quickie_auto_restart_form_lanes_position": args.quickie_auto_restart_form_lanes_position,
        "quickie_auto_class_separate_position": args.quickie_auto_class_separate_position,
        "quickie_window": args.quickie_window,
        "quickie_invert_lanes": args.quickie_invert_lanes,
        "end_of_lap_safety_margin": args.end_of_lap_safety_margin,
        "max_laps_behind_leader": args.max_laps_behind_leader,
    }


# ---------------------------------------------------------------------------
# Core capture + event runner
# ---------------------------------------------------------------------------


def capture(output_path: Path, description: str, event_kwargs: dict) -> None:
    """Connect to iRacing, run the Code 69 event, and record telemetry.

    The recording loop (main thread) and the event sequence (background thread)
    run in parallel against the same live SDK instance.  Recording stops
    automatically when event_sequence() returns after throwing the green flag.

    Parameters
    ----------
    output_path:
        Destination path for the telemetry JSON file.  The .meta.json sidecar
        is written to the same directory with the same stem.
    description:
        Human-readable label stored in the .meta.json sidecar.
    event_kwargs:
        Keyword arguments forwarded to RandomTimedCode69Event(), derived from
        the CLI args.  These are also stored verbatim in the .meta.json so the
        test runner can reconstruct the event with identical settings.
    """
    sdk = irsdk.IRSDK()
    bot_sdk = irsdk.IRSDK()
    pwa = pywinauto.Application()

    print("Waiting for iRacing connection …")
    while not sdk.startup():
        time.sleep(1.0)
    bot_sdk.startup()
    print("Connected to iRacing.\n")

    # ------------------------------------------------------------------
    # Capture static keys once
    # ------------------------------------------------------------------
    sdk.freeze_var_buffer_latest()
    static_data = _read_keys(sdk, STATIC_KEYS)
    sdk.unfreeze_var_buffer_latest()

    track_length_km = _parse_track_length_km(static_data.get("WeekendInfo"))
    driver_count = len((static_data.get("DriverInfo") or {}).get("Drivers") or [])
    print(
        f"  Track    : {static_data.get('WeekendInfo', {}).get('TrackLength', 'unknown')}"
    )
    print(f"  Drivers  : {driver_count}")
    print(
        f"  Rate     : {1 / TICK_INTERVAL_S:.0f} Hz  ({TICK_INTERVAL_S * 1000:.0f} ms/tick)"
    )
    print(f"  Output   : {output_path}")
    print()

    # ------------------------------------------------------------------
    # Threading primitives shared between the recording loop and the event
    # ------------------------------------------------------------------
    cancel_event = threading.Event()
    busy_event = threading.Event()
    chat_lock = threading.Lock()
    audio_queue: queue.Queue = queue.Queue()
    broadcast_text_queue: queue.Queue = queue.Queue()
    chat_consumer_queue: queue.Queue = queue.Queue()

    # This event is set by a patch on busy_event.clear() the moment
    # event_sequence() finishes — it signals the recording loop to stop.
    recording_stop = threading.Event()

    # ------------------------------------------------------------------
    # Construct the event
    # ------------------------------------------------------------------
    # min=0 / max=1 / likelihood=100 means the event fires immediately
    # when event_sequence() is called directly.  These scheduling knobs
    # don't matter here because we call event_sequence() directly.
    event = RandomTimedCode69Event(
        min=0,
        max=1,
        likelihood=100,
        **event_kwargs,
        sdk=bot_sdk,
        pwa=pwa,
        cancel_event=cancel_event,
        busy_event=busy_event,
        chat_lock=chat_lock,
        audio_queue=audio_queue,
        broadcast_text_queue=broadcast_text_queue,
        chat_consumer_queue=chat_consumer_queue,
    )

    # ------------------------------------------------------------------
    # Patch busy_event.clear so we know the exact moment the green flag
    # has been thrown and event_sequence() is about to return.
    # busy_event.clear() is the very last line of event_sequence().
    # ------------------------------------------------------------------
    _original_busy_clear = busy_event.clear

    def _on_event_finished() -> None:
        _original_busy_clear()
        recording_stop.set()

    busy_event.clear = _on_event_finished  # type: ignore[method-assign]

    # ------------------------------------------------------------------
    # Event thread
    # ------------------------------------------------------------------
    event_exception: list[BaseException] = []

    def _run_event() -> None:
        try:
            print("Starting Code 69 event sequence …\n")
            event.event_sequence()
        except KeyboardInterrupt:
            pass
        except Exception as exc:
            event_exception.append(exc)
            import traceback

            traceback.print_exc()
        finally:
            # Guarantee the recording loop always unblocks even if the event
            # crashed before reaching busy_event.clear().
            recording_stop.set()

    event_thread = threading.Thread(
        target=_run_event, name="Code69EventThread", daemon=True
    )

    # ------------------------------------------------------------------
    # Recording loop
    # ------------------------------------------------------------------
    frames: list[dict] = []
    start_wall = time.monotonic()

    event_thread.start()
    print("Recording …  (Ctrl-C to abort)\n")

    sdk.replay_set_play_speed(1)

    try:
        while not recording_stop.is_set():
            loop_start = time.monotonic()

            # Check connection
            if not sdk:
                print("\n[WARN] Lost iRacing connection, waiting to reconnect …")
                while not sdk:
                    time.sleep(1.0)
                print("[INFO] Reconnected.")

            # Snapshot dynamic keys
            sdk.freeze_var_buffer_latest()
            frame = _read_keys(sdk, DYNAMIC_KEYS)
            sdk.unfreeze_var_buffer_latest()
            frames.append(frame)

            # Progress report every 4 ticks (≈ 1 s)
            n = len(frames)
            if n % 4 == 0:
                elapsed = loop_start - start_wall
                approx_bytes = len(json.dumps(frame)) * n
                print(
                    f"  {n:>6} frames  |  {elapsed:>6.1f}s elapsed"
                    f"  |  ~{_format_bytes(approx_bytes)} est.",
                    end="\r",
                )

            # Pace the loop
            elapsed_this_tick = time.monotonic() - loop_start
            sleep_for = TICK_INTERVAL_S - elapsed_this_tick
            if sleep_for > 0:
                time.sleep(sleep_for)

    except KeyboardInterrupt:
        print("\n[INFO] Capture aborted by user (Ctrl-C).")
        cancel_event.set()
        recording_stop.set()

    # Wait for the event thread to finish cleanly
    event_thread.join(timeout=5.0)

    if not frames:
        print("[WARN] No frames captured — nothing written.")
        return

    # ------------------------------------------------------------------
    # Assemble and write the telemetry JSON
    # ------------------------------------------------------------------
    captured_at = datetime.now(tz=timezone.utc).isoformat()

    telemetry_output: dict = {
        "meta": {
            "captured_at": captured_at,
            "frame_count": len(frames),
            "tick_rate_hz": 1.0 / TICK_INTERVAL_S,
            "track_length_km": track_length_km,
            "static": static_data,
        },
        "frames": frames,
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Write compressed if the path ends with .gz, otherwise plain JSON.
    if output_path.suffix == ".gz":
        with gzip.open(output_path, "wt", encoding="utf-8", compresslevel=9) as fh:
            json.dump(telemetry_output, fh, separators=(",", ":"))
    else:
        with output_path.open("w", encoding="utf-8") as fh:
            json.dump(telemetry_output, fh, separators=(",", ":"))

    actual_size = output_path.stat().st_size
    print(f"\n[DONE] {len(frames)} frames written to: {output_path}")
    print(f"       File size    : {_format_bytes(actual_size)}")
    print(f"       Track length : {track_length_km} km")
    print(f"       Captured at  : {captured_at}")

    # ------------------------------------------------------------------
    # Assemble and write the .meta.json sidecar
    # ------------------------------------------------------------------
    final_restart_order = list(getattr(event, "final_restart_order", []))

    if not final_restart_order:
        print(
            "\n[WARN] final_restart_order is empty — the event did not reach the "
            "green flag (aborted or crashed).  The .meta.json will be written "
            "without an expected_restart_order; fill it in manually."
        )

    # Store lane_names as a plain list in event_kwargs for JSON serialisability.
    serialisable_kwargs = dict(event_kwargs)
    if isinstance(serialisable_kwargs.get("lane_names"), list):
        pass  # already a list
    elif isinstance(serialisable_kwargs.get("lane_names"), str):
        serialisable_kwargs["lane_names"] = [
            n.strip() for n in serialisable_kwargs["lane_names"].split(",")
        ]

    meta_output: dict = {
        "description": description,
        "event_kwargs": serialisable_kwargs,
        "expected_restart_order": final_restart_order if final_restart_order else [],
    }

    meta_path = output_path.with_suffix("").with_suffix(".meta.json")
    with meta_path.open("w", encoding="utf-8") as fh:
        json.dump(meta_output, fh, indent=2)

    print(f"\n[DONE] Sidecar written to  : {meta_path}")
    if final_restart_order:
        lane_summaries = " | ".join(
            f"Lane {i + 1}: {', '.join(lane)}"
            for i, lane in enumerate(final_restart_order)
        )
        print(f"       Restart order      : {lane_summaries}")
    else:
        print("       Restart order      : (not captured — edit meta.json manually)")

    if event_exception:
        print(f"\n[WARN] Event thread raised: {event_exception[0]!r}")


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------


def _default_output_path() -> Path:
    ts = datetime.now().strftime("%Y%m%dT%H%M%S")
    return Path("tests") / "fixtures" / f"telemetry_{ts}.json.gz"


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Record a live Code 69 sequence from iRacing and emit a telemetry "
            "JSON + .meta.json sidecar ready for replay-based testing."
        ),
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )

    # --- Output / metadata ------------------------------------------------
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        metavar="PATH",
        help="Telemetry output path.  Defaults to tests/fixtures/telemetry_<timestamp>.json",
    )
    parser.add_argument(
        "--description",
        type=str,
        default=None,
        metavar="TEXT",
        help="Human-readable description stored in the .meta.json sidecar.",
    )

    # --- Code 69 behaviour ------------------------------------------------
    parser.add_argument("--wave-arounds", action="store_true", default=True)
    parser.add_argument("--extra-lanes", action="store_true", default=True)
    parser.add_argument(
        "--notify-on-skipped-caution", action="store_true", default=True
    )
    parser.add_argument("--max-speed-km", type=int, default=69, metavar="N")
    parser.add_argument("--wet-speed-km", type=int, default=69, metavar="N")
    parser.add_argument("--restart-speed-pct", type=int, default=125, metavar="N")
    parser.add_argument("--reminder-frequency", type=int, default=8, metavar="N")
    parser.add_argument("--lane-names", type=str, default="Right,Left", metavar="NAMES")
    parser.add_argument(
        "--auto-restart-get-ready-position", type=float, default=1.79, metavar="F"
    )
    parser.add_argument(
        "--auto-restart-form-lanes-position", type=float, default=1.63, metavar="F"
    )
    parser.add_argument(
        "--auto-class-separate-position", type=float, default=-1.0, metavar="F"
    )
    parser.add_argument(
        "--quickie-auto-restart-get-ready-position",
        type=float,
        default=0.79,
        metavar="F",
    )
    parser.add_argument(
        "--quickie-auto-restart-form-lanes-position",
        type=float,
        default=0.63,
        metavar="F",
    )
    parser.add_argument(
        "--quickie-auto-class-separate-position", type=float, default=-1.0, metavar="F"
    )
    parser.add_argument("--quickie-window", type=int, default=-1, metavar="N")
    parser.add_argument("--quickie-invert-lanes", action="store_true", default=False)
    parser.add_argument(
        "--end-of-lap-safety-margin", type=float, default=0, metavar="F"
    )
    parser.add_argument("--max-laps-behind-leader", type=int, default=99, metavar="N")

    args = parser.parse_args(argv)

    output_path: Path = (
        args.output if args.output is not None else _default_output_path()
    )
    description: str = (
        args.description if args.description is not None else output_path.stem
    )
    event_kwargs = _build_event_kwargs(args)

    print("=" * 60)
    print("  iRacing Code 69 Telemetry Capture")
    print("=" * 60)
    print(f"  Description : {description}")
    print(f"  Wave arounds: {event_kwargs['wave_arounds']}")
    print(f"  Extra lanes : {event_kwargs['extra_lanes']}")
    print(f"  Max speed   : {event_kwargs['max_speed_km']} kph")
    print(f"  Lane names  : {event_kwargs['lane_names']}")
    print()

    capture(output_path=output_path, description=description, event_kwargs=event_kwargs)


if __name__ == "__main__":
    main()
