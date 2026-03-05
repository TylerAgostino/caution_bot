"""
conftest.py -- Shared pytest configuration and replay fixture infrastructure
============================================================================

This module defines the ``ReplayFixture`` dataclass that pairs a captured
telemetry JSON file with the bot settings used during that session and the
expected restart order at the moment the green flag is thrown.

ADDING A NEW FIXTURE
--------------------
1.  Capture a telemetry file during a real race or replay::

        python tests/capture_telemetry.py --output tests/fixtures/my_race.json

2.  Create a sidecar metadata file at the same path with a ``.meta.json``
    extension (e.g. ``tests/fixtures/my_race.meta.json``)::

        {
            "description": "Short human-readable description of the scenario",
            "event_kwargs": {
                "wave_arounds": true,
                "extra_lanes": true,
                "max_speed_km": 69,
                "restart_speed_pct": 125,
                "lane_names": ["Right", "Left"],
                "reminder_frequency": 8,
                "auto_restart_get_ready_position": 1.85,
                "auto_restart_form_lanes_position": 1.5,
                "auto_class_separate_position": -1,
                "quickie_auto_restart_get_ready_position": 0.85,
                "quickie_auto_restart_form_lanes_position": 0.5,
                "quickie_auto_class_separate_position": -1,
                "quickie_window": -1,
                "quickie_invert_lanes": false,
                "end_of_lap_safety_margin": 0.1,
                "max_laps_behind_leader": 99
            },
            "expected_restart_order": [
                ["11", "22", "33", "44"]
            ]
        }

    For a multi-lane restart, ``expected_restart_order`` has one inner list
    per lane, in lane order::

        "expected_restart_order": [
            ["11", "33"],
            ["22", "44"]
        ]

3.  The ``replay_fixtures`` fixture (defined below) auto-discovers every
    ``.meta.json`` file in ``tests/fixtures/`` and yields a ``ReplayFixture``
    for each one.  ``test_fixture_restart_order`` in ``test_fixtures.py``
    picks these up automatically — no registration needed.

META.JSON SCHEMA
----------------
All fields in ``event_kwargs`` are optional.  Any key omitted falls back to
the default defined in ``_DEFAULT_EVENT_KWARGS`` below, which matches the
constructor defaults of ``RandomTimedCode69Event``.

``expected_restart_order`` is required.  It must be a non-empty list of
non-empty lists of car-number strings.
"""

from __future__ import annotations

import json
import queue
import sys
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest

# ---------------------------------------------------------------------------
# Ensure project root is on sys.path so ``modules`` is importable when
# conftest is loaded by pytest before any test file adjusts sys.path.
# ---------------------------------------------------------------------------
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from modules.logging_configuration import init_logging  # noqa: E402
from modules.logging_context import set_logger  # noqa: E402

_logger, _logfile = init_logging()
set_logger(_logger, _logfile)

from modules.events.random_code_69_event import RandomTimedCode69Event  # noqa: E402
from tests.mock_irsdk import MockPWA, ReplaySDK  # noqa: E402

# ---------------------------------------------------------------------------
# Fixtures directory
# ---------------------------------------------------------------------------

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"

# ---------------------------------------------------------------------------
# Default event kwargs — mirrors RandomTimedCode69Event constructor defaults.
# Individual .meta.json files only need to specify values that differ.
# ---------------------------------------------------------------------------

_DEFAULT_EVENT_KWARGS: dict[str, Any] = {
    "wave_arounds": True,
    "notify_on_skipped_caution": False,
    "max_speed_km": 69,
    "restart_speed_pct": 125,
    "lane_names": ["Right", "Left"],
    "reminder_frequency": 8,
    "extra_lanes": True,
    "auto_restart_get_ready_position": 1.85,
    "auto_restart_form_lanes_position": 1.5,
    "auto_class_separate_position": -1,
    "quickie_auto_restart_get_ready_position": 0.85,
    "quickie_auto_restart_form_lanes_position": 0.5,
    "quickie_auto_class_separate_position": -1,
    "quickie_window": -1,
    "quickie_invert_lanes": False,
    "end_of_lap_safety_margin": 0.1,
    "max_laps_behind_leader": 99,
}


# ---------------------------------------------------------------------------
# ReplayFixture
# ---------------------------------------------------------------------------


