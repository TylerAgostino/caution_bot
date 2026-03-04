"""
Standalone test runner for RandomLapCode69Event.
Run directly via the Zed debugger using the "Test: Random Code 69" debug entry.
Does NOT require the Flet UI to be running.
"""

import logging
import queue
import sys
import threading
from pathlib import Path

# Ensure the project root (parent of this tests/ directory) is on sys.path
# so that `modules` is importable regardless of how the script is launched.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# ---------------------------------------------------------------------------
# Bootstrap logging so BaseEvent's logger is happy before any import touches it
# ---------------------------------------------------------------------------
from modules.logging_configuration import init_logging
from modules.logging_context import set_logger

logger, logfile = init_logging()
set_logger(logger, logfile)

root_log = logging.getLogger()
root_log.setLevel(logging.DEBUG)
stream_handler = logging.StreamHandler(sys.stdout)
stream_handler.setLevel(logging.DEBUG)
stream_handler.setFormatter(
    logging.Formatter("%(asctime)s [%(levelname)s] (%(event)s) %(message)s")
)
root_log.addHandler(stream_handler)

# ---------------------------------------------------------------------------
# Now safe to import the event module
# ---------------------------------------------------------------------------
from modules.events.random_code_69_event import RandomTimedCode69Event


def run_test():
    """
    Instantiate RandomLapCode69Event with minimal / sensible defaults and
    kick off event_sequence() directly on the calling thread so the debugger
    can step through it without any UI plumbing.
    """

    cancel_event = threading.Event()
    busy_event = threading.Event()
    chat_lock = threading.Lock()
    audio_queue = queue.Queue()
    broadcast_text_queue = queue.Queue()
    chat_consumer_queue = queue.Queue()

    print("=" * 60)
    print("  RandomLapCode69Event  –  direct test runner")
    print("=" * 60)

    chat_lock.acquire()

    event = RandomTimedCode69Event(
        min=0,  # trigger after lap 1
        max=1,  # trigger before lap 3
        likelihood=100,  # always fire
        wave_arounds=True,
        notify_on_skipped_caution=True,
        max_speed_km=69,
        restart_speed_pct=125,
        lane_names=["Right", "Left"],
        reminder_frequency=8,
        extra_lanes=True,
        auto_restart_get_ready_position=1.85,
        auto_restart_form_lanes_position=1.5,
        auto_class_separate_position=-1,
        quickie_auto_restart_get_ready_position=0.85,
        quickie_auto_restart_form_lanes_position=0.5,
        quickie_auto_class_separate_position=-1,
        quickie_window=-1,
        quickie_invert_lanes=False,
        end_of_lap_safety_margin=0,
        # ---- BaseEvent / shared knobs ------------------------------------
        cancel_event=cancel_event,
        busy_event=busy_event,
        chat_lock=chat_lock,
        audio_queue=audio_queue,
        broadcast_text_queue=broadcast_text_queue,
        chat_consumer_queue=chat_consumer_queue,
        max_laps_behind_leader=99,
    )

    print(f"\nEvent instantiated: {event!r}")
    print(f"  quickie              : {event.quickie}")
    print(f"  wave_arounds         : {event.wave_arounds}")
    print(f"  max_speed_km         : {event.max_speed_km}")
    print(f"  extra_lanes          : {event.extra_lanes}")
    print(f"  lane_names           : {event.lane_names}")
    print()

    # ------------------------------------------------------------------
    # Drain helper – runs in a background thread so queue messages that
    # the event_sequence posts don't block the main thread.
    # ------------------------------------------------------------------
    def drain(q: queue.Queue, label: str):
        while True:
            try:
                item = q.get(timeout=0.5)
                print(f"  [{label}] {item}")
                q.task_done()
            except queue.Empty:
                if cancel_event.is_set():
                    break

    for q, name in (
        (audio_queue, "AUDIO"),
        (broadcast_text_queue, "BROADCAST"),
        (chat_consumer_queue, "CHAT_CONSUMER"),
    ):
        t = threading.Thread(target=drain, args=(q, name), daemon=True)
        t.start()

    # ------------------------------------------------------------------
    # Run event_sequence() directly – no wait_for_start(), no likelihood
    # roll, just straight into the logic so you can set breakpoints.
    # ------------------------------------------------------------------
    print("Calling event_sequence() …  (Ctrl-C to abort)\n")
    try:
        event.event_sequence()
    except KeyboardInterrupt:
        print("\n[test] Interrupted by user.")
        cancel_event.set()
    except Exception:
        logger.exception("event_sequence raised an unhandled exception")
        cancel_event.set()
        sys.exit(1)
    else:
        print("\n[test] event_sequence() completed successfully.")
    finally:
        cancel_event.set()


if __name__ == "__main__":
    run_test()
