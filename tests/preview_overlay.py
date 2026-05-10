#!/usr/bin/env python3
"""
preview_overlay.py  —  Overlay appearance test server
======================================================
Serves the overlay HTML/CSS/SSE stack with **static data** so you can
tweak the overlay appearance without running the full Flet UI or
connecting to iRacing.

Simulated scenario
------------------
  • Q2 qualifying — checkered flag out, session clock at 0:00
  • P1-P9 safe: have finished their laps, advancing to Q3
  • P10 L. Stroll at_risk: last safe spot, still on a flying lap (no finished flag)
  • P11 E. Ocon elimination_zone: first to drop, also still on a flying lap
  • P12-P15 elimination_zone: have pitted; sealed unless Stroll/Ocon swap with them
  • P16-P20 knocked_out: eliminated in Q1, never ran in Q2
  • Race-control banner fires *rc_delay* seconds after the first client
    connects, then repeats every *rc_interval* seconds

Live reload
-----------
Whenever ``overlay.html`` or ``overlay.css`` changes on disk, every
connected browser tab reloads automatically — no manual refresh needed.

Manual RC trigger
-----------------
Visit http://localhost:<PORT>/trigger-rc in any tab (or hit it with curl)
to send the RC banner immediately to all connected overlays.

Usage
-----
    python tests/preview_overlay.py
    python tests/preview_overlay.py --port 9765 --width 1920 --height 1080
    python tests/preview_overlay.py --rc-delay 2 --rc-interval 20
    python tests/preview_overlay.py --no-browser

Then open http://localhost:9765/ in your browser or OBS browser source.
Press Ctrl+C to stop.
"""

from __future__ import annotations

import argparse
import json
import queue
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
_DEFAULT_CSS = _REPO_DIR / "modules" / "flet_pages" / "overlay.css"
_FONTS_DIR = _DEFAULT_CSS.parent / "fonts"

# ---------------------------------------------------------------------------
# Static scenario data  —  Q2 checkered flag, session still live
# ---------------------------------------------------------------------------
#
# Scenario: the Q2 session clock has hit zero and the checkered flag is out,
# but two drivers are still on flying laps — the results are not yet final.
#
# All four row statuses are represented so every CSS class is exercisable:
#
#   safe             — P1-P9   advancing to Q3, already finished their laps
#   at_risk          — P10  L. Stroll — last safe spot, still on a flying lap
#   elimination_zone — P11  E. Ocon   — first out, also still on a flying lap
#                      P12-P15 have pitted; their fates are sealed unless
#                              Stroll or Ocon swap with them
#   knocked_out      — P16-P20 eliminated in Q1, never ran in Q2
#
# Toggle to ALT_F1_STATE (/trigger-alt) to see the same standings with the
# session clock still running and no checkered flag.
# ---------------------------------------------------------------------------

