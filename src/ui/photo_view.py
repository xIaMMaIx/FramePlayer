"""
Digital Photo Frame View (Screensaver Mode).
Features dual-layer crossfading with:
1. Fullscreen Ambient Blurred Background (Stretches across entire screen, eliminating black bars)
2. Centered Sharp Foreground Photo (Preserves original aspect ratio without distortion)
3. Ambient live digital clock overlay
4. Fullscreen gesture tap detector for Quick Action wake modal.
"""

from typing import Callable, Optional
import flet as ft
import flet_video as ftv
from src.services.audio_controller import AudioController
from src.photo_engine import PhotoEngine
from src.state import AppState
from src.ui.theme import (
    ACCENT_RED,
    BG_DARK,
    TEXT_MUTED,
    TEXT_PRIMARY,
    TEXT_SECONDARY,
    TRANSPARENT_IMAGE_BASE64,
    DEFAULT_ART_URL,
)


class PhotoFrameView(ft.Container):
    def __init__(
        self,
        state: AppState,
        photo_engine: PhotoEngine,
        on_tap_wake: Callable[[], None],
        backend: Optional[AudioController] = None,
        config_mgr = None,
    ):
        self.state = state
        self.photo_engine = photo_engine
        self.on_tap_wake = on_tap_wake
        self.backend = backend
        self.config_mgr = config_mgr
        self._active_layer = 1  # 1: Layer A is visible, 2: Layer B is visible

        initial_photo = self.photo_engine.get_current_photo() or ""
        initial_src = self.photo_engine.get_photo_src(initial_photo) or TRANSPARENT_IMAGE_BASE64

        # ─── Layer A (Fullscreen Background Blur + Centered Foreground) ───
        self.bg_layer_a = ft.Image(
            src=initial_src or TRANSPARENT_IMAGE_BASE64,
            fit=ft.BoxFit.COVER,
            opacity=1.0,
            left=0,
            top=0,
            right=0,
            bottom=0,
        )
        self.fg_image_a = ft.Image(
            src=TRANSPARENT_IMAGE_BASE64,
            fit=ft.BoxFit.CONTAIN,
            left=0, top=0, right=0, bottom=0,
        )
        self.fg_video_a = ftv.Video(
            left=0, top=0, right=0, bottom=0,
            autoplay=True,
            visible=False,
            playlist=[],
        )
        self.fg_layer_a = ft.Stack([self.fg_image_a, self.fg_video_a], left=0, top=0, right=0, bottom=0)
        blur_val = self.photo_engine.blur_radius if hasattr(self, "photo_engine") and self.photo_engine else 24
        self.blur_effect_a = ft.Blur(blur_val, blur_val)
        self.container_layer_a = ft.Container(
            content=ft.Stack(
                controls=[
                    self.bg_layer_a,
                    ft.Container(blur=self.blur_effect_a, bgcolor="rgba(0, 0, 0, 0.40)", left=0, top=0, right=0, bottom=0),
                    self.fg_layer_a,
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
            src=initial_src or TRANSPARENT_IMAGE_BASE64,
            fit=ft.BoxFit.COVER,
            opacity=1.0,
            left=0,
            top=0,
            right=0,
            bottom=0,
        )
        self.fg_image_b = ft.Image(
            src=TRANSPARENT_IMAGE_BASE64,
            fit=ft.BoxFit.CONTAIN,
            left=0, top=0, right=0, bottom=0,
        )
        self.fg_video_b = ftv.Video(
            left=0, top=0, right=0, bottom=0,
            autoplay=True,
            visible=False,
            playlist=[],
        )
        self.fg_layer_b = ft.Stack([self.fg_image_b, self.fg_video_b], left=0, top=0, right=0, bottom=0)
        
        # Initial images
        self._set_image_source(self.bg_layer_a, initial_src)
        self._set_media_source(True, initial_src)
        self._set_image_source(self.bg_layer_b, initial_src)
        self._set_media_source(False, initial_src)

        self.blur_effect_b = ft.Blur(blur_val, blur_val)
        self.container_layer_b = ft.Container(
            content=ft.Stack(
                controls=[
                    self.bg_layer_b,
                    ft.Container(blur=self.blur_effect_b, bgcolor="rgba(0, 0, 0, 0.40)", left=0, top=0, right=0, bottom=0),
                    self.fg_layer_b,
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
            fit=ft.BoxFit.COVER,
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
                        ft.Icons.GRAPHIC_EQ_ROUNDED,
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
            padding=ft.Padding.symmetric(horizontal=12, vertical=6),
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


    def _set_media_source(self, is_layer_a: bool, src_val: str) -> None:
        is_vid = hasattr(self.photo_engine, "is_video") and self.photo_engine.is_video(src_val) if src_val else False
        img_control = self.fg_image_a if is_layer_a else self.fg_image_b
        vid_control = self.fg_video_a if is_layer_a else self.fg_video_b
        
        img_control.visible = not is_vid
        vid_control.visible = is_vid
        
        fit_mode = self._get_fit_mode()
        img_control.fit = fit_mode
        vid_control.fit = ft.BoxFit.COVER if fit_mode == ft.BoxFit.COVER else ft.BoxFit.CONTAIN
        
        if is_vid:
            muted = self.backend is not None and self.backend.current_track is not None
            vid_control.muted = muted
            vid_control.playlist = [ftv.VideoMedia(src_val)]
        else:
            if vid_control.playlist:
                vid_control.playlist.clear()
            self._set_image_source(img_control, src_val)

    def _set_image_source(self, img: ft.Image, src_val: str) -> None:
        if not src_val:
            img.src = TRANSPARENT_IMAGE_BASE64 # Transparent pixel
        else:
            img.src = src_val

    def advance_photo(self) -> None:
        blur_val = self.photo_engine.blur_radius if hasattr(self, "photo_engine") and self.photo_engine else 24
        self.blur_effect_a.sigma_x = blur_val
        self.blur_effect_a.sigma_y = blur_val
        self.blur_effect_b.sigma_x = blur_val
        self.blur_effect_b.sigma_y = blur_val

        """Loads next photo, prepares blurred background, and cross-fades layers."""
        next_photo = self.photo_engine.get_next_photo()
        if not next_photo:
            return

        photo_src = self.photo_engine.get_photo_src(next_photo) or TRANSPARENT_IMAGE_BASE64

        self.txt_counter.value = f"{self.photo_engine.current_index} / {self.photo_engine.total_photos}"
        self.update_now_playing()

        # Cross-fade logic between Layer A and Layer B
        if self._active_layer == 1:
            self._set_media_source(False, photo_src)
            self._set_image_source(self.bg_layer_b, photo_src)
            self.container_layer_b.opacity = 1.0
            self.container_layer_a.opacity = 0.0
            self._active_layer = 2
        else:
            self._set_media_source(True, photo_src)
            self._set_image_source(self.bg_layer_a, photo_src)
            self.container_layer_a.opacity = 1.0
            self.container_layer_b.opacity = 0.0
            self._active_layer = 1

        try:
            self.update()
        except Exception:
            pass

    def _get_fit_mode(self):
        if not hasattr(self, "config_mgr") or not self.config_mgr:
            return ft.BoxFit.CONTAIN
        return ft.BoxFit.COVER if self.config_mgr.get("photo_fill_mode") == "cover" else ft.BoxFit.CONTAIN

    def apply_settings(self) -> None:
        """Applies configuration changes immediately."""
        fit_mode = self._get_fit_mode()
        
        self.fg_image_a.fit = fit_mode
        self.fg_image_b.fit = fit_mode
        vid_fit = ft.BoxFit.COVER if fit_mode == ft.BoxFit.COVER else ft.BoxFit.CONTAIN
        self.fg_video_a.fit = vid_fit
        self.fg_video_b.fit = vid_fit
        
        show_bg = fit_mode == ft.BoxFit.CONTAIN
        self.bg_layer_a.visible = show_bg
        self.bg_layer_b.visible = show_bg
        
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
            self.img_mini_art.src = track.art_url or DEFAULT_ART_URL
            self.txt_mini_title.value = track.title
            self.txt_mini_artist.value = track.artist
            self.mini_player_card.visible = True
        else:
            self.mini_player_card.visible = False

        try:
            self.mini_player_card.update()
        except Exception:
            pass

    def reload_photos(self) -> None:
        blur_val = self.photo_engine.blur_radius if hasattr(self, "photo_engine") and self.photo_engine else 24
        self.blur_effect_a.sigma_x = blur_val
        self.blur_effect_a.sigma_y = blur_val
        self.blur_effect_b.sigma_x = blur_val
        self.blur_effect_b.sigma_y = blur_val

        """Refreshes active image upon folder change."""
        current = self.photo_engine.get_current_photo() or ""
        if current:
            photo_src = self.photo_engine.get_photo_src(current) or TRANSPARENT_IMAGE_BASE64
            if self._active_layer == 1:
                self._set_media_source(True, photo_src)
                self._set_image_source(self.bg_layer_a, photo_src)
            else:
                self._set_media_source(False, photo_src)
                self._set_image_source(self.bg_layer_b, photo_src)

        self.txt_counter.value = f"{self.photo_engine.current_index} / {self.photo_engine.total_photos}"
        try:
            self.update()
        except Exception:
            pass