@dataclass
class ReplayFixture:
    """A captured telemetry file paired with settings and the expected outcome.

    Attributes
    ----------
    telemetry_path:
        Path to the ``*.json`` telemetry file produced by ``capture_telemetry.py``.
    description:
        Human-readable label shown in pytest output (from the ``description``
        field of the ``.meta.json`` sidecar).
    event_kwargs:
        Keyword arguments forwarded to ``RandomTimedCode69Event()``.  Already
        merged with ``_DEFAULT_EVENT_KWARGS`` so every key is present.
    expected_restart_order:
        The expected restart order at the moment the green flag is thrown.
        A list of lanes; each lane is a list of car-number strings in order.
        For single-file restarts this will be a list containing one list.
    """

    telemetry_path: Path
    description: str
    event_kwargs: dict[str, Any]
    expected_restart_order: list[list[str]]

    # ------------------------------------------------------------------
    # Factory
    # ------------------------------------------------------------------

    @classmethod
    def from_meta_file(cls, meta_path: Path) -> "ReplayFixture":
        """Load a ``ReplayFixture`` from a ``.meta.json`` sidecar file.

        The corresponding telemetry file is expected to sit next to the
        sidecar with the same stem minus the ``.meta`` suffix.  The
        compressed variant (``.json.gz``) is preferred over plain ``.json``
        when both exist::

            tests/fixtures/my_race.json.gz       ← telemetry (preferred)
            tests/fixtures/my_race.json          ← telemetry (fallback)
            tests/fixtures/my_race.meta.json     ← sidecar (this file)

        Raises
        ------
        FileNotFoundError
            If the telemetry file does not exist next to the sidecar.
        ValueError
            If ``expected_restart_order`` is missing or malformed.
        """
        with meta_path.open("r", encoding="utf-8") as fh:
            meta = json.load(fh)

        # Derive the telemetry path: strip the ".meta" part of the stem.
        # e.g.  my_race.meta.json  →  my_race.json  (or my_race.json.gz)
        # Prefer the compressed variant when both exist; fall back to plain JSON.
        telemetry_stem = meta_path.name.replace(".meta.json", "")
        gz_path = meta_path.parent / f"{telemetry_stem}.json.gz"
        plain_path = meta_path.parent / f"{telemetry_stem}.json"

        if gz_path.exists():
            telemetry_path = gz_path
        elif plain_path.exists():
            telemetry_path = plain_path
        else:
            raise FileNotFoundError(
                f"Telemetry file '{plain_path}' (or '{gz_path}') not found "
                f"for sidecar '{meta_path}'."
            )

        # Merge supplied event_kwargs over the defaults.
        event_kwargs = {**_DEFAULT_EVENT_KWARGS, **meta.get("event_kwargs", {})}

        # Validate expected_restart_order.
        raw_order = meta.get("expected_restart_order")
        if not raw_order or not isinstance(raw_order, list):
            raise ValueError(
                f"'{meta_path}' must contain a non-empty 'expected_restart_order' list."
            )
        for lane in raw_order:
            if not isinstance(lane, list) or not lane:
                raise ValueError(
                    f"'{meta_path}': each lane in 'expected_restart_order' must be "
                    f"a non-empty list of car-number strings."
                )

        return cls(
            telemetry_path=telemetry_path,
            description=meta.get("description", meta_path.stem),
            event_kwargs=event_kwargs,
            expected_restart_order=raw_order,
        )

    # ------------------------------------------------------------------
    # Helpers used by tests
    # ------------------------------------------------------------------

    def build_sdk(self) -> ReplaySDK:
        """Return a fresh ``ReplaySDK`` loaded from ``self.telemetry_path``."""
        return ReplaySDK(self.telemetry_path)

    def build_event(self, sdk: ReplaySDK) -> RandomTimedCode69Event:
        """Construct a ``RandomTimedCode69Event`` wired to *sdk*.

        Threading primitives are created fresh for each call so fixtures can
        be run in isolation without shared state.
        """
        return RandomTimedCode69Event(
            # Scheduling knobs — bypassed because ReplayRunner calls
            # event_sequence() directly, but __init__ still needs them.
            min=0,
            max=1,
            likelihood=100,
            # All event-behaviour knobs come from the sidecar.
            **self.event_kwargs,
            # Infrastructure — fresh per run.
            sdk=sdk,
            pwa=MockPWA(),
            cancel_event=threading.Event(),
            busy_event=threading.Event(),
            chat_lock=threading.Lock(),
            audio_queue=queue.Queue(),
            broadcast_text_queue=queue.Queue(),
            chat_consumer_queue=queue.Queue(),
        )


# ---------------------------------------------------------------------------
# Discovery helper
# ---------------------------------------------------------------------------


def discover_fixtures() -> list[ReplayFixture]:
    """Return a ``ReplayFixture`` for every ``.meta.json`` file in ``FIXTURES_DIR``.

    Files that fail to load are skipped with a warning printed to stdout so a
    single broken sidecar doesn't block all other tests.
    """
    found: list[ReplayFixture] = []
    if not FIXTURES_DIR.exists():
        return found
    for meta_path in sorted(FIXTURES_DIR.glob("*.meta.json")):
        try:
            found.append(ReplayFixture.from_meta_file(meta_path))
        except Exception as exc:
            print(f"[WARN] Skipping fixture '{meta_path.name}': {exc}")
    return found


# ---------------------------------------------------------------------------
# pytest fixture
# ---------------------------------------------------------------------------


def pytest_generate_tests(metafunc: pytest.Metafunc) -> None:
    """Auto-parametrize any test that declares a ``replay_fixture`` parameter.

    Each ``.meta.json`` file in ``tests/fixtures/`` becomes one test case.
    The test ID is the fixture's ``description`` field so pytest output is
    readable::

        test_fixture_restart_order[3-wide at Bathurst - wave arounds]
        test_fixture_restart_order[multi-class Sebring - class separation]

    If no ``.meta.json`` files exist the parameter list is empty and the test
    is skipped automatically by pytest.
    """
    if "replay_fixture" in metafunc.fixturenames:
        fixtures = discover_fixtures()
        metafunc.parametrize(
            "replay_fixture",
            fixtures,
            ids=[f.description for f in fixtures],
        )