STATIC_F1_STATE: dict = {
    "session_name": "Q2",
    "time_remaining": "0:00",
    "checkered_flag": True,
    "sessions": ["Q1", "Q2"],
    "drivers": [
        # ── P1-P9 safe — advancing to Q3, laps completed ─────────────────────
        {
            "position": 1,
            "car_num": "1",
            "driver_name": "J. Hamilton",
            "best_time": "01:23.789",
            "status": "safe",
            "session_times": {"Q1": "01:25.123", "Q2": "01:23.789"},
            "no_current_time": False,
            "finished": True,
        },
        {
            "position": 2,
            "car_num": "44",
            "driver_name": "C. Verstappen",
            "best_time": "01:23.945",
            "status": "safe",
            "session_times": {"Q1": "01:25.456", "Q2": "01:23.945"},
            "no_current_time": False,
            "finished": True,
        },
        {
            "position": 3,
            "car_num": "4",
            "driver_name": "L. Norris",
            "best_time": "01:24.012",
            "status": "safe",
            "session_times": {"Q1": "01:25.234", "Q2": "01:24.012"},
            "no_current_time": False,
            "finished": True,
        },
        {
            "position": 4,
            "car_num": "81",
            "driver_name": "O. Piastri",
            "best_time": "01:24.156",
            "status": "safe",
            "session_times": {"Q1": "01:25.345", "Q2": "01:24.156"},
            "no_current_time": False,
            "finished": True,
        },
        {
            "position": 5,
            "car_num": "16",
            "driver_name": "C. Leclerc",
            "best_time": "01:24.234",
            "status": "safe",
            "session_times": {"Q1": "01:25.456", "Q2": "01:24.234"},
            "no_current_time": False,
            "finished": True,
        },
        {
            "position": 6,
            "car_num": "63",
            "driver_name": "G. Russell",
            "best_time": "01:24.389",
            "status": "safe",
            "session_times": {"Q1": "01:25.567", "Q2": "01:24.389"},
            "no_current_time": False,
            "finished": True,
        },
        {
            "position": 7,
            "car_num": "55",
            "driver_name": "C. Sainz",
            "best_time": "01:24.445",
            "status": "safe",
            "session_times": {"Q1": "01:25.678", "Q2": "01:24.445"},
            "no_current_time": False,
            "finished": True,
        },
        {
            "position": 8,
            "car_num": "14",
            "driver_name": "F. Alonso",
            "best_time": "01:24.567",
            "status": "safe",
            "session_times": {"Q1": "01:25.789", "Q2": "01:24.567"},
            "no_current_time": False,
            "finished": True,
        },
        {
            "position": 9,
            "car_num": "11",
            "driver_name": "S. Perez",
            "best_time": "01:24.623",
            "status": "safe",
            "session_times": {"Q1": "01:25.891", "Q2": "01:24.623"},
            "no_current_time": False,
            "finished": True,
        },
        # ── P10 at_risk — last Q3 spot, still on a flying lap ─────────────────
        {
            "position": 10,
            "car_num": "18",
            "driver_name": "L. Stroll",
            "best_time": "01:24.678",
            "status": "at_risk",
            "session_times": {"Q1": "01:26.012", "Q2": "01:24.678"},
            "no_current_time": False,
            "finished": False,  # still on a flying lap — could improve or be beaten
        },
        # ── P11 elimination_zone — first to drop, also still on a flying lap ──
        {
            "position": 11,
            "car_num": "31",
            "driver_name": "E. Ocon",
            "best_time": "01:24.712",
            "status": "elimination_zone",
            "session_times": {"Q1": "01:26.123", "Q2": "01:24.712"},
            "no_current_time": False,
            "finished": False,  # chasing Stroll for P10
        },
        # ── P12-P15 elimination_zone — pitted; eliminated unless above pair swaps
        {
            "position": 12,
            "car_num": "10",
            "driver_name": "P. Gasly",
            "best_time": "01:24.789",
            "status": "elimination_zone",
            "session_times": {"Q1": "01:26.234", "Q2": "01:24.789"},
            "no_current_time": False,
            "finished": True,
        },
        {
            "position": 13,
            "car_num": "27",
            "driver_name": "N. Hulkenberg",
            "best_time": "01:24.834",
            "status": "elimination_zone",
            "session_times": {"Q1": "01:26.345", "Q2": "01:24.834"},
            "no_current_time": False,
            "finished": True,
        },
        {
            "position": 14,
            "car_num": "77",
            "driver_name": "V. Bottas",
            "best_time": "01:24.956",
            "status": "elimination_zone",
            "session_times": {"Q1": "01:26.456", "Q2": "01:24.956"},
            "no_current_time": False,
            "finished": True,
        },
        {
            "position": 15,
            "car_num": "24",
            "driver_name": "G. Zhou",
            "best_time": "01:25.012",
            "status": "elimination_zone",
            "session_times": {"Q1": "01:26.567", "Q2": "01:25.012"},
            "no_current_time": False,
            "finished": True,
        },
        # ── P16-P20 knocked_out — eliminated in Q1, did not run Q2 ────────────
        {
            "position": 16,
            "car_num": "22",
            "driver_name": "Y. Tsunoda",
            "best_time": "01:26.789",
            "status": "knocked_out",
            "session_times": {"Q1": "01:26.789", "Q2": ""},
            "no_current_time": False,
            "finished": False,
        },
        {
            "position": 17,
            "car_num": "20",
            "driver_name": "K. Magnussen",
            "best_time": "01:26.891",
            "status": "knocked_out",
            "session_times": {"Q1": "01:26.891", "Q2": ""},
            "no_current_time": False,
            "finished": False,
        },
        {
            "position": 18,
            "car_num": "23",
            "driver_name": "A. Albon",
            "best_time": "01:27.012",
            "status": "knocked_out",
            "session_times": {"Q1": "01:27.012", "Q2": ""},
            "no_current_time": False,
            "finished": False,
        },
        {
            "position": 19,
            "car_num": "2",
            "driver_name": "S. Sargeant",
            "best_time": "01:27.123",
            "status": "knocked_out",
            "session_times": {"Q1": "01:27.123", "Q2": ""},
            "no_current_time": False,
            "finished": False,
        },
        {
            "position": 20,
            "car_num": "6",
            "driver_name": "N. Latifi",
            "best_time": "01:27.567",
            "status": "knocked_out",
            "session_times": {"Q1": "01:27.567", "Q2": ""},
            "no_current_time": False,
            "finished": False,
        },
    ],
}

