"""
Digital Photo Frame View (Screensaver Mode).
Features dual-layer crossfading with:
1. Fullscreen Ambient Blurred Background (Stretches across entire screen, eliminating black bars)
2. Centered Sharp Foreground Photo (Preserves original aspect ratio without distortion)
3. Ambient live digital clock overlay
4. Fullscreen gesture tap detector for Quick Action wake modal.
"""

from datetime import datetime
from pathlib import Path
from typing import Callable, Optional
import flet as ft
from src.music_backend import BaseMusicBackend
from src.photo_engine import PhotoEngine
from src.state import AppState
from src.ui.theme import (
    ACCENT_RED,
    BG_DARK,
    TEXT_MUTED,
    TEXT_PRIMARY,
    TEXT_SECONDARY,
    TRANSPARENT_IMAGE_BASE64,
)


class PhotoFrameView(ft.Container):
    def __init__(
        self,
        state: AppState,
        photo_engine: PhotoEngine,
        on_tap_wake: Callable[[], None],
        backend: Optional[BaseMusicBackend] = None,
    ):
        self.state = state
        self.photo_engine = photo_engine
        self.on_tap_wake = on_tap_wake
        self.backend = backend
        self._active_layer = 1  # 1: Layer A is visible, 2: Layer B is visible

        initial_photo = self.photo_engine.get_current_photo() or ""
        initial_blur_b64 = self.photo_engine.get_blurred_background(initial_photo) or TRANSPARENT_IMAGE_BASE64

        # ─── Layer A (Fullscreen Background Blur + Centered Foreground) ───
        self.bg_layer_a = ft.Image(
            src_base64=initial_blur_b64,
            fit=ft.ImageFit.COVER,
            opacity=0.65,
            left=0,
            top=0,
            right=0,
            bottom=0,
        )
        self.fg_layer_a = ft.Image(
            src=initial_photo if initial_photo else None,
            src_base64=TRANSPARENT_IMAGE_BASE64 if not initial_photo else None,
            fit=ft.ImageFit.CONTAIN,
        )
        self.container_layer_a = ft.Container(
            content=ft.Stack(
                controls=[
                    self.bg_layer_a,
                    ft.Container(bgcolor="rgba(0, 0, 0, 0.20)", left=0, top=0, right=0, bottom=0),
                    ft.Container(content=self.fg_layer_a, alignment=ft.alignment.center, left=0, top=0, right=0, bottom=0),
                ],
                expand=True,
            ),
            left=0,
            top=0,
            right=0,
            bottom=0,
            opacity=1.0,
            animate_opacity=ft.Animation(1000, ft.AnimationCurve.EASE_IN_OUT),
            expand=True,
        )

        # ─── Layer B (Fullscreen Background Blur + Centered Foreground) ───
        self.bg_layer_b = ft.Image(
            src_base64=initial_blur_b64,
            fit=ft.ImageFit.COVER,
            opacity=0.65,
            left=0,
            top=0,
            right=0,
            bottom=0,
        )
        self.fg_layer_b = ft.Image(
            src=initial_photo if initial_photo else None,
            src_base64=TRANSPARENT_IMAGE_BASE64 if not initial_photo else None,
            fit=ft.ImageFit.CONTAIN,
        )
        self.container_layer_b = ft.Container(
            content=ft.Stack(
                controls=[
                    self.bg_layer_b,
                    ft.Container(bgcolor="rgba(0, 0, 0, 0.20)", left=0, top=0, right=0, bottom=0),
                    ft.Container(content=self.fg_layer_b, alignment=ft.alignment.center, left=0, top=0, right=0, bottom=0),
                ],
                expand=True,
            ),
            left=0,
            top=0,
            right=0,
            bottom=0,
            opacity=0.0,
            animate_opacity=ft.Animation(1000, ft.AnimationCurve.EASE_IN_OUT),
            expand=True,
        )

        # ─── Ambient Overlays (Mini Now Playing & Counter) ───────────────────
        self.img_mini_art = ft.Image(
            src=None,
            width=52,
            height=52,
            border_radius=10,
            fit=ft.ImageFit.COVER,
        )
        self.art_wrapper = ft.Container(
            content=self.img_mini_art,
            border_radius=10,
            shadow=ft.BoxShadow(spread_radius=1, blur_radius=14, color="rgba(0, 0, 0, 0.7)"),
        )
        self.txt_mini_title = ft.Text(
            value="",
            size=14,
            weight=ft.FontWeight.BOLD,
            color=TEXT_PRIMARY,
            max_lines=1,
            overflow=ft.TextOverflow.ELLIPSIS,
            style=ft.TextStyle(shadow=ft.BoxShadow(spread_radius=0, blur_radius=8, color="rgba(0, 0, 0, 0.95)")),
        )
        self.txt_mini_artist = ft.Text(
            value="",
            size=12,
            weight=ft.FontWeight.W_500,
            color="#CBD5E1",
            max_lines=1,
            overflow=ft.TextOverflow.ELLIPSIS,
            style=ft.TextStyle(shadow=ft.BoxShadow(spread_radius=0, blur_radius=6, color="rgba(0, 0, 0, 0.95)")),
        )

        self.mini_player_card = ft.Container(
            content=ft.Row(
                controls=[
                    self.art_wrapper,
                    ft.Column(
                        controls=[
                            self.txt_mini_title,
                            self.txt_mini_artist,
                        ],
                        spacing=2,
                        width=240,
                        tight=True,
                    ),
                    ft.Icon(
                        ft.icons.GRAPHIC_EQ_ROUNDED,
                        size=20,
                        color=ACCENT_RED,
                    ),
                ],
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                spacing=10,
                tight=True,
            ),
            left=24,
            bottom=24,
            visible=False,
        )

        self.txt_counter = ft.Text(
            value=f"{self.photo_engine.current_index} / {self.photo_engine.total_photos}",
            size=12,
            color=TEXT_MUTED,
        )
        self.counter_badge = ft.Container(
            content=self.txt_counter,
            padding=ft.padding.symmetric(horizontal=12, vertical=6),
            border_radius=12,
            bgcolor="rgba(0, 0, 0, 0.6)",
            right=24,
            bottom=24,
        )

        # ─── Master Photo Frame Stack ──────────────────────────────────────
        photo_stack = ft.Stack(
            controls=[
                self.container_layer_b,
                self.container_layer_a,
                # Floating bottom-left Now Playing (Locked to bottom-left)
                self.mini_player_card,
                # Floating bottom-right counter (Locked to bottom-right)
                self.counter_badge,
            ],
            expand=True,
        )

        # GestureDetector wraps photo_stack
        gesture_wrapper = ft.GestureDetector(
            content=photo_stack,
            on_tap=self._handle_screen_tap,
            expand=True,
        )

        # PhotoFrameView is placed inside a Container in main.py, so it only needs expand=True
        super().__init__(
            content=gesture_wrapper,
            bgcolor=BG_DARK,
            padding=0,
            margin=0,
            expand=True,
        )

    def _handle_screen_tap(self, e) -> None:
        """User tapped the photo frame screensaver -> trigger wake action overlay."""
        self.state.reset_idle()
        self.on_tap_wake()

    def advance_photo(self) -> None:
        """Loads next photo, prepares blurred background, and cross-fades layers."""
        next_photo = self.photo_engine.get_next_photo()
        if not next_photo:
            return

        blur_b64 = self.photo_engine.get_blurred_background(next_photo) or TRANSPARENT_IMAGE_BASE64

        self.txt_counter.value = f"{self.photo_engine.current_index} / {self.photo_engine.total_photos}"
        self.update_now_playing()

        # Cross-fade logic between Layer A and Layer B
        if self._active_layer == 1:
            self.fg_layer_b.src = next_photo
            self.bg_layer_b.src_base64 = blur_b64
            self.container_layer_b.opacity = 1.0
            self.container_layer_a.opacity = 0.0
            self._active_layer = 2
        else:
            self.fg_layer_a.src = next_photo
            self.bg_layer_a.src_base64 = blur_b64
            self.container_layer_a.opacity = 1.0
            self.container_layer_b.opacity = 0.0
            self._active_layer = 1

        if getattr(self, "page", None):
            try:
                self.update()
            except Exception:
                pass

    def update_now_playing(self) -> None:
        """Updates the mini now-playing card at bottom-left when music is playing."""
        if not self.backend:
            self.mini_player_card.visible = False
            return

        track = self.backend.current_track
        is_playing = self.backend.is_playing

        if track and is_playing:
            self.img_mini_art.src = track.art_url or "https://images.unsplash.com/photo-1511671782779-c97d3d27a1d4?w=200&q=80"
            self.txt_mini_title.value = track.title
            self.txt_mini_artist.value = track.artist
            self.mini_player_card.visible = True
        else:
            self.mini_player_card.visible = False

        if getattr(self, "page", None):
            try:
                self.mini_player_card.update()
            except Exception:
                pass

    def reload_photos(self) -> None:
        """Refreshes active image upon folder change."""
        current = self.photo_engine.get_current_photo() or ""
        if current:
            blur_b64 = self.photo_engine.get_blurred_background(current) or TRANSPARENT_IMAGE_BASE64
            if self._active_layer == 1:
                self.fg_layer_a.src = current
                self.bg_layer_a.src_base64 = blur_b64
            else:
                self.fg_layer_b.src = current
                self.bg_layer_b.src_base64 = blur_b64

        self.txt_counter.value = f"{self.photo_engine.current_index} / {self.photo_engine.total_photos}"
        if getattr(self, "page", None):
            try:
                self.update()
            except Exception:
                pass
