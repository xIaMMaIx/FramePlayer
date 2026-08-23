"""
Left Navigation Dock (Sidebar) for CarPlay / Android Auto Theme.
Features oversized touch icons, active indicator pills, and live clock.
"""

from datetime import datetime
from typing import Callable
import flet as ft
from src.state import AppMode, AppState
from src.ui.theme import (
    ACCENT_RED,
    BORDER_RADIUS_BUTTON,
    SURFACE_DARK,
    SURFACE_TRANSLUCENT,
    TEXT_MUTED,
    TEXT_PRIMARY,
    TEXT_SECONDARY,
)


class Sidebar(ft.Container):
    def __init__(self, state: AppState, on_mode_select: Callable[[AppMode], None]):
        self.state = state
        self.on_mode_select = on_mode_select

        # Clock Text Control
        self.clock_text = ft.Text(
            value=datetime.now().strftime("%H:%M"),
            size=16,
            weight=ft.FontWeight.W_800,
            color=TEXT_PRIMARY,
            text_align=ft.TextAlign.CENTER,
        )

        # Navigation Buttons
        self.btn_music = self._create_nav_button(
            icon=ft.icons.MUSIC_NOTE_ROUNDED,
            label="Music",
            mode=AppMode.MUSIC_PLAYER,
        )
        self.btn_photos = self._create_nav_button(
            icon=ft.icons.PHOTO_LIBRARY_ROUNDED,
            label="Photos",
            mode=AppMode.PHOTO_FRAME,
        )
        self.btn_settings = self._create_nav_button(
            icon=ft.icons.SETTINGS_ROUNDED,
            label="Settings",
            mode=AppMode.SETTINGS,
        )

        # Idle countdown / status pill
        self.idle_pill_text = ft.Text("60s", size=11, color=TEXT_MUTED, weight=ft.FontWeight.BOLD)
        self.idle_pill = ft.Container(
            content=ft.Row(
                [
                    ft.Icon(ft.icons.TIMER_OUTLINED, size=13, color=TEXT_MUTED),
                    self.idle_pill_text,
                ],
                alignment=ft.MainAxisAlignment.CENTER,
                spacing=3,
            ),
            padding=ft.padding.symmetric(horizontal=8, vertical=5),
            border_radius=10,
            bgcolor="rgba(255, 255, 255, 0.06)",
            border=ft.border.all(1, "rgba(255, 255, 255, 0.1)"),
            tooltip="Screensaver Idle Countdown",
        )

        super().__init__(
            width=92,
            bgcolor=SURFACE_DARK,
            padding=ft.padding.symmetric(vertical=16, horizontal=8),
            border=ft.border.only(right=ft.BorderSide(1.5, "rgba(255, 255, 255, 0.12)")),
            content=ft.Column(
                controls=[
                    # Top: Live Digital Clock
                    ft.Container(
                        content=self.clock_text,
                        alignment=ft.alignment.center,
                        padding=ft.padding.only(bottom=10),
                    ),
                    ft.Divider(color="rgba(255, 255, 255, 0.12)", height=1),
                    # Center: Navigation items
                    ft.Column(
                        controls=[
                            self.btn_music,
                            self.btn_photos,
                            self.btn_settings,
                        ],
                        alignment=ft.MainAxisAlignment.CENTER,
                        horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                        spacing=16,
                        expand=True,
                    ),
                    # Bottom: Idle status & Screensaver trigger
                    ft.Column(
                        controls=[
                            self.idle_pill,
                        ],
                        horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                        spacing=8,
                    ),
                ],
                alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                expand=True,
            ),
        )

    def _create_nav_button(self, icon: str, label: str, mode: AppMode) -> ft.Container:
        """Builds a touch-friendly navigation icon button with active highlight."""
        is_active = self.state.mode == mode
        return ft.Container(
            content=ft.Column(
                controls=[
                    ft.Icon(
                        icon,
                        size=34,
                        color=ACCENT_RED if is_active else TEXT_SECONDARY,
                    ),
                    ft.Text(
                        label,
                        size=11,
                        color=TEXT_PRIMARY if is_active else TEXT_MUTED,
                        weight=ft.FontWeight.W_700 if is_active else ft.FontWeight.W_400,
                    ),
                ],
                alignment=ft.MainAxisAlignment.CENTER,
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                spacing=4,
            ),
            width=76,
            height=72,
            border_radius=BORDER_RADIUS_BUTTON,
            bgcolor="rgba(255, 0, 51, 0.18)" if is_active else "transparent",
            border=ft.border.all(1.5, ACCENT_RED) if is_active else ft.border.all(1, "transparent"),
            alignment=ft.alignment.center,
            ink=True,
            on_click=lambda e: self.on_mode_select(mode),
            animate=ft.Animation(200, ft.AnimationCurve.EASE_OUT),
        )

    def update_state(self) -> None:
        """Refreshes button styles based on current app state."""
        self.clock_text.value = datetime.now().strftime("%H:%M")

        # Update Idle Pill
        if self.state.is_playing:
            self.idle_pill_text.value = "Active"
            self.idle_pill_text.color = "#10B981"
        else:
            remaining = max(0, self.state.idle_threshold_seconds - self.state.idle_seconds)
            self.idle_pill_text.value = f"{remaining}s"
            self.idle_pill_text.color = TEXT_MUTED if remaining > 10 else "#F59E0B"

        # Update button highlights
        self._update_button_style(self.btn_music, AppMode.MUSIC_PLAYER)
        self._update_button_style(self.btn_photos, AppMode.PHOTO_FRAME)
        self._update_button_style(self.btn_settings, AppMode.SETTINGS)

        if getattr(self, "page", None):
            try:
                self.update()
            except Exception:
                pass

    def _update_button_style(self, button_container: ft.Container, target_mode: AppMode) -> None:
        is_active = self.state.mode == target_mode
        col = button_container.content
        icon_ctrl = col.controls[0]
        text_ctrl = col.controls[1]

        icon_ctrl.color = ACCENT_RED if is_active else TEXT_SECONDARY
        text_ctrl.color = TEXT_PRIMARY if is_active else TEXT_MUTED
        text_ctrl.weight = ft.FontWeight.W_700 if is_active else ft.FontWeight.W_400

        button_container.bgcolor = "rgba(255, 0, 51, 0.18)" if is_active else "transparent"
        button_container.border = ft.border.all(1.5, ACCENT_RED) if is_active else ft.border.all(1, "transparent")