# ALT state: same Q2 standings mid-session — clock running, no checkered flag,
# no driver has taken the flag yet.  Use /trigger-alt to toggle.
ALT_F1_STATE: dict = {
    **STATIC_F1_STATE,
    "time_remaining": "2:15",
    "checkered_flag": False,
    "drivers": [{**d, "finished": False} for d in STATIC_F1_STATE["drivers"]],
}

STATIC_RC_MESSAGE: dict = {
    "title": "Q2 — Checkered Flag",
    "text": "Stroll P10 / Ocon P11 on final laps — Q3 lineup not yet confirmed",
}

# ---------------------------------------------------------------------------
# Shared state
# ---------------------------------------------------------------------------

_rc_clients: list[queue.Queue] = []
_f1_clients: list[queue.Queue] = []
_reload_clients: list[queue.Queue] = []
_clients_lock = threading.Lock()

# Mutable current F1 state (can be swapped to ALT via /trigger-alt)
_current_f1_state: dict = STATIC_F1_STATE


def _broadcast_f1(state: dict) -> None:
    payload = json.dumps(state)
    with _clients_lock:
        for q in list(_f1_clients):
            q.put(payload)


def _broadcast_rc(msg: dict) -> None:
    payload = json.dumps(msg)
    with _clients_lock:
        for q in list(_rc_clients):
            q.put(payload)


def _broadcast_reload() -> None:
    with _clients_lock:
        for q in list(_reload_clients):
            q.put("reload")


# ---------------------------------------------------------------------------
# Background: periodic broadcaster
# ---------------------------------------------------------------------------


def _broadcaster(rc_delay: float, rc_interval: float) -> None:
    """
    Push the F1 state immediately, then every 2 s so the tower is always
    visible when you refresh.  Fire the RC banner after *rc_delay* seconds
    and repeat every *rc_interval* seconds.
    """
    time.sleep(0.5)  # brief pause so the HTTP server is fully up
    _broadcast_f1(_current_f1_state)

    rc_countdown = rc_delay
    tick = 2.0
    while True:
        time.sleep(tick)
        _broadcast_f1(_current_f1_state)
        rc_countdown -= tick
        if rc_countdown <= 0:
            _broadcast_rc(STATIC_RC_MESSAGE)
            rc_countdown = rc_interval


# ---------------------------------------------------------------------------
# Background: live-reload file watcher
# ---------------------------------------------------------------------------


def _file_watcher(watched_paths: list[Path]) -> None:
    """Reload connected browsers whenever any watched file changes on disk."""
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
                break  # one reload per tick is enough even if both files changed


# ---------------------------------------------------------------------------
# HTTP handler
# ---------------------------------------------------------------------------

