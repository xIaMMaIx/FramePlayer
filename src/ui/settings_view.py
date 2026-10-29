"""
Settings screen: one scrolling page with large touch targets, no tabs or sliders.
Screensaver delay, photo folder, slide timing, photo size and shuffle.
"""

from pathlib import Path
from typing import Callable, List, Optional, Tuple
import flet as ft

from src.config_manager import DEFAULT_SAMPLE_FOLDER, ConfigManager
from src.photo_engine import PhotoEngine
from src.state import AppState
from src.ui.theme import (
    ACCENT_RED,
    SURFACE_CARD,
    SURFACE_ELEVATED,
    SURFACE_GLASS_BORDER,
    TEXT_MUTED,
    TEXT_PRIMARY,
    TEXT_SECONDARY,
)

APP_VERSION = "1.0.0"

IDLE_OPTIONS = [(0, "Off"), (30, "30s"), (60, "1 min"), (120, "2 min"), (300, "5 min")]
INTERVAL_OPTIONS = [(5, "5s"), (10, "10s"), (20, "20s"), (30, "30s")]
FILL_OPTIONS = [("contain", "Fit"), ("cover", "Fill")]


def _nearest(options: List[Tuple], value) -> object:
    """Highlights the closest preset for numeric values saved by older versions (e.g. 8s)."""
    values = [v for v, _ in options]
    if value in values or not isinstance(value, (int, float)):
        return value
    return min(values, key=lambda v: abs(v - value))


