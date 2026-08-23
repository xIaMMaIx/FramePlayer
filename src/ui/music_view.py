"""
CarPlay / Android Auto-style Music Dashboard View.
Features Split-View layout:
- Left: Ambient Blurred Cover Art Backdrop, Large Album Art, Title, Artist, and Like button.
- Right: Quick Action Header (Connect YouTube, Library, Photo Frame, Settings),
         Jumbo Touch Controls, Seek Slider, Volume, and Upcoming Queue list.
"""

import base64
import io
from pathlib import Path
import re
from typing import Callable, Dict, List, Optional
import flet as ft
try:
    from PIL import Image, ImageFilter, ImageEnhance
except ImportError:
    Image = None
    ImageFilter = None
    ImageEnhance = None
import requests

from src.config_manager import ConfigManager
from src.music_backend import BaseMusicBackend, Track
from src.services.oauth_manager import OAuthManager
from src.state import AppState
from src.ui.theme import (
    ACCENT_CYAN,
    ACCENT_GREEN,
    ACCENT_RED,
    BORDER_RADIUS_CARD,
    BORDER_RADIUS_ROUND,
    SURFACE_CARD,
    SURFACE_ELEVATED,
    SURFACE_TRANSLUCENT,
    TEXT_MUTED,
    TEXT_PRIMARY,
    TEXT_SECONDARY,
    glass_card,
)

TRANSPARENT_IMAGE_BASE64 = (
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII="
)


