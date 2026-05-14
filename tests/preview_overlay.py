#!/usr/bin/env python3
"""
preview_overlay.py  —  Automated overlay simulation preview server
==================================================================

Serves the overlay HTML/CSS/SSE stack with a **fully automated session
simulation** so you can preview every overlay state transition without
running the full Flet UI or connecting to iRacing.

The simulation runs a complete F1-style qualifying event in a continuous loop:

    Pre-Q1 → Q1 (live) → Q1 (checkered + flying laps) →
    Pre-Q2 → Q2 (live) → Q2 (checkered + flying laps) →
    Pre-Q3 → Q3 (live) → Q3 (checkered + flying laps) →
    final standings pause → (restart)

Sub-session lengths (~30–60 s) and inter-session gaps (~12 s) are kept short
so the full demo loops in just a few minutes. All transitions are automatic.

Live reload
-----------
Whenever ``overlay.html`` changes on disk, every connected browser tab
reloads automatically — no manual refresh needed.

Usage
-----
    python tests/preview_overlay.py
    python tests/preview_overlay.py --port 9765 --width 1920 --height 1080
    python tests/preview_overlay.py --no-browser

Then open http://localhost:9765/ in your browser or OBS browser source.
Press Ctrl+C to stop.
"""

from __future__ import annotations

import argparse
import json
import math
import queue
import random
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

# ---------------------------------------------------------------------------
# Paths  (mirrors the layout expected by overlay_consumer_event.py)
# ---------------------------------------------------------------------------

_THIS_DIR = Path(__file__).parent
_REPO_DIR = _THIS_DIR.parent
_OVERLAY_HTML = _REPO_DIR / "modules" / "flet_pages" / "overlays" / "overlay.html"
_FONTS_DIR = _OVERLAY_HTML.parent.parent / "fonts"

# ---------------------------------------------------------------------------
# Driver roster
# ---------------------------------------------------------------------------
# 'speed' is each driver's offset (in seconds) above the fastest possible
# lap time.  Lower speed → faster driver.

_BASE_LAP = 83.0  # theoretical minimum lap time (seconds)

DRIVERS: list[dict] = [
    {"car": "63", "name": "River Page", "speed": 0.000},
    {"car": "99", "name": "Giovanni Romano", "speed": 0.152},
    {"car": "16", "name": "Alex Marsh King", "speed": 0.281},
    {"car": "69", "name": "Tyler Agostino", "speed": 0.354},
    {"car": "10", "name": "Chris Bright", "speed": 0.482},
    {"car": "45", "name": "Tyler Carlton", "speed": 0.601},
    {"car": "119", "name": "Rognald Hotdognald", "speed": 0.714},
    {"car": "9", "name": "Brooks Clayton", "speed": 0.852},
    {"car": "017", "name": "Erik Ronnenberg", "speed": 0.923},
    {"car": "8", "name": "Jason L", "speed": 1.051},
    {"car": "243", "name": "Austin Tucker", "speed": 1.168},
    {"car": "42", "name": "Greg Beckman", "speed": 1.287},
    {"car": "13", "name": "Todd Madole", "speed": 1.381},
    {"car": "64", "name": "Mr. Hall", "speed": 1.474},
    {"car": "22", "name": "Boy Howdy", "speed": 1.562},
    {"car": "87", "name": "xXhalcy0n_SPNKr_94Xx", "speed": 2.103},
    {"car": "2", "name": "Ethan Conde", "speed": 2.248},
    {"car": "067", "name": "Alex Anderson", "speed": 2.401},
    {"car": "837", "name": "Sean Nelan", "speed": 2.553},
    {"car": "5", "name": "Mac Verstoopen", "speed": 2.801},
]

# ---------------------------------------------------------------------------
# Session configuration  (short durations for a snappy demo loop)
# ---------------------------------------------------------------------------