class SettingsView(ft.Container):
    def __init__(
        self,
        state: AppState,
        config_mgr: ConfigManager,
        photo_engine: PhotoEngine,
        on_pick_folder: Callable[[], None],
        on_test_screensaver: Callable[[], None],
        on_back_to_player: Callable[[], None],
    ):
        self.state = state
        self.config_mgr = config_mgr
        self.photo_engine = photo_engine
        self.on_pick_folder = on_pick_folder

        self.txt_folder_name = ft.Text(size=15, weight=ft.FontWeight.BOLD, color=TEXT_PRIMARY, max_lines=1, overflow=ft.TextOverflow.ELLIPSIS)
        self.txt_folder_detail = ft.Text(size=12, color=TEXT_SECONDARY, max_lines=1, overflow=ft.TextOverflow.ELLIPSIS)
        self._fill_folder_texts()

        self.idle_choices = self._choice_row(IDLE_OPTIONS, self.config_mgr.get("idle_timeout_seconds"), self._set_idle)
        self.interval_choices = self._choice_row(
            INTERVAL_OPTIONS, self.config_mgr.get("slideshow_interval_seconds"), self._set_interval
        )
        self.fill_choices = self._choice_row(FILL_OPTIONS, self.config_mgr.get("photo_fill_mode"), self._set_fill)

        header = ft.Row(
            [
                ft.IconButton(
                    icon=ft.Icons.ARROW_BACK_ROUNDED,
                    icon_color=TEXT_PRIMARY,
                    icon_size=26,
                    tooltip="Back to player",
                    on_click=lambda e: on_back_to_player(),
                ),
                ft.Text("Settings", size=22, weight=ft.FontWeight.BOLD, color=TEXT_PRIMARY),
            ],
            spacing=4,
        )

        screensaver = self._section(
            "SCREENSAVER",
            [
                self._label("Start photo frame after", "When music is paused and nobody touches the screen"),
                self.idle_choices,
                ft.OutlinedButton(
                    content=ft.Row(
                        [ft.Icon(ft.Icons.PLAY_ARROW_ROUNDED, size=20, color=TEXT_PRIMARY), ft.Text("Preview photo frame", size=14, color=TEXT_PRIMARY)],
                        alignment=ft.MainAxisAlignment.CENTER,
                        tight=True,
                    ),
                    style=ft.ButtonStyle(
                        shape=ft.RoundedRectangleBorder(radius=12),
                        side=ft.BorderSide(1, SURFACE_GLASS_BORDER),
                        padding=ft.Padding.symmetric(horizontal=16, vertical=14),
                    ),
                    on_click=lambda e: on_test_screensaver(),
                ),
            ],
        )

        photos = self._section(
            "PHOTOS",
            [
                ft.Row(
                    [
                        ft.Icon(ft.Icons.FOLDER_ROUNDED, size=28, color=ACCENT_RED),
                        ft.Column([self.txt_folder_name, self.txt_folder_detail], spacing=2, expand=True),
                        ft.FilledButton(
                            content=ft.Text("Change", size=14, weight=ft.FontWeight.BOLD),
                            style=ft.ButtonStyle(
                                bgcolor=ACCENT_RED,
                                color=TEXT_PRIMARY,
                                shape=ft.RoundedRectangleBorder(radius=12),
                                padding=ft.Padding.symmetric(horizontal=18, vertical=12),
                            ),
                            on_click=lambda e: self.on_pick_folder(),
                        ),
                    ],
                    spacing=12,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                ),
                ft.TextButton(
                    content=ft.Text("Use sample photos", size=13, color=TEXT_SECONDARY),
                    on_click=self._use_samples,
                ),
                ft.Divider(height=1, color=SURFACE_GLASS_BORDER),
                self._label("Change photo every"),
                self.interval_choices,
                self._label("Photo size", "Fit shows the whole photo, Fill crops to the screen"),
                self.fill_choices,
                ft.Row(
                    [
                        ft.Text("Shuffle photos", size=15, color=TEXT_PRIMARY, expand=True),
                        ft.Switch(
                            value=self.config_mgr.get("slideshow_shuffle"),
                            active_color=ACCENT_RED,
                            on_change=self._set_shuffle,
                        ),
                    ],
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                ),
            ],
        )

        about = ft.Text(
            f"Frame Player {APP_VERSION} · plays YouTube Music without an account",
            size=12,
            color=TEXT_MUTED,
            text_align=ft.TextAlign.CENTER,
        )

        super().__init__(
            content=ft.Column(
                [header, screensaver, photos, ft.Container(about, alignment=ft.Alignment.CENTER, padding=8)],
                spacing=16,
                scroll=ft.ScrollMode.AUTO,
                expand=True,
                horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
            ),
            padding=ft.Padding(16, 8, 16, 16),
            expand=True,
        )

    # --- Building blocks ---

    @staticmethod
    def _section(title: str, controls: List[ft.Control]) -> ft.Column:
        return ft.Column(
            [
                ft.Text(title, size=12, weight=ft.FontWeight.BOLD, color=TEXT_MUTED),
                ft.Container(
                    content=ft.Column(controls, spacing=12),
                    padding=16,
                    border_radius=16,
                    bgcolor=SURFACE_CARD,
                    border=ft.Border.all(1, SURFACE_GLASS_BORDER),
                ),
            ],
            spacing=8,
            horizontal_alignment=ft.CrossAxisAlignment.STRETCH,  # Cards span the full width
        )

    @staticmethod
    def _label(text: str, hint: Optional[str] = None) -> ft.Column:
        controls = [ft.Text(text, size=15, color=TEXT_PRIMARY)]
        if hint:
            controls.append(ft.Text(hint, size=12, color=TEXT_MUTED))
        return ft.Column(controls, spacing=2)

    def _choice_row(self, options: List[Tuple], selected, on_select: Callable) -> ft.Row:
        """A row of large chip buttons; exactly one is highlighted."""
        row = ft.Row(spacing=8, wrap=True, run_spacing=8)
        row.data = (options, on_select)
        self._fill_choice_row(row, _nearest(options, selected))
        return row

    def _fill_choice_row(self, row: ft.Row, selected) -> None:
        options, on_select = row.data
        row.controls = [
            ft.Container(
                content=ft.Text(
                    label,
                    size=14,
                    weight=ft.FontWeight.BOLD if value == selected else ft.FontWeight.NORMAL,
                    color=TEXT_PRIMARY if value == selected else TEXT_SECONDARY,
                ),
                bgcolor=ACCENT_RED if value == selected else SURFACE_ELEVATED,
                border_radius=12,
                padding=ft.Padding.symmetric(horizontal=16, vertical=12),
                ink=True,
                on_click=lambda e, v=value, r=row: self._choose(r, v, on_select),
            )
            for value, label in options
        ]

    def _choose(self, row: ft.Row, value, on_select: Callable) -> None:
        self.state.reset_idle()
        on_select(value)
        self._fill_choice_row(row, value)
        row.update()

    # --- Setting handlers ---

    def _set_idle(self, seconds: int) -> None:
        self.config_mgr.set("idle_timeout_seconds", seconds)
        self.state.idle_threshold_seconds = seconds

    def _set_interval(self, seconds: int) -> None:
        self.config_mgr.set("slideshow_interval_seconds", seconds)

    def _set_fill(self, mode: str) -> None:
        self.config_mgr.set("photo_fill_mode", mode)

    def _set_shuffle(self, e) -> None:
        value = bool(e.control.value)
        self.config_mgr.set("slideshow_shuffle", value)
        self.photo_engine.set_shuffle(value)

    def _use_samples(self, e) -> None:
        self.config_mgr.set_photo_folder(str(DEFAULT_SAMPLE_FOLDER))
        self.photo_engine.scan_folder(str(DEFAULT_SAMPLE_FOLDER))
        self.update_folder_info()

    # --- Refresh ---

    def _fill_folder_texts(self) -> None:
        folder = Path(self.config_mgr.get("photo_folder"))
        count = self.photo_engine.total_photos
        self.txt_folder_name.value = folder.name or str(folder)
        self.txt_folder_detail.value = f"{count} photo{'s' if count != 1 else ''} · {folder}"

    def update_folder_info(self) -> None:
        """Called after the folder changes (picker or samples)."""
        self._fill_folder_texts()
        try:
            if self.page:
                self.update()
        except Exception:
            pass
