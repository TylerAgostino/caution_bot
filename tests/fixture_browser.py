"""
fixture_browser.py -- Interactive Fixture Frame Browser & Editor
================================================================

A Flet-based desktop utility that lets you load any test fixture telemetry
file, step through its frames one-by-one, inspect every field in the current
frame, and save edits back to disk (including re-compressing .json.gz files).

FEATURES
--------
* Fixture selector — choose any fixture from tests/fixtures/ via a dropdown.
* Frame navigation — Previous / Next buttons, direct frame-number input,
  and a slider for rapid scrubbing.
* Session flags decoder — human-readable flag names rendered as coloured chips.
* Per-car table — shows CarIdx, CarNumber, UserName, LapDistPct, LapCompleted,
  OnPitRoad, SessionFlags, LastLapTime, F2Time for every active car, sorted by
  LapDistPct descending (race order).
* Scalar fields panel — displays all non-array frame fields in a tidy grid.
* Inline editing — click any scalar or per-car cell to edit its value.
  Edits are held in memory until you explicitly save.
* Dirty indicator — the title bar shows an asterisk (*) when unsaved changes
  exist.
* Save button — writes the modified frames back to the original file
  (gzip-compressed if the source was .json.gz; plain JSON otherwise).
* Meta viewer — collapsible panel showing the fixture metadata and event_kwargs
  from the .meta.json sidecar.

USAGE
-----
    python tests/fixture_browser.py

    # Or point at a specific fixture:
    python tests/fixture_browser.py --fixture tests/fixtures/mugello.json.gz

KEYBOARD SHORTCUTS
------------------
  Left  / Right arrow keys : previous / next frame (when not editing a field)
  Ctrl+S                   : save

DEPENDENCIES
------------
Flet (already in requirements.txt).  No other new packages needed.
"""

from __future__ import annotations

import argparse
import gzip
import json
import sys
from pathlib import Path
from typing import Any

import flet as ft

# ---------------------------------------------------------------------------
# Project root on sys.path so we can reuse conftest helpers if needed later.
# ---------------------------------------------------------------------------
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"

# ---------------------------------------------------------------------------
# iRacing SessionFlags bit-mask → human-readable names
# (subset of irsdk.Flags that are relevant to caution_bot logic)
# ---------------------------------------------------------------------------
SESSION_FLAG_NAMES: list[tuple[int, str, str]] = [
    # (bit_value, short_name, colour)
    (0x00000001, "Checkered", "#9E9E9E"),
    (0x00000002, "White", "#ECEFF1"),
    (0x00000004, "Green", "#43A047"),
    (0x00000008, "YellowWaving", "#FDD835"),
    (0x00000010, "Yellow", "#FDD835"),
    (0x00000020, "Red", "#E53935"),
    (0x00000040, "Blue", "#1E88E5"),
    (0x00000080, "Debris", "#8D6E63"),
    (0x00000100, "Crossed", "#AB47BC"),
    (0x00000200, "YellowWave2", "#F9A825"),
    (0x00000400, "OneLapToGreen", "#66BB6A"),
    (0x00000800, "GreenHeld", "#00897B"),
    (0x00001000, "TenToGo", "#26C6DA"),
    (0x00002000, "FiveToGo", "#0288D1"),
    (0x00004000, "RandomWaving", "#FF7043"),
    (0x00008000, "Caution", "#FFA726"),
    (0x00010000, "CautionWaving", "#FFB74D"),
    (0x00020000, "Black", "#212121"),
    (0x00040000, "Disqualify", "#B71C1C"),
    (0x00080000, "Furled", "#7B1FA2"),
    (0x00100000, "Repair", "#F57F17"),
    (0x10000000, "StartHidden", "#546E7A"),
    (0x20000000, "StartReady", "#26A69A"),
    (0x40000000, "StartSet", "#FFA000"),
    (0x80000000, "StartGo", "#2E7D32"),
]

CAR_SESSION_FLAG_NAMES: list[tuple[int, str, str]] = [
    (0x0001, "IsOnTrack", "#43A047"),
    (0x0002, "Approaches", "#1E88E5"),
    (0x0004, "HasFastestLap", "#F9A825"),
    (0x0008, "IsLeader", "#E53935"),
    (0x0010, "LapBehind", "#AB47BC"),
    (0x0020, "OnPitRoad", "#8D6E63"),
]


def decode_flags(
    value: int, flag_table: list[tuple[int, str, str]]
) -> list[tuple[str, str]]:
    """Return a list of (name, colour) for every set bit in *value*."""
    return [(name, colour) for bit, name, colour in flag_table if value & bit]


# ---------------------------------------------------------------------------
# Telemetry file helpers
# ---------------------------------------------------------------------------


def load_telemetry(path: Path) -> dict:
    if path.suffix == ".gz":
        with gzip.open(path, "rt", encoding="utf-8") as fh:
            return json.load(fh)
    with path.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def save_telemetry(path: Path, data: dict) -> None:
    if path.suffix == ".gz":
        with gzip.open(path, "wt", encoding="utf-8", compresslevel=9) as fh:
            json.dump(data, fh, separators=(",", ":"))
    else:
        with path.open("w", encoding="utf-8") as fh:
            json.dump(data, fh, separators=(",", ":"))


def load_meta(telemetry_path: Path) -> dict | None:
    """Load the .meta.json sidecar for *telemetry_path*, or None if absent."""
    stem = telemetry_path.name.replace(".json.gz", "").replace(".json", "")
    meta_path = telemetry_path.parent / f"{stem}.meta.json"
    if not meta_path.exists():
        return None
    with meta_path.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def save_meta(telemetry_path: Path, meta: dict) -> None:
    stem = telemetry_path.name.replace(".json.gz", "").replace(".json", "")
    meta_path = telemetry_path.parent / f"{stem}.meta.json"
    with meta_path.open("w", encoding="utf-8") as fh:
        json.dump(meta, fh, indent=2)