_LIVE_RELOAD_SNIPPET = """
<script>
  /* Injected by preview_overlay.py - live reload on file changes */
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
    """Handles all requests for the preview server."""

    # Injected before the server starts (avoids passing state through __init__)
    port: int = 9765
    width: int = 1920
    height: int = 1080

    # ------------------------------------------------------------------ #
    # Routing                                                              #
    # ------------------------------------------------------------------ #

    def do_GET(self) -> None:  # noqa: N802
        global _current_f1_state

        path = self.path.split("?")[0]

        match path:
            case "/sse/rc":
                self._handle_sse(_rc_clients, initial_payload=None)
            case "/sse/f1":
                self._handle_sse(
                    _f1_clients, initial_payload=json.dumps(_current_f1_state)
                )
            case "/sse/reload":
                self._handle_sse(_reload_clients, initial_payload=None)
            case "/static/overlay.css":
                self._serve_file(_DEFAULT_CSS, "text/css")
            case "/trigger-rc":
                _broadcast_rc(STATIC_RC_MESSAGE)
                self._plain_response(200, "RC banner triggered.")
            case "/trigger-alt":
                _current_f1_state = (
                    ALT_F1_STATE
                    if _current_f1_state is STATIC_F1_STATE
                    else STATIC_F1_STATE
                )
                label = (
                    "ALT (mid-Q2, clock running, no checkered)"
                    if _current_f1_state is ALT_F1_STATE
                    else "MAIN (Q2 checkered, Stroll/Ocon on final laps)"
                )
                _broadcast_f1(_current_f1_state)
                self._plain_response(200, f"Switched to {label}.")
            case _ if path.startswith("/static/fonts/"):
                font_name = path[len("/static/fonts/") :]
                self._serve_file(_FONTS_DIR / font_name, "font/truetype")
            case _:
                self._serve_html(_OVERLAY_HTML)

    # ------------------------------------------------------------------ #
    # SSE                                                                  #
    # ------------------------------------------------------------------ #

    def _handle_sse(self, client_list: list, initial_payload: str | None) -> None:
        """Hold the connection open and stream data events."""
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
                    # Keepalive comment so the browser does not close the stream.
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
        # Inject live-reload listener before </body>
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

    def _plain_response(self, code: int, text: str) -> None:
        body = text.encode()
        self.send_response(code)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    # Suppress per-request access-log noise in the terminal.
    def log_message(self, format, *args):  # noqa: N802, A002
        pass


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Overlay appearance preview server — no iRacing connection needed.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--port", type=int, default=9765, help="HTTP port (default 9765)"
    )
    parser.add_argument(
        "--width", type=int, default=1920, help="Overlay canvas width (default 1920)"
    )
    parser.add_argument(
        "--height", type=int, default=1080, help="Overlay canvas height (default 1080)"
    )
    parser.add_argument(
        "--rc-delay",
        type=float,
        default=3.0,
        help="Seconds before first RC banner (default 3)",
    )
    parser.add_argument(
        "--rc-interval",
        type=float,
        default=30.0,
        help="Seconds between RC banners (default 30)",
    )
    parser.add_argument(
        "--no-browser", action="store_true", help="Don't auto-open a browser tab"
    )
    args = parser.parse_args()

    # Patch class-level config into handler before the server starts.
    PreviewHandler.port = args.port
    PreviewHandler.width = args.width
    PreviewHandler.height = args.height

    server = _Server(("", args.port), PreviewHandler)

    # ── Background broadcaster ──────────────────────────────────────────
    threading.Thread(
        target=_broadcaster,
        args=(args.rc_delay, args.rc_interval),
        daemon=True,
        name="preview-broadcaster",
    ).start()

    # ── Live-reload file watcher ────────────────────────────────────────
    watched = [p for p in [_OVERLAY_HTML, _DEFAULT_CSS] if p.exists()]
    if watched:
        threading.Thread(
            target=_file_watcher,
            args=(watched,),
            daemon=True,
            name="preview-watcher",
        ).start()

    url = f"http://localhost:{args.port}/"
    sep = "─" * 60
    print(f"\n  {sep}")
    print(f"  Overlay preview server")
    print(f"  {sep}")
    print(f"  Main overlay  →  {url}")
    print(f"  Scenario      →  Q2 checkered flag — Stroll / Ocon still on flying laps")
    print(
        f"  RC banner     →  fires in {args.rc_delay:.0f}s, then every {args.rc_interval:.0f}s"
    )
    print(f"  Live reload   →  active (edit overlay.html / overlay.css to trigger)")
    print(f"  {sep}")
    print(f"  Endpoints:")
    print(f"    GET /              — overlay page (main + timing tower + banner)")
    print(f"    GET /trigger-rc    — send RC banner immediately")
    print(f"    GET /trigger-alt   — toggle mid-Q2 view (clock running, no checkered)")
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
