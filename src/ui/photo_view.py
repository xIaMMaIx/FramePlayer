"""
Digital Photo Frame View (Screensaver Mode).
Two cross-fading layers, each with:
1. A fullscreen ambient backdrop: a tiny pre-blurred copy of the photo stretched over
   the screen (no black bars, and no blur filter running on the GPU)
2. The sharp photo or video on top (original aspect ratio, or cropped in "Fill" mode)
Plus a mini now-playing card, a photo counter and a fullscreen tap detector.

Photos are decoded on a worker thread, and only once the frame is first shown, so
neither app startup nor the UI event loop pays for them.
"""

import asyncio
from typing import Callable, Optional
import flet as ft
import flet_video as ftv
from src.services.audio_controller import AudioController
from src.photo_engine import PhotoEngine, Slide
from src.state import AppMode, AppState
from src.ui.theme import (
    ACCENT_RED,
    BG_DARK,
    TEXT_MUTED,
    TEXT_PRIMARY,
    TRANSPARENT_IMAGE_BASE64,
    DEFAULT_ART_URL,
)

FADE_MS = 1000


class _Layer:
    """One cross-fade layer: backdrop, dimmer, and the photo or video."""

    def __init__(self, opacity: float):
        self.backdrop = ft.Image(
            src=TRANSPARENT_IMAGE_BASE64,
            fit=ft.BoxFit.COVER,
            left=0, top=0, right=0, bottom=0,
        )
        self.dimmer = ft.Container(bgcolor="rgba(0, 0, 0, 0.40)", left=0, top=0, right=0, bottom=0)
        self.image = ft.Image(
            src=TRANSPARENT_IMAGE_BASE64,
            fit=ft.BoxFit.CONTAIN,
            left=0, top=0, right=0, bottom=0,
        )
        self.video = ftv.Video(
            left=0, top=0, right=0, bottom=0,
            autoplay=True,
            visible=False,
            playlist=[],
        )
        self.container = ft.Container(
            content=ft.Stack(
                controls=[
                    self.backdrop,
                    self.dimmer,
                    ft.Stack([self.image, self.video], left=0, top=0, right=0, bottom=0),
                ],
                expand=True,
            ),
            left=0,
            top=0,
            right=0,
            bottom=0,
            opacity=opacity,
            animate_opacity=ft.Animation(FADE_MS, ft.AnimationCurve.EASE_IN_OUT),
            expand=True,
        )

    def set_fit(self, fit: ft.BoxFit) -> None:
        self.image.fit = fit
        self.video.fit = fit
        # A photo that fills the screen hides the backdrop completely
        show_backdrop = fit == ft.BoxFit.CONTAIN
        self.backdrop.visible = show_backdrop
        self.dimmer.visible = show_backdrop

    def show(self, slide: Optional[Slide], mute_video: bool) -> None:
        """Loads a slide into this layer; None empties it (and stops its video)."""
        is_video = bool(slide and slide.is_video)
        self.image.visible = not is_video
        self.video.visible = is_video
        self.backdrop.src = (slide.backdrop if slide else None) or TRANSPARENT_IMAGE_BASE64
        if is_video:
            self.video.muted = mute_video
            self.video.playlist = [ftv.VideoMedia(slide.src)]
            self.image.src = TRANSPARENT_IMAGE_BASE64
        else:
            if self.video.playlist:
                self.video.playlist.clear()
            self.image.src = slide.src if slide else TRANSPARENT_IMAGE_BASE64


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

        # Both layers start empty; the first photo fades in when the frame is first shown
        self._active = _Layer(opacity=1.0)
        self._hidden = _Layer(opacity=0.0)
        self._shown_path: Optional[str] = None
        self._show_seq = 0  # Bumped per request so a slow decode never overwrites a newer photo
        self._preload_task: Optional[asyncio.Task] = None

        # ─── Ambient Overlays (Mini Now Playing & Counter) ───────────────────
        self.img_mini_art = ft.Image(
            src=TRANSPARENT_IMAGE_BASE64,
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

        self.txt_counter = ft.Text(value=self._counter_text(), size=12, color=TEXT_MUTED)
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
                self._hidden.container,
                self._active.container,
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

        if self.backend:
            self.backend.add_listener(self._on_player_changed)

    def _handle_screen_tap(self, e) -> None:
        """User tapped the photo frame screensaver -> back to the player."""
        self.state.reset_idle()
        self.on_tap_wake()

    def _push(self) -> None:
        try:
            self.update()
        except Exception:
            pass

    def _counter_text(self) -> str:
        return f"{self.photo_engine.current_index} / {self.photo_engine.total_photos}"

    def _get_fit_mode(self) -> ft.BoxFit:
        if self.config_mgr and self.config_mgr.get("photo_fill_mode") == "cover":
            return ft.BoxFit.COVER
        return ft.BoxFit.CONTAIN

    # ─── Slideshow ────────────────────────────────────────────────────────

    def on_show(self) -> None:
        """
        Call when the frame becomes visible (before the page update that reveals it):
        applies the current settings and loads the current photo if it is not up yet.
        """
        fit = self._get_fit_mode()
        self._active.set_fit(fit)
        self._hidden.set_fit(fit)
        self.update_now_playing(push=False)
        self.txt_counter.value = self._counter_text()
        current = self.photo_engine.get_current_photo()
        if current and current != self._shown_path:
            self._show_soon(current)

    async def advance_photo(self) -> None:
        """Cross-fades to the next photo."""
        await self._show(self.photo_engine.get_next_photo())

    def reload_photos(self) -> None:
        """Call after the photo folder was rescanned."""
        self._shown_path = None
        self.txt_counter.value = self._counter_text()
        if self.state.mode == AppMode.PHOTO_FRAME:
            self._show_soon(self.photo_engine.get_current_photo())
        else:
            self._push()  # The photo itself loads the next time the frame is shown

    def _show_soon(self, photo_path: Optional[str]) -> None:
        try:
            self.page.run_task(self._show, photo_path)
        except Exception as e:
            print(f"[PhotoFrame] Could not start loading a photo: {e}")

    async def _show(self, photo_path: Optional[str]) -> None:
        """Decodes a photo off the event loop, then cross-fades it in on the hidden layer."""
        self._show_seq += 1
        seq = self._show_seq
        slide = await asyncio.to_thread(self.photo_engine.load_slide, photo_path)
        if seq != self._show_seq:
            return  # A newer request took over while this one was decoding

        self.txt_counter.value = self._counter_text()
        if slide is None:
            self._push()  # Unreadable file: keep the current photo up
            return

        mute_video = self.backend is not None and self.backend.current_track is not None
        incoming, outgoing = self._hidden, self._active
        incoming.set_fit(self._get_fit_mode())
        incoming.show(slide, mute_video)
        incoming.container.opacity = 1.0
        outgoing.container.opacity = 0.0
        self._active, self._hidden = incoming, outgoing
        self._shown_path = photo_path
        self._push()

        asyncio.get_running_loop().call_later(FADE_MS / 1000 + 0.2, self._after_fade, seq)

    def _after_fade(self, seq: int) -> None:
        """Once the fade is over: free the layer that faded out and pre-load the next photo."""
        if seq != self._show_seq:
            return
        # Emptying the hidden layer releases its photo and stops a video that would
        # otherwise keep decoding behind the visible one.
        self._hidden.show(None, mute_video=True)
        self._push()
        # Decoding now, between fades, keeps the animation smooth and makes the next
        # change instant.
        self._preload_task = asyncio.get_running_loop().create_task(
            asyncio.to_thread(self.photo_engine.load_slide, self.photo_engine.peek_next_photo())
        )

    # ─── Now playing ──────────────────────────────────────────────────────

    def _on_player_changed(self) -> None:
        if self.state.mode == AppMode.PHOTO_FRAME:
            self.update_now_playing()

    def update_now_playing(self, push: bool = True) -> None:
        """Shows the mini now-playing card at bottom-left while music is playing."""
        track = self.backend.current_track if self.backend else None
        visible = bool(track and self.backend.is_playing)
        if visible:
            self.img_mini_art.src = track.thumb_url or DEFAULT_ART_URL
            self.txt_mini_title.value = track.title
            self.txt_mini_artist.value = track.artist
        self.mini_player_card.visible = visible

        if push:
            try:
                self.mini_player_card.update()
            except Exception:
                pass