SESSION_CONFIG: list[dict] = [
    {"name": "Q1", "duration": 60, "advancing": 15},  # 20 cars → 15 advance
    {"name": "Q2", "duration": 50, "advancing": 10},  # 15 cars → 10 advance
    {"name": "Q3", "duration": 40, "advancing": 0},  # 10 cars → winner
]

_ALL_SESSION_NAMES: list[str] = [s["name"] for s in SESSION_CONFIG]

# Timing constants (seconds)
_PRE_SESSION_DURATION = 12  # countdown before each session
_POST_CHECKERED_PAUSE = 4  # standings shown after all drivers finish
_LOOP_RESTART_PAUSE = 6  # final standings held before the sim loops
_SIM_TICK = 0.5  # broadcast interval

# ---------------------------------------------------------------------------
# Shared SSE client queues
# ---------------------------------------------------------------------------

_rc_clients: list[queue.Queue] = []
_f1_clients: list[queue.Queue] = []
_reload_clients: list[queue.Queue] = []
_clients_lock = threading.Lock()

# Most-recent F1 state — sent immediately to newly connected clients.
_current_f1_state: dict = {
    "session_name": "",
    "time_remaining": "--:--",
    "checkered_flag": False,
    "sessions": [],
    "drivers": [],
}


def _broadcast_f1(state: dict) -> None:
    global _current_f1_state
    _current_f1_state = state
    payload = json.dumps(state)
    with _clients_lock:
        for q in list(_f1_clients):
            q.put(payload)


def _broadcast_rc(title: str, text: str) -> None:
    payload = json.dumps({"title": title, "text": text})
    with _clients_lock:
        for q in list(_rc_clients):
            q.put(payload)


def _broadcast_reload() -> None:
    with _clients_lock:
        for q in list(_reload_clients):
            q.put("reload")


# ---------------------------------------------------------------------------
# Formatting helpers
# ---------------------------------------------------------------------------


