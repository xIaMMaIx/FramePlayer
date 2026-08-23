"""
Wake / Quick Action Overlay Modal.
Appears when tapping the screen during Photo Frame Screensaver mode.
Presents prominent, responsive touch action cards:
1. [ 🎵 YouTube Music ] -> Returns immediately to CarPlay dashboard.
2. [ 📁 Change Photo Folder ] -> Triggers directory picker and updates config.json.
3. [ ⚙️ Settings ] -> Opens Kiosk & Photo settings.
"""

from typing import Callable
import flet as ft
from src.state import AppState
from src.ui.theme import (
    ACCENT_CYAN,
    ACCENT_RED,
    BORDER_RADIUS_CARD,
    SURFACE_CARD,
    SURFACE_DARK,
    SURFACE_ELEVATED,
    TEXT_MUTED,
    TEXT_PRIMARY,
    TEXT_SECONDARY,
)


class ActionOverlay(ft.Container):
    def __init__(
        self,
        state: AppState,
        on_switch_to_music: Callable[[], None],
        on_change_folder: Callable[[], None],
        on_dismiss: Callable[[], None],
    ):
        self.state = state
        self.on_switch_to_music = on_switch_to_music
        self.on_change_folder = on_change_folder
        self.on_dismiss = on_dismiss

        # Card 1: Music Player Action Card
        card_music = self._build_action_card(
            title="YouTube Music",
            subtitle="กลับไปที่หน้าจอเครื่องเล่นเพลง",
            icon=ft.icons.MUSIC_NOTE_ROUNDED,
            icon_color="#FFFFFF",
            icon_bg=ACCENT_RED,
            on_click=self._handle_music_click,
        )

        # Card 2: Photo Folder Action Card
        card_folder = self._build_action_card(
            title="เปลี่ยนโฟลเดอร์รูป",
            subtitle="เลือกโฟลเดอร์รูปภาพในเครื่อง",
            icon=ft.icons.FOLDER_OPEN_ROUNDED,
            icon_color="#FFFFFF",
            icon_bg="#2563EB",
            on_click=self._handle_folder_click,
        )

        # Close / Dismiss Button
        btn_close = ft.IconButton(
            icon=ft.icons.CLOSE_ROUNDED,
            icon_color=TEXT_PRIMARY,
            icon_size=28,
            bgcolor="rgba(255, 255, 255, 0.12)",
            on_click=lambda e: self.on_dismiss(),
            tooltip="กลับสู่การเล่นสไลด์รูปภาพ",
        )

        # Modal Box Container
        modal_content = ft.Container(
            content=ft.Column(
                controls=[
                    # Header with title & close button
                    ft.Row(
                        controls=[
                            ft.Column(
                                controls=[
                                    ft.Text("Quick Actions", size=24, weight=ft.FontWeight.W_800, color=TEXT_PRIMARY),
                                    ft.Text("แตะเลือกเมนูที่ต้องการทำรายการ", size=13, color=TEXT_MUTED),
                                ],
                                spacing=2,
                            ),
                            btn_close,
                        ],
                        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                    ),
                    ft.Divider(color="rgba(255, 255, 255, 0.12)", height=20),
                    # Action Cards Row
                    ft.Row(
                        controls=[
                            card_music,
                            card_folder,
                        ],
                        alignment=ft.MainAxisAlignment.CENTER,
                        spacing=20,
                    ),
                ],
                alignment=ft.MainAxisAlignment.CENTER,
                spacing=8,
            ),
            width=620,
            padding=24,
            border_radius=24,
            bgcolor=SURFACE_CARD,
            border=ft.border.all(1.5, "rgba(255, 255, 255, 0.18)"),
        )

        super().__init__(
            content=ft.Column(
                controls=[modal_content],
                alignment=ft.MainAxisAlignment.CENTER,
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                expand=True,
            ),
            bgcolor="rgba(0, 0, 0, 0.85)",
            alignment=ft.alignment.center,
            visible=False,
            expand=True,
        )

    def _build_action_card(
        self,
        title: str,
        subtitle: str,
        icon: str,
        icon_color: str,
        icon_bg: str,
        on_click: Callable,
    ) -> ft.Container:
        """Constructs a responsive high-contrast touch card without glitchy blur shaders."""
        return ft.Container(
            content=ft.Column(
                controls=[
                    ft.Container(
                        content=ft.Icon(icon, size=40, color=icon_color),
                        width=72,
                        height=72,
                        border_radius=20,
                        bgcolor=icon_bg,
                        alignment=ft.alignment.center,
                    ),
                    ft.Column(
                        controls=[
                            ft.Text(title, size=17, weight=ft.FontWeight.W_700, color=TEXT_PRIMARY),
                            ft.Text(subtitle, size=11, color=TEXT_SECONDARY, text_align=ft.TextAlign.CENTER),
                        ],
                        horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                        spacing=3,
                    ),
                ],
                alignment=ft.MainAxisAlignment.CENTER,
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                spacing=12,
            ),
            width=260,
            height=190,
            padding=16,
            border_radius=18,
            bgcolor=SURFACE_ELEVATED,
            border=ft.border.all(1.2, "rgba(255, 255, 255, 0.12)"),
            ink=True,
            on_click=on_click,
            alignment=ft.alignment.center,
        )

    def _handle_music_click(self, e) -> None:
        self.state.reset_idle()
        self.on_switch_to_music()

    def _handle_folder_click(self, e) -> None:
        self.state.reset_idle()
        self.on_change_folder()

    def show(self) -> None:
        """Displays overlay."""
        self.visible = True
        if getattr(self, "page", None):
            try:
                self.update()
            except Exception:
                pass

    def hide(self) -> None:
        """Hides overlay."""
        self.visible = False
        if getattr(self, "page", None):
            try:
                self.update()
            except Exception:
                pass
