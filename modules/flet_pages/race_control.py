import json
import os
from typing import Dict, Optional

import flet as ft

from modules import SubprocessManager, events, subprocess_manager


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
        self.incident_caution_config = {}
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
        self.text_consumer_enabled = False
        self.audio_consumer_enabled = False

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

    def main(self, page: ft.Page):
        page.window.prevent_close = True
        self.page = page
        self.page.window.height = 1150
        self.page.window.width = 1400
        page.title = "Better Caution Bot - Race Control"
        page.theme_mode = ft.ThemeMode.DARK
        page.padding = 20

        # Set window close handler to stop events
        page.window.on_event = self.on_window_event

        # Build the UI
        page.add(
            self.build_header(),
            ft.Divider(height=20),
            ft.Row(
                [
                    self.build_main_tabs(),
                    ft.Container(width=20),
                    self.build_consumer_section(),
                ],
                vertical_alignment=ft.CrossAxisAlignment.START,
            ),
        )

    def build_header(self):
        """Build the header with start/stop buttons and status indicator"""
        self.status_indicator = ft.Container(
            content=ft.Row(
                [
                    ft.Icon(ft.Icons.CIRCLE, color=ft.Colors.RED, size=16),
                    ft.Text("Stopped", size=16, weight=ft.FontWeight.BOLD),
                ],
                spacing=5,
            ),
            padding=10,
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

        return ft.Container(
            content=ft.Row(
                [
                    self.start_button,
                    self.stop_button,
                    self.status_indicator,
                    ft.Container(expand=True),  # Spacer
                    save_button,
                    load_button,
                ],
                alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
            ),
            padding=10,
        )

    def build_main_tabs(self):
        """Build the main tab section for different event types"""
        self.tabs_control = ft.Tabs(
            selected_index=0,
            animation_duration=300,
            tabs=[
                ft.Tab(
                    text="Random Cautions",
                    icon=ft.Container(
                        content=ft.Icon(ft.Icons.WARNING_AMBER),
                        bgcolor=ft.Colors.GREEN
                        if self.random_cautions_enabled
                        else None,
                        border_radius=5,
                        padding=5,
                    ),
                    content=self.build_random_cautions_tab(),
                ),
                ft.Tab(
                    text="Random Code69s",
                    icon=ft.Container(
                        content=ft.Icon(ft.Icons.SPEED),
                        bgcolor=ft.Colors.GREEN
                        if self.random_code69s_enabled
                        else None,
                        border_radius=5,
                        padding=5,
                    ),
                    content=self.build_random_code69s_tab(),
                ),
                ft.Tab(
                    text="Incident Cautions",
                    icon=ft.Container(
                        content=ft.Icon(ft.Icons.CAR_CRASH),
                        bgcolor=ft.Colors.GREEN
                        if self.incident_cautions_enabled
                        else None,
                        border_radius=5,
                        padding=5,
                    ),
                    content=self.build_incident_cautions_tab(),
                ),
                ft.Tab(
                    text="Incident Penalties",
                    icon=ft.Container(
                        content=ft.Icon(ft.Icons.GAVEL),
                        bgcolor=ft.Colors.GREEN
                        if self.incident_penalties_enabled
                        else None,
                        border_radius=5,
                        padding=5,
                    ),
                    content=self.build_incident_penalties_tab(),
                ),
                ft.Tab(
                    text="Scheduled Messages",
                    icon=ft.Container(
                        content=ft.Icon(ft.Icons.MESSAGE),
                        bgcolor=ft.Colors.GREEN
                        if self.scheduled_messages_enabled
                        else None,
                        border_radius=5,
                        padding=5,
                    ),
                    content=self.build_scheduled_messages_tab(),
                ),
                ft.Tab(
                    text="Collision Penalty",
                    icon=ft.Container(
                        content=ft.Icon(ft.Icons.CAR_REPAIR),
                        bgcolor=ft.Colors.GREEN
                        if self.collision_penalty_enabled
                        else None,
                        border_radius=5,
                        padding=5,
                    ),
                    content=self.build_collision_penalty_tab(),
                ),
                ft.Tab(
                    text="Clear Black Flag",
                    icon=ft.Container(
                        content=ft.Icon(ft.Icons.FLAG),
                        bgcolor=ft.Colors.GREEN
                        if self.clear_black_flag_enabled
                        else None,
                        border_radius=5,
                        padding=5,
                    ),
                    content=self.build_clear_black_flag_tab(),
                ),
                ft.Tab(
                    text="Scheduled Black Flag",
                    icon=ft.Container(
                        content=ft.Icon(ft.Icons.SPORTS_SCORE),
                        bgcolor=ft.Colors.GREEN
                        if self.scheduled_black_flag_enabled
                        else None,
                        border_radius=5,
                        padding=5,
                    ),
                    content=self.build_scheduled_black_flag_tab(),
                ),
                ft.Tab(
                    text="Gap to Leader",
                    icon=ft.Container(
                        content=ft.Icon(ft.Icons.TIMER),
                        bgcolor=ft.Colors.GREEN if self.gap_to_leader_enabled else None,
                        border_radius=5,
                        padding=5,
                    ),
                    content=self.build_gap_to_leader_tab(),
                ),
            ],
            expand=1,
        )

        return ft.Container(
            content=self.tabs_control,
            width=900,
            height=900,
            border=ft.border.all(1, ft.Colors.OUTLINE),
            border_radius=5,
            padding=10,
        )

    def update_tab_indicators(self):
        """Update the visual indicators on tab icons"""
        if self.tabs_control and self.page:
            self.tabs_control.tabs[0].icon.bgcolor = (
                ft.Colors.GREEN if self.random_cautions_enabled else None
            )
            self.tabs_control.tabs[1].icon.bgcolor = (
                ft.Colors.GREEN if self.random_code69s_enabled else None
            )
            self.tabs_control.tabs[2].icon.bgcolor = (
                ft.Colors.GREEN if self.incident_cautions_enabled else None
            )
            self.tabs_control.tabs[3].icon.bgcolor = (
                ft.Colors.GREEN if self.incident_penalties_enabled else None
            )
            self.tabs_control.tabs[4].icon.bgcolor = (
                ft.Colors.GREEN if self.scheduled_messages_enabled else None
            )
            self.tabs_control.tabs[5].icon.bgcolor = (
                ft.Colors.GREEN if self.collision_penalty_enabled else None
            )
            self.tabs_control.tabs[6].icon.bgcolor = (
                ft.Colors.GREEN if self.clear_black_flag_enabled else None
            )
            self.tabs_control.tabs[7].icon.bgcolor = (
                ft.Colors.GREEN if self.scheduled_black_flag_enabled else None
            )
            self.tabs_control.tabs[8].icon.bgcolor = (
                ft.Colors.GREEN if self.gap_to_leader_enabled else None
            )
            self.page.update()

    def build_random_cautions_tab(self):
        """Build the Random Cautions tab content"""
        self.random_caution_list = ft.Column(
            scroll=ft.ScrollMode.AUTO, spacing=10, expand=True
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
            "Window Start/End (minutes)"
            if not global_config["use_lap_based"]
            else "Window Start/End (laps)",
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
                                size=20,
                                weight=ft.FontWeight.BOLD,
                            ),
                            ft.Container(expand=True),
                            enable_toggle,
                        ],
                        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                    ),
                    ft.Divider(),
                    lap_based_toggle,
                    ft.Container(height=10),
                    ft.Text(
                        "Global Caution Settings", size=14, weight=ft.FontWeight.BOLD
                    ),
                    ft.Row(
                        [pit_warning, pit_duration, max_laps_behind],
                        wrap=True,
                        spacing=10,
                    ),
                    ft.Row(
                        [wave_around_lap, extend_laps, pre_extend_laps],
                        wrap=True,
                        spacing=10,
                    ),
                    ft.Row(
                        [wave_arounds_check, notify_skip_check, full_sequence_check],
                        wrap=True,
                    ),
                    ft.Divider(),
                    window_label,
                    add_button,
                    ft.Container(height=10),
                    self.random_caution_list,
                ]
            ),
            padding=10,
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
                                    size=16,
                                    weight=ft.FontWeight.BOLD,
                                ),
                                ft.Container(expand=True),
                                remove_button,
                            ]
                        ),
                        ft.Divider(),
                        ft.Row(
                            [window_start, window_end, likelihood],
                            wrap=True,
                            spacing=10,
                        ),
                    ]
                ),
                padding=15,
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
            scroll=ft.ScrollMode.AUTO, spacing=10, expand=True
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
            "Window Start/End (minutes)"
            if not global_config["use_lap_based"]
            else "Window Start/End (laps)",
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
                                spacing=10,
                            ),
                            ft.Row(
                                [
                                    quickie_restart_pos,
                                    end_of_lap_margin,
                                    quickie_invert_check,
                                ],
                                wrap=True,
                                spacing=10,
                            ),
                        ]
                    ),
                    padding=10,
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
                                size=20,
                                weight=ft.FontWeight.BOLD,
                            ),
                            ft.Container(expand=True),
                            enable_toggle,
                        ],
                        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                    ),
                    ft.Divider(),
                    lap_based_toggle,
                    ft.Container(height=10),
                    ft.Text(
                        "Global Code69 Settings", size=14, weight=ft.FontWeight.BOLD
                    ),
                    ft.Row(
                        [max_speed, wet_speed, restart_speed, reminder_freq],
                        wrap=True,
                        spacing=10,
                    ),
                    ft.Row(
                        [class_sep, lanes_form, restart_pos, lane_names],
                        wrap=True,
                        spacing=10,
                    ),
                    ft.Row(
                        [wave_arounds_check, notify_skip_check],
                        wrap=True,
                    ),
                    advanced,
                    ft.Divider(),
                    window_label,
                    add_button,
                    ft.Container(height=10),
                    self.random_code69_list,
                ]
            ),
            padding=10,
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
                                    f"Random Code69 Event #{index + 1}",
                                    size=16,
                                    weight=ft.FontWeight.BOLD,
                                ),
                                ft.Container(expand=True),
                                remove_button,
                            ]
                        ),
                        ft.Divider(),
                        ft.Row(
                            [window_start, window_end, likelihood],
                            wrap=True,
                            spacing=10,
                        ),
                    ]
                ),
                padding=15,
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
            "Active Window (minutes)"
            if not config["use_lap_based"]
            else "Active Window (laps)",
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
                                        size=20,
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
                    ft.Divider(),
                    lap_based_toggle,
                    ft.Container(height=10),
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
                    ft.Row([increase_by], wrap=True, spacing=10),
                    ft.Row([auto_increase_check], wrap=True),
                    ft.Divider(),
                    window_label,
                    ft.Row([window_start, window_end], wrap=True, spacing=10),
                    ft.Divider(),
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
            padding=10,
        )

    def build_incident_penalties_tab(self):
        """Build the Incident Penalties tab content"""
        config = {
            "initial_penalty_incidents": 40,
            "initial_penalty": "d",
            "recurring_peanlty_every_incidents": 15,
            "recurring_penalty": "0",
            "end_recurring_incidents": 55,
            "end_recurring_penalty": "0",
            "sound": False,
        }
        self.incident_penalty_config = config

        def update_config(key, value):
            config[key] = value

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
                                        size=20,
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
                    ft.Divider(),
                    ft.Text("Initial Penalty", size=14, weight=ft.FontWeight.BOLD),
                    ft.Row([initial_incidents, initial_penalty], wrap=True, spacing=10),
                    ft.Divider(),
                    ft.Text("Recurring Penalties", size=14, weight=ft.FontWeight.BOLD),
                    ft.Row(
                        [recurring_incidents, recurring_penalty], wrap=True, spacing=10
                    ),
                    ft.Divider(),
                    ft.Text("Final Penalty", size=14, weight=ft.FontWeight.BOLD),
                    ft.Row([final_incidents, final_penalty], wrap=True, spacing=10),
                    ft.Divider(),
                    ft.Row([sound_check]),
                ],
                scroll=ft.ScrollMode.AUTO,
            ),
            padding=10,
        )

    def build_scheduled_messages_tab(self):
        """Build the Scheduled Messages tab content"""
        self.scheduled_messages_list = ft.Column(
            scroll=ft.ScrollMode.AUTO, spacing=10, expand=True
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
                                        size=20,
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
                    ft.Divider(),
                    add_button,
                    ft.Container(height=10),
                    self.scheduled_messages_list,
                ]
            ),
            padding=10,
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
                                    size=16,
                                    weight=ft.FontWeight.BOLD,
                                ),
                                ft.Container(expand=True),
                                remove_button,
                            ]
                        ),
                        ft.Divider(),
                        event_time,
                        message,
                        ft.Row([race_control_check, broadcast_check], wrap=True),
                    ]
                ),
                padding=15,
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
                                        size=20,
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
                    ft.Divider(),
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
            padding=10,
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
                                        size=20,
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
                    ft.Divider(),
                    ft.Row([interval], wrap=True, spacing=10),
                ],
                scroll=ft.ScrollMode.AUTO,
            ),
            padding=10,
        )

    def build_scheduled_black_flag_tab(self):
        """Build the Scheduled Black Flag tab content"""
        self.scheduled_black_flag_list = ft.Column(
            scroll=ft.ScrollMode.AUTO, spacing=10, expand=True
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
                                size=20,
                                weight=ft.FontWeight.BOLD,
                            ),
                            ft.Container(expand=True),
                            enable_toggle,
                        ],
                        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                    ),
                    ft.Divider(),
                    add_button,
                    ft.Container(height=10),
                    self.scheduled_black_flag_list,
                ]
            ),
            padding=10,
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
            hint_text="Negative = from end",
            disabled=self.is_running,
            on_change=lambda e: update_config(
                "event_time", float(e.control.value) if e.control.value else 0
            ),
        )

        cars = ft.TextField(
            label="Car Numbers",
            value=config["cars"],
            width=200,
            hint_text="Comma separated: 19,42,7",
            disabled=self.is_running,
            on_change=lambda e: update_config("cars", e.control.value),
        )

        penalty = ft.TextField(
            label="Penalty",
            value=config["penalty"],
            width=150,
            hint_text="e.g. L2, d, 4120",
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
                                    f"Black Flag Event #{index + 1}",
                                    size=16,
                                    weight=ft.FontWeight.BOLD,
                                ),
                                ft.Container(expand=True),
                                remove_button,
                            ]
                        ),
                        ft.Divider(),
                        ft.Row([event_time, cars, penalty], wrap=True, spacing=10),
                    ]
                ),
                padding=15,
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
                                        size=20,
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
                    ft.Divider(),
                    ft.Row([gap_to_leader, penalty], wrap=True, spacing=10),
                    ft.Row([sound_check], wrap=True),
                ],
                scroll=ft.ScrollMode.AUTO,
            ),
            padding=10,
        )

    def build_consumer_section(self):
        """Build the consumer events section (text and audio)"""
        return ft.Column(
            [
                ft.Container(
                    content=self.build_text_consumer(),
                    width=400,
                    border=ft.border.all(1, ft.Colors.OUTLINE),
                    border_radius=5,
                    padding=15,
                ),
                ft.Container(height=20),
                ft.Container(
                    content=self.build_audio_consumer(),
                    width=400,
                    border=ft.border.all(1, ft.Colors.OUTLINE),
                    border_radius=5,
                    padding=15,
                ),
            ],
        )

    def build_text_consumer(self):
        """Build the text consumer configuration"""
        config = {"password": "", "room": "", "test": False}
        self.text_consumer_config = config

        def update_config(key, value):
            config[key] = value

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
                ft.Text("Text Consumer (Discord)", size=16, weight=ft.FontWeight.BOLD),
                ft.Text(
                    "Display race control messages in Discord text channel",
                    size=11,
                    color=ft.Colors.GREY,
                ),
                ft.Divider(),
                enable_check,
                token_field,
                channel_field,
                test_check,
            ]
        )

    def build_audio_consumer(self):
        """Build the audio consumer configuration"""
        config = {
            "vc_id": "420037391882125313",
            "volume": 1.0,
            "token": "",
            "hello": True,
        }
        self.audio_consumer_config = config

        def update_config(key, value):
            config[key] = value

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
                    "Audio Consumer (Discord Bot)", size=16, weight=ft.FontWeight.BOLD
                ),
                ft.Text(
                    "Play audio cues in Discord voice channel",
                    size=11,
                    color=ft.Colors.GREY,
                ),
                ft.Divider(),
                enable_check,
                vc_id_field,
                ft.Text("Volume", size=12),
                volume_slider,
                token_field,
                hello_check,
            ]
        )

    def start_race_control(self, e):
        """Start the race control system"""
        self.is_running = True
        # Rebuild tabs to update disabled states
        self.tabs_control.tabs[0].content = self.build_random_cautions_tab()
        self.tabs_control.tabs[1].content = self.build_random_code69s_tab()
        self.tabs_control.tabs[2].content = self.build_incident_cautions_tab()
        self.tabs_control.tabs[3].content = self.build_incident_penalties_tab()
        self.tabs_control.tabs[4].content = self.build_scheduled_messages_tab()
        self.tabs_control.tabs[5].content = self.build_collision_penalty_tab()
        self.tabs_control.tabs[6].content = self.build_clear_black_flag_tab()
        self.tabs_control.tabs[7].content = self.build_scheduled_black_flag_tab()
        self.tabs_control.tabs[8].content = self.build_gap_to_leader_tab()

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
                events.LapCautionEvent if use_lap_based else events.RandomCautionEvent
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
                            "reminder_frequency": global_config["reminder_frequency"],
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
                        "incident_window_seconds": config["incident_window_seconds"],
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
            event_list.append({"class": events.IncidentPenaltyEvent, "args": config})

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
                        "tracking_window_seconds": config["tracking_window_seconds"],
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
                {"class": events.AudioConsumerEvent, "args": self.audio_consumer_config}
            )

        # Create event instances
        event_instances = [item["class"](**item["args"]) for item in event_list]

        # Create and start subprocess manager
        event_run_methods = [event.run for event in event_instances]
        self.subprocess_manager = SubprocessManager(event_run_methods)
        self.subprocess_manager.start()

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

    def stop_race_control(self, e):
        """Stop the race control system"""
        if self.subprocess_manager:
            self.subprocess_manager.stop()

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
        self.tabs_control.tabs[0].content = self.build_random_cautions_tab()
        self.tabs_control.tabs[1].content = self.build_random_code69s_tab()
        self.tabs_control.tabs[2].content = self.build_incident_cautions_tab()
        self.tabs_control.tabs[3].content = self.build_incident_penalties_tab()
        self.tabs_control.tabs[4].content = self.build_scheduled_messages_tab()
        self.tabs_control.tabs[5].content = self.build_collision_penalty_tab()
        self.tabs_control.tabs[6].content = self.build_clear_black_flag_tab()
        self.tabs_control.tabs[7].content = self.build_scheduled_black_flag_tab()
        self.tabs_control.tabs[8].content = self.build_gap_to_leader_tab()

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

        def load_preset(e):
            selected = preset_list.value
            if selected:
                self.load_preset(selected)
                close_dlg(e)

        # Get available presets
        presets = self.get_available_presets()

        if not presets:
            dlg = ft.AlertDialog(
                title=ft.Text("No Presets Found"),
                content=ft.Text("There are no saved presets available."),
                actions=[ft.TextButton("OK", on_click=close_dlg)],
            )
        else:
            preset_list = ft.Dropdown(
                label="Select Preset",
                options=[ft.dropdown.Option(p) for p in presets],
                width=300,
            )

            dlg = ft.AlertDialog(
                title=ft.Text("Load Preset"),
                content=preset_list,
                actions=[
                    ft.TextButton("Cancel", on_click=close_dlg),
                    ft.TextButton("Load", on_click=load_preset),
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

    def load_preset(self, name: str):
        """Load a saved preset"""
        preset_path = os.path.join("presets", f"{name}.json")
        if not os.path.exists(preset_path):
            return

        with open(preset_path, "r") as f:
            config = json.load(f)

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
        # Ensure use_lap_based is set (default to False for old presets)
        if "use_lap_based" not in self.incident_caution_config:
            self.incident_caution_config["use_lap_based"] = False
        # Ensure incident_window_seconds is set (default to 10 for old presets)
        if "incident_window_seconds" not in self.incident_caution_config:
            self.incident_caution_config["incident_window_seconds"] = 10
        # Ensure RandomCautionEvent parameters are set
        if "extend_laps" not in self.incident_caution_config:
            self.incident_caution_config["extend_laps"] = 0
        if "pre_extend_laps" not in self.incident_caution_config:
            self.incident_caution_config["pre_extend_laps"] = 1
        if "max_laps_behind_leader" not in self.incident_caution_config:
            self.incident_caution_config["max_laps_behind_leader"] = 0
        if "notify_on_skipped_caution" not in self.incident_caution_config:
            self.incident_caution_config["notify_on_skipped_caution"] = False
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

        # Update tab indicators
        self.update_tab_indicators()

        # Rebuild all tabs to reflect new values
        self.tabs_control.tabs[0].content = self.build_random_cautions_tab()
        self.tabs_control.tabs[1].content = self.build_random_code69s_tab()
        self.tabs_control.tabs[2].content = self.build_incident_cautions_tab()
        self.tabs_control.tabs[3].content = self.build_incident_penalties_tab()
        self.tabs_control.tabs[4].content = self.build_scheduled_messages_tab()
        self.tabs_control.tabs[5].content = self.build_collision_penalty_tab()
        self.tabs_control.tabs[6].content = self.build_clear_black_flag_tab()
        self.tabs_control.tabs[7].content = self.build_scheduled_black_flag_tab()
        self.tabs_control.tabs[8].content = self.build_gap_to_leader_tab()

        # Rebuild consumer section to reflect new values
        main_row = self.page.controls[2]  # The Row containing tabs and consumers
        main_row.controls[2] = self.build_consumer_section()

        # Show success message
        self.page.snack_bar = ft.SnackBar(
            content=ft.Text(f"Preset '{name}' loaded successfully!"),
            bgcolor=ft.Colors.GREEN,
        )
        self.page.snack_bar.open = True
        self.page.update()


def main(page: ft.Page):
    app = RaceControlApp()
    app.main(page)


if __name__ == "__main__":
    ft.app(target=main)