class MusicPlayerView(ft.Container):
    def __init__(
        self,
        state: AppState,
        backend: BaseMusicBackend,
        oauth_manager: Optional[OAuthManager] = None,
        config_mgr: Optional[ConfigManager] = None,
        on_interaction: Optional[Callable[[], None]] = None,
        on_open_library: Optional[Callable[[], None]] = None,
        on_open_login: Optional[Callable[[], None]] = None,
        on_open_photos: Optional[Callable[[], None]] = None,
        on_open_settings: Optional[Callable[[], None]] = None,
    ):
        super().__init__(expand=True)
        self.state = state
        self.backend = backend
        self.oauth_manager = oauth_manager
        self.config_mgr = config_mgr
        self.on_interaction = on_interaction or (lambda: None)
        self.on_open_library = on_open_library
        self.on_open_login = on_open_login
        self.on_open_photos = on_open_photos
        self.on_open_settings = on_open_settings
        self._is_user_seeking = False
        self._art_blur_cache: Dict[str, str] = {}

        self.img_art_blur = ft.Image(
            src_base64=self._get_blurred_cover_art(self._get_default_art()),
            fit=ft.ImageFit.COVER,
        )

        self.img_art_sharp_bg = ft.Image(
            src=self._get_default_art(),
            fit=ft.ImageFit.COVER,
        )

        self.img_art = ft.Image(
            src=self._get_default_art(),
            aspect_ratio=16 / 9,
            fit=ft.ImageFit.COVER,
            border_radius=16,
        )

        self.txt_title = ft.Text(
            value="No Track Playing",
            size=22,
            weight=ft.FontWeight.W_800,
            color=TEXT_PRIMARY,
            max_lines=1,
            overflow=ft.TextOverflow.ELLIPSIS,
        )

        self.txt_artist = ft.Text(
            value="Select a track to start",
            size=15,
            weight=ft.FontWeight.W_500,
            color=TEXT_SECONDARY,
            max_lines=1,
            overflow=ft.TextOverflow.ELLIPSIS,
        )

        self.txt_album = ft.Text(
            value="",
            size=12,
            weight=ft.FontWeight.W_400,
            color=TEXT_MUTED,
            max_lines=1,
            overflow=ft.TextOverflow.ELLIPSIS,
        )

        self.btn_like = ft.IconButton(
            icon=ft.icons.FAVORITE_BORDER_ROUNDED,
            icon_color=TEXT_SECONDARY,
            icon_size=28,
            on_click=self._handle_like_toggle,
            tooltip="Add to Liked Songs",
        )

        # --- Right Panel: Quick Actions Toolbar (Icon-Only) ---
        self.btn_account_action = ft.Container(
            content=ft.Icon(ft.icons.LOCK_OPEN_ROUNDED, size=20, color=TEXT_PRIMARY),
            padding=8,
            border_radius=10,
            bgcolor=ACCENT_RED,
            ink=True,
            on_click=lambda e: self.on_open_login() if self.on_open_login else None,
            tooltip="Sign in to YouTube Music via QR Code",
        )

        self.btn_quick_library = ft.Container(
            content=ft.Icon(ft.icons.PLAYLIST_PLAY_ROUNDED, size=22, color=ACCENT_RED),
            padding=8,
            border_radius=10,
            bgcolor="rgba(255, 0, 51, 0.15)",
            border=ft.border.all(1.2, "rgba(255, 0, 51, 0.4)"),
            ink=True,
            on_click=lambda e: self.on_open_library() if self.on_open_library else None,
            tooltip="Manage Local Playlist, Search & Add Songs",
        )

        self.btn_quick_photos = ft.Container(
            content=ft.Icon(ft.icons.PHOTO_LIBRARY_ROUNDED, size=20, color=ACCENT_CYAN),
            padding=8,
            border_radius=10,
            bgcolor="rgba(62, 166, 255, 0.15)",
            border=ft.border.all(1.2, "rgba(62, 166, 255, 0.4)"),
            ink=True,
            on_click=lambda e: self.on_open_photos() if self.on_open_photos else None,
            tooltip="Launch Photo Slideshow Screensaver",
        )

        self.btn_quick_settings = ft.Container(
            content=ft.Icon(ft.icons.SETTINGS_ROUNDED, size=20, color=TEXT_SECONDARY),
            padding=8,
            border_radius=10,
            bgcolor="rgba(255, 255, 255, 0.06)",
            border=ft.border.all(1, "rgba(255, 255, 255, 0.15)"),
            ink=True,
            on_click=lambda e: self.on_open_settings() if self.on_open_settings else None,
            tooltip="Open Settings",
        )

        # --- Right Panel: Controls, Sliders & Mini Queue ---

        # 1. Transport Controls
        self.btn_shuffle = ft.IconButton(
            icon=ft.icons.SHUFFLE_ROUNDED,
            icon_color=TEXT_MUTED,
            icon_size=28,
            on_click=self._handle_shuffle,
            tooltip="Shuffle",
        )

        self.btn_prev = ft.IconButton(
            icon=ft.icons.SKIP_PREVIOUS_ROUNDED,
            icon_color=TEXT_PRIMARY,
            icon_size=42,
            on_click=self._handle_prev,
            tooltip="Previous Track",
        )

        self.btn_play_pause = ft.Container(
            content=ft.Icon(
                ft.icons.PLAY_ARROW_ROUNDED,
                size=44,
                color=TEXT_PRIMARY,
            ),
            width=68,
            height=68,
            border_radius=BORDER_RADIUS_ROUND,
            bgcolor=ACCENT_RED,
            alignment=ft.alignment.center,
            ink=True,
            on_click=self._handle_play_pause,
            shadow=ft.BoxShadow(
                spread_radius=1,
                blur_radius=14,
                color="rgba(255, 0, 51, 0.4)",
            ),
        )

        self.btn_next = ft.IconButton(
            icon=ft.icons.SKIP_NEXT_ROUNDED,
            icon_color=TEXT_PRIMARY,
            icon_size=42,
            on_click=self._handle_next,
            tooltip="Next Track",
        )

        self.btn_repeat = ft.IconButton(
            icon=ft.icons.REPEAT_ROUNDED,
            icon_color=TEXT_MUTED,
            icon_size=28,
            on_click=self._handle_repeat,
            tooltip="Repeat Mode",
        )

        # 2. Seek Bar & Durations
        self.txt_elapsed = ft.Text("00:00", size=12, color=TEXT_SECONDARY, weight=ft.FontWeight.W_500)
        self.txt_total = ft.Text("00:00", size=12, color=TEXT_SECONDARY, weight=ft.FontWeight.W_500)
        self.slider_progress = ft.Slider(
            min=0.0,
            max=100.0,
            value=0.0,
            active_color=ACCENT_RED,
            inactive_color="rgba(255, 255, 255, 0.15)",
            thumb_color=TEXT_PRIMARY,
            on_change_start=self._handle_seek_start,
            on_change_end=self._handle_seek_end,
        )

        # 3. Mini Queue List
        self.queue_column = ft.Column(spacing=6, scroll=ft.ScrollMode.AUTO)

        # Build responsive layout (Landscape vs Portrait)
        super().__init__(
            padding=16,
            expand=True,
        )
        self.rebuild_layout()

        if self.backend:
            self.backend.on_track_changed = lambda track: self.update_view()
            self.backend.on_state_changed = lambda: self.update_view()

        self.update_view()

    def _get_default_art(self) -> str:
        return "https://images.unsplash.com/photo-1511671782779-c97d3d27a1d4?w=600&auto=format&fit=crop&q=80"

    def _get_blurred_cover_art(self, art_url: Optional[str]) -> Optional[str]:
        """Generates Gaussian-blurred base64 cover art with user-configured blur radius."""
        if not Image or not art_url:
            return None

        radius = self.config_mgr.get("background_blur_radius", 24) if self.config_mgr else 24
        cache_key = f"{art_url}_{radius}"
        if cache_key in self._art_blur_cache:
            return self._art_blur_cache[cache_key]

        try:
            resp = requests.get(art_url, timeout=4)
            if resp.status_code == 200:
                with Image.open(io.BytesIO(resp.content)) as img:
                    img = img.convert("RGB")
                    w, h = img.size

                    if h > 0 and (w / h) < 1.6:
                        crop_top = int(h * 0.12)
                        crop_bottom = int(h * 0.88)
                        img = img.crop((0, crop_top, w, crop_bottom))

                    enhancer = ImageEnhance.Color(img)
                    img = enhancer.enhance(1.40)
                    bright = ImageEnhance.Brightness(img)
                    img = bright.enhance(1.15)

                    bg = img.resize((380, 520), Image.Resampling.BILINEAR)
                    blurred = bg.filter(ImageFilter.GaussianBlur(radius=radius))
                    buf = io.BytesIO()
                    blurred.save(buf, format="JPEG", quality=85)
                    b64_str = base64.b64encode(buf.getvalue()).decode("utf-8")
                    self._art_blur_cache[cache_key] = b64_str
                    return b64_str
        except Exception as e:
            print(f"[MusicView] Error generating blurred art base64: {e}")

        return None

    def _refresh_account_button(self) -> None:
        """Refreshes the Connect YouTube / Account button based on auth state (Icon-only)."""
        is_logged_in = self.oauth_manager.is_authenticated() if self.oauth_manager else False

        if is_logged_in:
            self.btn_account_action.content = ft.Icon(ft.icons.CHECK_CIRCLE_ROUNDED, size=20, color=ACCENT_GREEN)
            self.btn_account_action.bgcolor = "rgba(0, 230, 118, 0.15)"
            self.btn_account_action.border = ft.border.all(1.2, "rgba(0, 230, 118, 0.4)")
            self.btn_account_action.on_click = lambda e: self.on_open_settings() if self.on_open_settings else None
            self.btn_account_action.tooltip = "Connected to YouTube Music. Tap to manage."
        else:
            self.btn_account_action.content = ft.Icon(ft.icons.LOCK_OPEN_ROUNDED, size=20, color=TEXT_PRIMARY)
            self.btn_account_action.bgcolor = ACCENT_RED
            self.btn_account_action.border = None
            self.btn_account_action.on_click = lambda e: self.on_open_login() if self.on_open_login else None
            self.btn_account_action.tooltip = "Sign in to YouTube Music via QR Code"

    def rebuild_layout(self) -> None:
        """Dynamically rebuilds layout with 16:9 widescreen cover art and separated controls."""
        is_portrait = False
        if self.config_mgr:
            is_portrait = self.config_mgr.get("orientation", "landscape") == "portrait"

        # 16:9 Widescreen Cover Card
        art_card = ft.Container(
            content=self.img_art,
            border_radius=16,
            clip_behavior=ft.ClipBehavior.ANTI_ALIAS,
            shadow=ft.BoxShadow(
                spread_radius=0,
                blur_radius=14,
                color="rgba(0, 0, 0, 0.4)",
            ),
        )

        # Track Info Row (Title, Artist, Like)
        info_row = ft.Row(
            controls=[
                ft.Column(
                    controls=[
                        self.txt_title,
                        self.txt_artist,
                    ],
                    spacing=2,
                    expand=True,
                ),
                self.btn_like,
            ],
            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        )

        # Single Combined Inline Controls & Seeker Row (Compact layout)
        compact_controls_row = ft.Row(
            controls=[
                ft.Row(
                    controls=[
                        self.btn_shuffle,
                        self.btn_prev,
                        self.btn_play_pause,
                        self.btn_next,
                        self.btn_repeat,
                    ],
                    spacing=2 if is_portrait else 4,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                ),
                self.txt_elapsed,
                ft.Container(content=self.slider_progress, expand=True),
                self.txt_total,
            ],
            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
            spacing=6 if is_portrait else 10,
        )

        # Dedicated Controls Card (Expands to bottom in landscape, controls stay top-aligned)
        controls_card = glass_card(
            content=ft.Column(
                controls=[
                    info_row,
                    compact_controls_row,
                ],
                alignment=ft.MainAxisAlignment.START,
                spacing=8 if is_portrait else 12,
            ),
            padding=12 if is_portrait else 16,
            expand=True if not is_portrait else False,
            bgcolor=SURFACE_CARD,
        )

        # Top Quick Actions Toolbar
        quick_actions_row = ft.Row(
            controls=[
                ft.Row(
                    [
                        ft.Icon(ft.icons.MUSIC_NOTE_ROUNDED, size=20, color=ACCENT_RED),
                        ft.Text("YouTube Music", size=15, weight=ft.FontWeight.W_800, color=TEXT_PRIMARY),
                    ],
                    spacing=6,
                ),
                ft.Row(
                    [
                        self.btn_account_action,
                        self.btn_quick_library,
                        self.btn_quick_photos,
                        self.btn_quick_settings,
                    ],
                    spacing=8,
                ),
            ],
            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        )

        # Upcoming Queue Header
        queue_header = ft.Row(
            controls=[
                ft.Row(
                    [
                        ft.Icon(ft.icons.QUEUE_MUSIC_ROUNDED, size=18, color=ACCENT_RED),
                        ft.Text("Upcoming Queue", size=15, weight=ft.FontWeight.BOLD, color=TEXT_PRIMARY),
                    ],
                    spacing=6,
                ),
                ft.Text(f"{len(self.backend.queue)} tracks", size=12, color=TEXT_MUTED),
            ],
            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        )

        # Queue Container
        queue_card = ft.Container(
            content=self.queue_column,
            expand=True,
            border_radius=12,
            bgcolor="rgba(0, 0, 0, 0.2)",
            padding=8,
        )

        # Queue and Toolbar Panel
        queue_panel = glass_card(
            content=ft.Column(
                controls=[
                    quick_actions_row,
                    ft.Divider(color="rgba(255, 255, 255, 0.08)", height=12),
                    queue_header,
                    queue_card,
                ],
                spacing=8,
                expand=True,
            ),
            padding=14 if is_portrait else 16,
            expand=1,
            bgcolor=SURFACE_CARD,
        )

        if is_portrait:
            # Sizing for portrait (Compact inline buttons)
            self.txt_title.size = 16
            self.txt_artist.size = 12
            self.btn_play_pause.width = 44
            self.btn_play_pause.height = 44
            if hasattr(self.btn_play_pause.content, "size"):
                self.btn_play_pause.content.size = 26
            self.btn_prev.icon_size = 24
            self.btn_next.icon_size = 24
            self.btn_shuffle.icon_size = 16
            self.btn_repeat.icon_size = 16

            self.content = ft.Column(
                controls=[
                    art_card,
                    controls_card,
                    queue_panel,
                ],
                spacing=10,
                expand=True,
            )
        else:
            # Sizing for landscape (Equal 50/50 left and right split, sleek inline player)
            self.txt_title.size = 20
            self.txt_artist.size = 14
            self.btn_play_pause.width = 48
            self.btn_play_pause.height = 48
            if hasattr(self.btn_play_pause.content, "size"):
                self.btn_play_pause.content.size = 28
            self.btn_prev.icon_size = 28
            self.btn_next.icon_size = 28
            self.btn_shuffle.icon_size = 18
            self.btn_repeat.icon_size = 18

            left_player_col = ft.Column(
                controls=[
                    art_card,
                    controls_card,
                ],
                spacing=12,
                expand=1,
            )

            self.content = ft.Row(
                controls=[
                    left_player_col,
                    queue_panel,
                ],
                spacing=16,
                expand=True,
            )

        if getattr(self, "page", None):
            try:
                self.update()
            except Exception:
                pass

    def _render_queue_list(self) -> None:
        """Renders upcoming tracks with spaced list tiles and clean thumbnail margins."""
        self.queue_column.controls.clear()
        current_track = self.backend.current_track

        for track in self.backend.queue:
            is_active = current_track and current_track.id == track.id
            item = ft.Container(
                content=ft.Row(
                    controls=[
                        # Mini thumbnail with rounded border
                        ft.Image(
                            src=track.art_url or self._get_default_art(),
                            width=48,
                            height=48,
                            border_radius=8,
                            fit=ft.ImageFit.COVER,
                        ),
                        # Dedicated spacing container between thumbnail and text
                        ft.Container(width=6),
                        # Track & Artist Column
                        ft.Column(
                            controls=[
                                ft.Text(
                                    track.title,
                                    size=14,
                                    weight=ft.FontWeight.BOLD if is_active else ft.FontWeight.W_500,
                                    color=ACCENT_RED if is_active else TEXT_PRIMARY,
                                    max_lines=1,
                                    overflow=ft.TextOverflow.ELLIPSIS,
                                ),
                                ft.Text(
                                    track.artist,
                                    size=12,
                                    color=TEXT_SECONDARY,
                                    max_lines=1,
                                    overflow=ft.TextOverflow.ELLIPSIS,
                                ),
                            ],
                            spacing=2,
                            expand=True,
                        ),
                        # Equalizer icon or duration
                        ft.Icon(
                            ft.icons.EQUALIZER_ROUNDED if is_active else ft.icons.ACCESS_TIME_ROUNDED,
                            size=16,
                            color=ACCENT_RED if is_active else TEXT_MUTED,
                        ),
                        ft.Text(
                            track.formatted_duration,
                            size=12,
                            color=ACCENT_RED if is_active else TEXT_MUTED,
                            weight=ft.FontWeight.BOLD if is_active else ft.FontWeight.NORMAL,
                        ),
                    ],
                    alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    spacing=8,
                ),
                padding=ft.padding.symmetric(horizontal=12, vertical=8),
                border_radius=10,
                bgcolor="rgba(255, 0, 51, 0.12)" if is_active else "rgba(255, 255, 255, 0.03)",
                border=ft.border.all(1, "rgba(255, 0, 51, 0.4)") if is_active else None,
                ink=True,
                on_click=lambda e, t_id=track.id: self._handle_track_select(t_id),
            )
            self.queue_column.controls.append(item)

    # --- Event Handlers ---

    def _handle_track_select(self, track_id: str) -> None:
        self.on_interaction()
        # If clicked track is already the active playing track, keep playing without restarting
        if self.backend.current_track and self.backend.current_track.id == track_id and self.backend.is_playing:
            return

        self.backend.play_track_by_id(track_id)
        self.state.is_playing = True
        self.state.reset_idle()
        self.update_view()

    def _handle_play_pause(self, e) -> None:
        self.on_interaction()
        is_now_playing = self.backend.toggle_play()
        self.state.is_playing = is_now_playing
        self.state.reset_idle()
        self.update_view()

    def _handle_next(self, e) -> None:
        self.on_interaction()
        self.backend.next_track()
        self.state.reset_idle()
        self.update_view()

    def _handle_prev(self, e) -> None:
        self.on_interaction()
        self.backend.prev_track()
        self.state.reset_idle()
        self.update_view()

    def _handle_shuffle(self, e) -> None:
        self.on_interaction()
        is_shuffled = self.backend.toggle_shuffle()
        self.btn_shuffle.icon_color = ACCENT_RED if is_shuffled else TEXT_MUTED
        if getattr(self.btn_shuffle, "page", None):
            self.btn_shuffle.update()
        self.update_view()

    def _handle_repeat(self, e) -> None:
        self.on_interaction()
        mode = self.backend.cycle_repeat()
        if mode == "one":
            self.btn_repeat.icon = ft.icons.REPEAT_ONE_ROUNDED
            self.btn_repeat.icon_color = ACCENT_RED
        elif mode == "all":
            self.btn_repeat.icon = ft.icons.REPEAT_ROUNDED
            self.btn_repeat.icon_color = ACCENT_RED
        else:
            self.btn_repeat.icon = ft.icons.REPEAT_ROUNDED
            self.btn_repeat.icon_color = TEXT_MUTED
        if getattr(self.btn_repeat, "page", None):
            self.btn_repeat.update()

    def _handle_like_toggle(self, e) -> None:
        self.on_interaction()
        is_liked = self.backend.toggle_like()
        self.btn_like.icon = ft.icons.FAVORITE_ROUNDED if is_liked else ft.icons.FAVORITE_BORDER_ROUNDED
        self.btn_like.icon_color = ACCENT_RED if is_liked else TEXT_SECONDARY
        if getattr(self.btn_like, "page", None):
            self.btn_like.update()

    def _handle_seek_start(self, e) -> None:
        self.on_interaction()
        self._is_user_seeking = True

    def _handle_seek_end(self, e) -> None:
        self._is_user_seeking = False
        target_pos = float(e.control.value)
        self.backend.seek(target_pos)
        self.update_view()

    def update_view(self) -> None:
        """Full refresh of music view controls, blurred background, and metadata."""
        track = self.backend.current_track
        is_playing = self.backend.is_playing

        self._refresh_account_button()

        if track:
            art_src = track.art_url or self._get_default_art()
            self.img_art.src = art_src
            self.img_art_sharp_bg.src = art_src
            b64 = self._get_blurred_cover_art(track.art_url)
            self.img_art_blur.src_base64 = b64
            try:
                self.img_art_blur.update()
            except Exception:
                pass
            
            self.txt_title.value = track.title
            self.txt_artist.value = track.artist
            self.txt_album.value = track.album
            self.txt_total.value = track.formatted_duration
            self.slider_progress.max = max(1.0, track.duration_seconds)
            self.btn_like.icon = (
                ft.icons.FAVORITE_ROUNDED if getattr(track, "is_liked", False) else ft.icons.FAVORITE_BORDER_ROUNDED
            )
            self.btn_like.icon_color = ACCENT_RED if getattr(track, "is_liked", False) else TEXT_SECONDARY

        # Play/Pause Icon
        icon_ctrl = self.btn_play_pause.content
        icon_ctrl.name = ft.icons.PAUSE_ROUNDED if is_playing else ft.icons.PLAY_ARROW_ROUNDED

        # Shuffle & Repeat Highlights
        self.btn_shuffle.icon_color = ACCENT_RED if self.backend.shuffle else TEXT_MUTED
        if self.backend.repeat == "one":
            self.btn_repeat.icon = ft.icons.REPEAT_ONE_ROUNDED
            self.btn_repeat.icon_color = ACCENT_RED
        elif self.backend.repeat == "all":
            self.btn_repeat.icon = ft.icons.REPEAT_ROUNDED
            self.btn_repeat.icon_color = ACCENT_RED
        else:
            self.btn_repeat.icon = ft.icons.REPEAT_ROUNDED
            self.btn_repeat.icon_color = TEXT_MUTED

        try:
            self.update()
        except Exception:
            pass

        # Update progress if not currently being scrubbed
        if not self._is_user_seeking:
            pos = self.backend.position_seconds
            self.slider_progress.value = min(pos, self.slider_progress.max)
            mins = int(pos // 60)
            secs = int(pos % 60)
            self.txt_elapsed.value = f"{mins:02d}:{secs:02d}"

        self._render_queue_list()
        if getattr(self, "page", None):
            try:
                self.update()
            except Exception:
                pass

    def update_progress_only(self) -> None:
        """Lightweight tick update for seeker and timestamp without rebuilding queue."""
        if not self._is_user_seeking and getattr(self, "page", None):
            try:
                pos = self.backend.position_seconds
                self.slider_progress.value = min(pos, self.slider_progress.max)
                mins = int(pos // 60)
                secs = int(pos % 60)
                self.txt_elapsed.value = f"{mins:02d}:{secs:02d}"
                self.slider_progress.update()
                self.txt_elapsed.update()
            except Exception:
                pass
