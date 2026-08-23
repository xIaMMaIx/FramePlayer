"""
Settings View for Kiosk Configuration.
Allows configuring photo folder directory, slideshow speed, background blur intensity,
idle screensaver timeout, and YouTube Music OAuth 2.0 Account Login / Logout.
"""

from pathlib import Path
from typing import Callable, Optional
import flet as ft

from src.config_manager import ConfigManager
from src.photo_engine import PhotoEngine
from src.services.oauth_manager import OAuthManager
from src.services.ytmusic_service import YTMusicService
from src.state import AppState
from src.ui.theme import (
    ACCENT_CYAN,
    ACCENT_GREEN,
    ACCENT_RED,
    BORDER_RADIUS_CARD,
    SURFACE_CARD,
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
        oauth_manager: OAuthManager,
        ytmusic_service: YTMusicService,
        on_pick_folder: Callable[[], None],
        on_test_screensaver: Callable[[], None],
        on_open_login: Callable[[], None],
        on_logout: Callable[[], None],
        on_back_to_player: Optional[Callable[[], None]] = None,
        on_orientation_changed: Optional[Callable[[str], None]] = None,
    ):
        self.state = state
        self.config_mgr = config_mgr
        self.photo_engine = photo_engine
        self.oauth_manager = oauth_manager
        self.ytmusic_service = ytmusic_service
        self.on_pick_folder = on_pick_folder
        self.on_test_screensaver = on_test_screensaver
        self.on_open_login = on_open_login
        self.on_logout = on_logout
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

        # Shuffle Switch
        self.switch_shuffle = ft.Switch(
            value=self.config_mgr.get("slideshow_shuffle", True),
            active_color=ACCENT_RED,
            on_change=self._handle_shuffle_change,
        )

        # OAuth Client Credentials Fields
        self.tf_client_id = ft.TextField(
            value=self.config_mgr.get("oauth_client_id", ""),
            label="Google OAuth Client ID",
            hint_text="xxxxx.apps.googleusercontent.com",
            text_size=12,
            color=TEXT_PRIMARY,
            border_color="rgba(255, 255, 255, 0.15)",
            focused_border_color=ACCENT_RED,
            content_padding=ft.padding.symmetric(horizontal=12, vertical=8),
            on_change=self._handle_client_id_change,
        )
        self.tf_client_secret = ft.TextField(
            value=self.config_mgr.get("oauth_client_secret", ""),
            label="Google OAuth Client Secret",
            password=True,
            can_reveal_password=True,
            text_size=12,
            color=TEXT_PRIMARY,
            border_color="rgba(255, 255, 255, 0.15)",
            focused_border_color=ACCENT_RED,
            content_padding=ft.padding.symmetric(horizontal=12, vertical=8),
            on_change=self._handle_client_secret_change,
        )

        # Account Status Badge & Button Container
        self.account_status_row = ft.Row(spacing=8, vertical_alignment=ft.CrossAxisAlignment.CENTER)
        self.account_action_container = ft.Container()
        self._refresh_account_status_ui()

        # Build View with Tabs
        self.tabs = ft.Tabs(
            selected_index=0,
            animation_duration=250,
            indicator_color=ACCENT_RED,
            label_color=TEXT_PRIMARY,
            unselected_label_color=TEXT_MUTED,
            tabs=[
                ft.Tab(
                    text="หน้าจอ (Display)",
                    icon=ft.icons.SMARTPHONE_ROUNDED,
                    content=self._build_display_tab(),
                ),
                ft.Tab(
                    text="กรอบรูป (Photos)",
                    icon=ft.icons.PHOTO_LIBRARY_ROUNDED,
                    content=self._build_photo_tab(),
                ),
                ft.Tab(
                    text="บัญชี (Account)",
                    icon=ft.icons.ACCOUNT_CIRCLE_ROUNDED,
                    content=self._build_account_tab(),
                ),
            ],
            expand=True,
        )

        content_col = ft.Column(
            controls=[
                # Top Header Row
                ft.Row(
                    controls=[
                        ft.Row(
                            [
                                ft.Icon(ft.icons.SETTINGS_ROUNDED, size=24, color=ACCENT_RED),
                                ft.Text("Settings & Configuration", size=20, weight=ft.FontWeight.BOLD, color=TEXT_PRIMARY),
                            ],
                            spacing=10,
                        ),
                        ft.ElevatedButton(
                            content=ft.Row([ft.Icon(ft.icons.MUSIC_NOTE_ROUNDED, size=18), ft.Text("Back to Player", weight=ft.FontWeight.BOLD)]),
                            bgcolor=ACCENT_RED,
                            color=TEXT_PRIMARY,
                            style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=10), padding=ft.padding.symmetric(horizontal=16, vertical=10)),
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

    def _refresh_account_status_ui(self) -> None:
        """Updates account badge and login/logout action button."""
        is_logged_in = self.oauth_manager.is_authenticated()
        self.account_status_row.controls.clear()

        if is_logged_in:
            self.account_status_row.controls.extend(
                [
                    ft.Icon(ft.icons.CHECK_CIRCLE_ROUNDED, color=ACCENT_GREEN, size=20),
                    ft.Text("Account:", size=14, color=TEXT_PRIMARY, weight=ft.FontWeight.BOLD),
                    ft.Container(
                        content=ft.Text("Connected (OAuth 2.0)", size=12, color=ACCENT_GREEN, weight=ft.FontWeight.BOLD),
                        padding=ft.padding.symmetric(horizontal=10, vertical=4),
                        border_radius=6,
                        bgcolor="rgba(16, 185, 129, 0.15)",
                    ),
                ]
            )
            self.account_action_container.content = ft.OutlinedButton(
                content=ft.Row([ft.Icon(ft.icons.LOGOUT_ROUNDED, size=18), ft.Text("Disconnect Account")]),
                style=ft.ButtonStyle(
                    color=ACCENT_RED,
                    side=ft.BorderSide(1, "rgba(255, 0, 51, 0.4)"),
                    shape=ft.RoundedRectangleBorder(radius=10),
                    padding=ft.padding.symmetric(horizontal=16, vertical=12),
                ),
                on_click=lambda e: self.on_logout(),
            )
        else:
            self.account_status_row.controls.extend(
                [
                    ft.Icon(ft.icons.ACCOUNT_CIRCLE_OUTLINED, color=TEXT_MUTED, size=20),
                    ft.Text("Account:", size=14, color=TEXT_PRIMARY, weight=ft.FontWeight.BOLD),
                    ft.Container(
                        content=ft.Text("Guest / Unauthenticated", size=12, color=TEXT_MUTED, weight=ft.FontWeight.BOLD),
                        padding=ft.padding.symmetric(horizontal=10, vertical=4),
                        border_radius=6,
                        bgcolor="rgba(255, 255, 255, 0.06)",
                    ),
                ]
            )
            self.account_action_container.content = ft.ElevatedButton(
                content=ft.Row([ft.Icon(ft.icons.LOGIN_ROUNDED, size=18), ft.Text("Sign In with YouTube Music")]),
                bgcolor=ACCENT_RED,
                color=TEXT_PRIMARY,
                style=ft.ButtonStyle(
                    shape=ft.RoundedRectangleBorder(radius=10),
                    padding=ft.padding.symmetric(horizontal=16, vertical=12),
                ),
                on_click=lambda e: self.on_open_login(),
            )

    def _build_display_tab(self) -> ft.Container:
        """Tab for Screen Orientation and Screensaver Timeout."""
        btn_test_saver = ft.ElevatedButton(
            content=ft.Row(
                [
                    ft.Icon(ft.icons.PLAY_CIRCLE_OUTLINE_ROUNDED, size=20),
                    ft.Text("Launch Photo Frame Now", size=14, weight=ft.FontWeight.BOLD),
                ],
                alignment=ft.MainAxisAlignment.CENTER,
            ),
            bgcolor=SURFACE_ELEVATED,
            color=TEXT_PRIMARY,
            style=ft.ButtonStyle(
                shape=ft.RoundedRectangleBorder(radius=12),
                side=ft.BorderSide(1, "rgba(255, 255, 255, 0.2)"),
                padding=ft.padding.symmetric(horizontal=18, vertical=14),
            ),
            on_click=lambda e: self.on_test_screensaver(),
        )

        card_content = ft.Column(
            controls=[
                # Screen Orientation Section
                ft.Row(
                    [
                        ft.Icon(ft.icons.SCREEN_ROTATION_ROUNDED, color=ACCENT_CYAN, size=22),
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
                        ft.Icon(ft.icons.NIGHTLIGHT_ROUNDED, color=ACCENT_RED, size=22),
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
            padding=ft.padding.only(top=12),
            expand=True,
        )

    def _build_photo_tab(self) -> ft.Container:
        """Tab for local photo folder configuration."""
        btn_browse = ft.ElevatedButton(
            content=ft.Row(
                [
                    ft.Icon(ft.icons.FOLDER_OPEN_ROUNDED, size=20),
                    ft.Text("Browse Folder", size=14, weight=ft.FontWeight.BOLD),
                ],
                alignment=ft.MainAxisAlignment.CENTER,
            ),
            bgcolor=ACCENT_RED,
            color=TEXT_PRIMARY,
            style=ft.ButtonStyle(
                shape=ft.RoundedRectangleBorder(radius=12),
                padding=ft.padding.symmetric(horizontal=18, vertical=14),
            ),
            on_click=lambda e: self.on_pick_folder(),
        )

        btn_reset_samples = ft.OutlinedButton(
            content=ft.Row(
                [
                    ft.Icon(ft.icons.RESTART_ALT_ROUNDED, size=18, color=TEXT_SECONDARY),
                    ft.Text("Use Sample Photos", size=13, color=TEXT_SECONDARY),
                ],
                alignment=ft.MainAxisAlignment.CENTER,
            ),
            style=ft.ButtonStyle(
                shape=ft.RoundedRectangleBorder(radius=12),
                side=ft.BorderSide(1, "rgba(255, 255, 255, 0.15)"),
                padding=ft.padding.symmetric(horizontal=14, vertical=12),
            ),
            on_click=self._handle_reset_samples,
        )

        card_content = ft.Column(
            controls=[
                ft.Row(
                    [
                        ft.Icon(ft.icons.IMAGE_ROUNDED, color=ACCENT_CYAN, size=22),
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
                    border=ft.border.all(1, "rgba(255, 255, 255, 0.08)"),
                ),
                ft.Row([btn_browse, btn_reset_samples], spacing=10),
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
            padding=ft.padding.only(top=12),
            expand=True,
        )

    def _build_account_tab(self) -> ft.Container:
        """Tab for YouTube Music OAuth 2.0 Account & Credentials."""
        card_content = ft.Column(
            controls=[
                ft.Row(
                    [
                        ft.Icon(ft.icons.ACCOUNT_CIRCLE_ROUNDED, color=ACCENT_RED, size=22),
                        ft.Text("YouTube Music Account", size=16, weight=ft.FontWeight.BOLD, color=TEXT_PRIMARY),
                    ],
                    spacing=8,
                ),
                ft.Text("Sign in with Google OAuth 2.0 to access your personal playlists and library.", size=12, color=TEXT_MUTED),
                ft.Container(height=4),
                self.account_status_row,
                ft.Container(height=4),
                self.account_action_container,
                ft.Divider(color="rgba(255, 255, 255, 0.08)", height=16),
                ft.ExpansionTile(
                    title=ft.Text("Advanced: Custom Google Cloud Credentials", size=13, color=TEXT_SECONDARY),
                    subtitle=ft.Text("Optionally specify your own Google Cloud OAuth 2.0 Client ID & Secret", size=11, color=TEXT_MUTED),
                    controls=[
                        ft.Container(
                            content=ft.Column(
                                controls=[
                                    self.tf_client_id,
                                    self.tf_client_secret,
                                ],
                                spacing=10,
                            ),
                            padding=ft.padding.symmetric(vertical=8),
                        )
                    ],
                ),
            ],
            spacing=12,
            scroll=ft.ScrollMode.AUTO,
        )

        return ft.Container(
            content=glass_card(content=card_content, padding=20),
            padding=ft.padding.only(top=12),
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
                padding=ft.padding.symmetric(horizontal=12, vertical=10),
                border_radius=10,
                bgcolor="rgba(255, 0, 51, 0.25)" if is_sel else "rgba(255, 255, 255, 0.05)",
                border=ft.border.all(1, ACCENT_RED if is_sel else "rgba(255, 255, 255, 0.1)"),
                alignment=ft.alignment.center,
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
        if getattr(self, "page", None):
            try:
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
                padding=ft.padding.symmetric(horizontal=12, vertical=10),
                border_radius=10,
                bgcolor="rgba(255, 0, 51, 0.25)" if is_sel else "rgba(255, 255, 255, 0.05)",
                border=ft.border.all(1, ACCENT_RED if is_sel else "rgba(255, 255, 255, 0.1)"),
                alignment=ft.alignment.center,
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
        if getattr(self, "page", None):
            try:
                self.update()
            except Exception:
                pass

    def _handle_blur_change(self, e) -> None:
        val = int(e.control.value)
        self.config_mgr.set("background_blur_radius", val)
        self.photo_engine.set_blur_radius(val)
        self.txt_blur_val.value = f"{val}px"
        if getattr(self.txt_blur_val, "page", None):
            try:
                self.txt_blur_val.update()
            except Exception:
                pass

    def _handle_speed_change(self, e) -> None:
        val = int(e.control.value)
        self.config_mgr.set("slideshow_interval_seconds", val)
        self.txt_speed_val.value = f"{val}s"
        if getattr(self.txt_speed_val, "page", None):
            try:
                self.txt_speed_val.update()
            except Exception:
                pass

    def _handle_shuffle_change(self, e) -> None:
        val = bool(e.control.value)
        self.config_mgr.set("slideshow_shuffle", val)
        self.photo_engine.set_shuffle(val)

    def _handle_client_id_change(self, e) -> None:
        val = str(e.control.value).strip()
        self.config_mgr.set("oauth_client_id", val)

    def _handle_client_secret_change(self, e) -> None:
        val = str(e.control.value).strip()
        self.config_mgr.set("oauth_client_secret", val)

    def _handle_reset_samples(self, e) -> None:
        sample_dir = Path("assets/samples").resolve()
        self.config_mgr.set_photo_folder(str(sample_dir))
        self.photo_engine.scan_folder(str(sample_dir))
        self.update_folder_info()

    def update_folder_info(self) -> None:
        """Refreshes folder path and image counter."""
        self.txt_folder_path.value = self.config_mgr.get("photo_folder", "")
        self.txt_photo_count.value = f"{self.photo_engine.total_photos} photos detected (.jpg, .jpeg, .png, .webp)"
        self._refresh_account_status_ui()
        if getattr(self, "page", None):
            try:
                self.update()
            except Exception:
                pass
