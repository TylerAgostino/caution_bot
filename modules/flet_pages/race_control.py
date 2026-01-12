import asyncio
import json
import logging
import os
from math import isnan
from typing import Dict, Optional

import flet as ft
import pandas as pd

from modules import SubprocessManager, events, subprocess_manager
from modules.events import BaseEvent, F1QualifyingEvent
from modules.logging_context import get_logger


class RaceControlApp:
    def __init__(self):
        self.page: Optional[ft.Page] = None
        self.subprocess_manager: Optional[SubprocessManager] = None
        self.is_running: bool = False
        self.status_indicator: Optional[ft.Container] = None
        self.start_button: Optional[ft.ElevatedButton] = None
        self.stop_button: Optional[ft.ElevatedButton] = None

        # Event configuration storage
        self.random_caution_configs = []
        self.random_caution_global_config = {
            "use_lap_based": False,
            "pit_close_advance_warning": 5,
            "pit_close_max_duration": 90,
            "max_laps_behind_leader": 0,
            "wave_around_lap": 1,
            "extend_laps": 0,
            "pre_extend_laps": 1,
            "wave_arounds": True,
            "notify_on_skipped_caution": False,
            "full_sequence": True,
        }
        self.random_code69_configs = []
        self.random_code69_global_config = {
            "use_lap_based": False,
            "max_speed_km": 69,
            "wet_speed_km": 69,
            "restart_speed_pct": 125,
            "reminder_frequency": 8,
            "auto_restart_get_ready_position": 1.79,
            "auto_restart_form_lanes_position": 1.63,
            "auto_class_separate_position": -1.0,
            "quickie_auto_restart_get_ready_position": 0.79,
            "quickie_auto_restart_form_lanes_position": 0.63,
            "quickie_auto_class_separate_position": -1,
            "quickie_window": 5,
            "quickie_invert_lanes": False,
            "end_of_lap_safety_margin": 0.1,
            "lane_names": "Right,Left",
            "wave_arounds": True,
            "notify_on_skipped_caution": False,
        }
        self.incident_caution_config = {
            "drivers_threshold": 3,
            "incident_window_seconds": 10,
            "overall_driver_window": 30,
            "auto_increase": False,
            "increase_by": 1,
            "min": 0,
            "max": -1,
            "use_lap_based": False,
            "extend_laps": 0,
            "pre_extend_laps": 1,
            "max_laps_behind_leader": 0,
            "notify_on_skipped_caution": False,
            "full_sequence": True,
            "pit_close_advance_warning": 5,
            "pit_close_max_duration": 90,
            "wave_around_lap": 1,
            "wave_arounds": True,
        }
        self.incident_penalty_config = {}
        self.scheduled_messages = []
        self.collision_penalty_config = {
            "collisions_per_penalty": 3,
            "penalty": "d",
            "tracking_window_seconds": 10,
            "max_laps_behind_leader": 99,
        }
        self.clear_black_flag_config = {
            "interval": 5,
        }
        self.scheduled_black_flag_configs = []
        self.gap_to_leader_config = {
            "gap_to_leader": 60.0,
            "penalty": "4120",
            "sound": True,
        }
        self.text_consumer_config = {}
        self.audio_consumer_config = {}
        self.chat_consumer_config = {}
        self.text_consumer_enabled = False
        self.audio_consumer_enabled = False
        self.chat_consumer_enabled = False
        self.chat_message_list = None
        self.chat_refresh_timer = None

        # Master enable toggles for event tabs
        self.random_cautions_enabled = True
        self.random_code69s_enabled = True
        self.incident_cautions_enabled = True
        self.incident_penalties_enabled = True
        self.scheduled_messages_enabled = True
        self.collision_penalty_enabled = False
        self.clear_black_flag_enabled = False
        self.scheduled_black_flag_enabled = False
        self.gap_to_leader_enabled = False

        # Tab references for updating indicators
        self.tabs_control = None

        # F1 Qualifying mode state
        self.f1_subprocess_manager: Optional[SubprocessManager] = None
        self.f1_event: Optional[F1QualifyingEvent] = None
        self.f1_elim_sessions = [
            {"duration": "12", "advancing_cars": "15"},
            {"duration": "10", "advancing_cars": "10"},
        ]

        # F1 Qualifying leaderboard column reference for updates
        self.f1_leaderboard_column = None
        self.f1_final_session = {"duration": "8", "advancing_cars": "0"}
        self.f1_wait_between = 120
        self.f1_refresh_timer = None
        self.f1_dialog = None

        # Beer Goggles mode state
        self.goggle_event: Optional[BaseEvent] = None
        self.goggles_refresh_timer = None
        self.goggles_dialog = None
        self.goggles_selected_tab = 0  # Track selected tab to preserve it
        self.goggles_tabs_control = None  # Store reference to Tabs control

    def get_starred_preset(self):
        """Get the name of the starred preset"""
        settings_path = os.path.join("presets", ".settings.json")
        if os.path.exists(settings_path):
            try:
                with open(settings_path, "r") as f:
                    settings = json.load(f)
                    return settings.get("starred_preset")
            except:
                pass
        return None

    def set_starred_preset(self, preset_name: str):
        """Set a preset as starred"""
        preset_dir = "presets"
        if not os.path.exists(preset_dir):
            os.makedirs(preset_dir)

        settings_path = os.path.join(preset_dir, ".settings.json")
        settings = {}
        if os.path.exists(settings_path):
            try:
                with open(settings_path, "r") as f:
                    settings = json.load(f)
            except:
                pass

        settings["starred_preset"] = preset_name
        with open(settings_path, "w") as f:
            json.dump(settings, f, indent=4)

    def load_default_preset(self):
        """Load the starred preset configuration data on application startup"""
        starred = self.get_starred_preset()

        # If no starred preset, star the first available preset
        if not starred:
            presets = self.get_available_presets()
            if presets:
                starred = presets[0]
                self.set_starred_preset(starred)

        # Load the starred preset data (but don't rebuild UI yet)
        if starred:
            preset_path = os.path.join("presets", f"{starred}.json")
            if os.path.exists(preset_path):
                try:
                    with open(preset_path, "r") as f:
                        config = json.load(f)

                    # Check if this is an old-format preset (list) or new format (dict)
                    if isinstance(config, dict):
                        # Load all configuration data
                        self._load_config_data(config)
                    else:
                        # Old format - skip loading, will use defaults
                        pass
                except Exception as e:
                    # If there's any error loading the preset, just use defaults
                    pass

    def main(self, page: ft.Page):
        page.window.prevent_close = True
        self.page = page
        self.page.window.height = 1040
        self.page.window.width = 1400
        page.title = "Better Caution Bot - Race Control"
        page.theme_mode = ft.ThemeMode.DARK
        page.padding = 10

        # Set window close handler to stop events
        page.window.on_event = self.on_window_event

        # Load the starred preset before building UI
        self.load_default_preset()

        # Build the UI
        page.add(
            self.build_header(),
            ft.Divider(height=10),
            ft.Row(
                [
                    self.build_main_tabs(),
                    ft.Container(width=10),
                    self.build_consumer_section(),
                ],
                vertical_alignment=ft.CrossAxisAlignment.START,
            ),
            ft.Divider(height=10),
            self.build_footer(),
        )

    def build_header(self):
        """Build the header with start/stop buttons and status indicator"""
        self.status_indicator = ft.Container(
            content=ft.Row(
                [
                    ft.Icon(ft.Icons.CIRCLE, color=ft.Colors.RED, size=14),
                    ft.Text("Stopped", size=14, weight=ft.FontWeight.BOLD),
                ],
                spacing=5,
            ),
            padding=8,
            border_radius=5,
            bgcolor=ft.Colors.with_opacity(0.1, ft.Colors.RED),
        )

        self.start_button = ft.ElevatedButton(
            "Start Race Control",
            icon=ft.Icons.PLAY_ARROW,
            on_click=self.start_race_control,
            style=ft.ButtonStyle(bgcolor=ft.Colors.GREEN, color=ft.Colors.WHITE),
        )

        self.stop_button = ft.ElevatedButton(
            "Stop Race Control",
            icon=ft.Icons.STOP,
            on_click=self.stop_race_control,
            disabled=True,
            style=ft.ButtonStyle(bgcolor=ft.Colors.RED, color=ft.Colors.WHITE),
        )

        load_button = ft.ElevatedButton(
            "Load Preset",
            icon=ft.Icons.FOLDER_OPEN,
            on_click=self.show_load_preset_dialog,
        )

        save_button = ft.ElevatedButton(
            "Save Preset", icon=ft.Icons.SAVE, on_click=self.show_save_preset_dialog
        )

        # Show starred preset indicator
        starred_preset = self.get_starred_preset()
        starred_indicator = (
            ft.Container(
                content=ft.Row(
                    [
                        ft.Icon(ft.Icons.STAR, color=ft.Colors.AMBER, size=16),
                        ft.Text(
                            (
                                f"Default: {starred_preset}"
                                if starred_preset
                                else "No default preset"
                            ),
                            size=12,
                            italic=True,
                        ),
                    ],
                    spacing=5,
                ),
                padding=5,
            )
            if starred_preset
            else ft.Container()
        )

        return ft.Container(
            content=ft.Row(
                [
                    self.start_button,
                    self.stop_button,
                    self.status_indicator,
                    ft.Container(expand=True),  # Spacer
                    starred_indicator,
                    save_button,
                    load_button,
                ],
                alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
            ),
            padding=5,
        )

    def get_tab_definitions(self):
        """Get all tab definitions with their enabled status"""
        return [
            {
                "name": "Random Cautions",
                "icon": ft.Icons.WARNING_AMBER,
                "enabled": self.random_cautions_enabled,
                "build_func": self.build_random_cautions_tab,
            },
            {
                "name": "Random Code69s",
                "icon": ft.Icons.SPEED,
                "enabled": self.random_code69s_enabled,
                "build_func": self.build_random_code69s_tab,
            },
            {
                "name": "Incident Cautions",
                "icon": ft.Icons.CAR_CRASH,
                "enabled": self.incident_cautions_enabled,
                "build_func": self.build_incident_cautions_tab,
            },
            {
                "name": "Incident Penalties",
                "icon": ft.Icons.GAVEL,
                "enabled": self.incident_penalties_enabled,
                "build_func": self.build_incident_penalties_tab,
            },
            {
                "name": "Scheduled Messages",
                "icon": ft.Icons.MESSAGE,
                "enabled": self.scheduled_messages_enabled,
                "build_func": self.build_scheduled_messages_tab,
            },
            {
                "name": "Collision Penalty",
                "icon": ft.Icons.CAR_REPAIR,
                "enabled": self.collision_penalty_enabled,
                "build_func": self.build_collision_penalty_tab,
            },
            {
                "name": "Clear Black Flag",
                "icon": ft.Icons.FLAG,
                "enabled": self.clear_black_flag_enabled,
                "build_func": self.build_clear_black_flag_tab,
            },
            {
                "name": "Scheduled Black Flag",
                "icon": ft.Icons.SPORTS_SCORE,
                "enabled": self.scheduled_black_flag_enabled,
                "build_func": self.build_scheduled_black_flag_tab,
            },
            {
                "name": "Gap to Leader",
                "icon": ft.Icons.TIMER,
                "enabled": self.gap_to_leader_enabled,
                "build_func": self.build_gap_to_leader_tab,
            },
        ]

    def build_main_tabs(self):
        """Build the main tab section for different event types, sorted by enabled status"""
        # Get tab definitions and sort: enabled first, then disabled
        tab_defs = self.get_tab_definitions()
        sorted_tabs = sorted(tab_defs, key=lambda x: (not x["enabled"], x["name"]))

        # Build tabs from sorted definitions
        tabs = []
        for tab_def in sorted_tabs:
            tab = ft.Tab(
                text=tab_def["name"],
                icon=ft.Container(
                    content=ft.Icon(tab_def["icon"]),
                    bgcolor=ft.Colors.GREEN if tab_def["enabled"] else None,
                    border_radius=5,
                    padding=5,
                ),
                content=tab_def["build_func"](),
            )
            tabs.append(tab)

        self.tabs_control = ft.Tabs(
            selected_index=0,
            animation_duration=300,
            tabs=tabs,
            expand=1,
        )

        return ft.Container(
            content=self.tabs_control,
            width=900,
            height=800,
            border=ft.border.all(1, ft.Colors.OUTLINE),
            border_radius=5,
            padding=8,
        )

    def update_tab_indicators(self):
        """Update the visual indicators on tab icons and reorder tabs"""
        if self.tabs_control and self.page:
            # Remember the currently selected tab name
            current_tab_name = None
            if 0 <= self.tabs_control.selected_index < len(self.tabs_control.tabs):
                current_tab_name = self.tabs_control.tabs[
                    self.tabs_control.selected_index
                ].text

            # Get sorted tab definitions
            tab_defs = self.get_tab_definitions()
            sorted_tabs = sorted(tab_defs, key=lambda x: (not x["enabled"], x["name"]))

            # Rebuild tabs in sorted order
            new_tabs = []
            new_selected_index = 0
            for i, tab_def in enumerate(sorted_tabs):
                tab = ft.Tab(
                    text=tab_def["name"],
                    icon=ft.Container(
                        content=ft.Icon(tab_def["icon"]),
                        bgcolor=ft.Colors.GREEN if tab_def["enabled"] else None,
                        border_radius=5,
                        padding=5,
                    ),
                    content=tab_def["build_func"](),
                )
                new_tabs.append(tab)

                # Track the new index of the previously selected tab
                if tab_def["name"] == current_tab_name:
                    new_selected_index = i

            # Update tabs and maintain selection
            self.tabs_control.tabs = new_tabs
            self.tabs_control.selected_index = new_selected_index
            self.page.update()

    def rebuild_all_tabs(self):
        """Rebuild all tab contents (used when enabling/disabling race control)"""
        if self.tabs_control and self.page:
            tab_defs = self.get_tab_definitions()
            sorted_tabs = sorted(tab_defs, key=lambda x: (not x["enabled"], x["name"]))

            # Rebuild each tab's content
            for i, tab_def in enumerate(sorted_tabs):
                if i < len(self.tabs_control.tabs):
                    self.tabs_control.tabs[i].content = tab_def["build_func"]()

            self.page.update()

    def build_random_cautions_tab(self):
        """Build the Random Cautions tab content"""
        self.random_caution_list = ft.Column(
            scroll=ft.ScrollMode.AUTO, spacing=5, expand=True
        )

        def toggle_enabled(e):
            self.random_cautions_enabled = e.control.value
            self.update_tab_indicators()

        enable_toggle = ft.Switch(
            label="Enable Random Cautions",
            value=self.random_cautions_enabled,
            on_change=toggle_enabled,
            disabled=self.is_running,
        )

        # Global settings
        global_config = self.random_caution_global_config

        def update_global_config(key, value):
            global_config[key] = value
            if key == "full_sequence":
                pit_warning.disabled = not value or self.is_running
                pit_duration.disabled = not value or self.is_running
                self.page.update()

        def toggle_lap_based(e):
            global_config["use_lap_based"] = e.control.value
            window_label.value = (
                "Window Start/End (laps)"
                if e.control.value
                else "Window Start/End (minutes)"
            )
            self.page.update()

        lap_based_toggle = ft.Row(
            [
                ft.Text("Time Based", size=14, weight=ft.FontWeight.BOLD),
                ft.Switch(
                    value=global_config["use_lap_based"],
                    disabled=self.is_running,
                    on_change=toggle_lap_based,
                ),
                ft.Text("Lap Based", size=14, weight=ft.FontWeight.BOLD),
            ],
            spacing=10,
        )

        window_label = ft.Text(
            (
                "Window Start/End (minutes)"
                if not global_config["use_lap_based"]
                else "Window Start/End (laps)"
            ),
            size=12,
            weight=ft.FontWeight.BOLD,
        )

        pit_warning = ft.TextField(
            label="Pit Close Warning (s)",
            value=str(global_config["pit_close_advance_warning"]),
            keyboard_type=ft.KeyboardType.NUMBER,
            width=150,
            disabled=not global_config["full_sequence"] or self.is_running,
            on_change=lambda e: update_global_config(
                "pit_close_advance_warning",
                int(e.control.value) if e.control.value else 0,
            ),
        )

        pit_duration = ft.TextField(
            label="Pit Close Duration (s)",
            value=str(global_config["pit_close_max_duration"]),
            keyboard_type=ft.KeyboardType.NUMBER,
            width=150,
            disabled=not global_config["full_sequence"] or self.is_running,
            on_change=lambda e: update_global_config(
                "pit_close_max_duration",
                int(e.control.value) if e.control.value else 0,
            ),
        )

        max_laps_behind = ft.TextField(
            label="Max Laps Behind Leader",
            value=str(global_config["max_laps_behind_leader"]),
            keyboard_type=ft.KeyboardType.NUMBER,
            width=150,
            disabled=self.is_running,
            on_change=lambda e: update_global_config(
                "max_laps_behind_leader",
                int(e.control.value) if e.control.value else 0,
            ),
        )

        wave_around_lap = ft.TextField(
            label="Wave Around Lap",
            value=str(global_config["wave_around_lap"]),
            keyboard_type=ft.KeyboardType.NUMBER,
            width=150,
            disabled=self.is_running,
            on_change=lambda e: update_global_config(
                "wave_around_lap",
                int(e.control.value) if e.control.value else 0,
            ),
        )

        extend_laps = ft.TextField(
            label="Extend Laps",
            value=str(global_config["extend_laps"]),
            keyboard_type=ft.KeyboardType.NUMBER,
            width=150,
            disabled=self.is_running,
            on_change=lambda e: update_global_config(
                "extend_laps",
                int(e.control.value) if e.control.value else 0,
            ),
        )

        pre_extend_laps = ft.TextField(
            label="Pre-Extend Laps",
            value=str(global_config["pre_extend_laps"]),
            keyboard_type=ft.KeyboardType.NUMBER,
            width=150,
            disabled=self.is_running,
            on_change=lambda e: update_global_config(
                "pre_extend_laps",
                int(e.control.value) if e.control.value else 0,
            ),
        )

        wave_arounds_check = ft.Checkbox(
            label="Wave Arounds",
            value=global_config["wave_arounds"],
            disabled=self.is_running,
            on_change=lambda e: update_global_config("wave_arounds", e.control.value),
        )

        notify_skip_check = ft.Checkbox(
            label="Notify on Skipped",
            value=global_config["notify_on_skipped_caution"],
            disabled=self.is_running,
            on_change=lambda e: update_global_config(
                "notify_on_skipped_caution", e.control.value
            ),
        )

        full_sequence_check = ft.Checkbox(
            label="Full Pit Close Sequence",
            value=global_config["full_sequence"],
            disabled=self.is_running,
            on_change=lambda e: update_global_config("full_sequence", e.control.value),
        )

        add_button = ft.ElevatedButton(
            "Add Random Caution Event",
            icon=ft.Icons.ADD,
            disabled=self.is_running,
            on_click=lambda _: self.add_random_caution_event(),
        )

        # Populate list from existing configs, or add initial event if empty
        if self.random_caution_configs:
            for i, cfg in enumerate(self.random_caution_configs):
                self.random_caution_list.controls.append(
                    self.create_random_caution_card(i, cfg)
                )
        else:
            self.add_random_caution_event()

        return ft.Container(
            content=ft.Column(
                [
                    ft.Row(
                        [
                            ft.Text(
                                "Random Caution Events",
                                size=16,
                                weight=ft.FontWeight.BOLD,
                            ),
                            ft.Container(expand=True),
                            enable_toggle,
                        ],
                        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                    ),
                    ft.Divider(height=5),
                    lap_based_toggle,
                    ft.Container(height=5),
                    ft.Text(
                        "Global Caution Settings", size=13, weight=ft.FontWeight.BOLD
                    ),
                    ft.Row(
                        [pit_warning, pit_duration, max_laps_behind],
                        wrap=True,
                        spacing=8,
                    ),
                    ft.Row(
                        [wave_around_lap, extend_laps, pre_extend_laps],
                        wrap=True,
                        spacing=8,
                    ),
                    ft.Row(
                        [wave_arounds_check, notify_skip_check, full_sequence_check],
                        wrap=True,
                        spacing=8,
                    ),
                    ft.Divider(height=5),
                    window_label,
                    add_button,
                    ft.Container(height=5),
                    self.random_caution_list,
                ],
                spacing=5,
            ),
            padding=8,
        )

    def add_random_caution_event(self):
        """Add a new random caution event configuration"""
        index = len(self.random_caution_configs)

        config = {
            "min": 5,
            "max": 10,
            "likelihood": "100",
        }
        self.random_caution_configs.append(config)

        card = self.create_random_caution_card(index, config)
        self.random_caution_list.controls.append(card)
        self.page.update()

    def create_random_caution_card(self, index: int, config: Dict):
        """Create a card for a random caution event configuration"""

        def update_config(key, value):
            config[key] = value
            if key == "full_sequence":
                pit_warning.disabled = not value or self.is_running
                pit_duration.disabled = not value or self.is_running
                self.page.update()

        remove_button = ft.IconButton(
            icon=ft.Icons.DELETE,
            icon_color=ft.Colors.RED,
            tooltip="Remove this event",
            on_click=lambda _: self.remove_random_caution_event(index),
        )

        use_lap_based = self.random_caution_global_config["use_lap_based"]
        window_label = "laps" if use_lap_based else "minutes"

        window_start = ft.TextField(
            label=f"Window Start ({window_label})",
            value=str(config["min"]),
            keyboard_type=ft.KeyboardType.NUMBER,
            width=150,
            on_change=lambda e: update_config(
                "min", float(e.control.value) if e.control.value else 0
            ),
        )

        window_end = ft.TextField(
            label=f"Window End ({window_label})",
            value=str(config["max"]),
            keyboard_type=ft.KeyboardType.NUMBER,
            width=150,
            on_change=lambda e: update_config(
                "max", float(e.control.value) if e.control.value else 0
            ),
        )

        likelihood = ft.TextField(
            label="Likelihood (%)",
            value=str(config["likelihood"]),
            keyboard_type=ft.KeyboardType.NUMBER,
            width=150,
            on_change=lambda e: update_config("likelihood", e.control.value),
        )

        return ft.Card(
            content=ft.Container(
                content=ft.Column(
                    [
                        ft.Row(
                            [
                                ft.Text(
                                    f"Caution Event #{index + 1}",
                                    size=14,
                                    weight=ft.FontWeight.BOLD,
                                ),
                                ft.Container(expand=True),
                                remove_button,
                            ]
                        ),
                        ft.Divider(height=5),
                        ft.Row(
                            [window_start, window_end, likelihood],
                            wrap=True,
                            spacing=8,
                        ),
                    ],
                    spacing=5,
                ),
                padding=10,
            )
        )

    def remove_random_caution_event(self, index: int):
        """Remove a random caution event"""
        if len(self.random_caution_configs) > 0:
            self.random_caution_configs.pop(index)
            self.random_caution_list.controls.pop(index)
            # Rebuild the list to update indices
            self.random_caution_list.controls.clear()
            for i, config in enumerate(self.random_caution_configs):
                self.random_caution_list.controls.append(
                    self.create_random_caution_card(i, config)
                )
            self.page.update()

    def build_random_code69s_tab(self):
        """Build the Random Code69s tab content"""
        self.random_code69_list = ft.Column(
            scroll=ft.ScrollMode.AUTO, spacing=5, expand=True
        )

        def toggle_enabled(e):
            self.random_code69s_enabled = e.control.value
            self.update_tab_indicators()

        enable_toggle = ft.Switch(
            label="Enable Random Code69s",
            value=self.random_code69s_enabled,
            disabled=self.is_running,
            on_change=toggle_enabled,
        )

        # Global settings
        global_config = self.random_code69_global_config

        def update_global_config(key, value):
            global_config[key] = value

        def toggle_lap_based(e):
            global_config["use_lap_based"] = e.control.value
            window_label.value = (
                "Window Start/End (laps)"
                if e.control.value
                else "Window Start/End (minutes)"
            )
            self.page.update()

        lap_based_toggle = ft.Row(
            [
                ft.Text("Time Based", size=14, weight=ft.FontWeight.BOLD),
                ft.Switch(
                    value=global_config["use_lap_based"],
                    disabled=self.is_running,
                    on_change=toggle_lap_based,
                ),
                ft.Text("Lap Based", size=14, weight=ft.FontWeight.BOLD),
            ],
            spacing=10,
        )

        window_label = ft.Text(
            (
                "Window Start/End (minutes)"
                if not global_config["use_lap_based"]
                else "Window Start/End (laps)"
            ),
            size=12,
            weight=ft.FontWeight.BOLD,
        )

        max_speed = ft.TextField(
            label="Pace Speed (kph)",
            value=str(global_config["max_speed_km"]),
            keyboard_type=ft.KeyboardType.NUMBER,
            width=150,
            disabled=self.is_running,
            on_change=lambda e: update_global_config(
                "max_speed_km", int(e.control.value) if e.control.value else 0
            ),
        )

        wet_speed = ft.TextField(
            label="Wet Pace (kph)",
            value=str(global_config["wet_speed_km"]),
            keyboard_type=ft.KeyboardType.NUMBER,
            width=150,
            disabled=self.is_running,
            on_change=lambda e: update_global_config(
                "wet_speed_km", int(e.control.value) if e.control.value else 0
            ),
        )

        restart_speed = ft.TextField(
            label="Restart Speed %",
            value=str(global_config["restart_speed_pct"]),
            keyboard_type=ft.KeyboardType.NUMBER,
            width=150,
            disabled=self.is_running,
            on_change=lambda e: update_global_config(
                "restart_speed_pct", int(e.control.value) if e.control.value else 0
            ),
        )

        reminder_freq = ft.TextField(
            label="Reminder Frequency",
            value=str(global_config["reminder_frequency"]),
            keyboard_type=ft.KeyboardType.NUMBER,
            width=150,
            disabled=self.is_running,
            on_change=lambda e: update_global_config(
                "reminder_frequency", int(e.control.value) if e.control.value else 0
            ),
        )

        class_sep = ft.TextField(
            label="Class Sep Position",
            value=str(global_config["auto_class_separate_position"]),
            keyboard_type=ft.KeyboardType.NUMBER,
            width=150,
            hint_text="-1 to disable",
            disabled=self.is_running,
            on_change=lambda e: update_global_config(
                "auto_class_separate_position",
                float(e.control.value) if e.control.value else 0,
            ),
        )

        lanes_form = ft.TextField(
            label="Lanes Form Position",
            value=str(global_config["auto_restart_form_lanes_position"]),
            keyboard_type=ft.KeyboardType.NUMBER,
            width=150,
            hint_text="-1 to disable",
            disabled=self.is_running,
            on_change=lambda e: update_global_config(
                "auto_restart_form_lanes_position",
                float(e.control.value) if e.control.value else 0,
            ),
        )

        restart_pos = ft.TextField(
            label="Restart Position",
            value=str(global_config["auto_restart_get_ready_position"]),
            keyboard_type=ft.KeyboardType.NUMBER,
            width=150,
            hint_text="-1 to disable",
            disabled=self.is_running,
            on_change=lambda e: update_global_config(
                "auto_restart_get_ready_position",
                float(e.control.value) if e.control.value else 0,
            ),
        )

        lane_names = ft.TextField(
            label="Lane Names",
            value=global_config["lane_names"],
            width=150,
            hint_text="Right,Left",
            disabled=self.is_running,
            on_change=lambda e: update_global_config("lane_names", e.control.value),
        )

        quickie_window = ft.TextField(
            label="Quickie Window",
            value=str(global_config["quickie_window"]),
            keyboard_type=ft.KeyboardType.NUMBER,
            width=150,
            hint_text="-1 to disable",
            disabled=self.is_running,
            on_change=lambda e: update_global_config(
                "quickie_window", float(e.control.value) if e.control.value else 0
            ),
        )

        quickie_class_sep = ft.TextField(
            label="Quickie Class Sep",
            value=str(global_config["quickie_auto_class_separate_position"]),
            keyboard_type=ft.KeyboardType.NUMBER,
            width=150,
            disabled=self.is_running,
            on_change=lambda e: update_global_config(
                "quickie_auto_class_separate_position",
                float(e.control.value) if e.control.value else 0,
            ),
        )

        quickie_lanes_form = ft.TextField(
            label="Quickie Lanes Form",
            value=str(global_config["quickie_auto_restart_form_lanes_position"]),
            keyboard_type=ft.KeyboardType.NUMBER,
            width=150,
            disabled=self.is_running,
            on_change=lambda e: update_global_config(
                "quickie_auto_restart_form_lanes_position",
                float(e.control.value) if e.control.value else 0,
            ),
        )

        quickie_restart_pos = ft.TextField(
            label="Quickie Restart Pos",
            value=str(global_config["quickie_auto_restart_get_ready_position"]),
            keyboard_type=ft.KeyboardType.NUMBER,
            width=150,
            disabled=self.is_running,
            on_change=lambda e: update_global_config(
                "quickie_auto_restart_get_ready_position",
                float(e.control.value) if e.control.value else 0,
            ),
        )

        end_of_lap_margin = ft.TextField(
            label="End of Lap Safety Margin",
            value=str(global_config["end_of_lap_safety_margin"]),
            keyboard_type=ft.KeyboardType.NUMBER,
            width=180,
            disabled=self.is_running,
            on_change=lambda e: update_global_config(
                "end_of_lap_safety_margin",
                float(e.control.value) if e.control.value else 0,
            ),
        )

        wave_arounds_check = ft.Checkbox(
            label="Wave Arounds",
            value=global_config["wave_arounds"],
            disabled=self.is_running,
            on_change=lambda e: update_global_config("wave_arounds", e.control.value),
        )

        notify_skip_check = ft.Checkbox(
            label="Notify on Skipped",
            value=global_config["notify_on_skipped_caution"],
            disabled=self.is_running,
            on_change=lambda e: update_global_config(
                "notify_on_skipped_caution", e.control.value
            ),
        )

        quickie_invert_check = ft.Checkbox(
            label="Quickie Invert Lanes",
            value=global_config["quickie_invert_lanes"],
            disabled=self.is_running,
            on_change=lambda e: update_global_config(
                "quickie_invert_lanes", e.control.value
            ),
        )

        # Advanced settings in an expansion tile
        advanced = ft.ExpansionTile(
            title=ft.Text("Advanced Quickie Settings"),
            subtitle=ft.Text("Quickie event fine-tuning options"),
            collapsed_text_color=ft.Colors.BLUE,
            text_color=ft.Colors.BLUE,
            controls=[
                ft.Container(
                    content=ft.Column(
                        [
                            ft.Row(
                                [quickie_window, quickie_class_sep, quickie_lanes_form],
                                wrap=True,
                                spacing=8,
                            ),
                            ft.Row(
                                [
                                    quickie_restart_pos,
                                    end_of_lap_margin,
                                    quickie_invert_check,
                                ],
                                wrap=True,
                                spacing=8,
                            ),
                        ]
                    ),
                    padding=8,
                )
            ],
        )

        add_button = ft.ElevatedButton(
            "Add Random Code69 Event",
            icon=ft.Icons.ADD,
            disabled=self.is_running,
            on_click=lambda _: self.add_random_code69_event(),
        )

        # Populate list from existing configs, or add initial event if empty
        if self.random_code69_configs:
            for i, cfg in enumerate(self.random_code69_configs):
                self.random_code69_list.controls.append(
                    self.create_random_code69_card(i, cfg)
                )
        else:
            self.add_random_code69_event()

        return ft.Container(
            content=ft.Column(
                [
                    ft.Row(
                        [
                            ft.Text(
                                "Random Code69 Events",
                                size=16,
                                weight=ft.FontWeight.BOLD,
                            ),
                            ft.Container(expand=True),
                            enable_toggle,
                        ],
                        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                    ),
                    ft.Divider(height=5),
                    lap_based_toggle,
                    ft.Container(height=5),
                    ft.Text(
                        "Global Code69 Settings", size=13, weight=ft.FontWeight.BOLD
                    ),
                    ft.Row(
                        [max_speed, wet_speed, restart_speed, reminder_freq],
                        wrap=True,
                        spacing=8,
                    ),
                    ft.Row(
                        [class_sep, lanes_form, restart_pos, lane_names],
                        wrap=True,
                        spacing=8,
                    ),
                    ft.Row(
                        [wave_arounds_check, notify_skip_check],
                        wrap=True,
                        spacing=8,
                    ),
                    advanced,
                    ft.Divider(height=5),
                    window_label,
                    add_button,
                    ft.Container(height=5),
                    self.random_code69_list,
                ],
                spacing=5,
            ),
            padding=8,
        )

    def add_random_code69_event(self):
        """Add a new random code69 event configuration"""
        index = len(self.random_code69_configs)

        config = {
            "min": 5,
            "max": -15,
            "likelihood": "75",
        }
        self.random_code69_configs.append(config)

        card = self.create_random_code69_card(index, config)
        self.random_code69_list.controls.append(card)
        self.page.update()

    def create_random_code69_card(self, index: int, config: Dict):
        """Create a card for a random code69 event configuration"""

        def update_config(key, value):
            config[key] = value

        remove_button = ft.IconButton(
            icon=ft.Icons.DELETE,
            icon_color=ft.Colors.RED,
            tooltip="Remove this Code69",
            disabled=self.is_running,
            on_click=lambda _: self.remove_random_code69_event(index),
        )

        window_start = ft.TextField(
            label="Window Start",
            value=str(config["min"]),
            keyboard_type=ft.KeyboardType.NUMBER,
            width=150,
            disabled=self.is_running,
            on_change=lambda e: update_config(
                "min", float(e.control.value) if e.control.value else 0
            ),
        )

        window_end = ft.TextField(
            label="Window End",
            value=str(config["max"]),
            keyboard_type=ft.KeyboardType.NUMBER,
            width=150,
            hint_text="Negative = from end",
            disabled=self.is_running,
            on_change=lambda e: update_config(
                "max", float(e.control.value) if e.control.value else 0
            ),
        )

        likelihood = ft.TextField(
            label="Likelihood (%)",
            value=str(config["likelihood"]),
            keyboard_type=ft.KeyboardType.NUMBER,
            width=150,
            disabled=self.is_running,
            on_change=lambda e: update_config(
                "likelihood", int(e.control.value) if e.control.value else 0
            ),
        )

        pit_warning = ft.TextField(
            label="Pit Close Warning (s)",
            value=str(self.random_caution_global_config["pit_close_advance_warning"]),
            keyboard_type=ft.KeyboardType.NUMBER,
            width=150,
            disabled=not self.random_caution_global_config["full_sequence"]
            or self.is_running,
            on_change=lambda e: update_config(
                "pit_close_advance_warning",
                int(e.control.value) if e.control.value else 0,
            ),
        )

        pit_duration = ft.TextField(
            label="Pit Close Duration (s)",
            value=str(self.random_caution_global_config["pit_close_max_duration"]),
            keyboard_type=ft.KeyboardType.NUMBER,
            width=150,
            disabled=not self.random_caution_global_config["full_sequence"]
            or self.is_running,
            on_change=lambda e: update_config(
                "pit_close_max_duration", int(e.control.value) if e.control.value else 0
            ),
        )

        full_sequence_check = ft.Checkbox(
            label="Full Sequence",
            value=self.random_caution_global_config["full_sequence"],
            disabled=self.is_running,
            on_change=lambda e: update_config("full_sequence", e.control.value),
        )

        return ft.Card(
            content=ft.Container(
                content=ft.Column(
                    [
                        ft.Row(
                            [
                                ft.Text(
                                    f"Code69 Event #{index + 1}",
                                    size=14,
                                    weight=ft.FontWeight.BOLD,
                                ),
                                ft.Container(expand=True),
                                remove_button,
                            ]
                        ),
                        ft.Divider(height=5),
                        ft.Row(
                            [window_start, window_end, likelihood],
                            wrap=True,
                            spacing=8,
                        ),
                    ],
                    spacing=5,
                ),
                padding=10,
            )
        )

    def remove_random_code69_event(self, index: int):
        """Remove a random code69 event"""
        if len(self.random_code69_configs) > 0:
            self.random_code69_configs.pop(index)
            self.random_code69_list.controls.pop(index)
            # Rebuild the list to update indices
            self.random_code69_list.controls.clear()
            for i, config in enumerate(self.random_code69_configs):
                self.random_code69_list.controls.append(
                    self.create_random_code69_card(i, config)
                )
            self.page.update()

    def build_incident_cautions_tab(self):
        """Build the Incident Cautions tab content"""
        # Use existing config if available, otherwise use defaults
        if (
            not hasattr(self, "incident_caution_config")
            or not self.incident_caution_config
        ):
            config = {
                "use_lap_based": False,
                "drivers_threshold": 3,
                "incident_window_seconds": 10,
                "overall_driver_window": 30,
                "auto_increase": False,
                "increase_by": 1,
                "min": 5,
                "max": -15,
                "pit_close_advance_warning": 5,
                "pit_close_max_duration": 90,
                "wave_arounds": True,
                "full_sequence": True,
                "wave_around_lap": 1,
                "extend_laps": 0,
                "pre_extend_laps": 1,
                "max_laps_behind_leader": 0,
                "notify_on_skipped_caution": False,
            }
            self.incident_caution_config = config
        else:
            config = self.incident_caution_config

        # Store reference to global config
        global_config = config

        def update_config(key, value):
            config[key] = value
            if key == "auto_increase":
                increase_by.disabled = not value or self.is_running
                self.page.update()
            elif key == "full_sequence":
                pit_warning.disabled = not value or self.is_running
                pit_duration.disabled = not value or self.is_running
                self.page.update()

        def toggle_enabled(e):
            self.incident_cautions_enabled = e.control.value
            self.update_tab_indicators()

        def toggle_lap_based(e):
            config["use_lap_based"] = e.control.value
            window_label.value = (
                "Active Window (laps)" if e.control.value else "Active Window (minutes)"
            )
            self.page.update()

        enable_toggle = ft.Switch(
            label="Enable Incident Cautions",
            value=self.incident_cautions_enabled,
            disabled=self.is_running,
            on_change=toggle_enabled,
        )

        lap_based_toggle = ft.Row(
            [
                ft.Text("Time Based", size=14, weight=ft.FontWeight.BOLD),
                ft.Switch(
                    value=config["use_lap_based"],
                    disabled=self.is_running,
                    on_change=toggle_lap_based,
                ),
                ft.Text("Lap Based", size=14, weight=ft.FontWeight.BOLD),
            ],
            spacing=10,
        )

        window_label = ft.Text(
            (
                "Active Window (minutes)"
                if not config["use_lap_based"]
                else "Active Window (laps)"
            ),
            size=12,
            weight=ft.FontWeight.BOLD,
        )

        drivers_threshold = ft.TextField(
            label="Drivers Threshold",
            value=str(config["drivers_threshold"]),
            keyboard_type=ft.KeyboardType.NUMBER,
            width=150,
            hint_text="# of cars with 4x",
            disabled=self.is_running,
            on_change=lambda e: update_config(
                "drivers_threshold", int(e.control.value) if e.control.value else 0
            ),
        )

        incident_window = ft.TextField(
            label="Individual 4x Window (s)",
            value=str(config["incident_window_seconds"]),
            keyboard_type=ft.KeyboardType.NUMBER,
            width=180,
            hint_text="Window to detect driver 4x",
            disabled=self.is_running,
            on_change=lambda e: update_config(
                "incident_window_seconds",
                int(e.control.value) if e.control.value else 0,
            ),
        )

        overall_window = ft.TextField(
            label="Overall Driver Window (s)",
            value=str(config["overall_driver_window"]),
            keyboard_type=ft.KeyboardType.NUMBER,
            width=180,
            hint_text="Window to count multiple drivers",
            disabled=self.is_running,
            on_change=lambda e: update_config(
                "overall_driver_window", int(e.control.value) if e.control.value else 0
            ),
        )

        auto_increase_check = ft.Checkbox(
            label="Auto Raise Threshold",
            value=config["auto_increase"],
            disabled=self.is_running,
            on_change=lambda e: update_config("auto_increase", e.control.value),
        )

        increase_by = ft.TextField(
            label="Increase By",
            value=str(config["increase_by"]),
            keyboard_type=ft.KeyboardType.NUMBER,
            width=120,
            disabled=not config["auto_increase"] or self.is_running,
            on_change=lambda e: update_config(
                "increase_by", int(e.control.value) if e.control.value else 0
            ),
        )

        window_start = ft.TextField(
            label="Window Start",
            value=str(config["min"]),
            keyboard_type=ft.KeyboardType.NUMBER,
            width=180,
            disabled=self.is_running,
            on_change=lambda e: update_config(
                "min", float(e.control.value) if e.control.value else 0
            ),
        )

        window_end = ft.TextField(
            label="Window End",
            value=str(config["max"]),
            keyboard_type=ft.KeyboardType.NUMBER,
            width=180,
            hint_text="Negative = from end",
            disabled=self.is_running,
            on_change=lambda e: update_config(
                "max", float(e.control.value) if e.control.value else 0
            ),
        )

        pit_warning = ft.TextField(
            label="Pit Close Warning (s)",
            value=str(config["pit_close_advance_warning"]),
            keyboard_type=ft.KeyboardType.NUMBER,
            width=150,
            disabled=not config["full_sequence"] or self.is_running,
            on_change=lambda e: update_config(
                "pit_close_advance_warning",
                int(e.control.value) if e.control.value else 0,
            ),
        )

        pit_duration = ft.TextField(
            label="Pit Close Duration (s)",
            value=str(config["pit_close_max_duration"]),
            keyboard_type=ft.KeyboardType.NUMBER,
            width=150,
            disabled=not config["full_sequence"] or self.is_running,
            on_change=lambda e: update_config(
                "pit_close_max_duration", int(e.control.value) if e.control.value else 0
            ),
        )

        wave_around_lap = ft.TextField(
            label="Wave Around Lap",
            value=str(config["wave_around_lap"]),
            keyboard_type=ft.KeyboardType.NUMBER,
            width=150,
            disabled=self.is_running,
            on_change=lambda e: update_config(
                "wave_around_lap", int(e.control.value) if e.control.value else 0
            ),
        )

        wave_arounds_check = ft.Checkbox(
            label="Wave Arounds",
            value=config["wave_arounds"],
            disabled=self.is_running,
            on_change=lambda e: update_config("wave_arounds", e.control.value),
        )

        full_sequence_check = ft.Checkbox(
            label="Full Pit Close Sequence",
            value=config["full_sequence"],
            disabled=self.is_running,
            on_change=lambda e: update_config("full_sequence", e.control.value),
        )

        extend_laps = ft.TextField(
            label="Extend Laps",
            value=str(config["extend_laps"]),
            keyboard_type=ft.KeyboardType.NUMBER,
            width=150,
            hint_text="0 = no extension",
            disabled=self.is_running,
            on_change=lambda e: update_config(
                "extend_laps", int(e.control.value) if e.control.value else 0
            ),
        )

        pre_extend_laps = ft.TextField(
            label="Pre-Extend Laps",
            value=str(config["pre_extend_laps"]),
            keyboard_type=ft.KeyboardType.NUMBER,
            width=150,
            hint_text="Laps before announcing",
            disabled=self.is_running,
            on_change=lambda e: update_config(
                "pre_extend_laps", int(e.control.value) if e.control.value else 0
            ),
        )

        max_laps_behind = ft.TextField(
            label="Max Laps Behind Leader",
            value=str(config["max_laps_behind_leader"]),
            keyboard_type=ft.KeyboardType.NUMBER,
            width=180,
            hint_text="0 = unlimited",
            disabled=self.is_running,
            on_change=lambda e: update_config(
                "max_laps_behind_leader", int(e.control.value) if e.control.value else 0
            ),
        )

        notify_skip_check = ft.Checkbox(
            label="Notify on Skipped Caution",
            value=config["notify_on_skipped_caution"],
            disabled=self.is_running,
            on_change=lambda e: update_config(
                "notify_on_skipped_caution", e.control.value
            ),
        )

        return ft.Container(
            content=ft.Column(
                [
                    ft.Row(
                        [
                            ft.Column(
                                [
                                    ft.Text(
                                        "Multi-Driver Incident Caution",
                                        size=16,
                                        weight=ft.FontWeight.BOLD,
                                    ),
                                    ft.Text(
                                        "Triggers a caution when multiple drivers receive 4x incidents within a time window",
                                        size=12,
                                        color=ft.Colors.GREY,
                                    ),
                                ],
                                expand=True,
                            ),
                            enable_toggle,
                        ],
                        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                    ),
                    ft.Divider(height=5),
                    lap_based_toggle,
                    ft.Container(height=5),
                    ft.Text(
                        "Incident Detection Settings",
                        size=14,
                        weight=ft.FontWeight.BOLD,
                    ),
                    ft.Text(
                        "Individual 4x Window: Time to detect a single driver getting 4x incidents",
                        size=11,
                        color=ft.Colors.GREY,
                        italic=True,
                    ),
                    ft.Text(
                        "Overall Driver Window: Time window to count multiple drivers with 4x",
                        size=11,
                        color=ft.Colors.GREY,
                        italic=True,
                    ),
                    ft.Row(
                        [drivers_threshold, incident_window, overall_window],
                        wrap=True,
                        spacing=10,
                    ),
                    ft.Row([increase_by], wrap=True, spacing=8),
                    ft.Row([auto_increase_check], wrap=True),
                    ft.Divider(height=5),
                    window_label,
                    ft.Row([window_start, window_end], wrap=True, spacing=8),
                    ft.Divider(height=5),
                    ft.Text(
                        "Caution Sequence Settings", size=14, weight=ft.FontWeight.BOLD
                    ),
                    ft.Row(
                        [pit_warning, pit_duration, wave_around_lap],
                        wrap=True,
                        spacing=10,
                    ),
                    ft.Row(
                        [extend_laps, pre_extend_laps, max_laps_behind],
                        wrap=True,
                        spacing=10,
                    ),
                    ft.Row(
                        [wave_arounds_check, full_sequence_check, notify_skip_check],
                        wrap=True,
                    ),
                ],
                scroll=ft.ScrollMode.AUTO,
            ),
            padding=8,
        )

    def build_incident_penalties_tab(self):
        """Build the Incident Penalties tab content"""
        # Only initialize config if it doesn't exist yet
        if not self.incident_penalty_config:
            self.incident_penalty_config = {
                "initial_penalty_incidents": 40,
                "initial_penalty": "d",
                "recurring_peanlty_every_incidents": 15,
                "recurring_penalty": "0",
                "end_recurring_incidents": 55,
                "end_recurring_penalty": "0",
                "sound": False,
            }
        config = self.incident_penalty_config

        def update_config(key, value):
            self.incident_penalty_config[key] = value

        def toggle_enabled(e):
            self.incident_penalties_enabled = e.control.value
            self.update_tab_indicators()

        enable_toggle = ft.Switch(
            label="Enable Incident Penalties",
            value=self.incident_penalties_enabled,
            disabled=self.is_running,
            on_change=toggle_enabled,
        )

        initial_incidents = ft.TextField(
            label="Initial Penalty After (incidents)",
            value=str(config["initial_penalty_incidents"]),
            keyboard_type=ft.KeyboardType.NUMBER,
            width=200,
            disabled=self.is_running,
            on_change=lambda e: update_config(
                "initial_penalty_incidents",
                int(e.control.value) if e.control.value else 0,
            ),
        )

        initial_penalty = ft.TextField(
            label="Initial Penalty",
            value=config["initial_penalty"],
            width=150,
            hint_text="d = drive through, # = seconds",
            disabled=self.is_running,
            on_change=lambda e: update_config("initial_penalty", e.control.value),
        )

        recurring_incidents = ft.TextField(
            label="Then Every (incidents)",
            value=str(config["recurring_peanlty_every_incidents"]),
            keyboard_type=ft.KeyboardType.NUMBER,
            width=150,
            disabled=self.is_running,
            on_change=lambda e: update_config(
                "recurring_peanlty_every_incidents",
                int(e.control.value) if e.control.value else 0,
            ),
        )

        recurring_penalty = ft.TextField(
            label="Recurring Penalty",
            value=config["recurring_penalty"],
            width=150,
            hint_text="0 = none",
            disabled=self.is_running,
            on_change=lambda e: update_config("recurring_penalty", e.control.value),
        )

        final_incidents = ft.TextField(
            label="Final Penalty After (incidents)",
            value=str(config["end_recurring_incidents"]),
            keyboard_type=ft.KeyboardType.NUMBER,
            width=200,
            disabled=self.is_running,
            on_change=lambda e: update_config(
                "end_recurring_incidents",
                int(e.control.value) if e.control.value else 0,
            ),
        )

        final_penalty = ft.TextField(
            label="Final Penalty",
            value=config["end_recurring_penalty"],
            width=150,
            hint_text="0 = none",
            disabled=self.is_running,
            on_change=lambda e: update_config("end_recurring_penalty", e.control.value),
        )

        sound_check = ft.Checkbox(
            label="Play Sound on Penalty",
            value=config["sound"],
            disabled=self.is_running,
            on_change=lambda e: update_config("sound", e.control.value),
        )

        return ft.Container(
            content=ft.Column(
                [
                    ft.Row(
                        [
                            ft.Column(
                                [
                                    ft.Text(
                                        "Incident Penalty System",
                                        size=16,
                                        weight=ft.FontWeight.BOLD,
                                    ),
                                    ft.Text(
                                        "Automatically penalize drivers based on their incident count",
                                        size=12,
                                        color=ft.Colors.GREY,
                                    ),
                                ],
                                expand=True,
                            ),
                            enable_toggle,
                        ],
                        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                    ),
                    ft.Divider(height=5),
                    ft.Text("Initial Penalty", size=14, weight=ft.FontWeight.BOLD),
                    ft.Row([initial_incidents, initial_penalty], wrap=True, spacing=8),
                    ft.Divider(height=5),
                    ft.Text("Recurring Penalties", size=14, weight=ft.FontWeight.BOLD),
                    ft.Row(
                        [recurring_incidents, recurring_penalty], wrap=True, spacing=8
                    ),
                    ft.Divider(height=5),
                    ft.Text("Final Penalty", size=14, weight=ft.FontWeight.BOLD),
                    ft.Row([final_incidents, final_penalty], wrap=True, spacing=8),
                    ft.Divider(height=5),
                    ft.Row([sound_check]),
                ],
                scroll=ft.ScrollMode.AUTO,
            ),
            padding=8,
        )

    def build_scheduled_messages_tab(self):
        """Build the Scheduled Messages tab content"""
        self.scheduled_messages_list = ft.Column(
            scroll=ft.ScrollMode.AUTO, spacing=5, expand=True
        )

        def toggle_enabled(e):
            self.scheduled_messages_enabled = e.control.value
            self.update_tab_indicators()

        enable_toggle = ft.Switch(
            label="Enable Scheduled Messages",
            value=self.scheduled_messages_enabled,
            disabled=self.is_running,
            on_change=toggle_enabled,
        )

        add_button = ft.ElevatedButton(
            "Add Scheduled Message",
            icon=ft.Icons.ADD,
            disabled=self.is_running,
            on_click=lambda _: self.add_scheduled_message(),
        )

        # Populate list from existing configs
        if self.scheduled_messages:
            for i, cfg in enumerate(self.scheduled_messages):
                self.scheduled_messages_list.controls.append(
                    self.create_scheduled_message_card(i, cfg)
                )

        return ft.Container(
            content=ft.Column(
                [
                    ft.Row(
                        [
                            ft.Column(
                                [
                                    ft.Text(
                                        "Scheduled Messages",
                                        size=16,
                                        weight=ft.FontWeight.BOLD,
                                    ),
                                    ft.Text(
                                        "Send messages at specific times during the race",
                                        size=12,
                                        color=ft.Colors.GREY,
                                    ),
                                ],
                                expand=True,
                            ),
                            enable_toggle,
                        ],
                        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                    ),
                    ft.Divider(height=5),
                    add_button,
                    ft.Container(height=5),
                    self.scheduled_messages_list,
                ]
            ),
            padding=8,
        )

    def add_scheduled_message(self):
        """Add a new scheduled message"""
        index = len(self.scheduled_messages)

        config = {
            "event_time": 5.0,
            "message": "",
            "race_control": False,
            "broadcast": False,
        }
        self.scheduled_messages.append(config)

        card = self.create_scheduled_message_card(index, config)
        self.scheduled_messages_list.controls.append(card)
        self.page.update()

    def create_scheduled_message_card(self, index: int, config: Dict):
        """Create a card for a scheduled message"""

        def update_config(key, value):
            config[key] = value

        remove_button = ft.IconButton(
            icon=ft.Icons.DELETE,
            icon_color=ft.Colors.RED,
            tooltip="Remove this message",
            disabled=self.is_running,
            on_click=lambda _: self.remove_scheduled_message(index),
        )

        event_time = ft.TextField(
            label="Event Time (minutes)",
            value=str(config["event_time"]),
            keyboard_type=ft.KeyboardType.NUMBER,
            width=150,
            disabled=self.is_running,
            on_change=lambda e: update_config(
                "event_time", float(e.control.value) if e.control.value else 0
            ),
        )

        message = ft.TextField(
            label="Message",
            value=config["message"],
            width=400,
            multiline=True,
            min_lines=2,
            max_lines=4,
            disabled=self.is_running,
            on_change=lambda e: update_config("message", e.control.value),
        )

        race_control_check = ft.Checkbox(
            label="Send to Race Control",
            value=config["race_control"],
            disabled=self.is_running,
            on_change=lambda e: update_config("race_control", e.control.value),
        )

        broadcast_check = ft.Checkbox(
            label="Send to Broadcast",
            value=config["broadcast"],
            disabled=self.is_running,
            on_change=lambda e: update_config("broadcast", e.control.value),
        )

        return ft.Card(
            content=ft.Container(
                content=ft.Column(
                    [
                        ft.Row(
                            [
                                ft.Text(
                                    f"Scheduled Message #{index + 1}",
                                    size=14,
                                    weight=ft.FontWeight.BOLD,
                                ),
                                ft.Container(expand=True),
                                remove_button,
                            ]
                        ),
                        ft.Divider(height=5),
                        event_time,
                        message,
                        ft.Row(
                            [race_control_check, broadcast_check], wrap=True, spacing=8
                        ),
                    ],
                    spacing=5,
                ),
                padding=10,
            )
        )

    def remove_scheduled_message(self, index: int):
        """Remove a scheduled message"""
        if len(self.scheduled_messages) > 0:
            self.scheduled_messages.pop(index)
            self.scheduled_messages_list.controls.pop(index)
            # Rebuild the list to update indices
            self.scheduled_messages_list.controls.clear()
            for i, config in enumerate(self.scheduled_messages):
                self.scheduled_messages_list.controls.append(
                    self.create_scheduled_message_card(i, config)
                )
            self.page.update()

    def build_collision_penalty_tab(self):
        """Build the Collision Penalty tab content"""
        config = self.collision_penalty_config

        def update_config(key, value):
            config[key] = value

        def toggle_enabled(e):
            self.collision_penalty_enabled = e.control.value
            self.update_tab_indicators()

        enable_toggle = ft.Switch(
            label="Enable Collision Penalty",
            value=self.collision_penalty_enabled,
            disabled=self.is_running,
            on_change=toggle_enabled,
        )

        collisions_per_penalty = ft.TextField(
            label="Collisions Per Penalty",
            value=str(config["collisions_per_penalty"]),
            keyboard_type=ft.KeyboardType.NUMBER,
            width=180,
            disabled=self.is_running,
            on_change=lambda e: update_config(
                "collisions_per_penalty", int(e.control.value) if e.control.value else 3
            ),
        )

        penalty = ft.TextField(
            label="Penalty",
            value=config["penalty"],
            width=150,
            hint_text="d = drive through",
            disabled=self.is_running,
            on_change=lambda e: update_config("penalty", e.control.value),
        )

        tracking_window = ft.TextField(
            label="Tracking Window (seconds)",
            value=str(config["tracking_window_seconds"]),
            keyboard_type=ft.KeyboardType.NUMBER,
            width=180,
            disabled=self.is_running,
            on_change=lambda e: update_config(
                "tracking_window_seconds",
                int(e.control.value) if e.control.value else 10,
            ),
        )

        max_laps_behind = ft.TextField(
            label="Max Laps Behind Leader",
            value=str(config["max_laps_behind_leader"]),
            keyboard_type=ft.KeyboardType.NUMBER,
            width=180,
            disabled=self.is_running,
            on_change=lambda e: update_config(
                "max_laps_behind_leader",
                int(e.control.value) if e.control.value else 99,
            ),
        )

        return ft.Container(
            content=ft.Column(
                [
                    ft.Row(
                        [
                            ft.Column(
                                [
                                    ft.Text(
                                        "Collision Penalty Event",
                                        size=16,
                                        weight=ft.FontWeight.BOLD,
                                    ),
                                    ft.Text(
                                        "Penalizes drivers for repeated collision patterns",
                                        size=12,
                                        color=ft.Colors.GREY,
                                    ),
                                ],
                                expand=True,
                            ),
                            enable_toggle,
                        ],
                        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                    ),
                    ft.Divider(height=5),
                    ft.Row(
                        [
                            collisions_per_penalty,
                            penalty,
                            tracking_window,
                            max_laps_behind,
                        ],
                        wrap=True,
                        spacing=10,
                    ),
                ],
                scroll=ft.ScrollMode.AUTO,
            ),
            padding=8,
        )

    def build_clear_black_flag_tab(self):
        """Build the Clear Black Flag tab content"""
        config = self.clear_black_flag_config

        def update_config(key, value):
            config[key] = value

        def toggle_enabled(e):
            self.clear_black_flag_enabled = e.control.value
            self.update_tab_indicators()

        enable_toggle = ft.Switch(
            label="Enable Clear Black Flag",
            value=self.clear_black_flag_enabled,
            disabled=self.is_running,
            on_change=toggle_enabled,
        )

        interval = ft.TextField(
            label="Check Interval (seconds)",
            value=str(config["interval"]),
            keyboard_type=ft.KeyboardType.NUMBER,
            width=180,
            disabled=self.is_running,
            on_change=lambda e: update_config(
                "interval", int(e.control.value) if e.control.value else 5
            ),
        )

        return ft.Container(
            content=ft.Column(
                [
                    ft.Row(
                        [
                            ft.Column(
                                [
                                    ft.Text(
                                        "Clear Black Flag Event",
                                        size=16,
                                        weight=ft.FontWeight.BOLD,
                                    ),
                                    ft.Text(
                                        "Automatically clears black flags at regular intervals",
                                        size=12,
                                        color=ft.Colors.GREY,
                                    ),
                                ],
                                expand=True,
                            ),
                            enable_toggle,
                        ],
                        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                    ),
                    ft.Divider(height=5),
                    ft.Row([interval], wrap=True, spacing=8),
                ],
                scroll=ft.ScrollMode.AUTO,
            ),
            padding=8,
        )

    def build_scheduled_black_flag_tab(self):
        """Build the Scheduled Black Flag tab content"""
        self.scheduled_black_flag_list = ft.Column(
            scroll=ft.ScrollMode.AUTO, spacing=5, expand=True
        )

        def toggle_enabled(e):
            self.scheduled_black_flag_enabled = e.control.value
            self.update_tab_indicators()

        enable_toggle = ft.Switch(
            label="Enable Scheduled Black Flag",
            value=self.scheduled_black_flag_enabled,
            disabled=self.is_running,
            on_change=toggle_enabled,
        )

        add_button = ft.ElevatedButton(
            "Add Scheduled Black Flag",
            icon=ft.Icons.ADD,
            disabled=self.is_running,
            on_click=lambda _: self.add_scheduled_black_flag(),
        )

        # Populate list from existing configs
        if self.scheduled_black_flag_configs:
            for i, cfg in enumerate(self.scheduled_black_flag_configs):
                self.scheduled_black_flag_list.controls.append(
                    self.create_scheduled_black_flag_card(i, cfg)
                )

        return ft.Container(
            content=ft.Column(
                [
                    ft.Row(
                        [
                            ft.Text(
                                "Scheduled Black Flag Events",
                                size=16,
                                weight=ft.FontWeight.BOLD,
                            ),
                            ft.Container(expand=True),
                            enable_toggle,
                        ],
                        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                    ),
                    ft.Divider(height=5),
                    add_button,
                    ft.Container(height=5),
                    self.scheduled_black_flag_list,
                ]
            ),
            padding=8,
        )

    def add_scheduled_black_flag(self):
        """Add a new scheduled black flag event"""
        index = len(self.scheduled_black_flag_configs)
        config = {
            "event_time": -1,
            "cars": "19",
            "penalty": "L2",
        }
        self.scheduled_black_flag_configs.append(config)
        card = self.create_scheduled_black_flag_card(index, config)
        self.scheduled_black_flag_list.controls.append(card)
        self.page.update()

    def create_scheduled_black_flag_card(self, index: int, config: Dict):
        """Create a card for a scheduled black flag event"""

        def update_config(key, value):
            config[key] = value

        remove_button = ft.IconButton(
            icon=ft.Icons.DELETE,
            icon_color=ft.Colors.RED,
            tooltip="Remove this event",
            disabled=self.is_running,
            on_click=lambda _: self.remove_scheduled_black_flag(index),
        )

        event_time = ft.TextField(
            label="Event Time (minutes)",
            value=str(config["event_time"]),
            keyboard_type=ft.KeyboardType.NUMBER,
            width=150,
            disabled=self.is_running,
            on_change=lambda e: update_config(
                "event_time", float(e.control.value) if e.control.value else 0
            ),
        )

        cars = ft.TextField(
            label="Car Numbers (comma separated)",
            value=config["cars"],
            width=300,
            disabled=self.is_running,
            on_change=lambda e: update_config("cars", e.control.value),
        )

        penalty = ft.TextField(
            label="Penalty Message",
            value=config["penalty"],
            width=300,
            disabled=self.is_running,
            on_change=lambda e: update_config("penalty", e.control.value),
        )

        return ft.Card(
            content=ft.Container(
                content=ft.Column(
                    [
                        ft.Row(
                            [
                                ft.Text(
                                    f"Scheduled Black Flag #{index + 1}",
                                    size=14,
                                    weight=ft.FontWeight.BOLD,
                                ),
                                ft.Container(expand=True),
                                remove_button,
                            ]
                        ),
                        ft.Divider(height=5),
                        ft.Row([event_time, cars, penalty], wrap=True, spacing=8),
                    ],
                    spacing=5,
                ),
                padding=10,
            )
        )

    def remove_scheduled_black_flag(self, index: int):
        """Remove a scheduled black flag event"""
        if len(self.scheduled_black_flag_configs) > 0:
            self.scheduled_black_flag_configs.pop(index)
            self.scheduled_black_flag_list.controls.pop(index)
            # Rebuild the list to update indices
            self.scheduled_black_flag_list.controls.clear()
            for i, config in enumerate(self.scheduled_black_flag_configs):
                self.scheduled_black_flag_list.controls.append(
                    self.create_scheduled_black_flag_card(i, config)
                )
            self.page.update()

    def build_gap_to_leader_tab(self):
        """Build the Gap to Leader Penalty tab content"""
        config = self.gap_to_leader_config

        def update_config(key, value):
            config[key] = value

        def toggle_enabled(e):
            self.gap_to_leader_enabled = e.control.value
            self.update_tab_indicators()

        enable_toggle = ft.Switch(
            label="Enable Gap to Leader Penalty",
            value=self.gap_to_leader_enabled,
            disabled=self.is_running,
            on_change=toggle_enabled,
        )

        gap_to_leader = ft.TextField(
            label="Gap to Leader (seconds)",
            value=str(config["gap_to_leader"]),
            keyboard_type=ft.KeyboardType.NUMBER,
            width=180,
            disabled=self.is_running,
            on_change=lambda e: update_config(
                "gap_to_leader", float(e.control.value) if e.control.value else 60.0
            ),
        )

        penalty = ft.TextField(
            label="Penalty",
            value=config["penalty"],
            width=150,
            hint_text="e.g. 4120",
            disabled=self.is_running,
            on_change=lambda e: update_config("penalty", e.control.value),
        )

        sound_check = ft.Checkbox(
            label="Play Sound",
            value=config["sound"],
            disabled=self.is_running,
            on_change=lambda e: update_config("sound", e.control.value),
        )

        return ft.Container(
            content=ft.Column(
                [
                    ft.Row(
                        [
                            ft.Column(
                                [
                                    ft.Text(
                                        "Gap to Leader Penalty Event",
                                        size=16,
                                        weight=ft.FontWeight.BOLD,
                                    ),
                                    ft.Text(
                                        "Penalizes drivers who fall too far behind the leader",
                                        size=12,
                                        color=ft.Colors.GREY,
                                    ),
                                ],
                                expand=True,
                            ),
                            enable_toggle,
                        ],
                        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                    ),
                    ft.Divider(height=5),
                    ft.Row([gap_to_leader, penalty], wrap=True, spacing=8),
                    ft.Row([sound_check], wrap=True),
                ],
                scroll=ft.ScrollMode.AUTO,
            ),
            padding=8,
        )

    def build_consumer_section(self):
        """Build the consumer events section (text, audio, and chat)"""
        return ft.Column(
            [
                ft.Container(
                    content=self.build_text_consumer(),
                    width=400,
                    border=ft.border.all(1, ft.Colors.OUTLINE),
                    border_radius=5,
                    padding=10,
                ),
                ft.Container(height=8),
                ft.Container(
                    content=self.build_audio_consumer(),
                    width=400,
                    border=ft.border.all(1, ft.Colors.OUTLINE),
                    border_radius=5,
                    padding=10,
                ),
                ft.Container(height=8),
                ft.Container(
                    content=self.build_chat_consumer(),
                    width=400,
                    border=ft.border.all(1, ft.Colors.OUTLINE),
                    border_radius=5,
                    padding=10,
                ),
            ],
        )

    def build_text_consumer(self):
        """Build the text consumer configuration"""
        # Only initialize config if it doesn't exist yet
        if not self.text_consumer_config:
            self.text_consumer_config = {"password": "", "room": "", "test": False}
        config = self.text_consumer_config

        def update_config(key, value):
            self.text_consumer_config[key] = value

        def toggle_enabled(e):
            self.text_consumer_enabled = e.control.value
            token_field.disabled = not e.control.value or self.is_running
            channel_field.disabled = not e.control.value or self.is_running
            test_check.disabled = not e.control.value or self.is_running
            self.page.update()

        enable_check = ft.Checkbox(
            label="Enable Text Consumer (Discord)",
            value=self.text_consumer_enabled,
            on_change=toggle_enabled,
            disabled=self.is_running,
        )

        token_field = ft.TextField(
            label="Bot Token",
            value=config["password"],
            password=True,
            can_reveal_password=True,
            width=250,
            disabled=not self.text_consumer_enabled or self.is_running,
            on_change=lambda e: update_config("password", e.control.value),
        )

        channel_field = ft.TextField(
            label="Text Channel ID",
            value=config["room"],
            width=250,
            disabled=not self.text_consumer_enabled or self.is_running,
            on_change=lambda e: update_config("room", e.control.value),
        )

        test_check = ft.Checkbox(
            label="Test Mode",
            value=config["test"],
            disabled=not self.text_consumer_enabled or self.is_running,
            on_change=lambda e: update_config("test", e.control.value),
        )

        return ft.Column(
            [
                ft.Text("Text Consumer (Discord)", size=14, weight=ft.FontWeight.BOLD),
                ft.Divider(height=5),
                enable_check,
                token_field,
                channel_field,
                test_check,
            ],
            spacing=5,
        )

    def build_audio_consumer(self):
        """Build the audio consumer configuration"""
        # Only initialize config if it doesn't exist yet
        if not self.audio_consumer_config:
            self.audio_consumer_config = {
                "vc_id": "420037391882125313",
                "volume": 1.0,
                "token": "",
                "hello": True,
            }
        config = self.audio_consumer_config

        def update_config(key, value):
            self.audio_consumer_config[key] = value

        def toggle_enabled(e):
            self.audio_consumer_enabled = e.control.value
            vc_id_field.disabled = not e.control.value or self.is_running
            volume_slider.disabled = not e.control.value or self.is_running
            token_field.disabled = not e.control.value or self.is_running
            hello_check.disabled = not e.control.value or self.is_running
            self.page.update()

        enable_check = ft.Checkbox(
            label="Enable Audio Consumer (Discord)",
            value=self.audio_consumer_enabled,
            on_change=toggle_enabled,
            disabled=self.is_running,
        )

        vc_id_field = ft.TextField(
            label="Discord Voice Channel ID",
            value=config["vc_id"],
            width=250,
            disabled=not self.audio_consumer_enabled or self.is_running,
            on_change=lambda e: update_config("vc_id", e.control.value),
        )

        volume_slider = ft.Slider(
            min=0,
            max=2,
            value=config["volume"],
            divisions=20,
            label="{value}",
            width=250,
            disabled=not self.audio_consumer_enabled or self.is_running,
            on_change=lambda e: update_config("volume", e.control.value),
        )

        token_field = ft.TextField(
            label="Bot Token (optional)",
            value=config["token"],
            password=True,
            can_reveal_password=True,
            width=250,
            disabled=not self.audio_consumer_enabled or self.is_running,
            hint_text="Uses BOT_TOKEN env var if empty",
            on_change=lambda e: update_config("token", e.control.value),
        )

        hello_check = ft.Checkbox(
            label="Play Hello on Connect",
            value=config["hello"],
            disabled=not self.audio_consumer_enabled or self.is_running,
            on_change=lambda e: update_config("hello", e.control.value),
        )

        return ft.Column(
            [
                ft.Text(
                    "Audio Consumer (Discord Bot)", size=14, weight=ft.FontWeight.BOLD
                ),
                ft.Divider(height=5),
                enable_check,
                vc_id_field,
                ft.Text("Volume", size=11),
                volume_slider,
                token_field,
                hello_check,
            ],
            spacing=5,
        )

    def build_chat_consumer(self):
        """Build the chat consumer configuration"""
        # Only initialize config if it doesn't exist yet
        if not self.chat_consumer_config:
            self.chat_consumer_config = {"test": False}
        config = self.chat_consumer_config

        def update_config(key, value):
            self.chat_consumer_config[key] = value

        def toggle_enabled(e):
            self.chat_consumer_enabled = e.control.value
            test_check.disabled = not e.control.value or self.is_running
            self.page.update()

        # Create a ListView to display chat messages
        self.chat_message_list = ft.ListView(
            expand=1,
            spacing=3,
            padding=8,
            auto_scroll=True,
            height=120,
        )

        return ft.Column(
            [
                ft.Text(
                    "Chat Consumer (Driver Messages)",
                    size=14,
                    weight=ft.FontWeight.BOLD,
                ),
                ft.Divider(height=5),
                ft.Container(height=5),
                ft.Text("Driver Messages:", size=11, weight=ft.FontWeight.BOLD),
                ft.Container(
                    content=self.chat_message_list,
                    border=ft.border.all(1, ft.Colors.OUTLINE),
                    border_radius=5,
                    bgcolor=ft.Colors.with_opacity(0.05, ft.Colors.ON_SURFACE),
                ),
            ],
            spacing=5,
        )

    def start_race_control(self, e):
        """Start the race control system"""
        # Get logger for logging errors
        logger_instance = get_logger()
        logger = (
            logging.LoggerAdapter(logger_instance, {"event": "RaceControl"})
            if logger_instance
            else None
        )

        try:
            self.is_running = True
            # Rebuild tabs to update disabled states
            self.rebuild_all_tabs()

            # Rebuild consumer section to disable controls
            # Note: Consumer section is in page.controls[2].controls[2]
            main_row = self.page.controls[2]  # The Row containing tabs and consumers
            main_row.controls[2] = self.build_consumer_section()

            # Build event list
            event_list = []

            # Add Random Caution Events (only if enabled)
            if self.random_cautions_enabled:
                global_config = self.random_caution_global_config
                use_lap_based = global_config["use_lap_based"]
                event_class = (
                    events.LapCautionEvent
                    if use_lap_based
                    else events.RandomCautionEvent
                )

                for config in self.random_caution_configs:
                    # If time-based, convert minutes to seconds
                    min_val = int(config["min"])
                    max_val = int(config["max"])

                    event_list.append(
                        {
                            "class": event_class,
                            "args": {
                                "min": min_val,
                                "max": max_val,
                                "pit_close_advance_warning": global_config[
                                    "pit_close_advance_warning"
                                ],
                                "pit_close_max_duration": global_config[
                                    "pit_close_max_duration"
                                ],
                                "wave_arounds": global_config["wave_arounds"],
                                "notify_on_skipped_caution": global_config[
                                    "notify_on_skipped_caution"
                                ],
                                "full_sequence": global_config["full_sequence"],
                                "wave_around_lap": global_config["wave_around_lap"],
                                "extend_laps": global_config["extend_laps"],
                                "pre_extend_laps": global_config["pre_extend_laps"],
                                "max_laps_behind_leader": global_config[
                                    "max_laps_behind_leader"
                                ],
                                "likelihood": config["likelihood"],
                            },
                        }
                    )

            # Add Random Code69 Events (only if enabled)
            if self.random_code69s_enabled:
                global_config = self.random_code69_global_config
                use_lap_based = global_config["use_lap_based"]
                event_class = (
                    events.RandomLapCode69Event
                    if use_lap_based
                    else events.RandomTimedCode69Event
                )

                for config in self.random_code69_configs:
                    # If time-based, convert minutes to seconds
                    min_val = int(config["min"])
                    max_val = int(config["max"])

                    event_list.append(
                        {
                            "class": event_class,
                            "args": {
                                "min": min_val,
                                "max": max_val,
                                "max_speed_km": global_config["max_speed_km"],
                                "wet_speed_km": global_config["wet_speed_km"],
                                "restart_speed_pct": global_config["restart_speed_pct"],
                                "reminder_frequency": global_config[
                                    "reminder_frequency"
                                ],
                                "auto_restart_get_ready_position": global_config[
                                    "auto_restart_get_ready_position"
                                ],
                                "auto_restart_form_lanes_position": global_config[
                                    "auto_restart_form_lanes_position"
                                ],
                                "auto_class_separate_position": global_config[
                                    "auto_class_separate_position"
                                ],
                                "quickie_auto_restart_get_ready_position": global_config[
                                    "quickie_auto_restart_get_ready_position"
                                ],
                                "quickie_auto_restart_form_lanes_position": global_config[
                                    "quickie_auto_restart_form_lanes_position"
                                ],
                                "quickie_auto_class_separate_position": global_config[
                                    "quickie_auto_class_separate_position"
                                ],
                                "quickie_window": global_config["quickie_window"],
                                "quickie_invert_lanes": global_config[
                                    "quickie_invert_lanes"
                                ],
                                "end_of_lap_safety_margin": global_config[
                                    "end_of_lap_safety_margin"
                                ],
                                "lane_names": global_config["lane_names"].split(","),
                                "wave_arounds": global_config["wave_arounds"],
                                "notify_on_skipped_caution": global_config[
                                    "notify_on_skipped_caution"
                                ],
                                "likelihood": config["likelihood"],
                            },
                        }
                    )

            # Add Incident Caution Event (only if enabled)
            if self.incident_cautions_enabled and self.incident_caution_config:
                config = self.incident_caution_config
                use_lap_based = config.get("use_lap_based", False)
                event_class = (
                    events.MultiDriverLapIncidentEvent
                    if use_lap_based
                    else events.MultiDriverTimedIncidentEvent
                )

                min_val = int(config["min"])
                max_val = int(config["max"])

                event_list.append(
                    {
                        "class": event_class,
                        "args": {
                            "drivers_threshold": config["drivers_threshold"],
                            "incident_window_seconds": config[
                                "incident_window_seconds"
                            ],
                            "overall_driver_window": config["overall_driver_window"],
                            "auto_increase": config["auto_increase"],
                            "increase_by": config["increase_by"],
                            "min": min_val,
                            "max": max_val,
                            "pit_close_advance_warning": config[
                                "pit_close_advance_warning"
                            ],
                            "pit_close_max_duration": config["pit_close_max_duration"],
                            "wave_arounds": config["wave_arounds"],
                            "full_sequence": config["full_sequence"],
                            "wave_around_lap": config["wave_around_lap"],
                            "extend_laps": config["extend_laps"],
                            "pre_extend_laps": config["pre_extend_laps"],
                            "max_laps_behind_leader": config["max_laps_behind_leader"],
                            "notify_on_skipped_caution": config[
                                "notify_on_skipped_caution"
                            ],
                        },
                    }
                )

            # Add Incident Penalty Event (only if enabled)
            if self.incident_penalties_enabled and self.incident_penalty_config:
                config = self.incident_penalty_config
                event_list.append(
                    {"class": events.IncidentPenaltyEvent, "args": config}
                )

            # Add Scheduled Messages (only if enabled)
            if self.scheduled_messages_enabled:
                for config in self.scheduled_messages:
                    if config["message"]:  # Only add if there's a message
                        event_list.append(
                            {
                                "class": events.ScheduledMessageEvent,
                                "args": {
                                    "event_time": config["event_time"],
                                    "message": config["message"],
                                    "race_control": config["race_control"],
                                    "broadcast": config["broadcast"],
                                },
                            }
                        )

            # Add Collision Penalty Event (only if enabled)
            if self.collision_penalty_enabled:
                config = self.collision_penalty_config
                event_list.append(
                    {
                        "class": events.CollisionPenaltyEvent,
                        "args": {
                            "collisions_per_penalty": config["collisions_per_penalty"],
                            "penalty": config["penalty"],
                            "tracking_window_seconds": config[
                                "tracking_window_seconds"
                            ],
                            "max_laps_behind_leader": config["max_laps_behind_leader"],
                        },
                    }
                )

            # Add Clear Black Flag Event (only if enabled)
            if self.clear_black_flag_enabled:
                config = self.clear_black_flag_config
                event_list.append(
                    {
                        "class": events.ClearBlackFlagEvent,
                        "args": {
                            "interval": config["interval"],
                        },
                    }
                )

            # Add Scheduled Black Flag Events (only if enabled)
            if self.scheduled_black_flag_enabled:
                for config in self.scheduled_black_flag_configs:
                    event_list.append(
                        {
                            "class": events.SprintRaceDQEvent,
                            "args": {
                                "event_time": config["event_time"],
                                "cars": config["cars"],
                                "penalty": config["penalty"],
                            },
                        }
                    )

            # Add Gap to Leader Penalty Event (only if enabled)
            if self.gap_to_leader_enabled:
                config = self.gap_to_leader_config
                event_list.append(
                    {
                        "class": events.GapToLeaderPenaltyEvent,
                        "args": {
                            "gap_to_leader": config["gap_to_leader"],
                            "penalty": config["penalty"],
                            "sound": config["sound"],
                        },
                    }
                )

            # Add Text Consumer if enabled
            if self.text_consumer_enabled:
                event_list.append(
                    {
                        "class": events.DiscordTextConsumerEvent,
                        "args": self.text_consumer_config,
                    }
                )

            # Add Audio Consumer if enabled
            if self.audio_consumer_enabled:
                event_list.append(
                    {
                        "class": events.AudioConsumerEvent,
                        "args": self.audio_consumer_config,
                    }
                )

            # Add Chat Consumer if enabled
            if self.chat_consumer_enabled:
                event_list.append(
                    {
                        "class": events.ChatConsumerEvent,
                        "args": self.chat_consumer_config,
                    }
                )

            # Create event instances with error handling
            event_instances = []
            for i, item in enumerate(event_list):
                try:
                    event_instance = item["class"](**item["args"])
                    event_instances.append(event_instance)
                    if logger:
                        logger.info(
                            f"Successfully initialized event: {item['class'].__name__}"
                        )
                except Exception as ex:
                    error_msg = f"Failed to initialize event {item['class'].__name__}: {str(ex)}"
                    if logger:
                        logger.error(error_msg)
                        logger.exception(ex)
                    # Show error dialog to user
                    self.show_error_dialog(
                        "Event Initialization Error",
                        f"{error_msg}\n\nCheck logs for more details.",
                    )
                    # Reset running state
                    self.is_running = False
                    self.rebuild_all_tabs()
                    main_row = self.page.controls[2]
                    main_row.controls[2] = self.build_consumer_section()
                    self.page.update()
                    return

            if logger:
                logger.info(f"Started {len(event_instances)} events successfully")

            # Create and start subprocess manager
            event_run_methods = [event.run for event in event_instances]
            self.subprocess_manager = SubprocessManager(event_run_methods)
            self.subprocess_manager.start()

            # Start chat consumer refresh task if enabled
            if self.chat_consumer_enabled:
                self.page.run_task(self.chat_refresh_task)

            # Update UI
            self.is_running = True
            self.start_button.disabled = True
            self.stop_button.disabled = False
            self.status_indicator.content = ft.Row(
                [
                    ft.Icon(ft.Icons.CIRCLE, color=ft.Colors.GREEN, size=16),
                    ft.Text("Running", size=16, weight=ft.FontWeight.BOLD),
                ],
                spacing=5,
            )
            self.status_indicator.bgcolor = ft.Colors.with_opacity(0.1, ft.Colors.GREEN)
            self.page.update()

        except Exception as ex:
            # Catch any unexpected errors during startup
            error_msg = f"Unexpected error starting race control: {str(ex)}"
            if logger:
                logger.error(error_msg)
                logger.exception(ex)
            self.show_error_dialog(
                "Race Control Error",
                f"{error_msg}\n\nCheck logs for more details.",
            )
            # Reset running state
            self.is_running = False
            self.rebuild_all_tabs()
            main_row = self.page.controls[2]
            main_row.controls[2] = self.build_consumer_section()
            self.page.update()

    async def chat_refresh_task(self):
        """Background task to check for new chat messages and display them"""
        import datetime
        import queue

        while self.is_running and self.chat_consumer_enabled:
            try:
                # Access the shared chat_consumer_queue from SubprocessManager
                if self.subprocess_manager and hasattr(
                    self.subprocess_manager, "chat_consumer_queue"
                ):
                    chat_queue = self.subprocess_manager.chat_consumer_queue

                    # Check for new messages in the queue
                    try:
                        while not chat_queue.empty():
                            message = chat_queue.get_nowait()
                            # Add message to the UI list
                            if self.chat_message_list:
                                timestamp = datetime.datetime.now().strftime("%H:%M:%S")
                                message_container = ft.Container(
                                    content=ft.Column(
                                        [
                                            ft.Text(
                                                f"{timestamp}",
                                                size=10,
                                                color=ft.Colors.GREY,
                                            ),
                                            ft.Text(
                                                message,
                                                size=14,
                                                weight=ft.FontWeight.W_500,
                                            ),
                                        ],
                                        spacing=2,
                                    ),
                                    padding=5,
                                    bgcolor=ft.Colors.with_opacity(
                                        0.1, ft.Colors.PRIMARY
                                    ),
                                    border_radius=5,
                                )
                                self.chat_message_list.controls.append(
                                    message_container
                                )
                                self.page.update()
                    except queue.Empty:
                        pass
            except Exception as e:
                # Log any errors but don't stop the refresh task
                print(f"Error in chat_refresh_task: {e}")

            await asyncio.sleep(0.2)  # Check 5 times per second

    def stop_race_control(self, e):
        """Stop the race control system"""
        if self.subprocess_manager:
            self.subprocess_manager.stop()
            self.subprocess_manager = None

        # Clear chat messages when stopping
        if self.chat_message_list:
            self.chat_message_list.controls.clear()

        # Update UI
        self.is_running = False
        self.start_button.disabled = False
        self.stop_button.disabled = True
        self.status_indicator.content = ft.Row(
            [
                ft.Icon(ft.Icons.CIRCLE, color=ft.Colors.RED, size=16),
                ft.Text("Stopped", size=16, weight=ft.FontWeight.BOLD),
            ],
            spacing=5,
        )
        self.status_indicator.bgcolor = ft.Colors.with_opacity(0.1, ft.Colors.RED)

        # Rebuild tabs to re-enable all controls
        self.rebuild_all_tabs()

        # Rebuild consumer section to re-enable controls
        # Note: Consumer section is in page.controls[2].controls[2]
        main_row = self.page.controls[2]  # The Row containing tabs and consumers
        main_row.controls[2] = self.build_consumer_section()

        self.page.update()

    def on_window_event(self, e):
        """Handle window events, particularly close event"""
        if e.data == "close":
            # Stop race control if running
            if self.is_running and self.subprocess_manager:
                self.stop_race_control(e)
                for thread in self.subprocess_manager.threads:
                    thread.join()
            e.page.window.destroy()

    def show_error_dialog(self, title, message):
        """Show an error dialog to the user"""

        def close_dlg(e):
            self.page.close(dlg)

        dlg = ft.AlertDialog(
            title=ft.Text(title),
            content=ft.Text(message),
            actions=[
                ft.TextButton("OK", on_click=close_dlg),
            ],
        )
        self.page.open(dlg)

    def show_save_preset_dialog(self, e):
        """Show dialog to save current configuration as preset"""

        def close_dlg(e):
            self.page.close(dlg)

        def save_preset(e):
            preset_name = name_field.value
            if preset_name:
                self.save_preset(preset_name)
                close_dlg(e)

        name_field = ft.TextField(label="Preset Name", autofocus=True)

        dlg = ft.AlertDialog(
            title=ft.Text("Save Preset"),
            content=name_field,
            actions=[
                ft.TextButton("Cancel", on_click=close_dlg),
                ft.TextButton("Save", on_click=save_preset),
            ],
        )

        self.page.open(dlg)

    def show_load_preset_dialog(self, e):
        """Show dialog to load a saved preset"""

        def close_dlg(e):
            self.page.close(dlg)

        def load_preset_handler(e):
            selected = preset_list.value
            if selected:
                self.load_preset(selected)
                close_dlg(e)

        def star_preset_handler(e):
            selected = preset_list.value
            if selected:
                self.set_starred_preset(selected)
                # Refresh the header to show the new starred preset
                header_row = self.page.controls[0]
                header_row.content = self.build_header().content
                # Refresh the dialog to show the new star
                self.page.close(dlg)
                self.show_load_preset_dialog(e)
                # Show success message
                self.page.snack_bar = ft.SnackBar(
                    content=ft.Text(f"Preset '{selected}' is now starred!"),
                    bgcolor=ft.Colors.BLUE,
                )
                self.page.snack_bar.open = True
                self.page.update()

        # Get available presets
        presets = self.get_available_presets()
        starred_preset = self.get_starred_preset()

        if not presets:
            dlg = ft.AlertDialog(
                title=ft.Text("No Presets Found"),
                content=ft.Text("There are no saved presets available."),
                actions=[ft.TextButton("OK", on_click=close_dlg)],
            )
        else:
            # Filter out old-format presets
            valid_presets = []
            for p in presets:
                preset_path = os.path.join("presets", f"{p}.json")
                try:
                    with open(preset_path, "r") as f:
                        config = json.load(f)
                    if isinstance(config, dict) and not p.endswith(".settings"):
                        valid_presets.append(p)
                except:
                    pass

            if not valid_presets:
                dlg = ft.AlertDialog(
                    title=ft.Text("No Valid Presets Found"),
                    content=ft.Text(
                        "All presets use the old format. Please save new presets using the 'Save Preset' button."
                    ),
                    actions=[ft.TextButton("OK", on_click=close_dlg)],
                )
            else:
                # Create dropdown with star indicator for starred preset
                options = []
                for p in valid_presets:
                    label = f"★ {p}" if p == starred_preset else p
                    options.append(ft.dropdown.Option(key=p, text=label))

                preset_list = ft.Dropdown(
                    label="Select Preset",
                    options=options,
                    value=starred_preset if starred_preset in valid_presets else None,
                    width=300,
                )

                star_button = ft.TextButton(
                    "⭐ Star",
                    on_click=star_preset_handler,
                    tooltip="Set as default preset to load on startup",
                )

                dlg = ft.AlertDialog(
                    title=ft.Text("Load Preset"),
                    content=preset_list,
                    actions=[
                        ft.TextButton("Cancel", on_click=close_dlg),
                        star_button,
                        ft.TextButton("Load", on_click=load_preset_handler),
                    ],
                )

        self.page.open(dlg)

    def get_available_presets(self):
        """Get list of available preset files"""
        presets = []
        preset_dir = "presets"
        if os.path.exists(preset_dir):
            for file in os.listdir(preset_dir):
                if file.endswith(".json"):
                    presets.append(file[:-5])
        return presets

    def save_preset(self, name: str):
        """Save current configuration as a preset"""
        preset_dir = "presets"
        if not os.path.exists(preset_dir):
            os.makedirs(preset_dir)

        config = {
            "random_cautions": self.random_caution_configs,
            "random_caution_global_config": self.random_caution_global_config,
            "random_cautions_enabled": self.random_cautions_enabled,
            "random_code69s": self.random_code69_configs,
            "random_code69_global_config": self.random_code69_global_config,
            "random_code69s_enabled": self.random_code69s_enabled,
            "incident_caution": self.incident_caution_config,
            "incident_cautions_enabled": self.incident_cautions_enabled,
            "incident_penalty": self.incident_penalty_config,
            "incident_penalties_enabled": self.incident_penalties_enabled,
            "scheduled_messages": self.scheduled_messages,
            "scheduled_messages_enabled": self.scheduled_messages_enabled,
            "collision_penalty": self.collision_penalty_config,
            "collision_penalty_enabled": self.collision_penalty_enabled,
            "clear_black_flag": self.clear_black_flag_config,
            "clear_black_flag_enabled": self.clear_black_flag_enabled,
            "scheduled_black_flags": self.scheduled_black_flag_configs,
            "scheduled_black_flag_enabled": self.scheduled_black_flag_enabled,
            "gap_to_leader": self.gap_to_leader_config,
            "gap_to_leader_enabled": self.gap_to_leader_enabled,
            "text_consumer": {
                "enabled": self.text_consumer_enabled,
                "config": self.text_consumer_config,
            },
            "audio_consumer": {
                "enabled": self.audio_consumer_enabled,
                "config": self.audio_consumer_config,
            },
            "chat_consumer": {
                "enabled": self.chat_consumer_enabled,
                "config": self.chat_consumer_config,
            },
        }

        with open(os.path.join(preset_dir, f"{name}.json"), "w") as f:
            json.dump(config, f, indent=4)

        # Show success message
        self.page.snack_bar = ft.SnackBar(
            content=ft.Text(f"Preset '{name}' saved successfully!"),
            bgcolor=ft.Colors.GREEN,
        )
        self.page.snack_bar.open = True
        self.page.update()

    def _load_config_data(self, config: dict):
        """Load configuration data from a preset config dictionary

        Args:
            config: Dictionary containing preset configuration data
        """
        # Load Random Cautions
        self.random_caution_configs = config.get("random_cautions", [])
        self.random_caution_global_config = config.get(
            "random_caution_global_config",
            {
                "use_lap_based": False,
                "pit_close_advance_warning": 5,
                "pit_close_max_duration": 90,
                "max_laps_behind_leader": 0,
                "wave_around_lap": 1,
                "extend_laps": 0,
                "pre_extend_laps": 1,
                "wave_arounds": True,
                "notify_on_skipped_caution": False,
                "full_sequence": True,
            },
        )
        self.random_cautions_enabled = config.get("random_cautions_enabled", True)

        # Load Random Code69s
        self.random_code69_configs = config.get("random_code69s", [])
        self.random_code69_global_config = config.get(
            "random_code69_global_config",
            {
                "use_lap_based": False,
                "max_speed_km": 69,
                "wet_speed_km": 69,
                "restart_speed_pct": 125,
                "reminder_frequency": 8,
                "auto_restart_get_ready_position": 1.79,
                "auto_restart_form_lanes_position": 1.63,
                "auto_class_separate_position": -1.0,
                "quickie_auto_restart_get_ready_position": 0.79,
                "quickie_auto_restart_form_lanes_position": 0.63,
                "quickie_auto_class_separate_position": -1,
                "quickie_window": 5,
                "quickie_invert_lanes": False,
                "end_of_lap_safety_margin": 0.1,
                "lane_names": "Right,Left",
                "wave_arounds": True,
                "notify_on_skipped_caution": False,
            },
        )
        self.random_code69s_enabled = config.get("random_code69s_enabled", True)

        # Load Incident Caution
        self.incident_caution_config = config.get("incident_caution", {})
        # Ensure all required fields are set with defaults
        if "drivers_threshold" not in self.incident_caution_config:
            self.incident_caution_config["drivers_threshold"] = 3
        if "incident_window_seconds" not in self.incident_caution_config:
            self.incident_caution_config["incident_window_seconds"] = 10
        if "overall_driver_window" not in self.incident_caution_config:
            self.incident_caution_config["overall_driver_window"] = 30
        if "auto_increase" not in self.incident_caution_config:
            self.incident_caution_config["auto_increase"] = False
        if "increase_by" not in self.incident_caution_config:
            self.incident_caution_config["increase_by"] = 1
        if "min" not in self.incident_caution_config:
            self.incident_caution_config["min"] = 0
        if "max" not in self.incident_caution_config:
            self.incident_caution_config["max"] = -1
        if "use_lap_based" not in self.incident_caution_config:
            self.incident_caution_config["use_lap_based"] = False
        if "extend_laps" not in self.incident_caution_config:
            self.incident_caution_config["extend_laps"] = 0
        if "pre_extend_laps" not in self.incident_caution_config:
            self.incident_caution_config["pre_extend_laps"] = 1
        if "max_laps_behind_leader" not in self.incident_caution_config:
            self.incident_caution_config["max_laps_behind_leader"] = 0
        if "notify_on_skipped_caution" not in self.incident_caution_config:
            self.incident_caution_config["notify_on_skipped_caution"] = False
        if "full_sequence" not in self.incident_caution_config:
            self.incident_caution_config["full_sequence"] = True
        if "pit_close_advance_warning" not in self.incident_caution_config:
            self.incident_caution_config["pit_close_advance_warning"] = 5
        if "pit_close_max_duration" not in self.incident_caution_config:
            self.incident_caution_config["pit_close_max_duration"] = 90
        if "wave_around_lap" not in self.incident_caution_config:
            self.incident_caution_config["wave_around_lap"] = 1
        if "wave_arounds" not in self.incident_caution_config:
            self.incident_caution_config["wave_arounds"] = True
        self.incident_cautions_enabled = config.get("incident_cautions_enabled", True)

        # Load Incident Penalty
        self.incident_penalty_config = config.get("incident_penalty", {})
        self.incident_penalties_enabled = config.get("incident_penalties_enabled", True)

        # Load Scheduled Messages
        self.scheduled_messages = config.get("scheduled_messages", [])
        self.scheduled_messages_enabled = config.get("scheduled_messages_enabled", True)

        # Load Collision Penalty
        self.collision_penalty_config = config.get(
            "collision_penalty",
            {
                "collisions_per_penalty": 3,
                "penalty": "d",
                "tracking_window_seconds": 10,
                "max_laps_behind_leader": 99,
            },
        )
        self.collision_penalty_enabled = config.get("collision_penalty_enabled", False)

        # Load Clear Black Flag
        self.clear_black_flag_config = config.get("clear_black_flag", {"interval": 5})
        self.clear_black_flag_enabled = config.get("clear_black_flag_enabled", False)

        # Load Scheduled Black Flags
        self.scheduled_black_flag_configs = config.get("scheduled_black_flags", [])
        self.scheduled_black_flag_enabled = config.get(
            "scheduled_black_flag_enabled", False
        )

        # Load Gap to Leader
        self.gap_to_leader_config = config.get(
            "gap_to_leader",
            {
                "gap_to_leader": 60.0,
                "penalty": "4120",
                "sound": True,
            },
        )
        self.gap_to_leader_enabled = config.get("gap_to_leader_enabled", False)

        # Load Text Consumer
        text_consumer = config.get("text_consumer", {})
        self.text_consumer_enabled = text_consumer.get("enabled", False)
        self.text_consumer_config = text_consumer.get("config", {})

        # Load Audio Consumer
        audio_consumer = config.get("audio_consumer", {})
        self.audio_consumer_enabled = audio_consumer.get("enabled", False)
        self.audio_consumer_config = audio_consumer.get("config", {})

        # Load Chat Consumer
        self.chat_consumer_enabled = True
        self.chat_consumer_config = {}

    def load_preset(self, name: str, silent: bool = False):
        """Load a saved preset

        Args:
            name: Name of the preset to load
            silent: If True, don't show success message (for startup loading)
        """
        preset_path = os.path.join("presets", f"{name}.json")
        if not os.path.exists(preset_path):
            return

        with open(preset_path, "r") as f:
            config = json.load(f)

        # Check if this is an old-format preset (list) or new format (dict)
        if not isinstance(config, dict):
            # Old format preset file - show error message
            if not silent:
                self.page.snack_bar = ft.SnackBar(
                    content=ft.Text(
                        f"Preset '{name}' uses old format. Please save it again to update."
                    ),
                    bgcolor=ft.Colors.ORANGE,
                )
                self.page.snack_bar.open = True
                self.page.update()
            return

        # Load configuration data using shared method
        self._load_config_data(config)

        # Update tab indicators
        self.update_tab_indicators()

        # Rebuild all tabs to reflect new values
        self.rebuild_all_tabs()

        # Rebuild consumer section to reflect new values
        main_row = self.page.controls[2]  # The Row containing tabs and consumers
        main_row.controls[2] = self.build_consumer_section()

        # Refresh the header to show current starred preset
        if self.page and self.page.controls:
            header_row = self.page.controls[0]
            header_row.content = self.build_header().content

        # Show success message (unless silent mode for startup)
        if not silent:
            self.page.snack_bar = ft.SnackBar(
                content=ft.Text(f"Preset '{name}' loaded successfully!"),
                bgcolor=ft.Colors.GREEN,
            )
            self.page.snack_bar.open = True
            self.page.update()

    def build_footer(self):
        """Build the footer with special mode buttons"""
        return ft.Container(
            content=ft.Row(
                [
                    ft.Text("Special Modes:", size=14, weight=ft.FontWeight.BOLD),
                    ft.ElevatedButton(
                        "F1 Qualifying",
                        icon=ft.Icons.SPEED,
                        on_click=self.open_f1_qualifying,
                        style=ft.ButtonStyle(
                            bgcolor=ft.Colors.BLUE_900,
                            color=ft.Colors.WHITE,
                        ),
                    ),
                    ft.ElevatedButton(
                        "Beer Goggles",
                        icon=ft.Icons.REMOVE_RED_EYE,
                        on_click=self.open_beer_goggles,
                        style=ft.ButtonStyle(
                            bgcolor=ft.Colors.AMBER_900,
                            color=ft.Colors.WHITE,
                        ),
                    ),
                ],
                alignment=ft.MainAxisAlignment.CENTER,
                spacing=10,
            ),
            padding=5,
            bgcolor=ft.Colors.with_opacity(0.05, ft.Colors.WHITE),
            border_radius=5,
        )

    def open_f1_qualifying(self, e):
        """Open F1 Qualifying mode dialog"""
        self.f1_dialog = ft.AlertDialog(
            modal=False,  # Allow interaction with other windows
            title=ft.Text("F1 Qualifying Mode"),
            content=self.build_f1_qualifying_content(),
            actions=[ft.TextButton("Close", on_click=self.close_f1_dialog)],
        )
        self.page.overlay.append(self.f1_dialog)
        self.f1_dialog.open = True
        self.page.update()

    def build_f1_qualifying_content(self):
        """Build the F1 qualifying configuration UI"""
        session_list = ft.Column(
            scroll=ft.ScrollMode.AUTO,
            height=300,
            spacing=10,
        )

        def rebuild_sessions():
            session_list.controls.clear()

            # Header
            header = ft.Row(
                [
                    ft.Container(
                        ft.Text("Session", weight=ft.FontWeight.BOLD), width=80
                    ),
                    ft.Container(
                        ft.Text("Duration (Mins)", weight=ft.FontWeight.BOLD), width=150
                    ),
                    ft.Container(
                        ft.Text("Advancing Cars", weight=ft.FontWeight.BOLD), width=150
                    ),
                    ft.Container(width=100),
                ]
            )
            session_list.controls.append(header)
            session_list.controls.append(ft.Divider())

            # Elimination sessions
            for i, session in enumerate(self.f1_elim_sessions):

                def make_duration_change(idx):
                    def on_change(e):
                        self.f1_elim_sessions[idx]["duration"] = e.control.value

                    return on_change

                def make_advancing_change(idx):
                    def on_change(e):
                        self.f1_elim_sessions[idx]["advancing_cars"] = e.control.value

                    return on_change

                def make_remove_click(idx):
                    def on_click(e):
                        self.f1_elim_sessions.pop(idx)
                        rebuild_sessions()
                        self.page.update()

                    return on_click

                row = ft.Row(
                    [
                        ft.Container(ft.Text(f"Q{i + 1}", size=16), width=80),
                        ft.TextField(
                            value=session["duration"],
                            width=150,
                            on_change=make_duration_change(i),
                            text_align=ft.TextAlign.CENTER,
                        ),
                        ft.TextField(
                            value=session["advancing_cars"],
                            width=150,
                            on_change=make_advancing_change(i),
                            text_align=ft.TextAlign.CENTER,
                        ),
                        ft.IconButton(
                            icon=ft.Icons.DELETE,
                            icon_color=ft.Colors.RED,
                            on_click=make_remove_click(i),
                        ),
                    ]
                )
                session_list.controls.append(row)

            # Final session
            def on_final_duration_change(e):
                self.f1_final_session["duration"] = e.control.value

            final_row = ft.Row(
                [
                    ft.Container(
                        ft.Text(f"Q{len(self.f1_elim_sessions) + 1}", size=16), width=80
                    ),
                    ft.TextField(
                        value=self.f1_final_session["duration"],
                        width=150,
                        on_change=on_final_duration_change,
                        text_align=ft.TextAlign.CENTER,
                    ),
                    ft.TextField(
                        value="0",
                        width=150,
                        disabled=True,
                        text_align=ft.TextAlign.CENTER,
                    ),
                    ft.Container(width=100),
                ]
            )
            session_list.controls.append(final_row)

        rebuild_sessions()

        def add_session(e):
            self.f1_elim_sessions.append({"duration": "", "advancing_cars": ""})
            rebuild_sessions()
            self.page.update()

        def on_wait_change(e):
            try:
                self.f1_wait_between = int(e.control.value)
            except:
                pass

        controls = ft.Column(
            [
                session_list,
                ft.Row(
                    [
                        ft.ElevatedButton(
                            "Add Session",
                            icon=ft.Icons.ADD,
                            on_click=add_session,
                        ),
                    ]
                ),
                ft.Divider(),
                ft.Row(
                    [
                        ft.Text("Wait Between Sessions (seconds):", size=14),
                        ft.TextField(
                            value=str(self.f1_wait_between),
                            width=100,
                            on_change=on_wait_change,
                            text_align=ft.TextAlign.CENTER,
                        ),
                    ]
                ),
                ft.Divider(),
                ft.Row(
                    [
                        ft.ElevatedButton(
                            "Start F1 Qualifying",
                            icon=ft.Icons.PLAY_ARROW,
                            on_click=self.start_f1_qualifying,
                            style=ft.ButtonStyle(
                                bgcolor=ft.Colors.GREEN,
                                color=ft.Colors.WHITE,
                            ),
                        ),
                        ft.ElevatedButton(
                            "Stop F1 Qualifying",
                            icon=ft.Icons.STOP,
                            on_click=self.stop_f1_qualifying,
                            style=ft.ButtonStyle(
                                bgcolor=ft.Colors.RED,
                                color=ft.Colors.WHITE,
                            ),
                        ),
                    ],
                    spacing=10,
                ),
                ft.Container(height=10),
                self.build_f1_leaderboard(),
            ],
            scroll=ft.ScrollMode.AUTO,
            width=1600,
            height=1000,
        )

        return controls

    def build_f1_leaderboard(self):
        """Build F1 qualifying leaderboard display - returns container that will be updated"""
        # Create persistent Column that we'll update (not replace)
        self.f1_leaderboard_column = ft.Column(
            [
                ft.Text(
                    "Start qualifying to see leaderboard",
                    size=14,
                    color=ft.Colors.GREY,
                )
            ],
            scroll=ft.ScrollMode.AUTO,
        )

        self.f1_leaderboard_container = ft.Container(
            content=self.f1_leaderboard_column,
            padding=20,
            expand=True,
        )
        return self.f1_leaderboard_container

    def format_lap_time(self, x):
        """Format lap time in MM:SS.mmm format"""
        if isinstance(x, (int, float)) and not isnan(x) and x > 0:
            mins = int(x // 60)
            secs = int(x % 60)
            millis = int((x % 1) * 1000)
            return f"{mins:02d}:{secs:02d}.{millis:03d}"
        return ""

    def update_f1_leaderboard(self):
        """Update F1 leaderboard with current data"""
        if not self.f1_event or not self.f1_leaderboard_column:
            return

        try:
            # Get leaderboard data
            leaderboard = self.f1_event.leaderboard_df.copy()

            if leaderboard.empty:
                # Update controls list instead of replacing content
                self.f1_leaderboard_column.controls = [
                    ft.Text(
                        "Waiting for lap data...",
                        size=14,
                        color=ft.Colors.GREY,
                    )
                ]
                self.f1_leaderboard_column.update()
                return

            # Parse session info
            subsession_name = self.f1_event.subsession_name
            time_remaining = self.f1_event.subsession_time_remaining

            # Determine driver at risk
            all_sessions = [*self.f1_elim_sessions, self.f1_final_session]
            advancing_cars_list = [s["advancing_cars"] for s in all_sessions]

            driver_at_risk_idx = None
            if subsession_name and subsession_name.startswith("Q"):
                try:
                    subsession_index = int(subsession_name.split("Q")[1]) - 1
                    if 0 <= subsession_index < len(advancing_cars_list):
                        driver_at_risk = int(advancing_cars_list[subsession_index])
                        if 0 < driver_at_risk <= len(leaderboard):
                            driver_at_risk_idx = driver_at_risk - 1
                except:
                    pass

            # Build header
            header = ft.Row(
                [
                    ft.Text(
                        f"⏱️ {time_remaining}",
                        size=24,
                        weight=ft.FontWeight.BOLD,
                        color=ft.Colors.CYAN,
                    ),
                    ft.Text(
                        f"🏁 {subsession_name}",
                        size=24,
                        weight=ft.FontWeight.BOLD,
                        color=ft.Colors.AMBER,
                    ),
                ],
                spacing=40,
                alignment=ft.MainAxisAlignment.CENTER,
            )

            # Build leaderboard table
            rows = []

            # Header row
            header_cells = [
                ft.Container(
                    ft.Text("Pos", weight=ft.FontWeight.BOLD, size=14),
                    padding=8,
                    width=60,
                    alignment=ft.alignment.center,
                ),
                ft.Container(
                    ft.Text("Car #", weight=ft.FontWeight.BOLD, size=14),
                    padding=8,
                    width=80,
                    alignment=ft.alignment.center,
                ),
                ft.Container(
                    ft.Text("Driver", weight=ft.FontWeight.BOLD, size=14),
                    padding=8,
                    width=200,
                    alignment=ft.alignment.center,
                ),
            ]

            # Add column headers for each session (skip 'Driver' column in iteration)
            for col in leaderboard.columns:
                if col == "Driver":
                    continue
                header_cells.append(
                    ft.Container(
                        ft.Text(col, weight=ft.FontWeight.BOLD, size=14),
                        padding=8,
                        width=150,
                        alignment=ft.alignment.center,
                    )
                )

            rows.append(
                ft.Container(
                    ft.Row(header_cells, spacing=2),
                    bgcolor=ft.Colors.with_opacity(0.3, ft.Colors.BLUE),
                    border_radius=3,
                )
            )

            # Data rows
            for idx, (car_num, row_data) in enumerate(leaderboard.iterrows()):
                cells = []

                # Position
                cells.append(
                    ft.Container(
                        ft.Text(str(idx + 1), size=14, weight=ft.FontWeight.BOLD),
                        padding=8,
                        width=60,
                        alignment=ft.alignment.center,
                    )
                )

                # Car number
                cells.append(
                    ft.Container(
                        ft.Text(str(car_num), size=14, weight=ft.FontWeight.BOLD),
                        padding=8,
                        width=80,
                        alignment=ft.alignment.center,
                    )
                )

                # Driver name
                driver_name = row_data.get("Driver", "Unknown")
                cells.append(
                    ft.Container(
                        ft.Text(str(driver_name), size=14, weight=ft.FontWeight.W_500),
                        padding=8,
                        width=200,
                        alignment=ft.alignment.center_left,
                    )
                )

                # Lap times for each session (skip 'Driver' column)
                for col_idx, col in enumerate(leaderboard.columns):
                    if col == "Driver":
                        continue
                    value = row_data[col]
                    formatted_value = self.format_lap_time(value)

                    # Determine cell color
                    bgcolor = None
                    text_color = ft.Colors.WHITE

                    if formatted_value:
                        # Check if this is personal best (fastest in this row)
                        row_times = [
                            row_data[c]
                            for c in leaderboard.columns
                            if isinstance(row_data[c], (int, float))
                            and not isnan(row_data[c])
                            and row_data[c] > 0
                        ]
                        if row_times and value == min(row_times):
                            bgcolor = ft.Colors.with_opacity(0.3, ft.Colors.YELLOW)

                        # Check if this is session best (fastest in this column)
                        col_times = [
                            leaderboard.loc[r, col]
                            for r in leaderboard.index
                            if isinstance(leaderboard.loc[r, col], (int, float))
                            and not isnan(leaderboard.loc[r, col])
                            and leaderboard.loc[r, col] > 0
                        ]
                        if col_times and value == min(col_times):
                            bgcolor = ft.Colors.with_opacity(0.4, ft.Colors.GREEN)

                        # Check if this is overall best
                        all_times = []
                        for c in leaderboard.columns:
                            for r in leaderboard.index:
                                v = leaderboard.loc[r, c]
                                if (
                                    isinstance(v, (int, float))
                                    and not isnan(v)
                                    and v > 0
                                ):
                                    all_times.append(v)
                        if all_times and value == min(all_times):
                            bgcolor = ft.Colors.with_opacity(0.5, ft.Colors.PURPLE)

                    cells.append(
                        ft.Container(
                            ft.Text(
                                formatted_value,
                                size=14,
                                color=text_color,
                                weight=ft.FontWeight.W_500,
                            ),
                            padding=8,
                            width=150,
                            bgcolor=bgcolor,
                            alignment=ft.alignment.center,
                        )
                    )

                # Orange highlight for driver at risk
                row_bgcolor = None
                if driver_at_risk_idx is not None and idx == driver_at_risk_idx:
                    row_bgcolor = ft.Colors.with_opacity(0.3, ft.Colors.ORANGE)

                # Grey highlight for waiting/eliminated drivers
                if self.f1_event.waiting_on and car_num in self.f1_event.waiting_on:
                    row_bgcolor = ft.Colors.with_opacity(0.3, ft.Colors.GREY)

                rows.append(
                    ft.Container(
                        ft.Row(cells, spacing=2),
                        bgcolor=row_bgcolor,
                        border_radius=3,
                        padding=2,
                    )
                )

            # Update controls list instead of replacing content (preserves scroll)
            self.f1_leaderboard_column.controls = [
                header,
                ft.Divider(height=10),
                ft.Column(rows, spacing=2, scroll=ft.ScrollMode.AUTO),
            ]
            self.f1_leaderboard_column.update()

        except Exception as ex:
            # Silently handle errors during updates
            pass

    async def f1_refresh_task(self):
        """Background task to refresh F1 leaderboard"""
        while self.f1_event and self.f1_subprocess_manager:
            self.update_f1_leaderboard()
            await asyncio.sleep(0.5)  # Update twice per second

    def start_f1_qualifying(self, e):
        """Start F1 Qualifying event"""
        all_sessions = [*self.f1_elim_sessions, self.f1_final_session]
        session_lengths = ", ".join([s["duration"] for s in all_sessions])
        advancing_cars = ", ".join([s["advancing_cars"] for s in all_sessions])

        self.f1_event = F1QualifyingEvent(
            session_lengths, advancing_cars, wait_between_sessions=self.f1_wait_between
        )
        self.f1_subprocess_manager = SubprocessManager([self.f1_event.run])
        self.f1_subprocess_manager.start()

        # Start refresh task
        self.page.run_task(self.f1_refresh_task)

        self.page.show_snack_bar(
            ft.SnackBar(
                content=ft.Text("F1 Qualifying Started!"), bgcolor=ft.Colors.GREEN
            )
        )
        self.page.update()

    def stop_f1_qualifying(self, e):
        """Stop F1 Qualifying event"""
        if self.f1_subprocess_manager:
            self.f1_subprocess_manager.stop()
            self.f1_subprocess_manager = None

        self.f1_event = None

        # Clear leaderboard
        if self.f1_leaderboard_column:
            self.f1_leaderboard_column.controls = [
                ft.Text(
                    "Qualifying stopped",
                    size=14,
                    color=ft.Colors.GREY,
                )
            ]
            self.f1_leaderboard_column.update()

        self.page.show_snack_bar(
            ft.SnackBar(
                content=ft.Text("F1 Qualifying Stopped!"), bgcolor=ft.Colors.RED
            )
        )
        self.page.update()

    def close_f1_dialog(self, e):
        """Close F1 Qualifying dialog"""
        if self.f1_dialog:
            self.f1_dialog.open = False
            self.page.update()

    def open_beer_goggles(self, e):
        """Open Beer Goggles SDK viewer dialog"""
        self.goggles_dialog = ft.AlertDialog(
            modal=False,  # Allow interaction with other windows
            title=ft.Text("Beer Goggles SDK Viewer"),
            content=self.build_beer_goggles_content(),
            actions=[ft.TextButton("Close", on_click=self.close_goggles_dialog)],
        )
        self.page.overlay.append(self.goggles_dialog)
        self.goggles_dialog.open = True
        self.page.update()

    def build_beer_goggles_content(self):
        """Build the Beer Goggles SDK viewer UI"""
        self.goggles_connection_status = ft.Text(
            "Disconnected",
            color=ft.Colors.RED,
            size=16,
            weight=ft.FontWeight.BOLD,
        )

        def connect_goggles(e):
            self.goggle_event = BaseEvent()
            self.goggles_connection_status.value = "Connected"
            self.goggles_connection_status.color = ft.Colors.GREEN
            self.goggles_connection_status.update()

            # Build initial telemetry tabs structure (only once)
            self.build_initial_goggles_tabs()

            # Start refresh task
            self.page.run_task(self.goggles_refresh_task)

            self.page.show_snack_bar(
                ft.SnackBar(
                    content=ft.Text("Connected to iRacing SDK"), bgcolor=ft.Colors.GREEN
                )
            )

        def disconnect_goggles(e):
            self.goggle_event = None
            self.goggles_connection_status.value = "Disconnected"
            self.goggles_connection_status.color = ft.Colors.RED
            self.goggles_connection_status.update()

            # Clear telemetry display
            if hasattr(self, "goggles_telemetry_display"):
                self.goggles_telemetry_display.content = ft.Column(
                    [
                        ft.Text(
                            "Connect to iRacing to view telemetry data",
                            size=14,
                            color=ft.Colors.GREY,
                        ),
                    ],
                    scroll=ft.ScrollMode.AUTO,
                )
                self.goggles_tabs_control = None
                self.goggles_telemetry_display.update()

            self.page.show_snack_bar(
                ft.SnackBar(
                    content=ft.Text("Disconnected from iRacing SDK"),
                    bgcolor=ft.Colors.RED,
                )
            )

        self.goggles_telemetry_display = ft.Container(
            content=ft.Column(
                [
                    ft.Text(
                        "Connect to iRacing to view telemetry data",
                        size=14,
                        color=ft.Colors.GREY,
                    ),
                ],
                scroll=ft.ScrollMode.AUTO,
            ),
            padding=10,
            border=ft.border.all(1, ft.Colors.GREY),
            border_radius=5,
            height=500,
        )

        controls = ft.Column(
            [
                ft.Row(
                    [
                        ft.ElevatedButton(
                            "Connect",
                            icon=ft.Icons.LINK,
                            on_click=connect_goggles,
                            style=ft.ButtonStyle(
                                bgcolor=ft.Colors.GREEN,
                                color=ft.Colors.WHITE,
                            ),
                        ),
                        ft.ElevatedButton(
                            "Disconnect",
                            icon=ft.Icons.LINK_OFF,
                            on_click=disconnect_goggles,
                            style=ft.ButtonStyle(
                                bgcolor=ft.Colors.RED,
                                color=ft.Colors.WHITE,
                            ),
                        ),
                        self.goggles_connection_status,
                    ],
                    spacing=10,
                ),
                ft.Divider(),
                self.goggles_telemetry_display,
            ],
            width=1100,
            height=700,
            scroll=ft.ScrollMode.AUTO,
        )

        return controls

    def build_telemetry_section(self, section_name, fields):
        """Build a telemetry section with all fields"""
        if not self.goggle_event:
            return ft.Column([ft.Text("Not connected", color=ft.Colors.GREY)])

        controls = []
        for field in fields:
            try:
                # Use bracket notation to access iRSDK fields
                value = self.goggle_event.sdk[field]
                if isinstance(value, list):
                    value_str = str(value)
                else:
                    value_str = str(value)

                controls.append(
                    ft.Container(
                        ft.Row(
                            [
                                ft.Text(
                                    field + ":",
                                    size=11,
                                    weight=ft.FontWeight.BOLD,
                                    width=250,
                                ),
                                ft.Text(value_str, size=11, color=ft.Colors.CYAN),
                            ],
                            spacing=10,
                        ),
                        padding=ft.padding.symmetric(vertical=2, horizontal=5),
                    )
                )
            except Exception as ex:
                # Field not available, skip it
                pass

        # Create a container to hold these controls (for updating later)
        container = ft.Column(controls, scroll=ft.ScrollMode.AUTO, spacing=1)
        return container

    def build_initial_goggles_tabs(self):
        """Build the initial Tabs structure (called once on connect)"""
        if not self.goggle_event or not hasattr(self, "goggles_telemetry_display"):
            return

        # Clear previous tab contents
        self.goggles_tab_contents = {}

        # Define all field sections
        global_field_sections = {
            "Session": [
                "SessionTime",
                "SessionTick",
                "SessionNum",
                "SessionState",
                "SessionUniqueID",
                "SessionFlags",
                "SessionTimeRemain",
                "SessionLapsRemain",
                "SessionLapsRemainEx",
                "SessionTimeTotal",
                "SessionLapsTotal",
                "SessionJokerLapsRemain",
                "SessionOnJokerLap",
                "SessionTimeOfDay",
                "PaceMode",
                "TrackTemp",
                "TrackTempCrew",
                "AirTemp",
                "TrackWetness",
                "Skies",
                "AirDensity",
                "AirPressure",
                "WindVel",
                "WindDir",
                "RelativeHumidity",
                "FogLevel",
                "Precipitation",
                "SolarAltitude",
                "SolarAzimuth",
                "WeatherDeclaredWet",
            ],
            "Player Car": [
                "PlayerCarPosition",
                "PlayerCarClassPosition",
                "PlayerCarClass",
                "PlayerTrackSurface",
                "PlayerTrackSurfaceMaterial",
                "PlayerCarIdx",
                "PlayerCarTeamIncidentCount",
                "PlayerCarMyIncidentCount",
                "PlayerCarDriverIncidentCount",
                "PlayerCarWeightPenalty",
                "PlayerCarPowerAdjust",
                "PlayerCarDryTireSetLimit",
                "PlayerCarTowTime",
                "PlayerCarInPitStall",
                "PlayerCarPitSvStatus",
                "PlayerTireCompound",
                "PlayerFastRepairsUsed",
                "OnPitRoad",
                "SteeringWheelAngle",
                "Throttle",
                "Brake",
                "Clutch",
                "Gear",
                "RPM",
                "PlayerCarSLFirstRPM",
                "PlayerCarSLShiftRPM",
                "PlayerCarSLLastRPM",
                "PlayerCarSLBlinkRPM",
                "Lap",
                "LapCompleted",
                "LapDist",
                "LapDistPct",
                "RaceLaps",
                "LapBestLap",
                "LapBestLapTime",
                "LapLastLapTime",
                "LapCurrentLapTime",
                "Speed",
                "IsOnTrackCar",
                "IsInGarage",
            ],
            "Telemetry": [
                "RFcoldPressure",
                "RFtempCL",
                "RFtempCM",
                "RFtempCR",
                "RFwearL",
                "RFwearM",
                "RFwearR",
                "LFcoldPressure",
                "LFtempCL",
                "LFtempCM",
                "LFtempCR",
                "LFwearL",
                "LFwearM",
                "LFwearR",
                "RRcoldPressure",
                "RRtempCL",
                "RRtempCM",
                "RRtempCR",
                "RRwearL",
                "RRwearM",
                "RRwearR",
                "LRcoldPressure",
                "LRtempCL",
                "LRtempCM",
                "LRtempCR",
                "LRwearL",
                "LRwearM",
                "LRwearR",
                "FuelUsePerHour",
                "Voltage",
                "WaterTemp",
                "WaterLevel",
                "FuelLevel",
                "FuelLevelPct",
                "OilTemp",
                "OilPress",
                "OilLevel",
                "ManifoldPress",
            ],
            "Pits": [
                "PitRepairLeft",
                "PitOptRepairLeft",
                "PitstopActive",
                "FastRepairUsed",
                "FastRepairAvailable",
                "LFTiresUsed",
                "RFTiresUsed",
                "LRTiresUsed",
                "RRTiresUsed",
                "TireSetsUsed",
                "LFTiresAvailable",
                "RFTiresAvailable",
                "LRTiresAvailable",
                "RRTiresAvailable",
                "TireSetsAvailable",
                "PitSvFlags",
                "PitSvLFP",
                "PitSvRFP",
                "PitSvLRP",
                "PitSvRRP",
                "PitSvFuel",
                "PitSvTireCompound",
            ],
            "Audio": [
                "RadioTransmitCarIdx",
                "RadioTransmitRadioIdx",
                "RadioTransmitFrequencyIdx",
                "TireLF_RumblePitch",
                "TireRF_RumblePitch",
                "TireLR_RumblePitch",
                "TireRR_RumblePitch",
            ],
            "Performance": [
                "FrameRate",
                "CpuUsageFG",
                "CpuUsageBG",
                "GpuUsage",
                "ChanAvgLatency",
                "ChanLatency",
                "ChanQuality",
                "ChanPartnerQuality",
            ],
            "Replay": [
                "IsReplayPlaying",
                "ReplayFrameNum",
                "ReplayFrameNumEnd",
                "CamCarIdx",
                "CamCameraNumber",
                "CamGroupNumber",
                "ReplayPlaySpeed",
            ],
        }

        # CarIdx fields for the per-car table
        caridx_fields = [
            "CarIdxLap",
            "CarIdxLapCompleted",
            "CarIdxLapDistPct",
            "CarIdxTrackSurface",
            "CarIdxTrackSurfaceMaterial",
            "CarIdxOnPitRoad",
            "CarIdxPosition",
            "CarIdxClassPosition",
            "CarIdxClass",
            "CarIdxF2Time",
            "CarIdxEstTime",
            "CarIdxLastLapTime",
            "CarIdxBestLapTime",
            "CarIdxBestLapNum",
            "CarIdxTireCompound",
            "CarIdxQualTireCompound",
            "CarIdxQualTireCompoundLocked",
            "CarIdxFastRepairsUsed",
            "CarIdxSessionFlags",
            "CarIdxPaceLine",
            "CarIdxPaceRow",
            "CarIdxPaceFlags",
            "CarIdxSteer",
            "CarIdxRPM",
            "CarIdxGear",
            "CarIdxP2P_Status",
            "CarIdxP2P_Count",
        ]

        # Build tabs (only once)
        tab_list = []
        for section_name, fields in global_field_sections.items():
            tab_content = self.build_telemetry_section(section_name, fields)
            # Store reference to the content column for updates
            self.goggles_tab_contents[section_name] = tab_content
            tab_list.append(ft.Tab(text=section_name, content=tab_content))

        # Build CarIdx table tab
        caridx_tab_content = self.build_caridx_table(caridx_fields)
        self.goggles_tab_contents["Per-Car Data"] = caridx_tab_content
        tab_list.append(ft.Tab(text="Per-Car Data", content=caridx_tab_content))

        # Build Driver Info tab
        driver_info_content = self.build_driver_info_table()
        self.goggles_tab_contents["Driver Info"] = driver_info_content
        tab_list.append(ft.Tab(text="Driver Info", content=driver_info_content))

        def on_tab_change(e):
            """Save selected tab index"""
            self.goggles_selected_tab = e.control.selected_index

        self.goggles_tabs_control = ft.Tabs(
            selected_index=self.goggles_selected_tab,
            animation_duration=300,
            tabs=tab_list,
            expand=True,
            scrollable=True,
            on_change=on_tab_change,
        )

        self.goggles_telemetry_display.content = self.goggles_tabs_control
        self.goggles_telemetry_display.update()

    def build_driver_info_table(self):
        """Build the Driver Info table showing static driver information"""
        # Create DataTable with driver info columns
        columns = [
            ft.DataColumn(ft.Text("CarIdx", weight=ft.FontWeight.BOLD, size=11)),
            ft.DataColumn(ft.Text("Driver Name", weight=ft.FontWeight.BOLD, size=11)),
            ft.DataColumn(ft.Text("Car Number", weight=ft.FontWeight.BOLD, size=11)),
            ft.DataColumn(ft.Text("Team Name", weight=ft.FontWeight.BOLD, size=11)),
            ft.DataColumn(ft.Text("Car Name", weight=ft.FontWeight.BOLD, size=11)),
            ft.DataColumn(ft.Text("Car Class", weight=ft.FontWeight.BOLD, size=11)),
            ft.DataColumn(ft.Text("iRating", weight=ft.FontWeight.BOLD, size=11)),
            ft.DataColumn(ft.Text("License", weight=ft.FontWeight.BOLD, size=11)),
            ft.DataColumn(ft.Text("User ID", weight=ft.FontWeight.BOLD, size=11)),
        ]

        self.goggles_driver_info_datatable = ft.DataTable(
            columns=columns,
            rows=[],
            border=ft.border.all(1, ft.Colors.GREY_700),
            border_radius=5,
            vertical_lines=ft.border.BorderSide(1, ft.Colors.GREY_800),
            horizontal_lines=ft.border.BorderSide(1, ft.Colors.GREY_800),
            heading_row_color=ft.Colors.with_opacity(0.3, ft.Colors.BLUE),
            heading_row_height=35,
            data_row_max_height=30,
            data_row_min_height=25,
            column_spacing=15,
        )

        # Populate driver info on initial build
        self.update_driver_info_table()

        return ft.Column(
            [
                ft.Text(
                    "Driver Information (Static Data)",
                    size=16,
                    weight=ft.FontWeight.BOLD,
                ),
                ft.Row(
                    [
                        ft.Container(
                            content=self.goggles_driver_info_datatable,
                            border=ft.border.all(1, ft.Colors.GREY_600),
                            border_radius=5,
                            padding=10,
                        ),
                    ],
                    scroll=ft.ScrollMode.ALWAYS,
                    expand=True,
                ),
            ],
            scroll=ft.ScrollMode.AUTO,
            spacing=10,
            expand=True,
        )

    def update_driver_info_table(self):
        """Update the driver info table with static driver data"""
        if not self.goggle_event or not hasattr(self, "goggles_driver_info_datatable"):
            return

        try:
            driver_info = self.goggle_event.sdk["DriverInfo"]
            if not driver_info or "Drivers" not in driver_info:
                return

            drivers = driver_info["Drivers"]
            if not isinstance(drivers, list):
                return

            rows = []
            for idx, driver in enumerate(drivers):
                if not isinstance(driver, dict):
                    continue

                cells = [
                    ft.DataCell(ft.Text(str(driver.get("CarIdx", idx)), size=10)),
                    ft.DataCell(ft.Text(str(driver.get("UserName", "N/A")), size=10)),
                    ft.DataCell(ft.Text(str(driver.get("CarNumber", "N/A")), size=10)),
                    ft.DataCell(ft.Text(str(driver.get("TeamName", "N/A")), size=10)),
                    ft.DataCell(
                        ft.Text(str(driver.get("CarScreenName", "N/A")), size=10)
                    ),
                    ft.DataCell(
                        ft.Text(str(driver.get("CarClassShortName", "N/A")), size=10)
                    ),
                    ft.DataCell(ft.Text(str(driver.get("IRating", "N/A")), size=10)),
                    ft.DataCell(ft.Text(str(driver.get("LicString", "N/A")), size=10)),
                    ft.DataCell(ft.Text(str(driver.get("UserID", "N/A")), size=10)),
                ]
                rows.append(ft.DataRow(cells=cells))

            self.goggles_driver_info_datatable.rows = rows
            self.goggles_driver_info_datatable.update()
        except Exception as e:
            print(f"Driver info table update error: {e}")
            pass

    def build_caridx_table(self, caridx_fields):
        """Build the CarIdx per-car data table"""
        # Create DataTable
        columns = [
            ft.DataColumn(ft.Text("Car #", weight=ft.FontWeight.BOLD, size=12)),
            ft.DataColumn(ft.Text("Driver", weight=ft.FontWeight.BOLD, size=11)),
        ]

        # Add columns for each field (remove 'CarIdx' prefix for display)
        for field in caridx_fields:
            display_name = field.replace("CarIdx", "")
            columns.append(ft.DataColumn(ft.Text(display_name, size=10)))

        self.goggles_caridx_datatable = ft.DataTable(
            columns=columns,
            rows=[],
            border=ft.border.all(1, ft.Colors.GREY_700),
            border_radius=5,
            vertical_lines=ft.border.BorderSide(1, ft.Colors.GREY_800),
            horizontal_lines=ft.border.BorderSide(1, ft.Colors.GREY_800),
            heading_row_color=ft.Colors.with_opacity(0.3, ft.Colors.BLUE),
            heading_row_height=35,
            data_row_max_height=30,
            data_row_min_height=25,
            column_spacing=10,
        )

        return ft.Column(
            [
                ft.Text(
                    "Per-Car Data (All CarIdx Fields)",
                    size=16,
                    weight=ft.FontWeight.BOLD,
                ),
                ft.Row(
                    [
                        ft.Container(
                            content=self.goggles_caridx_datatable,
                            border=ft.border.all(1, ft.Colors.GREY_600),
                            border_radius=5,
                            padding=10,
                        ),
                    ],
                    scroll=ft.ScrollMode.ALWAYS,
                    expand=True,
                ),
            ],
            scroll=ft.ScrollMode.AUTO,
            spacing=10,
            expand=True,
        )

    def update_goggles_display(self):
        """Update Beer Goggles telemetry display - only updates tab content"""
        if not self.goggle_event or not self.goggles_tabs_control:
            return

        try:
            # Define all field sections (same order as initial build)
            global_field_sections = {
                "Session": [
                    "SessionTime",
                    "SessionTick",
                    "SessionNum",
                    "SessionState",
                    "SessionUniqueID",
                    "SessionFlags",
                    "SessionTimeRemain",
                    "SessionLapsRemain",
                    "SessionLapsRemainEx",
                    "SessionTimeTotal",
                    "SessionLapsTotal",
                    "SessionJokerLapsRemain",
                    "SessionOnJokerLap",
                    "SessionTimeOfDay",
                    "PaceMode",
                    "TrackTemp",
                    "TrackTempCrew",
                    "AirTemp",
                    "TrackWetness",
                    "Skies",
                    "AirDensity",
                    "AirPressure",
                    "WindVel",
                    "WindDir",
                    "RelativeHumidity",
                    "FogLevel",
                    "Precipitation",
                    "SolarAltitude",
                    "SolarAzimuth",
                    "WeatherDeclaredWet",
                ],
                "Player Car": [
                    "PlayerCarPosition",
                    "PlayerCarClassPosition",
                    "PlayerCarClass",
                    "PlayerTrackSurface",
                    "PlayerTrackSurfaceMaterial",
                    "PlayerCarIdx",
                    "PlayerCarTeamIncidentCount",
                    "PlayerCarMyIncidentCount",
                    "PlayerCarDriverIncidentCount",
                    "PlayerCarWeightPenalty",
                    "PlayerCarPowerAdjust",
                    "PlayerCarDryTireSetLimit",
                    "PlayerCarTowTime",
                    "PlayerCarInPitStall",
                    "PlayerCarPitSvStatus",
                    "PlayerTireCompound",
                    "PlayerFastRepairsUsed",
                    "OnPitRoad",
                    "SteeringWheelAngle",
                    "Throttle",
                    "Brake",
                    "Clutch",
                    "Gear",
                    "RPM",
                    "PlayerCarSLFirstRPM",
                    "PlayerCarSLShiftRPM",
                    "PlayerCarSLLastRPM",
                    "PlayerCarSLBlinkRPM",
                    "Lap",
                    "LapCompleted",
                    "LapDist",
                    "LapDistPct",
                    "RaceLaps",
                    "LapBestLap",
                    "LapBestLapTime",
                    "LapLastLapTime",
                    "LapCurrentLapTime",
                    "Speed",
                    "IsOnTrackCar",
                    "IsInGarage",
                ],
                "Telemetry": [
                    "RFcoldPressure",
                    "RFtempCL",
                    "RFtempCM",
                    "RFtempCR",
                    "RFwearL",
                    "RFwearM",
                    "RFwearR",
                    "LFcoldPressure",
                    "LFtempCL",
                    "LFtempCM",
                    "LFtempCR",
                    "LFwearL",
                    "LFwearM",
                    "LFwearR",
                    "RRcoldPressure",
                    "RRtempCL",
                    "RRtempCM",
                    "RRtempCR",
                    "RRwearL",
                    "RRwearM",
                    "RRwearR",
                    "LRcoldPressure",
                    "LRtempCL",
                    "LRtempCM",
                    "LRtempCR",
                    "LRwearL",
                    "LRwearM",
                    "LRwearR",
                    "FuelUsePerHour",
                    "Voltage",
                    "WaterTemp",
                    "WaterLevel",
                    "FuelLevel",
                    "FuelLevelPct",
                    "OilTemp",
                    "OilPress",
                    "OilLevel",
                    "ManifoldPress",
                ],
                "Pits": [
                    "PitRepairLeft",
                    "PitOptRepairLeft",
                    "PitstopActive",
                    "FastRepairUsed",
                    "FastRepairAvailable",
                    "LFTiresUsed",
                    "RFTiresUsed",
                    "LRTiresUsed",
                    "RRTiresUsed",
                    "TireSetsUsed",
                    "LFTiresAvailable",
                    "RFTiresAvailable",
                    "LRTiresAvailable",
                    "RRTiresAvailable",
                    "TireSetsAvailable",
                    "PitSvFlags",
                    "PitSvLFP",
                    "PitSvRFP",
                    "PitSvLRP",
                    "PitSvRRP",
                    "PitSvFuel",
                    "PitSvTireCompound",
                ],
                "Audio": [
                    "RadioTransmitCarIdx",
                    "RadioTransmitRadioIdx",
                    "RadioTransmitFrequencyIdx",
                    "TireLF_RumblePitch",
                    "TireRF_RumblePitch",
                    "TireLR_RumblePitch",
                    "TireRR_RumblePitch",
                ],
                "Performance": [
                    "FrameRate",
                    "CpuUsageFG",
                    "CpuUsageBG",
                    "GpuUsage",
                    "ChanAvgLatency",
                    "ChanLatency",
                    "ChanQuality",
                    "ChanPartnerQuality",
                ],
                "Replay": [
                    "IsReplayPlaying",
                    "ReplayFrameNum",
                    "ReplayFrameNumEnd",
                    "CamCarIdx",
                    "CamCameraNumber",
                    "CamGroupNumber",
                    "ReplayPlaySpeed",
                ],
            }

            # CarIdx fields for the per-car table
            caridx_fields = [
                "CarIdxLap",
                "CarIdxLapCompleted",
                "CarIdxLapDistPct",
                "CarIdxTrackSurface",
                "CarIdxTrackSurfaceMaterial",
                "CarIdxOnPitRoad",
                "CarIdxPosition",
                "CarIdxClassPosition",
                "CarIdxClass",
                "CarIdxF2Time",
                "CarIdxEstTime",
                "CarIdxLastLapTime",
                "CarIdxBestLapTime",
                "CarIdxBestLapNum",
                "CarIdxTireCompound",
                "CarIdxQualTireCompound",
                "CarIdxQualTireCompoundLocked",
                "CarIdxFastRepairsUsed",
                "CarIdxSessionFlags",
                "CarIdxPaceLine",
                "CarIdxPaceRow",
                "CarIdxPaceFlags",
                "CarIdxSteer",
                "CarIdxRPM",
                "CarIdxGear",
                "CarIdxP2P_Status",
                "CarIdxP2P_Count",
            ]

            # Update each telemetry tab's content by updating the column's controls
            for section_name, fields in global_field_sections.items():
                if section_name in self.goggles_tab_contents:
                    tab_column = self.goggles_tab_contents[section_name]
                    # Build new controls list
                    new_controls = []
                    for field in fields:
                        try:
                            value = self.goggle_event.sdk[field]
                            if isinstance(value, list):
                                new_controls.append(
                                    ft.Text(
                                        f"{field}: {value}",
                                        size=11,
                                        selectable=True,
                                    )
                                )
                            else:
                                new_controls.append(
                                    ft.Container(
                                        ft.Row(
                                            [
                                                ft.Text(
                                                    field,
                                                    size=11,
                                                    weight=ft.FontWeight.BOLD,
                                                    width=200,
                                                ),
                                                ft.Text(
                                                    str(value),
                                                    size=11,
                                                    selectable=True,
                                                ),
                                            ]
                                        ),
                                        padding=2,
                                    )
                                )
                        except:
                            pass
                    # Update the column's controls (preserves scroll)
                    tab_column.controls = new_controls
                    tab_column.update()

            # Update the CarIdx table
            if hasattr(self, "goggles_caridx_datatable"):
                rows = []
                try:
                    # Get the number of cars - use bracket notation, not .get()
                    caridx_lap = self.goggle_event.sdk["CarIdxLap"]
                    if isinstance(caridx_lap, list):
                        num_cars = len(caridx_lap)
                    else:
                        num_cars = 0

                    # Get driver info for name lookup
                    driver_names = {}
                    try:
                        driver_info = self.goggle_event.sdk["DriverInfo"]
                        if driver_info and "Drivers" in driver_info:
                            drivers = driver_info["Drivers"]
                            if isinstance(drivers, list):
                                for driver in drivers:
                                    if isinstance(driver, dict):
                                        car_idx_key = driver.get("CarIdx")
                                        driver_name = driver.get("UserName", "Unknown")
                                        if car_idx_key is not None:
                                            driver_names[car_idx_key] = driver_name
                    except:
                        pass

                    for car_idx in range(num_cars):
                        cells = [
                            ft.DataCell(ft.Text(str(car_idx), size=10)),
                            ft.DataCell(
                                ft.Text(driver_names.get(car_idx, "N/A"), size=9)
                            ),
                        ]

                        for field in caridx_fields:
                            try:
                                value = self.goggle_event.sdk[field][car_idx]
                                # Format the value
                                if isinstance(value, float):
                                    if value > 1000:
                                        display_value = f"{value:.1f}"
                                    else:
                                        display_value = f"{value:.2f}"
                                else:
                                    display_value = str(value)
                                cells.append(
                                    ft.DataCell(ft.Text(display_value, size=9))
                                )
                            except:
                                cells.append(ft.DataCell(ft.Text("-", size=9)))

                        rows.append(ft.DataRow(cells=cells))

                    self.goggles_caridx_datatable.rows = rows
                    self.goggles_caridx_datatable.update()
                except Exception as e:
                    # Debug: print the error
                    print(f"CarIdx table update error: {e}")
                    pass

        except Exception as ex:
            pass

    async def goggles_refresh_task(self):
        """Background task to refresh Beer Goggles telemetry"""
        while self.goggle_event:
            self.update_goggles_display()
            await asyncio.sleep(0.25)  # Update 4 times per second

    def close_goggles_dialog(self, e):
        """Close Beer Goggles dialog"""
        if self.goggles_dialog:
            self.goggles_dialog.open = False
            self.page.update()


def main(page: ft.Page):
    app = RaceControlApp()
    app.main(page)


if __name__ == "__main__":
    ft.app(target=main)
