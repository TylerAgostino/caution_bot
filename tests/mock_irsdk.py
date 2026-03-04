"""
mock_irsdk.py -- Drop-in iRacing SDK replacement for replay-based testing
==========================================================================

This module provides two classes:

  ReplaySDK
  ---------
  A drop-in replacement for ``irsdk.IRSDK`` that, instead of connecting to a
  live iRacing process, replays frames from a telemetry JSON file previously
  captured by ``capture_telemetry.py``.

  Intended use::

      sdk = ReplaySDK("path/to/telemetry.json")
      event = SomeEvent(sdk=sdk, pwa=MockPWA(), ...)
      event.event_sequence()

  The ``ReplaySDK`` interface mirrors every method and attribute of
  ``irsdk.IRSDK`` that is actually used by the caution_bot event code:

  * ``sdk[key]``                  -- dict-style read from the current frame,
                                     with static keys (WeekendInfo, DriverInfo,
                                     CarIdxClass, CarIdxBestLapTime) merged in
                                     transparently from ``meta.static``.
  * ``bool(sdk)``                 -- always True (simulates "connected")
  * ``sdk.startup()``             -- no-op
  * ``sdk.shutdown()``            -- no-op
  * ``sdk.freeze_var_buffer_latest()``   -- advances to the next frame
  * ``sdk.unfreeze_var_buffer_latest()`` -- no-op
  * ``sdk.chat_command(n)``       -- no-op

  Additional replay-specific API:
  * ``sdk.frames``                -- the full list of frame dicts
  * ``sdk.current_frame_index``   -- index of the *current* frame (0-based)
  * ``sdk.meta``                  -- the "meta" dict from the JSON file
  * ``sdk.static``                -- the static-key dict from ``meta.static``
  * ``sdk.is_replay_exhausted``   -- True once all frames have been consumed
  * ``sdk.reset()``               -- rewind to frame 0
  * ``sdk.peek_next()``           -- return the next frame dict without advancing

  File format (as produced by ``capture_telemetry.py``)
  ------------------------------------------------------
  Keys that never change during a session (``WeekendInfo``, ``DriverInfo``,
  ``CarIdxClass``, ``CarIdxBestLapTime``) are stored once in
  ``meta.static`` rather than being repeated in every frame.
  ``__getitem__`` checks the current frame first, then falls back to
  ``meta.static``, so callers never need to know which bucket a key lives in.
  Telemetry files that pre-date this format (where those keys appear inline
  in every frame) continue to work without modification.

  MockPWA
  -------
  A minimal stand-in for ``pywinauto.Application`` that silently absorbs every
  call made by ``BaseEvent.__init__`` and ``BaseEvent._chat``.  Pass an
  instance as the ``pwa=`` kwarg when constructing an event under test so that
  the pywinauto code path does not raise.

IMPORTANT
---------
* This module does NOT import from ``modules`` (no caution_bot internals).
* This module does NOT subclass or import ``irsdk.IRSDK``.  It is a
  completely independent class that only matches the interface.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# MockPWA
# ---------------------------------------------------------------------------


class _MockWindow:
    """Pretends to be a pywinauto WindowSpecification.

    Absorbs ``type_keys()`` and any attribute access that returns another
    ``_MockWindow``, so code like::

        self.pwa["iRacing.com Simulator"].type_keys("^v")

    works without error.
    """

    def type_keys(self, keys: str, *args: Any, **kwargs: Any) -> "_MockWindow":
        return self

    def __getattr__(self, name: str) -> Any:
        # Return self for chained calls (e.g. .wrapper_object())
        return self

    def __call__(self, *args: Any, **kwargs: Any) -> "_MockWindow":
        return self


class MockPWA:
    """Drop-in replacement for ``pywinauto.Application``.

    All methods are no-ops.  The ``connect()`` method accepts the same
    keyword arguments as pywinauto's Application.connect() so that the call
    inside ``BaseEvent.__init__`` succeeds::

        self.pwa.connect(best_match="iRacing.com Simulator", timeout=10)

    Subscript access (``self.pwa["iRacing.com Simulator"]``) returns a
    ``_MockWindow`` whose ``type_keys`` method is also a no-op.
    """

    def connect(self, *args: Any, **kwargs: Any) -> "MockPWA":
        """Pretend to connect to a running application window."""
        return self

    def start(self, *args: Any, **kwargs: Any) -> "MockPWA":
        return self

    def __getitem__(self, key: Any) -> _MockWindow:
        return _MockWindow()

    def __getattr__(self, name: str) -> Any:
        # Catch-all: return a callable no-op for any other attribute access
        def _noop(*args: Any, **kwargs: Any) -> None:
            return None

        return _noop


# ---------------------------------------------------------------------------
# ReplaySDK
# ---------------------------------------------------------------------------


class ReplaySDK:
    """Drop-in replacement for ``irsdk.IRSDK`` that replays recorded frames.

    Parameters
    ----------
    telemetry_path:
        Path to a JSON file produced by ``capture_telemetry.py``.  The file
        must have the structure::

            {
                "meta": { "frame_count": N, ... },
                "frames": [ { "SessionTime": ..., ... }, ... ]
            }

    Raises
    ------
    FileNotFoundError
        If *telemetry_path* does not exist.
    ValueError
        If the JSON file does not contain a ``"frames"`` list.
    """

    def __init__(self, telemetry_path: str | Path) -> None:
        path = Path(telemetry_path)
        if not path.exists():
            raise FileNotFoundError(f"Telemetry file not found: {path}")

        with path.open("r", encoding="utf-8") as fh:
            data = json.load(fh)

        if "frames" not in data or not isinstance(data["frames"], list):
            raise ValueError(
                f"Telemetry file '{path}' must contain a top-level 'frames' list."
            )

        #: Full list of frame dicts, one per recorded tick.
        self.frames: list[dict] = data["frames"]

        #: Metadata dict from the JSON (captured_at, frame_count, …).
        self.meta: dict = data.get("meta", {})

        #: Static keys captured once at session start (WeekendInfo, DriverInfo,
        #: CarIdxClass, CarIdxBestLapTime).  Merged into every __getitem__
        #: lookup so event code sees no difference from the old per-frame format.
        #: Falls back to an empty dict for telemetry files that pre-date this
        #: format (those files have the static keys inline in every frame).
        self.static: dict = self.meta.get("static", {})

        #: Index of the frame that will be returned by the *next* ``__getitem__``
        #: call.  Starts at 0.  Incremented by ``freeze_var_buffer_latest()``.
        self.current_frame_index: int = 0

        # Cache the total number of frames for fast boundary checks.
        self._total_frames: int = len(self.frames)

    # ------------------------------------------------------------------
    # Core interface: dict-style reads
    # ------------------------------------------------------------------

    def __getitem__(self, key: str) -> Any:
        """Return the value for *key* from the current frame.

        Lookup order:
        1. The current frame dict (dynamic keys such as ``SessionTime``,
           ``CarIdxLapDistPct``, etc.)
        2. ``self.static`` (keys hoisted into ``meta.static`` by the capture
           tool: ``WeekendInfo``, ``DriverInfo``, ``CarIdxClass``,
           ``CarIdxBestLapTime``).

        This means callers never need to know which bucket a key lives in.
        Telemetry files that pre-date the static-hoisting format (where those
        keys appear inline in every frame) continue to work because step 1
        will find them before step 2 is ever reached.

        Parameters
        ----------
        key:
            A telemetry key such as ``"SessionTime"`` or ``"CarIdxLapDistPct"``.

        Raises
        ------
        KeyError
            If *key* is not present in either the current frame or ``static``.
        IndexError
            If the replay is exhausted (``current_frame_index`` is beyond the
            last frame) and you try to read a key.
        """
        if self.current_frame_index >= self._total_frames:
            raise IndexError(
                f"ReplaySDK: replay exhausted (frame {self.current_frame_index} of "
                f"{self._total_frames}).  No more data to read."
            )
        frame = self.frames[self.current_frame_index]
        if key in frame:
            return frame[key]
        # Fall back to static keys (WeekendInfo, DriverInfo, CarIdxClass,
        # CarIdxBestLapTime) stored in meta.static by the capture tool.
        if key in self.static:
            return self.static[key]
        raise KeyError(
            f"ReplaySDK: key '{key}' not found in frame {self.current_frame_index} "
            f"or in meta.static."
        )

    # ------------------------------------------------------------------
    # Boolean truthiness -- always True so "if self.sdk:" passes
    # ------------------------------------------------------------------

    def __bool__(self) -> bool:
        return True

    # ------------------------------------------------------------------
    # Lifecycle no-ops
    # ------------------------------------------------------------------

    def startup(self) -> bool:
        """No-op.  In production this connects to iRacing; here it just returns True."""
        return True

    def shutdown(self) -> None:
        """No-op.  In production this disconnects from iRacing."""
        return

    # ------------------------------------------------------------------
    # Buffer control
    # ------------------------------------------------------------------

    def freeze_var_buffer_latest(self) -> None:
        """Advance to the next frame.

        This is the primary mechanism by which the event loop "ticks".  Every
        call advances ``current_frame_index`` by one, making the subsequent
        ``sdk[key]`` calls read from the new frame.

        Raises
        ------
        StopIteration
            When all frames have been consumed (i.e. the replay is exhausted).
            This is intentional: the event loop should catch this signal and
            understand that the replay has ended.
        """
        self.current_frame_index += 1
        if self.current_frame_index >= self._total_frames:
            raise StopIteration(
                f"ReplaySDK: all {self._total_frames} frames have been consumed."
            )

    def unfreeze_var_buffer_latest(self) -> None:
        """No-op.  In production this releases the latched telemetry buffer."""
        return

    # ------------------------------------------------------------------
    # Chat / UI no-ops
    # ------------------------------------------------------------------

    def chat_command(self, n: int) -> None:
        """No-op.  In production this sends an iRacing chat command."""
        return

    # ------------------------------------------------------------------
    # Replay-specific helpers
    # ------------------------------------------------------------------

    @property
    def is_replay_exhausted(self) -> bool:
        """True when all frames have been consumed."""
        return self.current_frame_index >= self._total_frames

    def reset(self) -> None:
        """Rewind the replay to frame 0."""
        self.current_frame_index = 0

    def peek_next(self) -> dict | None:
        """Return the *next* frame dict without advancing the index.

        Returns ``None`` if the replay is already exhausted.

        This is useful in assertions where you want to inspect what the event
        will *see* on the following tick without actually consuming the frame::

            next_frame = sdk.peek_next()
            assert next_frame["SessionTick"] == expected_tick
        """
        next_index = self.current_frame_index + 1
        if next_index >= self._total_frames:
            return None
        return self.frames[next_index]
