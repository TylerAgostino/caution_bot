"""
OverlayConsumerEvent
====================
Serves browser-based OBS overlays over a local HTTP server.

Endpoints
---------
GET /                    – Consolidated qualifying overlay (timing tower + standings board).
GET /static/fonts/<name> – Font files served from the flet_pages/fonts/ directory.
GET /sse/rc              – Server-Sent Events stream for race-control messages.
GET /sse/f1              – Server-Sent Events stream for F1 timing state.

Usage
-----
Add a **single** Browser Source in OBS pointed at::

    http://localhost:<port>/

Enable "Allow transparency" in the Browser Source settings.

The overlay automatically switches between the **timing tower** and the **full
standings board** based on session state:

* **Timing tower** – shown while a session is live and at least one eligible
  driver has not yet completed their final timed lap after the checkered flag.
* **Standings board** – shown once every eligible driver has crossed the line,
  and again during the pre-session countdown between rounds.

Integration with F1 Qualifying
-------------------------------
After starting the F1QualifyingEvent, set ``overlay_event.f1_event = f1_event`` so
the overlay server can poll the live leaderboard.  Clear it on stop.

Message queue
-------------
The overlay consumer reads from the shared ``broadcast_text_queue`` just like the
Discord/SDK text consumers.  If you want both Discord and overlay running at the
same time, be aware that each message is consumed by one reader only; choose one
consumer per deployment or extend SubprocessManager with fan-out if needed.
"""

import json
import queue
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from math import isnan
from pathlib import Path
from typing import TYPE_CHECKING

from modules.events import BaseEvent

if TYPE_CHECKING:
    from modules.events.f1_qualifying_event import F1QualifyingEvent

# --------------------------------------------------------------------------- #
# Paths
# --------------------------------------------------------------------------- #

_THIS_DIR = Path(__file__).parent
_OVERLAY_HTML = _THIS_DIR.parent / "flet_pages" / "overlays" / "overlay.html"
_FONTS_DIR = _OVERLAY_HTML.parent.parent / "fonts"


# --------------------------------------------------------------------------- #
# HTTP server
# --------------------------------------------------------------------------- #


class _OverlayHTTPServer(ThreadingHTTPServer):
    """ThreadingHTTPServer with sane defaults for a local overlay server.

    allow_reuse_address – lets the server rebind to the same port immediately
                          after a stop/start cycle without hitting 'Address
                          already in use' errors.
    daemon_threads      – request-handler threads (including long-lived SSE
                          connections) are killed automatically when the main
                          event thread exits, so they never block shutdown.
    """

    allow_reuse_address = True
    daemon_threads = True


# --------------------------------------------------------------------------- #
# Event
# --------------------------------------------------------------------------- #