def discover_fixtures() -> list[Path]:
    """Return sorted list of telemetry paths in FIXTURES_DIR."""
    paths: list[Path] = []
    seen_stems: set[str] = set()
    for p in sorted(FIXTURES_DIR.glob("*.json.gz")):
        stem = p.name.replace(".json.gz", "")
        seen_stems.add(stem)
        paths.append(p)
    for p in sorted(FIXTURES_DIR.glob("*.json")):
        if p.name.endswith(".meta.json"):
            continue
        stem = p.name.replace(".json", "")
        if stem not in seen_stems:
            paths.append(p)
    return paths


# ---------------------------------------------------------------------------
# Colour helpers
# ---------------------------------------------------------------------------

SCALAR_CELL_BG = "#1E1E2E"
HEADER_BG = "#181825"
ROW_EVEN_BG = "#1E1E2E"
ROW_ODD_BG = "#242436"
ACCENT = "#CBA6F7"
TEXT_MAIN = "#CDD6F4"
TEXT_DIM = "#6C7086"
TEXT_GREEN = "#A6E3A1"
TEXT_RED = "#F38BA8"
TEXT_YELLOW = "#F9E2AF"
SURFACE0 = "#313244"
SURFACE1 = "#45475A"
DIRTY_COLOUR = "#F9E2AF"
CLEAN_COLOUR = TEXT_GREEN


# ===========================================================================
# Main App
# ===========================================================================


