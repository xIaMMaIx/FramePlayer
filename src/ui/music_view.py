"""
CarPlay / Android Auto-style Music Dashboard View.
Features Split-View layout:
- Left: Ambient Blurred Cover Art Backdrop, Large Album Art, Title, Artist, and Like button.
- Right: Menu (Library, Photo Frame, Settings), large touch controls, seek slider,
         and the playlist (which is also the play queue).
"""

from typing import Callable, Optional
import flet as ft

from src.services.audio_controller import AudioController
from src.state import AppState
from src.ui.theme import (
    ACCENT_RED,
    BORDER_RADIUS_ROUND,
    SURFACE_CARD,
    TEXT_MUTED,
    TEXT_PRIMARY,
    TEXT_SECONDARY,
    glass_card,
    DEFAULT_ART_URL,
)


class MusicPlayerView(ft.Container):
    def __init__(
        self,
        state: AppState,
        backend: AudioController,
        is_portrait: bool = False,
        on_interaction: Optional[Callable[[], None]] = None,
        on_open_library: Optional[Callable[[], None]] = None,
        on_open_photos: Optional[Callable[[], None]] = None,
        on_open_settings: Optional[Callable[[], None]] = None,
    ):
        super().__init__(expand=True)
        self.state = state
        self.backend = backend
        self.is_portrait = is_portrait
        self.on_interaction = on_interaction or (lambda: None)
        self.on_open_library = on_open_library
        self.on_open_photos = on_open_photos
        self.on_open_settings = on_open_settings
        self._is_user_seeking = False

        self.img_art = ft.Image(
            src=self._get_default_art(),
            aspect_ratio=16 / 9,
            fit=ft.BoxFit.COVER,
            border_radius=16,
        )

        self.txt_title = ft.Text(
            value="No Track Playing",
            size=20,
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
            icon=ft.Icons.FAVORITE_BORDER_ROUNDED,
            icon_color=TEXT_SECONDARY,
            icon_size=28,
            on_click=self._handle_like_toggle,
            tooltip="Save to My Playlist",
        )

        # --- Right Panel: Header buttons ---
        self.btn_photos = ft.IconButton(
            icon=ft.Icons.PHOTO_LIBRARY_ROUNDED,
            icon_color=TEXT_SECONDARY,
            icon_size=22,
            tooltip="Photo Frame",
            on_click=lambda e: self.on_open_photos() if self.on_open_photos else None,
        )
        self.btn_settings = ft.IconButton(
            icon=ft.Icons.SETTINGS_ROUNDED,
            icon_color=TEXT_PRIMARY,
            icon_size=24,
            tooltip="Settings",
            on_click=lambda e: self.on_open_settings() if self.on_open_settings else None,
        )

        # --- Right Panel: Controls, Sliders & Mini Queue ---

        # 1. Transport Controls
        self.btn_shuffle = ft.IconButton(
            icon=ft.Icons.SHUFFLE_ROUNDED,
            icon_color=TEXT_MUTED,
            icon_size=24,
            width=48,
            height=48,
            on_click=self._handle_shuffle,
            tooltip="Shuffle",
        )

        self.btn_prev = ft.IconButton(
            icon=ft.Icons.SKIP_PREVIOUS_ROUNDED,
            icon_color=TEXT_PRIMARY,
            icon_size=42,
            on_click=self._handle_prev,
            tooltip="Previous Track",
        )

        self.btn_play_pause = ft.Container(
            content=ft.Icon(
                ft.Icons.PLAY_ARROW_ROUNDED,
                size=44,
                color=TEXT_PRIMARY,
            ),
            width=68,
            height=68,
            border_radius=BORDER_RADIUS_ROUND,
            bgcolor=ACCENT_RED,
            alignment=ft.Alignment.CENTER,
            ink=True,
            on_click=self._handle_play_pause,
            shadow=ft.BoxShadow(
                spread_radius=1,
                blur_radius=14,
                color="rgba(255, 0, 51, 0.4)",
            ),
        )

        self.btn_next = ft.IconButton(
            icon=ft.Icons.SKIP_NEXT_ROUNDED,
            icon_color=TEXT_PRIMARY,
            icon_size=42,
            on_click=self._handle_next,
            tooltip="Next Track",
        )

        self.btn_repeat = ft.IconButton(
            icon=ft.Icons.REPEAT_ROUNDED,
            icon_color=TEXT_MUTED,
            icon_size=24,
            width=48,
            height=48,
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

        # 3. Mini Queue List (Reorderable)
        self.queue_column = ft.ReorderableListView(
            spacing=6,
            expand=True,
            show_default_drag_handles=False,
            on_reorder=self._handle_queue_reorder,
        )

        # Build responsive layout (Landscape vs Portrait)
        super().__init__(
            padding=16,
            expand=True,
        )
        self.txt_queue_count = ft.Text("", size=12, color=TEXT_MUTED)
        self.rebuild_layout()

        if self.backend:
            self.backend.on_track_changed = lambda track: self.update_view()
            self.backend.on_state_changed = lambda: self.update_view()

        self.update_view()

    def _get_default_art(self) -> str:
        return DEFAULT_ART_URL

    def set_portrait(self, is_portrait: bool) -> None:
        """Re-lays out the view when the device rotates."""
        if is_portrait != self.is_portrait:
            self.is_portrait = is_portrait
            self.rebuild_layout()
            try:
                self.update()
            except Exception:
                pass

    def rebuild_layout(self) -> None:
        """Dynamically rebuilds layout with 16:9 widescreen cover art and separated controls."""
        is_portrait = self.is_portrait

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
        
        # Timeline Row
        timeline_row = ft.Row(
            controls=[
                self.txt_elapsed,
                ft.Container(content=self.slider_progress, expand=True),
                self.txt_total,
            ],
            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
            spacing=10,
        )

        # Playback Buttons Row
        playback_btns_row = ft.Row(
            controls=[
                self.btn_shuffle,
                self.btn_prev,
                self.btn_play_pause,
                self.btn_next,
                self.btn_repeat,
            ],
            spacing=8 if is_portrait else 16,
            alignment=ft.MainAxisAlignment.CENTER,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        )

        compact_controls_row = ft.Column(
            controls=[timeline_row, playback_btns_row],
            spacing=2,
        )



        # Unified Player Card (Artwork + Controls)
        player_card = glass_card(
            content=ft.Column(
                controls=[
                    art_card,
                    ft.Container(height=0),
                    info_row,
                    ft.Divider(color="rgba(255, 255, 255, 0.08)", height=8),
                    compact_controls_row,
                ],
                spacing=4,
                expand=True if not is_portrait else False,
                scroll=ft.ScrollMode.AUTO,
            ),
            padding=ft.Padding(16, 12, 16, 12) if not is_portrait else ft.Padding(12, 12, 12, 12),
            expand=1 if not is_portrait else False,
        )

        # Playlist header: tap the title to search and manage songs
        queue_header = ft.Row(
            controls=[
                ft.Container(
                    content=ft.Row(
                        [
                            ft.Icon(ft.Icons.QUEUE_MUSIC_ROUNDED, size=18, color=ACCENT_RED),
                            ft.Text("My Playlist", size=15, weight=ft.FontWeight.BOLD, color=TEXT_PRIMARY),
                            self.txt_queue_count,
                            ft.Icon(ft.Icons.CHEVRON_RIGHT_ROUNDED, size=20, color=TEXT_MUTED),
                        ],
                        spacing=6,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                    padding=ft.Padding.symmetric(horizontal=6, vertical=10),
                    border_radius=10,
                    ink=True,
                    expand=True,
                    tooltip="Search & manage playlist",
                    on_click=lambda e: self.on_open_library() if self.on_open_library else None,
                ),
                self.btn_photos,
                self.btn_settings,
            ],
            spacing=0,
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
            self.btn_play_pause.width = 52
            self.btn_play_pause.height = 52
            if hasattr(self.btn_play_pause.content, "size"):
                self.btn_play_pause.content.size = 26
            self.btn_prev.icon_size = 28
            self.btn_next.icon_size = 28
            self.btn_shuffle.icon_size = 22
            self.btn_repeat.icon_size = 22

            self.content = ft.Column(
                controls=[
                    player_card,
                    queue_panel,
                ],
                spacing=10,
                expand=True,
            )
        else:
            # Sizing for landscape (Equal 50/50 left and right split, sleek inline player)
            self.txt_title.size = 20
            self.txt_artist.size = 14
            self.btn_play_pause.width = 52
            self.btn_play_pause.height = 52
            if hasattr(self.btn_play_pause.content, "size"):
                self.btn_play_pause.content.size = 26
            self.btn_prev.icon_size = 28
            self.btn_next.icon_size = 28
            self.btn_shuffle.icon_size = 22
            self.btn_repeat.icon_size = 22

            self.content = ft.Row(
                controls=[
                    player_card,
                    queue_panel,
                ],
                spacing=16,
                expand=True,
            )

        try:
            self.update()
        except Exception:
            pass

    def _render_queue_list(self) -> None:
        """Renders upcoming tracks with drag handles for live reordering."""
        self.queue_column.controls.clear()
        current_track = self.backend.current_track

        for idx, track in enumerate(self.backend.queue):
            is_active = current_track and current_track.id == track.id
            item = ft.Container(
                key=f"queue_track_{track.id}_{idx}",
                content=ft.Row(
                    controls=[
                        # Drag handle icon for reordering
                        ft.ReorderableDragHandle(
                            content=ft.Container(
                                content=ft.Icon(
                                    ft.Icons.DRAG_HANDLE_ROUNDED,
                                    size=20,
                                    color=ACCENT_RED if is_active else TEXT_MUTED,
                                ),
                                padding=ft.Padding.only(right=2),
                            ),
                            mouse_cursor=ft.MouseCursor.GRAB,
                        ),
                        # Mini thumbnail with rounded border
                        ft.Image(
                            src=track.art_url or self._get_default_art(),
                            width=44,
                            height=44,
                            border_radius=8,
                            fit=ft.BoxFit.COVER,
                        ),
                        # Dedicated spacing container between thumbnail and text
                        ft.Container(width=4),
                        # Track & Artist Column
                        ft.Column(
                            controls=[
                                ft.Text(
                                    track.title,
                                    size=14,
                                    weight=ft.FontWeight.BOLD if is_active else ft.FontWeight.W_500,
                                    color=TEXT_PRIMARY,
                                    max_lines=2,
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
                            ft.Icons.EQUALIZER_ROUNDED if is_active else ft.Icons.ACCESS_TIME_ROUNDED,
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
                    spacing=6,
                ),
                padding=ft.Padding.symmetric(horizontal=10, vertical=8),
                border_radius=10,
                bgcolor="rgba(255, 0, 51, 0.12)" if is_active else "rgba(255, 255, 255, 0.03)",
                border=ft.Border.all(1, "rgba(255, 0, 51, 0.4)") if is_active else None,
                ink=True,
                on_click=lambda e, t_id=track.id: self._handle_track_select(t_id),
            )
            self.queue_column.controls.append(item)

    # --- Event Handlers ---

    def _handle_queue_reorder(self, e: ft.OnReorderEvent) -> None:
        self.on_interaction()
        old_idx = e.old_index
        new_idx = e.new_index
        if old_idx is None or new_idx is None or old_idx == new_idx:
            return

        self.backend.move_track(old_idx, new_idx)
        self.update_view()

    def _handle_track_select(self, track_id: str) -> None:
        self.on_interaction()
        # If clicked track is already the active playing track, keep playing without restarting
        if self.backend.current_track and self.backend.current_track.id == track_id and self.backend.is_playing:
            return

        self.backend.play_track_by_id(track_id)
        self.state.reset_idle()
        self.update_view()

    def _handle_play_pause(self, e) -> None:
        self.on_interaction()
        self.backend.toggle_play()
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
            self.btn_repeat.icon = ft.Icons.REPEAT_ONE_ROUNDED
            self.btn_repeat.icon_color = ACCENT_RED
        elif mode == "all":
            self.btn_repeat.icon = ft.Icons.REPEAT_ROUNDED
            self.btn_repeat.icon_color = ACCENT_RED
        else:
            self.btn_repeat.icon = ft.Icons.REPEAT_ROUNDED
            self.btn_repeat.icon_color = TEXT_MUTED
        if getattr(self.btn_repeat, "page", None):
            self.btn_repeat.update()

    def _handle_like_toggle(self, e) -> None:
        self.on_interaction()
        self.backend.toggle_saved()  # Heart = saved in My Playlist
        self.update_view()

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

        if track:
            art_src = track.art_url or self._get_default_art()
            self.img_art.src = art_src
            
            self.txt_title.value = track.title
            self.txt_artist.value = track.artist
            self.txt_album.value = track.album
            self.txt_total.value = track.formatted_duration
            self.slider_progress.max = max(1.0, track.duration_seconds)
            saved = self.backend.is_current_saved
            self.btn_like.icon = ft.Icons.FAVORITE_ROUNDED if saved else ft.Icons.FAVORITE_BORDER_ROUNDED
            self.btn_like.icon_color = ACCENT_RED if saved else TEXT_SECONDARY

        # Play/Pause Icon
        icon_ctrl = self.btn_play_pause.content
        if hasattr(icon_ctrl, "icon"):
            icon_ctrl.icon = ft.Icons.PAUSE_ROUNDED if is_playing else ft.Icons.PLAY_ARROW_ROUNDED
        elif hasattr(icon_ctrl, "name"):
            icon_ctrl.name = ft.Icons.PAUSE_ROUNDED if is_playing else ft.Icons.PLAY_ARROW_ROUNDED

        # Shuffle & Repeat Highlights
        self.btn_shuffle.icon_color = ACCENT_RED if self.backend.shuffle else TEXT_MUTED
        if self.backend.repeat == "one":
            self.btn_repeat.icon = ft.Icons.REPEAT_ONE_ROUNDED
            self.btn_repeat.icon_color = ACCENT_RED
        elif self.backend.repeat == "all":
            self.btn_repeat.icon = ft.Icons.REPEAT_ROUNDED
            self.btn_repeat.icon_color = ACCENT_RED
        else:
            self.btn_repeat.icon = ft.Icons.REPEAT_ROUNDED
            self.btn_repeat.icon_color = TEXT_MUTED

        # Update progress if not currently being scrubbed
        if not self._is_user_seeking:
            pos = self.backend.position_seconds
            self.slider_progress.value = min(pos, self.slider_progress.max)
            mins = int(pos // 60)
            secs = int(pos % 60)
            self.txt_elapsed.value = f"{mins:02d}:{secs:02d}"

        self.txt_queue_count.value = f"{len(self.backend.queue)} tracks"
        self._render_queue_list()
        try:
            self.update()
        except Exception:
            pass

    def update_progress_only(self) -> None:
        """Lightweight tick update for seeker and timestamp without rebuilding queue."""
        if not self._is_user_seeking:
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