def _fmt_time(seconds: float | None) -> str:
    """Format a lap time (seconds) as 'MM:SS.mmm', or '' for None."""
    if seconds is None:
        return ""
    minutes = int(seconds // 60)
    secs = seconds % 60
    return f"{minutes:02d}:{secs:06.3f}"


def _fmt_countdown(seconds: float) -> str:
    """Format a countdown value (seconds) as 'MM:SS'."""
    s = max(0.0, seconds)
    return f"{int(s // 60):02d}:{int(s % 60):02d}"


# ---------------------------------------------------------------------------
# Simulation helpers
# ---------------------------------------------------------------------------


def _gen_lap_time(driver: dict, session_idx: int) -> float:
    """Return a plausible lap time for *driver* in the given session (0-based)."""
    # Drivers tend to improve slightly as qualifying progresses.
    improvement = session_idx * random.uniform(0.02, 0.20)
    noise = random.gauss(0.0, 0.13)
    return _BASE_LAP + driver["speed"] - improvement + noise


def _compute_status(pos: int, advancing: int) -> str:
    """Return 'safe', 'at_risk', or 'elimination_zone' based on position vs. cutoff."""
    if advancing <= 0:
        return "safe"
    if pos > advancing:
        return "elimination_zone"
    if pos == advancing:
        return "at_risk"
    return "safe"


# ---------------------------------------------------------------------------
# Overlay state builder
# ---------------------------------------------------------------------------


def _build_overlay_state(
    *,
    session_name: str,
    time_remaining: str,
    checkered_flag: bool,
    laptimes: dict[str, dict[str, float]],  # {session_name: {car: seconds}}
    knocked_out: set[str],
    session_finishers: set[str],
    active_session: str | None,  # None during pre-session countdowns
    advancing: int,  # cars advancing from the active session (0 = final)
) -> dict:
    """
    Build the complete overlay state dict suitable for JSON-broadcasting.

    active_session
        The Qn name of the session currently running, or None if we are in a
        pre-session countdown phase.  Controls which session column is treated
        as "live" for status/no_current_time calculations.
    """

    # ── Determine which session columns to display ─────────────────────────
    # Show only sessions that already have at least one lap time recorded.
    visible_sessions: list[str] = [sn for sn in _ALL_SESSION_NAMES if laptimes.get(sn)]
    if not visible_sessions:
        visible_sessions = [_ALL_SESSION_NAMES[0]]

    # Always include the active session column even before any laps are set,
    # so that "No Time" placeholders appear from the first tick.
    if active_session and active_session not in visible_sessions:
        idx = _ALL_SESSION_NAMES.index(active_session)
        visible_sessions = _ALL_SESSION_NAMES[: idx + 1]

    is_active_q = active_session is not None and not session_name.startswith("Pre-")
    curr_times = laptimes.get(active_session, {}) if active_session else {}

    # ── Sort non-knocked-out drivers ───────────────────────────────────────
    # Primary:   current-session lap time (fastest first; inf if no time yet)
    # Secondary: best time in the most recent previous session (for tie-breaks)
    active_cars: list[str] = [d["car"] for d in DRIVERS if d["car"] not in knocked_out]

    def _active_sort_key(car: str) -> tuple:
        t_curr = curr_times.get(car, math.inf)
        t_prev = math.inf
        for sn in reversed(visible_sessions[:-1]):
            t = laptimes.get(sn, {}).get(car)
            if t is not None:
                t_prev = t
                break
        return (t_curr, t_prev)

    active_cars.sort(key=_active_sort_key)

    # ── Build active driver rows ───────────────────────────────────────────
    drivers_out: list[dict] = []

    for pos_0, car in enumerate(active_cars):
        pos = pos_0 + 1
        info = next(x for x in DRIVERS if x["car"] == car)

        has_curr_time = car in curr_times
        no_current_time = is_active_q and not has_curr_time

        # Status classification
        if is_active_q and advancing > 0 and has_curr_time:
            status = _compute_status(pos, advancing)
        else:
            status = "safe"

        # Best time shown in the timing tower
        best_raw: float | None = curr_times.get(car)
        if best_raw is None:
            for sn in reversed(visible_sessions):
                t = laptimes.get(sn, {}).get(car)
                if t is not None:
                    best_raw = t
                    break

        session_times_fmt = {
            sn: _fmt_time(laptimes.get(sn, {}).get(car)) for sn in visible_sessions
        }

        drivers_out.append(
            {
                "position": pos,
                "car_num": car,
                "driver_name": info["name"],
                "best_time": _fmt_time(best_raw),
                "status": status,
                "session_times": session_times_fmt,
                "no_current_time": no_current_time,
                "finished": car in session_finishers,
            }
        )

    # ── Append knocked-out drivers at the bottom ───────────────────────────
    ko_cars: list[str] = [d["car"] for d in DRIVERS if d["car"] in knocked_out]

    def _ko_sort_key(car: str) -> float:
        best = math.inf
        for sn in _ALL_SESSION_NAMES:
            t = laptimes.get(sn, {}).get(car)
            if t is not None and t < best:
                best = t
        return best

    ko_cars.sort(key=_ko_sort_key)

    for ko_pos_0, car in enumerate(ko_cars):
        info = next(x for x in DRIVERS if x["car"] == car)
        best_raw = None
        for sn in _ALL_SESSION_NAMES:
            t = laptimes.get(sn, {}).get(car)
            if t is not None and (best_raw is None or t < best_raw):
                best_raw = t

        session_times_fmt = {
            sn: _fmt_time(laptimes.get(sn, {}).get(car)) for sn in visible_sessions
        }

        drivers_out.append(
            {
                "position": len(active_cars) + ko_pos_0 + 1,
                "car_num": car,
                "driver_name": info["name"],
                "best_time": _fmt_time(best_raw),
                "status": "knocked_out",
                "session_times": session_times_fmt,
                "no_current_time": False,
                "finished": car in session_finishers,
            }
        )

    return {
        "session_name": session_name,
        "time_remaining": time_remaining,
        "checkered_flag": checkered_flag,
        "sessions": visible_sessions,
        "drivers": drivers_out,
    }


# ---------------------------------------------------------------------------
# Main simulation loop
# ---------------------------------------------------------------------------


def _run_simulation() -> None:
    """
    Drive the full qualifying session simulation indefinitely.

    Each iteration of the outer while-loop is one complete qualifying event:
        Pre-Q1 countdown → Q1 live → Q1 checkered/flying laps →
        Pre-Q2 countdown → Q2 live → Q2 checkered/flying laps →
        Pre-Q3 countdown → Q3 live → Q3 checkered/flying laps →
        final-standings pause → (loop)
    """
    time.sleep(0.5)  # brief pause so the HTTP server is fully up first

    while True:
        # ── Per-loop state reset ───────────────────────────────────────────
        laptimes: dict[str, dict[str, float]] = {sn: {} for sn in _ALL_SESSION_NAMES}
        knocked_out: set[str] = set()
        eligible: list[str] | None = None  # None → all 20 cars

        for sess_idx, sess_cfg in enumerate(SESSION_CONFIG):
            sess_name = sess_cfg["name"]
            duration = float(sess_cfg["duration"])
            advancing = sess_cfg["advancing"]
            pre_name = f"Pre-{sess_name}"

            # Cars eligible for this session
            session_cars: list[str] = (
                list(eligible) if eligible is not None else [d["car"] for d in DRIVERS]
            )
            active_cars_this_sess = [c for c in session_cars if c not in knocked_out]

            # ── Pre-session countdown ──────────────────────────────────────
            countdown_end = time.monotonic() + _PRE_SESSION_DURATION
            while time.monotonic() < countdown_end:
                state = _build_overlay_state(
                    session_name=pre_name,
                    time_remaining=_fmt_countdown(countdown_end - time.monotonic()),
                    checkered_flag=False,
                    laptimes=laptimes,
                    knocked_out=knocked_out,
                    session_finishers=set(),
                    active_session=None,
                    advancing=advancing,
                )
                _broadcast_f1(state)
                time.sleep(_SIM_TICK)

            # ── Schedule when each driver sets their lap times ─────────────
            # Every active car gets a first lap somewhere between 20 %–90 %
            # through the session.  ~65 % of cars also set a second (faster)
            # attempt in the latter half.
            first_reveals: dict[str, float] = {}
            second_reveals: dict[str, float] = {}

            for car in active_cars_this_sess:
                first_reveals[car] = random.uniform(0.20, 0.90) * duration
                if random.random() < 0.65:
                    t2 = random.uniform(0.55, 0.98) * duration
                    if t2 > first_reveals[car] + 2.0:
                        second_reveals[car] = t2

            # ── Active session ─────────────────────────────────────────────
            _broadcast_rc(
                "Race Control",
                "Pit Exit OPEN!",
            )

            sess_start = time.monotonic()
            session_finishers: set[str] = set()

            while True:
                elapsed = time.monotonic() - sess_start
                remaining = max(0.0, duration - elapsed)
                out_of_time = elapsed >= duration

                # Reveal first-lap times as each driver's scheduled moment arrives.
                for car in list(first_reveals):
                    if elapsed >= first_reveals[car]:
                        drv = next(d for d in DRIVERS if d["car"] == car)
                        laptimes[sess_name][car] = _gen_lap_time(drv, sess_idx)
                        del first_reveals[car]

                # Reveal second (potentially improved) lap times.
                for car in list(second_reveals):
                    if elapsed >= second_reveals[car]:
                        drv = next(d for d in DRIVERS if d["car"] == car)
                        new_t = _gen_lap_time(drv, sess_idx)
                        existing = laptimes[sess_name].get(car, math.inf)
                        if new_t < existing:
                            laptimes[sess_name][car] = new_t
                        del second_reveals[car]

                state = _build_overlay_state(
                    session_name=sess_name,
                    time_remaining=_fmt_countdown(remaining),
                    checkered_flag=out_of_time,
                    laptimes=laptimes,
                    knocked_out=knocked_out,
                    session_finishers=session_finishers,
                    active_session=sess_name,
                    advancing=advancing,
                )
                _broadcast_f1(state)

                if out_of_time:
                    _broadcast_rc(
                        "Race Control",
                        "Checkered Flag",
                    )
                    break

                time.sleep(_SIM_TICK)

            # ── Checkered-flag phase: drivers complete their flying laps ───
            # Any car that never set a time gets one now (they were still out).
            for car in active_cars_this_sess:
                if car not in laptimes[sess_name]:
                    drv = next(d for d in DRIVERS if d["car"] == car)
                    laptimes[sess_name][car] = _gen_lap_time(drv, sess_idx)

            # Stagger when each car crosses the line over the next few seconds.
            pending_finish: set[str] = set(active_cars_this_sess)
            checkered_window = max(4.0, len(pending_finish) * 0.6)
            finish_at: dict[str, float] = {
                car: time.monotonic() + random.uniform(0.3, checkered_window)
                for car in pending_finish
            }
            phase_deadline = time.monotonic() + checkered_window + 1.0

            while pending_finish and time.monotonic() < phase_deadline:
                now = time.monotonic()
                for car in list(pending_finish):
                    if now >= finish_at[car]:
                        session_finishers.add(car)
                        pending_finish.discard(car)

                state = _build_overlay_state(
                    session_name=sess_name,
                    time_remaining="00:00",
                    checkered_flag=True,
                    laptimes=laptimes,
                    knocked_out=knocked_out,
                    session_finishers=session_finishers,
                    active_session=sess_name,
                    advancing=advancing,
                )
                _broadcast_f1(state)
                time.sleep(_SIM_TICK)

            # Ensure every active car is marked finished before moving on.
            session_finishers.update(active_cars_this_sess)

            # ── Process results — determine who advances ───────────────────
            session_results: list[tuple[str, float]] = sorted(
                laptimes[sess_name].items(), key=lambda x: x[1]
            )

            if advancing > 0:
                advancing_cars = [car for car, _ in session_results[:advancing]]
                eliminated = [car for car, _ in session_results[advancing:]]

                for car in eliminated:
                    knocked_out.add(car)
                # Any eligible car with no recorded time is also eliminated.
                for car in active_cars_this_sess:
                    if car not in knocked_out and car not in laptimes[sess_name]:
                        knocked_out.add(car)

                eligible = advancing_cars
            else:
                # Final session — rank everyone, nobody is eliminated.
                eligible = [car for car, _ in session_results]

            # ── Post-checkered pause — show the all-done standings board ───
            pause_end = time.monotonic() + _POST_CHECKERED_PAUSE
            while time.monotonic() < pause_end:
                state = _build_overlay_state(
                    session_name=sess_name,
                    time_remaining="00:00",
                    checkered_flag=True,
                    laptimes=laptimes,
                    knocked_out=knocked_out,
                    session_finishers=session_finishers,
                    active_session=sess_name,
                    advancing=advancing,
                )
                _broadcast_f1(state)
                time.sleep(_SIM_TICK)

        # ── End of full event — hold final standings, then restart ─────────
        final_sess = _ALL_SESSION_NAMES[-1]
        loop_end = time.monotonic() + _LOOP_RESTART_PAUSE
        while time.monotonic() < loop_end:
            state = _build_overlay_state(
                session_name=final_sess,
                time_remaining="00:00",
                checkered_flag=True,
                laptimes=laptimes,
                knocked_out=knocked_out,
                session_finishers=session_finishers,
                active_session=final_sess,
                advancing=0,
            )
            _broadcast_f1(state)
            time.sleep(_SIM_TICK)

        # Brief blank gap before the next loop so the restart is perceptible.
        _broadcast_f1(
            {
                "session_name": "Pre-Q1",
                "time_remaining": "--:--",
                "checkered_flag": False,
                "sessions": [_ALL_SESSION_NAMES[0]],
                "drivers": [],
            }
        )
        time.sleep(1.5)


# ---------------------------------------------------------------------------
# File watcher — live reload on overlay.html changes
# ---------------------------------------------------------------------------


def _file_watcher(watched_paths: list[Path]) -> None:
    """Reload all connected browser tabs whenever a watched file changes."""
    mtimes: dict[Path, float] = {
        p: (p.stat().st_mtime if p.exists() else 0.0) for p in watched_paths
    }
    while True:
        time.sleep(1.0)
        for p in watched_paths:
            if not p.exists():
                continue
            mtime = p.stat().st_mtime
            if mtime != mtimes[p]:
                mtimes[p] = mtime
                print(f"  [live-reload] {p.name} changed — refreshing browsers")
                _broadcast_reload()
                break  # one reload per tick is enough


# ---------------------------------------------------------------------------
# HTTP handler
# ---------------------------------------------------------------------------

_LIVE_RELOAD_SNIPPET = """
<script>
  /* Injected by preview_overlay.py — live reload on file changes */
  (function () {
    const _r = new EventSource('/sse/reload');
    _r.onmessage = () => { console.log('[preview] reloading...'); location.reload(); };
  })();
</script>
"""


class _Server(ThreadingHTTPServer):
    allow_reuse_address = True
    daemon_threads = True


class PreviewHandler(BaseHTTPRequestHandler):
    """Request handler for the preview server."""

    # Class-level config — patched in main() before the server starts.
    port: int = 9765
    width: int = 1920
    height: int = 1080

    def do_GET(self) -> None:  # noqa: N802
        path = self.path.split("?")[0]

        match path:
            case "/health":
                self._handle_health()
            case "/sse/rc":
                self._handle_sse(_rc_clients, initial_payload=None)
            case "/sse/f1":
                self._handle_sse(
                    _f1_clients,
                    initial_payload=json.dumps(_current_f1_state),
                )
            case "/sse/reload":
                self._handle_sse(_reload_clients, initial_payload=None)
            case _ if path.startswith("/static/fonts/"):
                font_name = path[len("/static/fonts/") :]
                self._serve_file(_FONTS_DIR / font_name, "font/truetype")
            case _:
                self._serve_html(_OVERLAY_HTML)

    # ------------------------------------------------------------------ #
    # Health Check                                                         #
    # ------------------------------------------------------------------ #

    def _handle_health(self) -> None:
        """Health check endpoint for nginx upstream monitoring.

        Returns 200 OK with JSON payload indicating:
        - status: always "ok" when server is running
        - active: false (preview server is never "active" in production sense)
        - mode: "preview" to distinguish from live server
        - port: the port this server is listening on

        This allows nginx to:
        1. Use this server as a backup when the live server is down
        2. Keep serving overlay content even when no quali session is running
        3. Automatically fail back to this server when live server stops
        """
        payload = json.dumps(
            {
                "status": "ok",
                "active": False,
                "mode": "preview",
                "port": self.port,
            }
        )
        body = payload.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
        self.end_headers()
        self.wfile.write(body)

    # ------------------------------------------------------------------ #
    # SSE                                                                  #
    # ------------------------------------------------------------------ #

    def _handle_sse(self, client_list: list, initial_payload: str | None) -> None:
        """Hold the connection open and stream Server-Sent Events."""
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "keep-alive")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()

        client_q: queue.Queue = queue.Queue()
        if initial_payload is not None:
            client_q.put(initial_payload)

        with _clients_lock:
            client_list.append(client_q)

        try:
            while True:
                try:
                    data = client_q.get(timeout=15)
                    self.wfile.write(f"data: {data}\n\n".encode())
                    self.wfile.flush()
                except queue.Empty:
                    # Keepalive comment — prevents the browser from closing the stream.
                    self.wfile.write(b": ping\n\n")
                    self.wfile.flush()
        except Exception:
            pass
        finally:
            with _clients_lock:
                if client_q in client_list:
                    client_list.remove(client_q)

    # ------------------------------------------------------------------ #
    # Static / HTML                                                        #
    # ------------------------------------------------------------------ #

    def _serve_html(self, file_path: Path) -> None:
        if not file_path.exists():
            self.send_error(404, f"Overlay not found: {file_path.name}")
            return
        content = (
            file_path.read_text(encoding="utf-8")
            .replace("{{WIDTH}}", str(self.width))
            .replace("{{HEIGHT}}", str(self.height))
            .replace("{{PORT}}", str(self.port))
        )
        # Inject the live-reload listener just before </body>.
        body = content.replace("</body>", _LIVE_RELOAD_SNIPPET + "</body>", 1)
        encoded = body.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def _serve_file(self, file_path: Path, mime: str) -> None:
        if not file_path.exists():
            self.send_error(404, f"Not found: {file_path.name}")
            return
        data = file_path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", mime)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, format, *args):  # noqa: N802, A002
        pass  # suppress per-request access-log noise


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> None:
    total_demo_secs = (
        sum(
            _PRE_SESSION_DURATION + s["duration"] + _POST_CHECKERED_PAUSE
            for s in SESSION_CONFIG
        )
        + _LOOP_RESTART_PAUSE
    )

    parser = argparse.ArgumentParser(
        description="Automated overlay simulation preview — no iRacing connection needed.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--port", type=int, default=9765, help="HTTP port (default 9765)"
    )
    parser.add_argument(
        "--width", type=int, default=1920, help="Overlay canvas width  (default 1920)"
    )
    parser.add_argument(
        "--height", type=int, default=1080, help="Overlay canvas height (default 1080)"
    )
    parser.add_argument(
        "--no-browser", action="store_true", help="Don't auto-open a browser tab"
    )
    args = parser.parse_args()

    PreviewHandler.port = args.port
    PreviewHandler.width = args.width
    PreviewHandler.height = args.height

    server = _Server(("", args.port), PreviewHandler)

    # Background simulation thread
    threading.Thread(
        target=_run_simulation,
        daemon=True,
        name="preview-sim",
    ).start()

    # Live-reload file watcher
    watched = [_OVERLAY_HTML] if _OVERLAY_HTML.exists() else []
    if watched:
        threading.Thread(
            target=_file_watcher,
            args=(watched,),
            daemon=True,
            name="preview-watcher",
        ).start()

    url = f"http://localhost:{args.port}/"
    sep = "─" * 62
    print(f"\n  {sep}")
    print(f"  Overlay simulation preview server")
    print(f"  {sep}")
    print(f"  Open:  {url}")
    print(f"  {sep}")
    print(f"  Session flow (loops automatically every ~{total_demo_secs:.0f} s):")
    for s in SESSION_CONFIG:
        cars_in = (
            len(DRIVERS)
            if s == SESSION_CONFIG[0]
            else SESSION_CONFIG[SESSION_CONFIG.index(s) - 1]["advancing"]
        )
        adv_str = f"→ {s['advancing']} advance" if s["advancing"] else "→ final"
        print(
            f"    Pre-{s['name']} ({_PRE_SESSION_DURATION}s)  "
            f"{s['name']} live ({s['duration']}s, {cars_in} cars, {adv_str})"
        )
    print(f"  Live reload:  active (edit overlay.html to trigger)")
    print(f"  {sep}")
    print(f"  Press Ctrl+C to stop.\n")

    if not args.no_browser:
        threading.Timer(0.6, webbrowser.open, args=(url,)).start()

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n  Stopping preview server.")
        server.shutdown()
        server.server_close()


if __name__ == "__main__":
    main()