class FixtureBrowserApp:
    """Flet application for browsing and editing fixture frame data."""

    def __init__(self, initial_fixture: Path | None = None):
        self._initial_fixture = initial_fixture

        # Loaded data
        self._telemetry_path: Path | None = None
        self._data: dict | None = None  # full JSON (meta + frames)
        self._meta_sidecar: dict | None = None  # .meta.json contents
        self._frames: list[dict] = []
        self._static: dict = {}
        self._drivers: list[dict] = []  # DriverInfo.Drivers
        self._idx_to_driver: dict[int, dict] = {}

        self._frame_index: int = 0
        self._dirty: bool = False

        # Flet page reference (set in main())
        self._page: ft.Page | None = None

        # UI references we need to update dynamically
        self._frame_slider: ft.Slider | None = None
        self._frame_input: ft.TextField | None = None
        self._frame_count_label: ft.Text | None = None
        self._flags_row: ft.Row | None = None
        self._scalar_grid: ft.Column | None = None
        self._car_table_container: ft.Container | None = None
        self._meta_panel: ft.Column | None = None
        self._dirty_indicator: ft.Text | None = None
        self._fixture_dropdown: ft.Dropdown | None = None
        self._status_text: ft.Text | None = None
        self._expected_order_container: ft.Container | None = None

    # ------------------------------------------------------------------
    # Data loading
    # ------------------------------------------------------------------

    def _load_fixture(self, path: Path) -> None:
        self._telemetry_path = path
        self._data = load_telemetry(path)
        self._frames = self._data.get("frames", [])
        meta_blob = self._data.get("meta", {})
        self._static = meta_blob.get("static", {})
        self._drivers = self._static.get("DriverInfo", {}).get("Drivers", [])
        self._idx_to_driver = {d["CarIdx"]: d for d in self._drivers}
        self._meta_sidecar = load_meta(path)
        self._frame_index = 0
        self._dirty = False

    # ------------------------------------------------------------------
    # Flet entry point
    # ------------------------------------------------------------------

    def main(self, page: ft.Page) -> None:
        self._page = page
        page.title = "Fixture Frame Browser"
        page.theme_mode = ft.ThemeMode.DARK
        page.bgcolor = "#11111B"
        page.padding = 0
        page.window.width = 1400
        page.window.height = 900
        page.window.min_width = 900
        page.window.min_height = 600
        page.fonts = {
            "Mono": "https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;600&display=swap"
        }
        page.on_keyboard_event = self._on_keyboard

        page.add(self._build_ui())

        # Load initial fixture
        fixtures = discover_fixtures()
        if self._initial_fixture and self._initial_fixture.exists():
            self._load_fixture(self._initial_fixture)
            self._sync_dropdown_to_path(self._initial_fixture)
            self._refresh_all()
        elif fixtures:
            self._load_fixture(fixtures[0])
            self._refresh_all()

    # ------------------------------------------------------------------
    # Keyboard handler
    # ------------------------------------------------------------------

    def _on_keyboard(self, e: ft.KeyboardEvent) -> None:
        if e.key == "Arrow Left" and not e.ctrl:
            self._go_to_frame(self._frame_index - 1)
        elif e.key == "Arrow Right" and not e.ctrl:
            self._go_to_frame(self._frame_index + 1)
        elif e.key == "S" and e.ctrl:
            self._save()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self) -> ft.Column:
        # ---- Toolbar ----
        toolbar = self._build_toolbar()

        # ---- Navigation bar ----
        nav_bar = self._build_nav_bar()

        # ---- Flags row ----
        self._flags_row = ft.Row(
            controls=[],
            wrap=True,
            spacing=6,
            run_spacing=4,
        )
        flags_section = ft.Container(
            content=ft.Column(
                [
                    ft.Text(
                        "Session Flags",
                        size=11,
                        color=TEXT_DIM,
                        weight=ft.FontWeight.W_600,
                    ),
                    self._flags_row,
                ],
                spacing=4,
            ),
            bgcolor=HEADER_BG,
            padding=ft.padding.symmetric(horizontal=16, vertical=8),
            border=ft.border.only(bottom=ft.BorderSide(1, SURFACE0)),
        )

        # ---- Main content: scalars (left) + cars (right) ----
        self._scalar_grid = ft.Column(
            controls=[],
            spacing=0,
            scroll=ft.ScrollMode.AUTO,
            expand=True,
        )
        scalar_panel = ft.Container(
            content=ft.Column(
                [
                    ft.Container(
                        content=ft.Text(
                            "Scalar Fields",
                            size=11,
                            color=TEXT_DIM,
                            weight=ft.FontWeight.W_600,
                        ),
                        padding=ft.padding.only(left=12, top=8, bottom=6),
                    ),
                    ft.Container(
                        content=self._scalar_grid,
                        expand=True,
                    ),
                ],
                spacing=0,
                expand=True,
            ),
            expand=1,
            bgcolor=SCALAR_CELL_BG,
            border=ft.border.only(right=ft.BorderSide(1, SURFACE0)),
        )

        self._car_table_container = ft.Container(
            content=ft.Text("No fixture loaded.", color=TEXT_DIM),
            expand=3,
            bgcolor=HEADER_BG,
            padding=0,
        )

        main_body = ft.Row(
            controls=[scalar_panel, self._car_table_container],
            expand=True,
            spacing=0,
        )

        # ---- Meta / sidecar panel ----
        self._meta_panel = ft.Column(controls=[], spacing=0)
        meta_section = ft.Container(
            content=self._meta_panel,
            bgcolor=HEADER_BG,
            border=ft.border.only(top=ft.BorderSide(1, SURFACE0)),
            padding=ft.padding.symmetric(horizontal=16, vertical=8),
        )

        # ---- Status bar ----
        self._status_text = ft.Text("", size=11, color=TEXT_DIM)
        self._dirty_indicator = ft.Text(
            "", size=11, color=DIRTY_COLOUR, weight=ft.FontWeight.W_600
        )
        status_bar = ft.Container(
            content=ft.Row(
                [
                    self._dirty_indicator,
                    ft.Container(expand=True),
                    self._status_text,
                ]
            ),
            bgcolor="#0D0D1A",
            padding=ft.padding.symmetric(horizontal=16, vertical=4),
            border=ft.border.only(top=ft.BorderSide(1, SURFACE0)),
        )

        return ft.Column(
            controls=[
                toolbar,
                nav_bar,
                flags_section,
                ft.Container(content=main_body, expand=True),
                meta_section,
                status_bar,
            ],
            spacing=0,
            expand=True,
        )

    def _build_toolbar(self) -> ft.Container:
        fixtures = discover_fixtures()
        options = [
            ft.dropdown.Option(
                key=str(p),
                text=p.name.replace(".json.gz", "").replace(".json", ""),
            )
            for p in fixtures
        ]
        self._fixture_dropdown = ft.Dropdown(
            options=options,
            value=str(fixtures[0]) if fixtures else None,
            on_change=self._on_fixture_selected,
            text_style=ft.TextStyle(color=TEXT_MAIN, size=13),
            border_color=SURFACE1,
            focused_border_color=ACCENT,
            bgcolor=SURFACE0,
            width=320,
            content_padding=ft.padding.symmetric(horizontal=12, vertical=6),
        )

        save_btn = ft.ElevatedButton(
            text="Save",
            icon=ft.Icons.SAVE,
            on_click=lambda _: self._save(),
            bgcolor=SURFACE1,
            color=TEXT_GREEN,
            style=ft.ButtonStyle(
                shape=ft.RoundedRectangleBorder(radius=6),
            ),
        )

        reload_btn = ft.IconButton(
            icon=ft.Icons.REFRESH,
            tooltip="Reload fixture from disk (discard changes)",
            icon_color=TEXT_DIM,
            on_click=self._on_reload,
        )

        return ft.Container(
            content=ft.Row(
                [
                    ft.Text("Fixture:", size=13, color=TEXT_DIM),
                    self._fixture_dropdown,
                    ft.Container(expand=True),
                    reload_btn,
                    save_btn,
                ],
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                spacing=10,
            ),
            bgcolor=HEADER_BG,
            padding=ft.padding.symmetric(horizontal=16, vertical=10),
            border=ft.border.only(bottom=ft.BorderSide(1, SURFACE0)),
        )

    def _build_nav_bar(self) -> ft.Container:
        prev_btn = ft.IconButton(
            icon=ft.Icons.CHEVRON_LEFT,
            tooltip="Previous frame (←)",
            icon_color=ACCENT,
            on_click=lambda _: self._go_to_frame(self._frame_index - 1),
        )
        next_btn = ft.IconButton(
            icon=ft.Icons.CHEVRON_RIGHT,
            tooltip="Next frame (→)",
            icon_color=ACCENT,
            on_click=lambda _: self._go_to_frame(self._frame_index + 1),
        )
        first_btn = ft.IconButton(
            icon=ft.Icons.FIRST_PAGE,
            tooltip="First frame",
            icon_color=TEXT_DIM,
            on_click=lambda _: self._go_to_frame(0),
        )
        last_btn = ft.IconButton(
            icon=ft.Icons.LAST_PAGE,
            tooltip="Last frame",
            icon_color=TEXT_DIM,
            on_click=lambda _: self._go_to_frame(len(self._frames) - 1),
        )

        self._frame_input = ft.TextField(
            value="0",
            width=80,
            text_align=ft.TextAlign.CENTER,
            text_style=ft.TextStyle(color=TEXT_MAIN, size=13),
            border_color=SURFACE1,
            focused_border_color=ACCENT,
            bgcolor=SURFACE0,
            content_padding=ft.padding.symmetric(horizontal=8, vertical=4),
            on_submit=self._on_frame_input_submit,
        )

        self._frame_count_label = ft.Text("/ 0", color=TEXT_DIM, size=13)

        self._frame_slider = ft.Slider(
            min=0,
            max=1,
            value=0,
            divisions=1,
            expand=True,
            active_color=ACCENT,
            inactive_color=SURFACE1,
            thumb_color=ACCENT,
            on_change=self._on_slider_change,
            on_change_end=self._on_slider_change_end,
        )

        session_time_label_title = ft.Text("SessionTime:", size=11, color=TEXT_DIM)
        self._session_time_value = ft.Text(
            "—", size=12, color=TEXT_YELLOW, font_family="Mono"
        )
        self._session_tick_value = ft.Text(
            "", size=11, color=TEXT_DIM, font_family="Mono"
        )

        return ft.Container(
            content=ft.Row(
                [
                    first_btn,
                    prev_btn,
                    self._frame_input,
                    self._frame_count_label,
                    next_btn,
                    last_btn,
                    ft.VerticalDivider(width=1, color=SURFACE0),
                    self._frame_slider,
                    ft.VerticalDivider(width=1, color=SURFACE0),
                    session_time_label_title,
                    self._session_time_value,
                    self._session_tick_value,
                ],
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                spacing=6,
            ),
            bgcolor=HEADER_BG,
            padding=ft.padding.symmetric(horizontal=12, vertical=6),
            border=ft.border.only(bottom=ft.BorderSide(1, SURFACE0)),
        )

    # ------------------------------------------------------------------
    # Navigation
    # ------------------------------------------------------------------

    def _go_to_frame(self, index: int) -> None:
        if not self._frames:
            return
        index = max(0, min(len(self._frames) - 1, index))
        if index == self._frame_index:
            return
        self._frame_index = index
        self._refresh_all()

    def _on_slider_change(self, e: ft.ControlEvent) -> None:
        if not self._frames:
            return
        idx = int(round(float(e.data or 0)))
        idx = max(0, min(len(self._frames) - 1, idx))
        self._frame_index = idx
        # Lightweight update: just nav bar scalars + flags, avoid full rebuild
        self._refresh_nav()
        self._refresh_flags()
        self._refresh_scalars()

    def _on_slider_change_end(self, e: ft.ControlEvent) -> None:
        if not self._frames:
            return
        idx = int(round(float(e.data or 0)))
        self._frame_index = max(0, min(len(self._frames) - 1, idx))
        self._refresh_all()

    def _on_frame_input_submit(self, e: ft.ControlEvent) -> None:
        try:
            idx = int(e.data or "1") - 1  # 1-based input → 0-based index
            self._go_to_frame(idx)
        except ValueError:
            self._set_status(f"Invalid frame number: {e.data!r}", error=True)

    # ------------------------------------------------------------------
    # Fixture selection
    # ------------------------------------------------------------------

    def _on_fixture_selected(self, e: ft.ControlEvent) -> None:
        if not e.data:  # type: ignore[truthy-str]
            return
        path = Path(e.data)
        if not path.exists():
            self._set_status(f"File not found: {path}", error=True)
            return
        self._load_fixture(path)
        self._refresh_all()
        self._set_status(f"Loaded {path.name}  ({len(self._frames)} frames)")

    def _on_reload(self, _: Any) -> None:
        if self._telemetry_path is None:
            return
        self._load_fixture(self._telemetry_path)
        self._refresh_all()
        self._set_status(f"Reloaded {self._telemetry_path.name}")

    def _sync_dropdown_to_path(self, path: Path) -> None:
        if self._fixture_dropdown is None:
            return
        for opt in self._fixture_dropdown.options or []:
            if opt.key == str(path):
                self._fixture_dropdown.value = str(path)
                break

    # ------------------------------------------------------------------
    # Save
    # ------------------------------------------------------------------

    def _save(self) -> None:
        if self._telemetry_path is None or self._data is None:
            return
        try:
            self._data["frames"] = self._frames
            save_telemetry(self._telemetry_path, self._data)
            if self._meta_sidecar is not None:
                save_meta(self._telemetry_path, self._meta_sidecar)
            self._dirty = False
            self._refresh_dirty_indicator()
            self._set_status(f"Saved → {self._telemetry_path.name}")
        except Exception as exc:
            self._set_status(f"Save failed: {exc}", error=True)

    # ------------------------------------------------------------------
    # Refresh helpers
    # ------------------------------------------------------------------

    def _refresh_all(self) -> None:
        self._refresh_nav()
        self._refresh_flags()
        self._refresh_scalars()
        self._refresh_car_table()
        self._refresh_meta_panel()
        self._refresh_dirty_indicator()
        if self._page:
            self._page.update()

    def _refresh_nav(self) -> None:
        n = len(self._frames)
        if self._frame_slider:
            self._frame_slider.max = max(1, n - 1)
            self._frame_slider.value = self._frame_index
            if n > 1:
                self._frame_slider.divisions = n - 1
        if self._frame_input:
            self._frame_input.value = str(self._frame_index + 1)  # 1-based display
        if self._frame_count_label:
            self._frame_count_label.value = f"/ {n}"
        if not self._frames:
            return
        frame = self._frames[self._frame_index]
        if hasattr(self, "_session_time_value"):
            self._session_time_value.value = f"{frame.get('SessionTime', 0):.3f}s"
        if hasattr(self, "_session_tick_value"):
            self._session_tick_value.value = f"  tick {frame.get('SessionTick', '—')}"

    def _refresh_flags(self) -> None:
        if self._flags_row is None or not self._frames:
            return
        frame = self._frames[self._frame_index]
        flags_val = frame.get("SessionFlags", 0)
        chips: list[ft.Control] = []
        decoded = decode_flags(flags_val, SESSION_FLAG_NAMES)
        if decoded:
            for name, colour in decoded:
                chips.append(
                    ft.Container(
                        content=ft.Text(
                            name, size=11, color="#11111B", weight=ft.FontWeight.W_600
                        ),
                        bgcolor=colour,
                        border_radius=10,
                        padding=ft.padding.symmetric(horizontal=8, vertical=2),
                    )
                )
        else:
            chips.append(
                ft.Text(
                    "0x00000000  (no flags set)",
                    size=11,
                    color=TEXT_DIM,
                    font_family="Mono",
                )
            )
        chips.append(
            ft.Text(
                f"  0x{flags_val:08X}",
                size=11,
                color=TEXT_DIM,
                font_family="Mono",
            )
        )
        self._flags_row.controls = chips

    def _refresh_scalars(self) -> None:
        if self._scalar_grid is None or not self._frames:
            return
        frame = self._frames[self._frame_index]
        rows: list[ft.Control] = []
        scalar_keys = [k for k, v in frame.items() if not isinstance(v, list)]
        for key in scalar_keys:
            val = frame[key]
            rows.append(self._make_scalar_row(key, val))
        self._scalar_grid.controls = rows

    def _make_scalar_row(self, key: str, val: Any) -> ft.Container:
        """Build a single key/value row with inline edit support."""

        val_text = ft.Text(
            str(val),
            size=12,
            color=self._scalar_colour(key, val),
            font_family="Mono",
            expand=True,
            no_wrap=True,
            overflow=ft.TextOverflow.ELLIPSIS,
        )

        edit_field = ft.TextField(
            value=str(val),
            dense=True,
            text_style=ft.TextStyle(color=TEXT_MAIN, size=12, font_family="Mono"),
            border_color=ACCENT,
            focused_border_color=ACCENT,
            bgcolor=SURFACE0,
            content_padding=ft.padding.symmetric(horizontal=6, vertical=2),
            expand=True,
            visible=False,
        )

        row_ref: dict[str, Any] = {"editing": False}

        def start_edit(_: Any) -> None:
            if row_ref["editing"]:
                return
            row_ref["editing"] = True
            edit_field.value = str(frame_val_ref[0])
            val_text.visible = False
            edit_field.visible = True
            edit_btn.icon = ft.Icons.CHECK
            edit_btn.icon_color = TEXT_GREEN
            if self._page:
                self._page.update()
            edit_field.focus()

        def commit_edit(_: Any) -> None:
            raw = edit_field.value or ""
            new_val = self._coerce(raw, frame_val_ref[0])
            if new_val is None:
                edit_field.error_text = "invalid"
                if self._page:
                    self._page.update()
                return
            frame = self._frames[self._frame_index]
            frame[key] = new_val
            frame_val_ref[0] = new_val
            val_text.value = str(new_val)
            val_text.color = self._scalar_colour(key, new_val)
            val_text.visible = True
            edit_field.visible = False
            edit_field.error_text = None
            edit_btn.icon = ft.Icons.EDIT
            edit_btn.icon_color = TEXT_DIM
            row_ref["editing"] = False
            self._mark_dirty()
            if self._page:
                self._page.update()

        def cancel_edit(_: Any) -> None:
            val_text.visible = True
            edit_field.visible = False
            edit_btn.icon = ft.Icons.EDIT
            edit_btn.icon_color = TEXT_DIM
            row_ref["editing"] = False
            if self._page:
                self._page.update()

        # Hold a mutable reference to the current value
        frame_val_ref: list[Any] = [val]

        edit_field.on_submit = commit_edit
        edit_field.on_blur = cancel_edit

        edit_btn = ft.IconButton(
            icon=ft.Icons.EDIT,
            icon_size=14,
            icon_color=TEXT_DIM,
            tooltip="Edit value",
            on_click=lambda e: commit_edit(e) if row_ref["editing"] else start_edit(e),
            style=ft.ButtonStyle(padding=ft.padding.all(2)),
        )

        return ft.Container(
            content=ft.Row(
                [
                    ft.Container(
                        content=ft.Text(
                            key,
                            size=11,
                            color=TEXT_DIM,
                            no_wrap=True,
                            overflow=ft.TextOverflow.CLIP,
                        ),
                        width=160,
                        padding=ft.padding.only(left=12),
                    ),
                    ft.Container(
                        content=ft.Stack([val_text, edit_field]),
                        expand=True,
                        padding=ft.padding.symmetric(horizontal=4),
                    ),
                    edit_btn,
                ],
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                spacing=0,
            ),
            bgcolor=ROW_EVEN_BG,
            border=ft.border.only(bottom=ft.BorderSide(1, SURFACE0)),
            padding=ft.padding.symmetric(vertical=2),
        )

    def _scalar_colour(self, key: str, val: Any) -> str:
        if isinstance(val, bool):
            return TEXT_GREEN if val else TEXT_RED
        if key == "SessionFlags" and isinstance(val, int) and val != 0:
            return TEXT_YELLOW
        if isinstance(val, float):
            return TEXT_YELLOW
        if isinstance(val, int):
            return ACCENT
        return TEXT_MAIN

    def _refresh_car_table(self) -> None:
        if self._car_table_container is None or not self._frames:
            return
        frame = self._frames[self._frame_index]
        self._car_table_container.content = self._build_car_table(frame)

    def _build_car_table(self, frame: dict) -> ft.Column:
        """Build the per-car data table for the current frame."""
        lap_pct = frame.get("CarIdxLapDistPct", [])
        lap_comp = frame.get("CarIdxLapCompleted", [])
        on_pit = frame.get("CarIdxOnPitRoad", [])
        sess_flags = frame.get("CarIdxSessionFlags", [])
        last_lap = frame.get("CarIdxLastLapTime", [])
        f2_time = frame.get("CarIdxF2Time", [])

        n_slots = max(
            len(lap_pct),
            len(lap_comp),
            len(on_pit),
            len(sess_flags),
            len(last_lap),
            len(f2_time),
        )

        def _get(lst: list, i: int, default: Any = None) -> Any:
            return lst[i] if i < len(lst) else default

        # Build rows for active cars only (pct >= 0 or has completed laps)
        car_rows: list[dict] = []
        for car_idx in range(n_slots):
            pct = _get(lap_pct, car_idx, -1.0)
            laps = _get(lap_comp, car_idx, -1)
            # Skip empty slots
            if pct < 0 and laps < 0:
                continue
            driver = self._idx_to_driver.get(car_idx, {})
            car_num = driver.get("CarNumber", str(car_idx))
            name = driver.get("UserName", "—")
            car_rows.append(
                {
                    "car_idx": car_idx,
                    "car_num": car_num,
                    "name": name,
                    "pct": pct,
                    "laps": laps,
                    "on_pit": bool(_get(on_pit, car_idx, False)),
                    "flags": int(_get(sess_flags, car_idx, 0)),
                    "last_lap": float(_get(last_lap, car_idx, -1.0)),
                    "f2_time": float(_get(f2_time, car_idx, 0.0)),
                }
            )

        # Sort by laps DESC then pct DESC (approximate race order)
        car_rows.sort(key=lambda r: (r["laps"], r["pct"]), reverse=True)

        # ---- Header row ----
        col_widths = [40, 55, 160, 70, 55, 65, 70, 75, 75]
        col_labels = [
            "Idx",
            "Car#",
            "Driver",
            "Pct%",
            "Laps",
            "Pit?",
            "Flags",
            "LastLap",
            "F2Time",
        ]
        header_cells: list[ft.Control] = []
        for label, w in zip(col_labels, col_widths):
            header_cells.append(
                ft.Container(
                    content=ft.Text(
                        label,
                        size=11,
                        color=TEXT_DIM,
                        weight=ft.FontWeight.W_600,
                        no_wrap=True,
                    ),
                    width=w,
                    padding=ft.padding.symmetric(horizontal=4),
                )
            )
        header = ft.Container(
            content=ft.Row(header_cells, spacing=0),
            bgcolor=HEADER_BG,
            padding=ft.padding.symmetric(vertical=4),
            border=ft.border.only(bottom=ft.BorderSide(1, SURFACE1)),
        )

        # ---- Data rows ----
        data_rows: list[ft.Control] = [header]
        player_idx = frame.get("PlayerCarIdx", -1)

        for row_i, row in enumerate(car_rows):
            is_player = row["car_idx"] == player_idx
            bg = (
                "#2A1F3D"
                if is_player
                else (ROW_EVEN_BG if row_i % 2 == 0 else ROW_ODD_BG)
            )
            flag_chips = self._make_car_flag_chips(row["flags"])
            pit_text = ft.Text(
                "YES" if row["on_pit"] else "no",
                size=11,
                color=TEXT_YELLOW if row["on_pit"] else TEXT_DIM,
                font_family="Mono",
            )
            pct_colour = TEXT_GREEN if row["pct"] >= 0 else TEXT_DIM
            cells: list[ft.Control] = [
                self._car_cell(str(row["car_idx"]), col_widths[0], TEXT_DIM),
                self._car_cell(row["car_num"], col_widths[1], ACCENT, bold=is_player),
                self._car_cell(
                    row["name"][:22], col_widths[2], TEXT_MAIN, bold=is_player
                ),
                self._car_cell(
                    f"{row['pct']:.4f}" if row["pct"] >= 0 else "—",
                    col_widths[3],
                    pct_colour,
                ),
                self._car_cell(
                    str(row["laps"]) if row["laps"] >= 0 else "—",
                    col_widths[4],
                    TEXT_MAIN,
                ),
                ft.Container(
                    content=pit_text,
                    width=col_widths[5],
                    padding=ft.padding.symmetric(horizontal=4),
                ),
                ft.Container(
                    content=flag_chips,
                    width=col_widths[6],
                    padding=ft.padding.symmetric(horizontal=2),
                ),
                self._car_cell(
                    f"{row['last_lap']:.3f}" if row["last_lap"] >= 0 else "—",
                    col_widths[7],
                    TEXT_DIM,
                ),
                self._car_cell(f"{row['f2_time']:.3f}", col_widths[8], TEXT_DIM),
            ]

            # Make the pct cell editable
            car_idx_captured = row["car_idx"]
            data_rows.append(
                ft.Container(
                    content=ft.Row(cells, spacing=0),
                    bgcolor=bg,
                    padding=ft.padding.symmetric(vertical=3),
                    border=ft.border.only(bottom=ft.BorderSide(1, SURFACE0)),
                    on_long_press=lambda e, ci=car_idx_captured: self._open_car_edit_dialog(
                        ci
                    ),
                    tooltip="Long-press to edit car fields",
                )
            )

        table_col = ft.Column(
            controls=data_rows,
            spacing=0,
            scroll=ft.ScrollMode.AUTO,
            expand=True,
        )
        return ft.Column(
            [
                ft.Container(
                    content=ft.Text(
                        "Per-Car Data (sorted by race position)",
                        size=11,
                        color=TEXT_DIM,
                        weight=ft.FontWeight.W_600,
                    ),
                    padding=ft.padding.only(left=12, top=8, bottom=4),
                ),
                ft.Container(content=table_col, expand=True),
            ],
            spacing=0,
            expand=True,
        )

    def _car_cell(
        self, text: str, width: int, colour: str, bold: bool = False
    ) -> ft.Container:
        return ft.Container(
            content=ft.Text(
                text,
                size=12,
                color=colour,
                font_family="Mono",
                no_wrap=True,
                overflow=ft.TextOverflow.CLIP,
                weight=ft.FontWeight.W_600 if bold else ft.FontWeight.W_400,
            ),
            width=width,
            padding=ft.padding.symmetric(horizontal=4),
        )

    def _make_car_flag_chips(self, flags: int) -> ft.Row:
        decoded = decode_flags(flags, CAR_SESSION_FLAG_NAMES)
        if not decoded:
            return ft.Row([ft.Text("—", size=10, color=TEXT_DIM)], spacing=2)
        chips = [
            ft.Container(
                content=ft.Text(name[:3], size=9, color="#11111B"),
                bgcolor=colour,
                border_radius=4,
                padding=ft.padding.symmetric(horizontal=3, vertical=1),
            )
            for name, colour in decoded
        ]
        return ft.Row(chips, spacing=2, wrap=True)

    # ------------------------------------------------------------------
    # Car field edit dialog
    # ------------------------------------------------------------------

    def _open_car_edit_dialog(self, car_idx: int) -> None:
        """Open a dialog for editing all CarIdx-array values for one car."""
        if not self._frames or self._page is None:
            return
        frame = self._frames[self._frame_index]
        driver = self._idx_to_driver.get(car_idx, {})
        car_num = driver.get("CarNumber", str(car_idx))
        name = driver.get("UserName", "—")

        array_keys = [k for k, v in frame.items() if isinstance(v, list)]

        fields: dict[str, ft.TextField] = {}
        field_rows: list[ft.Control] = []

        for key in array_keys:
            arr = frame[key]
            cur_val = arr[car_idx] if car_idx < len(arr) else None
            if cur_val is None:
                continue
            tf = ft.TextField(
                label=key,
                value=str(cur_val),
                dense=True,
                text_style=ft.TextStyle(color=TEXT_MAIN, size=12, font_family="Mono"),
                label_style=ft.TextStyle(color=TEXT_DIM, size=11),
                border_color=SURFACE1,
                focused_border_color=ACCENT,
                bgcolor=SURFACE0,
                width=300,
            )
            fields[key] = tf
            field_rows.append(tf)

        def on_save(_: Any) -> None:
            frame = self._frames[self._frame_index]
            any_changed = False
            for key, tf in fields.items():
                arr = frame.get(key, [])
                if car_idx >= len(arr):
                    continue
                cur = arr[car_idx]
                new_val = self._coerce(tf.value or "", cur)
                if new_val is not None and new_val != cur:
                    arr[car_idx] = new_val
                    any_changed = True
            if any_changed:
                self._mark_dirty()
            dlg.open = False
            self._refresh_all()

        def on_cancel(_: Any) -> None:
            dlg.open = False
            if self._page:
                self._page.update()

        dlg = ft.AlertDialog(
            modal=True,
            title=ft.Text(
                f"Edit Car #{car_num}  —  {name}  (CarIdx {car_idx})", color=TEXT_MAIN
            ),
            content=ft.Container(
                content=ft.Column(
                    controls=field_rows,
                    spacing=8,
                    scroll=ft.ScrollMode.AUTO,
                ),
                width=340,
                height=420,
            ),
            actions=[
                ft.TextButton(
                    "Cancel", on_click=on_cancel, style=ft.ButtonStyle(color=TEXT_DIM)
                ),
                ft.ElevatedButton(
                    "Save",
                    on_click=on_save,
                    bgcolor=SURFACE1,
                    color=TEXT_GREEN,
                ),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
            bgcolor=HEADER_BG,
        )
        self._page.overlay.append(dlg)
        dlg.open = True
        self._page.update()

    # ------------------------------------------------------------------
    # Meta / sidecar panel
    # ------------------------------------------------------------------

    def _refresh_meta_panel(self) -> None:
        if self._meta_panel is None:
            return
        rows: list[ft.Control] = []

        # Telemetry meta
        if self._data:
            meta = self._data.get("meta", {})
            meta_items: list[ft.Control] = []
            for key in (
                "captured_at",
                "frame_count",
                "tick_rate_hz",
                "track_length_km",
            ):
                val = meta.get(key)
                if val is not None:
                    meta_items.append(
                        ft.Row(
                            [
                                ft.Text(f"{key}:", size=11, color=TEXT_DIM, width=160),
                                ft.Text(
                                    str(val),
                                    size=11,
                                    color=TEXT_MAIN,
                                    font_family="Mono",
                                ),
                            ],
                            spacing=4,
                        )
                    )
            rows.append(
                ft.ExpansionTile(
                    title=ft.Text(
                        "Telemetry Meta",
                        size=12,
                        color=TEXT_DIM,
                        weight=ft.FontWeight.W_600,
                    ),
                    controls=[
                        ft.Container(
                            content=ft.Column(meta_items, spacing=2),
                            padding=ft.padding.only(left=16, bottom=6),
                        )
                    ],
                    initially_expanded=False,
                    icon_color=TEXT_DIM,
                    text_color=TEXT_DIM,
                    bgcolor=HEADER_BG,
                    collapsed_bgcolor=HEADER_BG,
                )
            )

        # Sidecar meta (event_kwargs + expected_restart_order)
        if self._meta_sidecar:
            sidecar_items: list[ft.Control] = []

            desc = self._meta_sidecar.get("description", "")
            if desc:
                sidecar_items.append(
                    ft.Row(
                        [
                            ft.Text("description:", size=11, color=TEXT_DIM, width=220),
                            ft.Text(desc, size=11, color=TEXT_YELLOW),
                        ],
                        spacing=4,
                    )
                )

            # event_kwargs grid
            event_kwargs = self._meta_sidecar.get("event_kwargs", {})
            if event_kwargs:
                kw_rows: list[ft.Control] = []
                for k, v in sorted(event_kwargs.items()):
                    kw_rows.append(
                        ft.Row(
                            [
                                ft.Text(f"{k}:", size=11, color=TEXT_DIM, width=270),
                                ft.Text(
                                    json.dumps(v),
                                    size=11,
                                    color=TEXT_MAIN,
                                    font_family="Mono",
                                ),
                            ],
                            spacing=4,
                        )
                    )
                sidecar_items.append(
                    ft.ExpansionTile(
                        title=ft.Text("event_kwargs", size=11, color=TEXT_DIM),
                        controls=[
                            ft.Container(
                                content=ft.Column(kw_rows, spacing=1),
                                padding=ft.padding.only(left=16),
                            )
                        ],
                        initially_expanded=False,
                        icon_color=TEXT_DIM,
                        text_color=TEXT_DIM,
                        bgcolor=HEADER_BG,
                        collapsed_bgcolor=HEADER_BG,
                    )
                )

            # expected_restart_order
            expected = self._meta_sidecar.get("expected_restart_order", [])
            if expected:
                order_lines = [
                    ft.Row(
                        [
                            ft.Text(
                                f"Lane {i + 1}:", size=11, color=TEXT_DIM, width=60
                            ),
                            ft.Text(
                                ", ".join(lane),
                                size=11,
                                color=TEXT_GREEN,
                                font_family="Mono",
                            ),
                        ],
                        spacing=4,
                    )
                    for i, lane in enumerate(expected)
                ]
                sidecar_items.append(
                    ft.ExpansionTile(
                        title=ft.Text(
                            "expected_restart_order", size=11, color=TEXT_DIM
                        ),
                        controls=[
                            ft.Container(
                                content=ft.Column(order_lines, spacing=2),
                                padding=ft.padding.only(left=16),
                            )
                        ],
                        initially_expanded=True,
                        icon_color=TEXT_DIM,
                        text_color=TEXT_DIM,
                        bgcolor=HEADER_BG,
                        collapsed_bgcolor=HEADER_BG,
                    )
                )

            rows.append(
                ft.ExpansionTile(
                    title=ft.Text(
                        ".meta.json Sidecar",
                        size=12,
                        color=TEXT_DIM,
                        weight=ft.FontWeight.W_600,
                    ),
                    controls=[
                        ft.Container(
                            content=ft.Column(sidecar_items, spacing=0),
                            padding=ft.padding.only(left=16, bottom=6),
                        )
                    ],
                    initially_expanded=True,
                    icon_color=TEXT_DIM,
                    text_color=TEXT_DIM,
                    bgcolor=HEADER_BG,
                    collapsed_bgcolor=HEADER_BG,
                )
            )

        self._meta_panel.controls = rows

    # ------------------------------------------------------------------
    # Dirty tracking
    # ------------------------------------------------------------------

    def _mark_dirty(self) -> None:
        self._dirty = True
        self._refresh_dirty_indicator()

    def _refresh_dirty_indicator(self) -> None:
        if self._dirty_indicator is None:
            return
        if self._dirty:
            self._dirty_indicator.value = "● Unsaved changes  (Ctrl+S to save)"
            self._dirty_indicator.color = DIRTY_COLOUR
        else:
            self._dirty_indicator.value = "✓ All changes saved"
            self._dirty_indicator.color = CLEAN_COLOUR

    # ------------------------------------------------------------------
    # Status bar
    # ------------------------------------------------------------------

    def _set_status(self, msg: str, error: bool = False) -> None:
        if self._status_text is None:
            return
        self._status_text.value = msg
        self._status_text.color = TEXT_RED if error else TEXT_DIM
        if self._page:
            self._page.update()

    # ------------------------------------------------------------------
    # Type coercion for edits
    # ------------------------------------------------------------------

    @staticmethod
    def _coerce(raw: str, original: Any) -> Any:
        """Try to cast *raw* to the same Python type as *original*.

        Returns the cast value on success, or None on failure.
        """
        raw = raw.strip()
        if isinstance(original, bool):
            if raw.lower() in ("true", "1", "yes"):
                return True
            if raw.lower() in ("false", "0", "no"):
                return False
            return None
        if isinstance(original, int):
            try:
                return int(raw, 0)  # supports 0x hex literals
            except ValueError:
                try:
                    return int(float(raw))
                except ValueError:
                    return None
        if isinstance(original, float):
            try:
                return float(raw)
            except ValueError:
                return None
        if isinstance(original, str):
            return raw
        # For any other type, attempt literal eval
        try:
            import ast

            return ast.literal_eval(raw)
        except Exception:
            return raw  # fall back to string


# ===========================================================================
# CLI entry point
# ===========================================================================


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Browse and edit test fixture telemetry frames.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--fixture",
        metavar="PATH",
        type=Path,
        default=None,
        help="Path to a specific .json or .json.gz fixture to open on startup.",
    )
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    app = FixtureBrowserApp(initial_fixture=args.fixture)
    ft.app(target=app.main)


if __name__ == "__main__":
    main()
