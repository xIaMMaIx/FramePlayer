"""
Settings View for Kiosk Configuration.
Allows configuring photo folder directory, slideshow speed, background blur intensity,
and idle screensaver timeout.
"""

from pathlib import Path
from typing import Callable, Optional
import flet as ft

from src.config_manager import ConfigManager
from src.photo_engine import PhotoEngine

from src.state import AppState
from src.ui.theme import (
    ACCENT_CYAN,
    ACCENT_GREEN,
    ACCENT_RED,
    SURFACE_ELEVATED,
    TEXT_MUTED,
    TEXT_PRIMARY,
    TEXT_SECONDARY,
    glass_card,
)


class SettingsView(ft.Container):
    def __init__(
        self,
        state: AppState,
        config_mgr: ConfigManager,
        photo_engine: PhotoEngine,
        on_pick_folder: Callable[[], None],
        on_test_screensaver: Callable[[], None],
        on_back_to_player: Optional[Callable[[], None]] = None,
        on_orientation_changed: Optional[Callable[[str], None]] = None,
    ):
        self.state = state
        self.config_mgr = config_mgr
        self.photo_engine = photo_engine
        self.on_pick_folder = on_pick_folder
        self.on_test_screensaver = on_test_screensaver
        self.on_back_to_player = on_back_to_player
        self.on_orientation_changed = on_orientation_changed

        # --- Display Orientation Elements ---
        current_orient = self.config_mgr.get("orientation", "landscape")
        self.txt_orientation_val = ft.Text(
            "แนวนอน (Landscape)" if current_orient == "landscape" else "แนวตั้ง (Portrait)",
            size=14,
            color=TEXT_PRIMARY,
            weight=ft.FontWeight.BOLD,
        )
        self.orientation_seg_btn = self._build_orientation_selector(current_orient)

        # --- Photo Folder Elements ---
        self.txt_folder_path = ft.Text(
            value=self.config_mgr.get("photo_folder", ""),
            size=13,
            color=TEXT_PRIMARY,
            selectable=True,
            max_lines=2,
            overflow=ft.TextOverflow.ELLIPSIS,
        )

        self.txt_photo_count = ft.Text(
            value=f"{self.photo_engine.total_photos} photos detected (.jpg, .jpeg, .png, .webp)",
            size=12,
            color=ACCENT_GREEN,
            weight=ft.FontWeight.W_500,
        )

        # Slideshow speed slider
        current_speed = self.config_mgr.get("slideshow_interval_seconds", 8)
        self.txt_speed_val = ft.Text(f"{current_speed}s", size=14, color=TEXT_PRIMARY, weight=ft.FontWeight.BOLD)
        self.slider_speed = ft.Slider(
            min=4,
            max=30,
            divisions=26,
            value=current_speed,
            active_color=ACCENT_RED,
            inactive_color="rgba(255, 255, 255, 0.1)",
            label="{value}s",
            on_change=self._handle_speed_change,
            expand=True,
        )

        # Background Blur Intensity Slider
        current_blur = self.config_mgr.get("background_blur_radius", 24)
        self.txt_blur_val = ft.Text(f"{current_blur}px", size=14, color=TEXT_PRIMARY, weight=ft.FontWeight.BOLD)
        self.slider_blur = ft.Slider(
            min=5,
            max=50,
            divisions=45,
            value=current_blur,
            active_color=ACCENT_RED,
            inactive_color="rgba(255, 255, 255, 0.1)",
            label="{value}px",
            on_change=self._handle_blur_change,
            expand=True,
        )

        # Idle Timeout Selector
        current_idle = self.config_mgr.get("idle_timeout_seconds", 60)
        self.txt_idle_val = ft.Text(f"{current_idle}s", size=14, color=TEXT_PRIMARY, weight=ft.FontWeight.BOLD)
        self.idle_seg_btn = self._build_idle_selector(current_idle)

        # Fill Mode Selector
        current_fill = self.config_mgr.get("photo_fill_mode", "contain")
        self.fill_mode_seg = ft.SegmentedButton(
            selected=[current_fill],
            allow_empty_selection=False,
            allow_multiple_selection=False,
            segments=[
                ft.Segment(
                    value="contain",
                    label=ft.Text("Contain", size=12),
                    icon=ft.Icon(ft.Icons.FIT_SCREEN_ROUNDED, size=16),
                ),
                ft.Segment(
                    value="cover",
                    label=ft.Text("Cover", size=12),
                    icon=ft.Icon(ft.Icons.CROP_FREE_ROUNDED, size=16),
                ),
            ],
            on_change=self._handle_fill_mode_change,
        )

        # Shuffle Switch
        self.switch_shuffle = ft.Switch(
            value=self.config_mgr.get("slideshow_shuffle", True),
            active_color=ACCENT_RED,
            on_change=self._handle_shuffle_change,
        )

        # Build View with Tabs
        self.tabs = ft.Tabs(
            length=2,
            selected_index=0,
            animation_duration=300,
            expand=True,
            content=ft.Column(
                expand=True,
                controls=[
                    ft.TabBar(
                        tabs=[
                            ft.Tab(label="หน้าจอ (Display)", icon=ft.Icons.SMARTPHONE_ROUNDED),
                            ft.Tab(label="กรอบรูป (Photos)", icon=ft.Icons.PHOTO_LIBRARY_ROUNDED),
                        ]
                    ),
                    ft.TabBarView(
                        expand=True,
                        controls=[
                            self._build_display_tab(),
                            self._build_photo_tab(),
                        ]
                    )
                ]
            )
        )

        content_col = ft.Column(
            controls=[
                # Top Header Row
                ft.Row(
                    controls=[
                        ft.Row(
                            [
                                ft.Icon(ft.Icons.SETTINGS_ROUNDED, size=24, color=ACCENT_RED),
                                ft.Text("Settings & Configuration", size=20, weight=ft.FontWeight.BOLD, color=TEXT_PRIMARY),
                            ],
                            spacing=10,
                        ),
                        ft.ElevatedButton(
                            content=ft.Row([ft.Icon(ft.Icons.MUSIC_NOTE_ROUNDED, size=18), ft.Text("Back to Player", weight=ft.FontWeight.BOLD)]),
                            bgcolor=ACCENT_RED,
                            color=TEXT_PRIMARY,
                            style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=10), padding=ft.Padding(16, 10, 16, 10)),
                            on_click=lambda e: self.on_back_to_player() if self.on_back_to_player else None,
                        ),
                    ],
                    alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                ),
                ft.Divider(color="rgba(255, 255, 255, 0.1)", height=10),
                # Main Tabs Container
                ft.Container(
                    content=self.tabs,
                    expand=True,
                ),
            ],
            spacing=10,
            expand=True,
        )

        super().__init__(
            content=content_col,
            padding=16,
            expand=True,
        )

    def _build_display_tab(self) -> ft.Container:
        """Tab for Screen Orientation and Screensaver Timeout."""
        btn_test_saver = ft.ElevatedButton(
            content=ft.Row(
                [
                    ft.Icon(ft.Icons.PLAY_CIRCLE_OUTLINE_ROUNDED, size=20),
                    ft.Text("Launch Photo Frame Now", size=14, weight=ft.FontWeight.BOLD),
                ],
                alignment=ft.MainAxisAlignment.CENTER,
            ),
            bgcolor=SURFACE_ELEVATED,
            color=TEXT_PRIMARY,
            style=ft.ButtonStyle(
                shape=ft.RoundedRectangleBorder(radius=12),
                side=ft.BorderSide(1, "rgba(255, 255, 255, 0.2)"),
                padding=ft.Padding(18, 14, 18, 14),
            ),
            on_click=lambda e: self.on_test_screensaver(),
        )

        card_content = ft.Column(
            controls=[
                # Screen Orientation Section
                ft.Row(
                    [
                        ft.Icon(ft.Icons.SCREEN_ROTATION_ROUNDED, color=ACCENT_CYAN, size=22),
                        ft.Text("Screen Orientation (ทิศทางหน้าจอ)", size=16, weight=ft.FontWeight.BOLD, color=TEXT_PRIMARY),
                    ],
                    spacing=8,
                ),
                ft.Text(
                    "Choose between Landscape (แนวนอน 16:9) or Portrait (แนวตั้ง 9:16).",
                    size=12,
                    color=TEXT_MUTED,
                ),
                ft.Row(
                    [
                        ft.Text("Current Mode:", size=14, color=TEXT_PRIMARY),
                        self.txt_orientation_val,
                    ],
                    alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                ),
                self.orientation_seg_btn,
                ft.Divider(color="rgba(255, 255, 255, 0.08)", height=16),
                # Screensaver Idle Section
                ft.Row(
                    [
                        ft.Icon(ft.Icons.NIGHTLIGHT_ROUNDED, color=ACCENT_RED, size=22),
                        ft.Text("Idle Screensaver Trigger", size=16, weight=ft.FontWeight.BOLD, color=TEXT_PRIMARY),
                    ],
                    spacing=8,
                ),
                ft.Text(
                    "Starts photo slideshow when music is paused for the specified duration.",
                    size=12,
                    color=TEXT_MUTED,
                ),
                ft.Row(
                    [
                        ft.Text("Idle Timeout:", size=14, color=TEXT_PRIMARY),
                        self.txt_idle_val,
                    ],
                    alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                ),
                self.idle_seg_btn,
                ft.Container(height=6),
                btn_test_saver,
            ],
            spacing=12,
            scroll=ft.ScrollMode.AUTO,
        )

        return ft.Container(
            content=glass_card(content=card_content, padding=20),
            padding=ft.Padding(0, 12, 0, 0),
            expand=True,
        )

    def _build_photo_tab(self) -> ft.Container:
        """Tab for local photo folder configuration."""
        btn_browse = ft.ElevatedButton(
            content=ft.Row(
                [
                    ft.Icon(ft.Icons.FOLDER_OPEN_ROUNDED, size=20),
                    ft.Text("Browse Folder", size=14, weight=ft.FontWeight.BOLD),
                ],
                alignment=ft.MainAxisAlignment.CENTER,
            ),
            bgcolor=ACCENT_RED,
            color=TEXT_PRIMARY,
            style=ft.ButtonStyle(
                shape=ft.RoundedRectangleBorder(radius=12),
                padding=ft.Padding(18, 14, 18, 14),
            ),
            on_click=lambda e: self.on_pick_folder(),
        )

        btn_reset_samples = ft.OutlinedButton(
            content=ft.Row(
                [
                    ft.Icon(ft.Icons.RESTART_ALT_ROUNDED, size=18, color=TEXT_SECONDARY),
                    ft.Text("Use Sample Photos", size=13, color=TEXT_SECONDARY),
                ],
                alignment=ft.MainAxisAlignment.CENTER,
            ),
            style=ft.ButtonStyle(
                shape=ft.RoundedRectangleBorder(radius=12),
                side=ft.BorderSide(1, "rgba(255, 255, 255, 0.15)"),
                padding=ft.Padding(14, 12, 14, 12),
            ),
            on_click=self._handle_reset_samples,
        )

        card_content = ft.Column(
            controls=[
                ft.Row(
                    [
                        ft.Icon(ft.Icons.IMAGE_ROUNDED, color=ACCENT_CYAN, size=22),
                        ft.Text("Photo Slideshow Source", size=16, weight=ft.FontWeight.BOLD, color=TEXT_PRIMARY),
                    ],
                    spacing=8,
                ),
                ft.Text("Configure local images and ambient background presentation.", size=12, color=TEXT_MUTED),
                # Folder Path Display Box
                ft.Container(
                    content=ft.Column(
                        controls=[
                            ft.Text("CURRENT DIRECTORY", size=10, weight=ft.FontWeight.BOLD, color=TEXT_MUTED),
                            self.txt_folder_path,
                            self.txt_photo_count,
                        ],
                        spacing=4,
                    ),
                    padding=12,
                    border_radius=10,
                    bgcolor="rgba(255, 255, 255, 0.04)",
                    border=ft.Border(top=ft.BorderSide(1, "rgba(255, 255, 255, 0.08)"), right=ft.BorderSide(1, "rgba(255, 255, 255, 0.08)"), bottom=ft.BorderSide(1, "rgba(255, 255, 255, 0.08)"), left=ft.BorderSide(1, "rgba(255, 255, 255, 0.08)")),
                ),
                ft.Row([btn_browse, btn_reset_samples], spacing=10),
                ft.Divider(color="rgba(255, 255, 255, 0.08)", height=14),
                
                # Fill Mode Toggle
                ft.Row(
                    [
                        ft.Text("Fill Mode:", size=13, color=TEXT_PRIMARY),
                        self.fill_mode_seg,
                    ],
                    alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                ),
                ft.Divider(color="rgba(255, 255, 255, 0.08)", height=14),
                
                # Background Blur Slider
                ft.Row(
                    [
                        ft.Text("Background Blur (ความเบลอพื้นหลัง):", size=13, color=TEXT_PRIMARY),
                        self.txt_blur_val,
                    ],
                    alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                ),
                ft.Row([self.slider_blur]),
                # Slideshow Speed
                ft.Row(
                    [
                        ft.Text("Slide Duration (เวลาเปลี่ยนภาพ):", size=13, color=TEXT_PRIMARY),
                        self.txt_speed_val,
                    ],
                    alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                ),
                ft.Row([self.slider_speed]),
                # Randomize Toggle
                ft.Row(
                    [
                        ft.Text("Shuffle Photos (สุ่มลำดับภาพ)", size=13, color=TEXT_PRIMARY),
                        self.switch_shuffle,
                    ],
                    alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                ),
            ],
            spacing=10,
            scroll=ft.ScrollMode.AUTO,
        )

        return ft.Container(
            content=glass_card(content=card_content, padding=20),
            padding=ft.Padding(0, 12, 0, 0),
            expand=True,
        )

    def _build_orientation_selector(self, current_orientation: str) -> ft.Row:
        """Buttons to select Landscape or Portrait orientation."""
        options = [("landscape", "📱 แนวนอน (Landscape)"), ("portrait", "📲 แนวตั้ง (Portrait)")]
        btns = []
        for val, lbl in options:
            is_sel = val == current_orientation
            btn = ft.Container(
                content=ft.Text(
                    lbl,
                    size=12,
                    weight=ft.FontWeight.BOLD if is_sel else ft.FontWeight.NORMAL,
                    color=TEXT_PRIMARY if is_sel else TEXT_SECONDARY,
                ),
                padding=ft.Padding(12, 10, 12, 10),
                border_radius=10,
                bgcolor="rgba(255, 0, 51, 0.25)" if is_sel else "rgba(255, 255, 255, 0.05)",
                border=ft.Border(top=ft.BorderSide(1, ACCENT_RED if is_sel else "rgba(255, 255, 255, 0.1)"), right=ft.BorderSide(1, ACCENT_RED if is_sel else "rgba(255, 255, 255, 0.1)"), bottom=ft.BorderSide(1, ACCENT_RED if is_sel else "rgba(255, 255, 255, 0.1)"), left=ft.BorderSide(1, ACCENT_RED if is_sel else "rgba(255, 255, 255, 0.1)")),
                alignment=ft.Alignment(0, 0),
                ink=True,
                on_click=lambda e, o=val: self._handle_orientation_select(o),
                expand=True,
            )
            btns.append(btn)
        return ft.Row(controls=btns, spacing=8)

    def _handle_orientation_select(self, orientation: str) -> None:
        self.config_mgr.set("orientation", orientation)
        self.txt_orientation_val.value = "แนวนอน (Landscape)" if orientation == "landscape" else "แนวตั้ง (Portrait)"
        self.orientation_seg_btn.controls.clear()
        new_row = self._build_orientation_selector(orientation)
        self.orientation_seg_btn.controls.extend(new_row.controls)
        if self.on_orientation_changed:
            self.on_orientation_changed(orientation)
        try:
            if self.page:
                self.update()
        except Exception:
            pass

    def _build_idle_selector(self, current_idle: int) -> ft.Row:
        """Buttons to quickly select 5s (quick demo), 15s, 60s (standard), 120s."""
        options = [(5, "5s (Demo)"), (15, "15s"), (60, "60s (Default)"), (120, "2 min")]
        btns = []
        for secs, lbl in options:
            is_sel = secs == current_idle
            btn = ft.Container(
                content=ft.Text(
                    lbl,
                    size=12,
                    weight=ft.FontWeight.BOLD if is_sel else ft.FontWeight.NORMAL,
                    color=TEXT_PRIMARY if is_sel else TEXT_SECONDARY,
                ),
                padding=ft.Padding(12, 10, 12, 10),
                border_radius=10,
                bgcolor="rgba(255, 0, 51, 0.25)" if is_sel else "rgba(255, 255, 255, 0.05)",
                border=ft.Border(top=ft.BorderSide(1, ACCENT_RED if is_sel else "rgba(255, 255, 255, 0.1)"), right=ft.BorderSide(1, ACCENT_RED if is_sel else "rgba(255, 255, 255, 0.1)"), bottom=ft.BorderSide(1, ACCENT_RED if is_sel else "rgba(255, 255, 255, 0.1)"), left=ft.BorderSide(1, ACCENT_RED if is_sel else "rgba(255, 255, 255, 0.1)")),
                alignment=ft.Alignment(0, 0),
                ink=True,
                on_click=lambda e, s=secs: self._handle_idle_select(s),
                expand=True,
            )
            btns.append(btn)
        return ft.Row(controls=btns, spacing=8)

    def _handle_idle_select(self, seconds: int) -> None:
        self.config_mgr.set("idle_timeout_seconds", seconds)
        self.state.idle_threshold_seconds = seconds
        self.txt_idle_val.value = f"{seconds}s"
        self.idle_seg_btn.controls.clear()
        new_row = self._build_idle_selector(seconds)
        self.idle_seg_btn.controls.extend(new_row.controls)
        try:
            if self.page:
                self.update()
        except Exception:
            pass

    def _handle_blur_change(self, e) -> None:
        val = int(e.control.value)
        self.config_mgr.set("background_blur_radius", val)
        self.photo_engine.set_blur_radius(val)
        self.txt_blur_val.value = f"{val}px"
        try:
            if self.txt_blur_val.page:
                self.txt_blur_val.update()
        except Exception:
            pass

    def _handle_fill_mode_change(self, e) -> None:
        selected = list(e.control.selected)[0]
        self.config_mgr.set("photo_fill_mode", selected)

    def _handle_speed_change(self, e) -> None:
        val = int(e.control.value)
        self.config_mgr.set("slideshow_interval_seconds", val)
        self.txt_speed_val.value = f"{val}s"
        try:
            if self.txt_speed_val.page:
                self.txt_speed_val.update()
        except Exception:
            pass

    def _handle_shuffle_change(self, e) -> None:
        val = bool(e.control.value)
        self.config_mgr.set("slideshow_shuffle", val)
        self.photo_engine.set_shuffle(val)

    def _handle_reset_samples(self, e) -> None:
        sample_dir = Path("assets/samples").resolve()
        self.config_mgr.set_photo_folder(str(sample_dir))
        self.photo_engine.scan_folder(str(sample_dir))
        self.update_folder_info()

    def update_folder_info(self) -> None:
        """Refreshes folder path and image counter."""
        self.txt_folder_path.value = self.config_mgr.get("photo_folder", "")
        self.txt_photo_count.value = f"{self.photo_engine.total_photos} photos detected (.jpg, .jpeg, .png, .webp)"
        try:
            if self.page:
                self.update()
        except Exception:
            pass