class OverlayConsumerEvent(BaseEvent):
    """
    Consumer event that serves transparent HTML overlays for OBS browser sources.

    Parameters
    ----------
    port : int
        TCP port for the HTTP server (default 8765).
    width : int
        Overlay canvas width in pixels (default 1920).
    height : int
        Overlay canvas height in pixels (default 1080).
    """

    def __init__(
        self,
        port: int = 8765,
        width: int = 1920,
        height: int = 1080,
        *args,
        **kwargs,
    ):
        super().__init__(*args, **kwargs)
        self.port = int(port)
        self.width = int(width)
        self.height = int(height)

        # Per-overlay SSE client queues: list of queue.Queue, one per connected tab.
        self._rc_clients: list[queue.Queue] = []
        self._f1_clients: list[queue.Queue] = []
        self._clients_lock = threading.Lock()

        # Set this to a running F1QualifyingEvent to enable the timing-tower overlay.
        self.f1_event: F1QualifyingEvent | None = None

        self._server = None

    # ---------------------------------------------------------------------- #
    # Public broadcast helpers (called from event_sequence loop)
    # ---------------------------------------------------------------------- #

    def push_rc_message(self, title: str, text: str) -> None:
        """Broadcast a race-control banner to all connected /rc-message clients."""
        payload = json.dumps({"title": title, "text": text})
        with self._clients_lock:
            for q in list(self._rc_clients):
                q.put(payload)

    def push_f1_state(self, state: dict) -> None:
        """Broadcast an F1 timing-tower update to all connected /f1-timing clients."""
        payload = json.dumps(state)
        with self._clients_lock:
            for q in list(self._f1_clients):
                q.put(payload)

    # ---------------------------------------------------------------------- #
    # BaseEvent overrides
    # ---------------------------------------------------------------------- #

    def event_sequence(self) -> None:
        handler_class = self._build_handler()
        self._server = _OverlayHTTPServer(("", self.port), handler_class)

        server_thread = threading.Thread(
            target=self._server.serve_forever, daemon=True, name="overlay-http"
        )
        server_thread.start()
        self.logger.info("Overlay server listening on http://localhost:%d/", self.port)

        # ---- Main loop: drain queues and push state to SSE clients ---- #
        last_f1_state: dict | None = None
        try:
            while True:
                try:
                    # Race-control messages
                    try:
                        msg = self.broadcast_text_queue.get_nowait()
                        if isinstance(msg, dict):
                            self.push_rc_message(
                                msg.get("title", "Race Control"),
                                msg.get("text", ""),
                            )
                    except queue.Empty:
                        pass

                    # F1 timing tower state
                    if self.f1_event is not None:
                        state = self._build_f1_state()
                        # Only push when state actually changes to reduce traffic.
                        if state and state != last_f1_state:
                            self.push_f1_state(state)
                            last_f1_state = state

                except Exception as exc:
                    # Never let a single bad frame kill the HTTP server.
                    self.logger.warning(
                        "Overlay loop error (server kept alive): %s", exc, exc_info=True
                    )

                try:
                    self.sleep(0.5)
                except KeyboardInterrupt:
                    break
        finally:
            # Always shut down and close the socket so the port is freed
            # immediately and a restart can rebind without 'Address in use'.
            self._server.shutdown()
            self._server.server_close()
            self.logger.info("Overlay server stopped.")

    # ---------------------------------------------------------------------- #
    # F1 state serialiser
    # ---------------------------------------------------------------------- #

    def _build_f1_state(self) -> dict | None:
        """Read the live F1 event and return a JSON-serialisable timing-tower state."""
        ev = self.f1_event
        if ev is None:
            return None
        try:
            # Acquire the leaderboard lock (if present) so we never copy a
            # DataFrame that the F1 event thread is currently rebuilding.
            df_lock = getattr(ev, "leaderboard_lock", None)
            if df_lock is not None:
                with df_lock:
                    df = ev.leaderboard_df.copy()
            else:
                df = ev.leaderboard_df.copy()

            session_name = ev.subsession_name or ""
            time_remaining = ev.subsession_time_remaining or "--:--"
            checkered_flag = getattr(ev, "checkered_flag_out", False)
            q_cols = [c for c in df.columns if c != "Driver"]

            if df.empty:
                return {
                    "session_name": session_name,
                    "time_remaining": time_remaining,
                    "checkered_flag": checkered_flag,
                    "sessions": q_cols,
                    "drivers": [],
                }

            # Determine whether we are inside an active Qn session.
            is_active_session = session_name.startswith(
                "Q"
            ) and not session_name.startswith("Pre-")
            current_q_num = None
            session_advancing = None
            driver_at_risk_idx = None

            if is_active_session:
                try:
                    current_q_num = int(session_name[1:])
                    session_idx = current_q_num - 1
                    if 0 <= session_idx < len(ev.session_advancing_cars):
                        session_advancing = ev.session_advancing_cars[session_idx]
                        if 0 < session_advancing <= len(df):
                            driver_at_risk_idx = session_advancing - 1
                except (ValueError, IndexError):
                    pass

            knocked_out_set = getattr(ev, "knocked_out_drivers", set())
            session_finishers = getattr(ev, "session_finishers", set())
            drivers = []

            for pos, (car_num, row) in enumerate(df.iterrows()):
                # Best lap time across all sessions (smallest positive value).
                best_time = None
                for col in q_cols:
                    val = row.get(col)
                    if isinstance(val, (int, float)) and not isnan(val) and val > 0:
                        if best_time is None or val < best_time:
                            best_time = val

                # Per-session individual lap times for the standings overlay.
                session_times: dict[str, str] = {}
                for col in q_cols:
                    val = row.get(col)
                    if isinstance(val, (int, float)) and not isnan(val) and val > 0:
                        session_times[col] = _fmt_time(val)
                    else:
                        session_times[col] = ""

                # Has this driver NOT yet set a lap in the CURRENT session?
                # (Only meaningful during active sessions; knocked-out drivers are excluded.)
                no_current_time = False
                if (
                    is_active_session
                    and current_q_num is not None
                    and car_num not in knocked_out_set
                ):
                    current_q_col = f"Q{current_q_num}"
                    cval = row.get(current_q_col)
                    no_current_time = (
                        cval is None
                        or not isinstance(cval, (int, float))
                        or isnan(cval)
                        or cval <= 0
                    )

                # Determine status.
                status = self._driver_status(
                    car_num=car_num,
                    row=row,
                    pos=pos,
                    is_active_session=is_active_session,
                    current_q_num=current_q_num,
                    session_advancing=session_advancing,
                    driver_at_risk_idx=driver_at_risk_idx,
                    knocked_out=knocked_out_set,
                )

                drivers.append(
                    {
                        "position": pos + 1,
                        "car_num": str(car_num),
                        "driver_name": str(row.get("Driver", "Unknown")),
                        "best_time": _fmt_time(best_time),
                        "status": status,
                        "session_times": session_times,
                        "no_current_time": no_current_time,
                        "finished": car_num in session_finishers,
                    }
                )

            return {
                "session_name": session_name,
                "time_remaining": time_remaining,
                "checkered_flag": checkered_flag,
                "sessions": q_cols,
                "drivers": drivers,
            }

        except Exception:
            return None

    @staticmethod
    def _driver_status(
        car_num,
        row,
        pos: int,
        is_active_session: bool,
        current_q_num: int | None,
        session_advancing: int | None,
        driver_at_risk_idx: int | None,
        knocked_out: set,
    ) -> str:
        """Return one of: 'safe', 'at_risk', 'elimination_zone', 'knocked_out'."""
        # Explicitly tracked knocked-out drivers always take priority.
        if car_num in knocked_out:
            return "knocked_out"

        if not is_active_session or session_advancing is None or current_q_num is None:
            return "safe"

        # Drivers who have advanced to this session but not yet set a lap time are
        # shown as 'safe' (not eliminated – they just haven't run yet).
        current_q_col = f"Q{current_q_num}"
        val = row.get(current_q_col)
        no_current_time = (
            val is None or not isinstance(val, (int, float)) or isnan(val) or val <= 0
        )
        if no_current_time:
            return "safe"

        # Classify by finishing position relative to the cutoff.
        if session_advancing <= 0:
            return "safe"
        if driver_at_risk_idx is None:
            return "safe"
        if pos > driver_at_risk_idx:
            return "elimination_zone"
        if pos == driver_at_risk_idx:
            return "at_risk"
        return "safe"

    # ---------------------------------------------------------------------- #
    # HTTP handler factory
    # ---------------------------------------------------------------------- #

    def _build_handler(self):
        """Return a BaseHTTPRequestHandler class closed over *self* (the event)."""
        event = self

        class OverlayHandler(BaseHTTPRequestHandler):

            def do_GET(self):
                path = self.path.split("?")[0]
                if path == "/sse/rc":
                    self._handle_sse(event._rc_clients)
                elif path == "/sse/f1":
                    self._handle_sse(event._f1_clients)
                elif path.startswith("/static/fonts/"):
                    font_name = path[len("/static/fonts/") :]
                    self._serve_file(_FONTS_DIR / font_name, "font/truetype")
                else:
                    # All paths (including "/") serve the consolidated overlay.
                    self._serve_html(_OVERLAY_HTML)

            # ---------------------------------------------------------------- #
            # SSE
            # ---------------------------------------------------------------- #

            def _handle_sse(self, client_list: list):
                """Hold the connection open and stream JSON data events."""
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.send_header("Cache-Control", "no-cache")
                self.send_header("Connection", "keep-alive")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()

                client_q: queue.Queue = queue.Queue()
                with event._clients_lock:
                    client_list.append(client_q)

                try:
                    while True:
                        try:
                            data = client_q.get(timeout=15)
                            self.wfile.write(f"data: {data}\n\n".encode())
                            self.wfile.flush()
                        except queue.Empty:
                            # Keepalive comment keeps the connection alive.
                            self.wfile.write(b": ping\n\n")
                            self.wfile.flush()
                except Exception:
                    pass
                finally:
                    with event._clients_lock:
                        if client_q in client_list:
                            client_list.remove(client_q)

            # ---------------------------------------------------------------- #
            # Static files
            # ---------------------------------------------------------------- #

            def _serve_html(self, file_path: Path):
                if not file_path.exists():
                    self.send_error(404, f"Overlay not found: {file_path.name}")
                    return
                content = file_path.read_text(encoding="utf-8")
                # Simple template substitution for width/height/port.
                content = (
                    content.replace("{{WIDTH}}", str(event.width))
                    .replace("{{HEIGHT}}", str(event.height))
                    .replace("{{PORT}}", str(event.port))
                )
                body = content.encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def _serve_file(self, file_path: Path, mime: str):
                if not file_path.exists():
                    self.send_error(404, f"Not found: {file_path.name}")
                    return
                data = file_path.read_bytes()
                self.send_response(200)
                self.send_header("Content-Type", mime)
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            # Suppress default access-log noise.
            def log_message(self, format, *args):  # noqa: N802
                pass

        return OverlayHandler


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #


def _fmt_time(seconds) -> str:
    """Format a lap time given in seconds as MM:SS.mmm."""
    if (
        seconds is None
        or not isinstance(seconds, (int, float))
        or isnan(seconds)
        or seconds <= 0
    ):
        return ""
    mins = int(seconds // 60)
    secs = int(seconds % 60)
    millis = int((seconds % 1) * 1000)
    return f"{mins:02d}:{secs:02d}.{millis:03d}"
