"""
replay_runner.py -- Replay-based test runner for caution_bot events
====================================================================

This module provides the ``ReplayRunner`` class, which drives a
``RandomTimedCode69Event`` (or any ``BaseEvent`` subclass) through a
pre-recorded telemetry replay without any live iRacing connection, real-time
waits, or UI dependencies.

HOW IT WORKS
------------
1.  A ``ReplaySDK`` instance (from ``mock_irsdk.py``) is passed in together
    with a fully-constructed event object.

2.  Before the event thread is started, ``ReplayRunner`` monkeypatches a small
    set of the event's methods/attributes so that the test runs at maximum
    speed with no side-effects:

    * ``event.sleep``  →  a no-op lambda (so ``time.sleep`` is never called).
    * ``event._chat``  →  a wrapper that appends every message to
                          ``result.chat_messages`` before doing nothing else
                          (no pywinauto, no pyperclip).
    * ``event.audio_queue.put``  →  intercepted to capture audio event names.
    * ``event.broadcast_text_queue.put``  →  intercepted to capture broadcast dicts.

3.  ``event.event_sequence()`` is called in a **daemon background thread**.
    The main thread joins that thread up to *timeout* seconds.

4.  The event loop internally calls ``sdk.freeze_var_buffer_latest()`` which
    advances the ``ReplaySDK``'s frame pointer.  When all frames are consumed,
    ``ReplaySDK.freeze_var_buffer_latest()`` raises ``StopIteration``.  The
    runner catches this in the event thread and causes the thread to exit
    cleanly so the main thread's ``join()`` returns.

5.  After the thread finishes (or times out), a ``RunResult`` is returned with
    all captured data.

USAGE EXAMPLE
-------------
::

    from tests.mock_irsdk import ReplaySDK, MockPWA
    from tests.replay_runner import ReplayRunner
    from modules.events.random_code_69_event import RandomTimedCode69Event

    sdk = ReplaySDK("tests/fixtures/my_session.json")
    event = RandomTimedCode69Event(
        sdk=sdk,
        pwa=MockPWA(),
        likelihood=100,
        wave_arounds=False,
        extra_lanes=False,
        ...
    )

    runner = ReplayRunner(sdk, event)
    result = runner.run(timeout=30)

    assert result.completed
    assert any("Green Flag" in m for m in result.chat_messages)
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from typing import Any

# ---------------------------------------------------------------------------
# RunResult
# ---------------------------------------------------------------------------


@dataclass
class RunResult:
    """Captures everything the event produced during a replay run.

    Attributes
    ----------
    chat_messages:
        Every string passed to ``event._chat()``, in call order.
        Race-control messages are stored with their ``/all `` prefix already
        applied (matching what the real ``_chat`` implementation would send),
        so callers can assert on the exact wire format.
    audio_events:
        Every value put onto ``event.audio_queue``, in call order.
    broadcast_messages:
        Every value put onto ``event.broadcast_text_queue``, in call order.
    completed:
        ``True`` if ``event_sequence()`` returned normally (no unhandled
        exception, no timeout).
    timed_out:
        ``True`` if the runner's *timeout* expired before the event thread
        finished.
    frames_consumed:
        The value of ``sdk.current_frame_index`` when the run ended.
    exception:
        The unhandled exception raised by ``event_sequence()``, if any.
        ``None`` on a clean run.
    """

    chat_messages: list[str] = field(default_factory=list)
    audio_events: list[str] = field(default_factory=list)
    broadcast_messages: list[dict] = field(default_factory=list)
    completed: bool = False
    timed_out: bool = False
    frames_consumed: int = 0
    exception: BaseException | None = None
    #: The finalised restart order at the moment the green flag was thrown.
    #: Each inner list is one lane of car-number strings, in restart order.
    #: For single-file restarts there is exactly one inner list.
    #: Empty if the event did not reach the green flag (e.g. skipped, timed out).
    final_restart_order: list[list[str]] = field(default_factory=list)


# ---------------------------------------------------------------------------
# ReplayRunner
# ---------------------------------------------------------------------------


class ReplayRunner:
    """Drives an event through a pre-recorded telemetry replay.

    Parameters
    ----------
    sdk:
        A ``ReplaySDK`` instance loaded from a telemetry JSON file.  The same
        instance must have been passed as ``sdk=`` when the *event* was
        constructed.
    event:
        A fully-constructed ``BaseEvent`` (or subclass) instance.  Its
        ``event_sequence()`` method will be called directly (bypassing
        ``run()``/``wait_for_start()`` so likelihood, timing, and scheduling
        checks are skipped — we want to test the core logic).
    speed_multiplier:
        Kept for API symmetry but currently unused.  ``sleep()`` is always
        patched to a no-op so the replay runs at maximum CPU speed regardless
        of this value.
    """

    def __init__(
        self,
        sdk: Any,  # ReplaySDK — typed as Any to avoid circular imports
        event: Any,  # BaseEvent subclass
        speed_multiplier: float = 1.0,
    ) -> None:
        self._sdk = sdk
        self._event = event
        self._speed_multiplier = speed_multiplier  # reserved for future use

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run(self, timeout: float = 60.0) -> RunResult:
        """Run ``event.event_sequence()`` against the replay and return results.

        The event is executed in a daemon background thread so that a hung
        event does not block the test process forever.  The main thread waits
        at most *timeout* seconds for the event thread to finish.

        Parameters
        ----------
        timeout:
            Maximum wall-clock seconds to wait.  If the thread has not
            finished within this time ``RunResult.timed_out`` is set to
            ``True`` and the thread is abandoned (it is a daemon thread so it
            will be killed when the process exits).

        Returns
        -------
        RunResult
            Populated with all captures made during the run.
        """
        result = RunResult()

        # ------------------------------------------------------------------
        # 1.  Patch event.sleep → no-op
        #     We replace the bound method on the instance so that the original
        #     class method is untouched (important when tests share a class).
        # ------------------------------------------------------------------
        cancel_event = self._event.cancel_event

        def _noop_sleep(seconds: float) -> None:  # noqa: ARG001
            # Still honour cancellation so the event can be interrupted.
            if cancel_event.is_set():
                raise KeyboardInterrupt

        self._event.sleep = _noop_sleep

        # ------------------------------------------------------------------
        # 2.  Patch event._chat → capture messages, skip all UI/pyperclip work.
        #
        #     The real _chat acquires chat_lock, calls pyperclip, and uses
        #     pywinauto.  We replace it entirely.  We *do* replicate the
        #     race_control prefix logic so that callers can assert on the
        #     exact string (e.g. "/all Green Flag!").
        # ------------------------------------------------------------------
        def _capturing_chat(message: str, race_control: bool = False) -> None:
            # Replicate the /all prefix that the real implementation applies
            wire_message = f"/all {message}" if race_control else message
            result.chat_messages.append(wire_message)

            # Also replicate the player-DM detection so chat_consumer_queue
            # still gets populated (tests that care about DMs can check it).
            try:
                import re

                player_car_idx = self._sdk["PlayerCarIdx"]
                drivers = self._sdk["DriverInfo"]["Drivers"]
                driver = next(
                    (d for d in drivers if d["CarIdx"] == player_car_idx), None
                )
                if driver is not None:
                    player_car_number = str(driver["CarNumber"])
                    dm_pattern = rf"^[/@#]{re.escape(player_car_number)}\s+(.+)$"
                    match = re.match(dm_pattern, message)
                    if match:
                        self._event.chat_consumer_queue.put(match.group(1))
            except Exception:
                pass  # DM detection is best-effort

            # Release chat_lock if it happens to be held (the real _chat
            # acquires it; since we skip that acquisition, we must not leave
            # the lock permanently held).  The lock starts acquired in the
            # test helpers, so we must release it after each "send".
            try:
                if self._event.chat_lock.locked():
                    self._event.chat_lock.release()
            except Exception:
                pass

        self._event._chat = _capturing_chat

        # ------------------------------------------------------------------
        # 3.  Intercept audio_queue.put and broadcast_text_queue.put
        #
        #     We wrap the existing queue objects' ``put`` methods rather than
        #     replacing the queues themselves, so the event's reference to
        #     ``self.audio_queue`` still works.
        # ------------------------------------------------------------------
        original_audio_put = self._event.audio_queue.put
        original_broadcast_put = self._event.broadcast_text_queue.put

        def _audio_put(item: Any, *args: Any, **kwargs: Any) -> None:
            result.audio_events.append(item)
            original_audio_put(item, *args, **kwargs)

        def _broadcast_put(item: Any, *args: Any, **kwargs: Any) -> None:
            result.broadcast_messages.append(item)
            original_broadcast_put(item, *args, **kwargs)

        self._event.audio_queue.put = _audio_put
        self._event.broadcast_text_queue.put = _broadcast_put

        # ------------------------------------------------------------------
        # 4.  Make sure chat_lock is *released* at the start so _chat can run.
        #     (The test harness sometimes acquires it to simulate "chat busy"
        #     at startup — see the existing test_code69.py pattern — but for
        #     replay tests we want it free.)
        # ------------------------------------------------------------------
        try:
            # Non-blocking acquire to check state; immediately release
            if self._event.chat_lock.acquire(blocking=False):
                self._event.chat_lock.release()
            # If acquire failed the lock is held; release it once
            else:
                self._event.chat_lock.release()
        except Exception:
            pass

        # ------------------------------------------------------------------
        # 5.  Run event_sequence() in a background daemon thread.
        #
        #     We catch StopIteration (raised by ReplaySDK when frames run out)
        #     and KeyboardInterrupt (raised by our patched sleep when the
        #     cancel_event is set) as normal "end of replay" conditions.
        # ------------------------------------------------------------------
        event_thread_exception: list[BaseException] = []

        def _run_event() -> None:
            try:
                self._event.event_sequence()
                result.completed = True
            except StopIteration:
                # Replay exhausted — treat as a clean end if the event had
                # already done meaningful work (caller checks chat_messages etc.)
                result.completed = True
            except KeyboardInterrupt:
                # cancel_event was set (e.g. by test teardown)
                result.completed = False
            except Exception as exc:
                event_thread_exception.append(exc)
                result.completed = False

        thread = threading.Thread(
            target=_run_event, name="ReplayEventThread", daemon=True
        )
        thread.start()
        thread.join(timeout=timeout)

        if thread.is_alive():
            # Timed out — signal the event to stop and record the outcome
            cancel_event.set()
            result.timed_out = True
            result.completed = False
            # Give the thread a short grace period to acknowledge cancellation
            thread.join(timeout=2.0)

        # ------------------------------------------------------------------
        # 6.  Restore queue methods (good hygiene, prevents cross-test leakage
        #     if the same queue objects are reused).
        # ------------------------------------------------------------------
        try:
            self._event.audio_queue.put = original_audio_put
        except Exception:
            pass
        try:
            self._event.broadcast_text_queue.put = original_broadcast_put
        except Exception:
            pass

        # ------------------------------------------------------------------
        # 7.  Capture final state
        # ------------------------------------------------------------------
        result.frames_consumed = self._sdk.current_frame_index

        if event_thread_exception:
            result.exception = event_thread_exception[0]

        # Collect the final restart order that the event saved onto itself
        # just before throwing the green flag (see final_restart_order on
        # RandomTimedCode69Event).  Guard with getattr so this works for any
        # BaseEvent subclass that doesn't implement the attribute.
        result.final_restart_order = list(
            getattr(self._event, "final_restart_order", [])
        )

        return result
