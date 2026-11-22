"""
CarPlay / Android Auto-style Music Dashboard View.
Features Split-View layout:
- Left: Large Album Art, Title, Artist, Like button, seek slider and transport controls.
- Right: Menu (Library, Photo Frame, Settings) and the playlist (which is also the play queue).

Refreshes are incremental: playlist rows are built once per song and reused, and each
refresh sends only the controls that changed instead of re-sending the whole view.
"""

from typing import Callable, Dict, List, Optional
import flet as ft

from src.music_backend import Track
from src.services.audio_controller import AudioController
from src.state import AppMode, AppState
from src.ui.theme import (
    ACCENT_RED,
    BORDER_RADIUS_ROUND,
    SURFACE_CARD,
    TEXT_MUTED,
    TEXT_PRIMARY,
    TEXT_SECONDARY,
    THUMB_CACHE_HEIGHT,
    glass_card,
    DEFAULT_ART_URL,
)


def _format_time(seconds: float) -> str:
    return f"{int(seconds // 60):02d}:{int(seconds % 60):02d}"


class _QueueRow:
    """One playlist row. Built once per song; afterwards only its highlight changes."""

    def __init__(self, track: Track, key: str, on_select: Callable[[str], None]):
        self.is_active = False
        self.icon_handle = ft.Icon(ft.Icons.DRAG_HANDLE_ROUNDED, size=20, color=TEXT_MUTED)
        self.txt_title = ft.Text(
            track.title,
            size=14,
            weight=ft.FontWeight.W_500,
            color=TEXT_PRIMARY,
            max_lines=2,
            overflow=ft.TextOverflow.ELLIPSIS,
        )
        self.icon_state = ft.Icon(ft.Icons.ACCESS_TIME_ROUNDED, size=16, color=TEXT_MUTED)
        self.txt_duration = ft.Text(
            track.formatted_duration,
            size=12,
            color=TEXT_MUTED,
            weight=ft.FontWeight.NORMAL,
        )
        self.control = ft.Container(
            key=key,
            content=ft.Row(
                controls=[
                    # Drag handle icon for reordering
                    ft.ReorderableDragHandle(
                        content=ft.Container(content=self.icon_handle, padding=ft.Padding.only(right=2)),
                        mouse_cursor=ft.MouseCursor.GRAB,
                    ),
                    # Mini thumbnail with rounded border
                    ft.Image(
                        src=track.thumb_url or DEFAULT_ART_URL,
                        width=44,
                        height=44,
                        border_radius=8,
                        fit=ft.BoxFit.COVER,
                        cache_height=THUMB_CACHE_HEIGHT,
                    ),
                    # Dedicated spacing container between thumbnail and text
                    ft.Container(width=4),
                    # Track & Artist Column
                    ft.Column(
                        controls=[
                            self.txt_title,
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
                    # Equalizer icon (playing) or clock, then the duration
                    self.icon_state,
                    self.txt_duration,
                ],
                alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                spacing=6,
            ),
            padding=ft.Padding.symmetric(horizontal=10, vertical=8),
            border_radius=10,
            bgcolor="rgba(255, 255, 255, 0.03)",
            ink=True,
            on_click=lambda e: on_select(track.id),
        )

    def set_active(self, active: bool) -> bool:
        """Highlights the playing song. Returns True if anything changed."""
        if active == self.is_active:
            return False
        self.is_active = active
        accent = ACCENT_RED if active else TEXT_MUTED
        self.icon_handle.color = accent
        self.txt_title.weight = ft.FontWeight.BOLD if active else ft.FontWeight.W_500
        self.icon_state.icon = ft.Icons.EQUALIZER_ROUNDED if active else ft.Icons.ACCESS_TIME_ROUNDED
        self.icon_state.color = accent
        self.txt_duration.color = accent
        self.txt_duration.weight = ft.FontWeight.BOLD if active else ft.FontWeight.NORMAL
        self.control.bgcolor = "rgba(255, 0, 51, 0.12)" if active else "rgba(255, 255, 255, 0.03)"
        self.control.border = ft.Border.all(1, "rgba(255, 0, 51, 0.4)") if active else None
        return True


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
        super().__init__(padding=16, expand=True)
        self.state = state
        self.backend = backend
        self.is_portrait = is_portrait
        self.on_interaction = on_interaction or (lambda: None)
        self.on_open_library = on_open_library
        self.on_open_photos = on_open_photos
        self.on_open_settings = on_open_settings
        self._is_user_seeking = False

        # Playlist rows by track id, so a refresh reuses them instead of rebuilding
        self._rows: Dict[str, _QueueRow] = {}
        self._queue_ids: Optional[List[str]] = None
        self._active_row: Optional[_QueueRow] = None

        self.img_art = ft.Image(
            src=DEFAULT_ART_URL,
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

        # --- Transport Controls ---
        self.btn_shuffle = ft.IconButton(
            icon=ft.Icons.SHUFFLE_ROUNDED,
            icon_color=TEXT_MUTED,
            icon_size=22,
            width=48,
            height=48,
            on_click=self._handle_shuffle,
            tooltip="Shuffle",
        )

        self.btn_prev = ft.IconButton(
            icon=ft.Icons.SKIP_PREVIOUS_ROUNDED,
            icon_color=TEXT_PRIMARY,
            icon_size=28,
            on_click=self._handle_prev,
            tooltip="Previous Track",
        )

        self.icon_play_pause = ft.Icon(ft.Icons.PLAY_ARROW_ROUNDED, size=26, color=TEXT_PRIMARY)
        # Shown instead of the icon from the tap until sound starts (stream lookup + buffering)
        self.ring_loading = ft.ProgressRing(width=22, height=22, stroke_width=2.5, color=TEXT_PRIMARY, visible=False)
        self.btn_play_pause = ft.Container(
            content=ft.Stack([self.icon_play_pause, self.ring_loading], alignment=ft.Alignment.CENTER),
            width=52,
            height=52,
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
            icon_size=28,
            on_click=self._handle_next,
            tooltip="Next Track",
        )

        self.btn_repeat = ft.IconButton(
            icon=ft.Icons.REPEAT_ROUNDED,
            icon_color=TEXT_MUTED,
            icon_size=22,
            width=48,
            height=48,
            on_click=self._handle_repeat,
            tooltip="Repeat Mode",
        )

        # --- Seek Bar & Durations ---
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

        # --- Playlist (Reorderable) ---
        self.queue_column = ft.ReorderableListView(
            spacing=6,
            expand=True,
            show_default_drag_handles=False,
            on_reorder=self._handle_queue_reorder,
        )
        self.txt_queue_count = ft.Text("", size=12, color=TEXT_MUTED)

        self.rebuild_layout()
        self.backend.add_listener(self._on_player_changed)
        self.update_view()

    def is_isolated(self) -> bool:
        # Page-level updates (switching to the photo frame or settings) skip this view's
        # controls instead of diffing every playlist row; it sends its own changes.
        return True

    def set_portrait(self, is_portrait: bool) -> None:
        """Re-lays out the view when the device rotates."""
        if is_portrait != self.is_portrait:
            self.is_portrait = is_portrait
            self.rebuild_layout()

    def rebuild_layout(self) -> None:
        """Arranges the player card and the playlist side by side (landscape) or stacked (portrait)."""
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

        # Timeline Row; the once-a-second progress tick updates only this row
        self._timeline_row = ft.Row(
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

        # Unified Player Card (Artwork + Controls)
        self._player_card = glass_card(
            content=ft.Column(
                controls=[
                    art_card,
                    ft.Container(height=0),
                    info_row,
                    ft.Divider(color="rgba(255, 255, 255, 0.08)", height=8),
                    ft.Column(controls=[self._timeline_row, playback_btns_row], spacing=2),
                ],
                spacing=4,
                expand=not is_portrait,
                scroll=ft.ScrollMode.AUTO,
            ),
            padding=ft.Padding(12, 12, 12, 12) if is_portrait else ft.Padding(16, 12, 16, 12),
            expand=False if is_portrait else 1,
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

        # Portrait stacks the two cards with smaller titles; landscape is a 50/50 split
        self.txt_title.size = 16 if is_portrait else 20
        self.txt_artist.size = 12 if is_portrait else 14
        if is_portrait:
            self.content = ft.Column(controls=[self._player_card, queue_panel], spacing=10, expand=True)
        else:
            self.content = ft.Row(controls=[self._player_card, queue_panel], spacing=16, expand=True)

        self._push(self)

    # --- Event Handlers ---
    # The backend notifies its listeners on every change, which refreshes the view.

    def _on_player_changed(self) -> None:
        # Hidden behind the photo frame or settings: main.py refreshes on the way back
        if self.state.mode == AppMode.MUSIC_PLAYER:
            self.update_view()

    def _handle_queue_reorder(self, e: ft.OnReorderEvent) -> None:
        self.on_interaction()
        if e.old_index is None or e.new_index is None or e.old_index == e.new_index:
            return
        self.backend.move_track(e.old_index, e.new_index)

    def _handle_track_select(self, track_id: str) -> None:
        self.on_interaction()
        self.backend.play_track_by_id(track_id)  # Keeps playing if it is already the current song

    def _handle_play_pause(self, e) -> None:
        self.on_interaction()
        self.backend.toggle_play()

    def _handle_next(self, e) -> None:
        self.on_interaction()
        self.backend.next_track()

    def _handle_prev(self, e) -> None:
        self.on_interaction()
        self.backend.prev_track()

    def _handle_shuffle(self, e) -> None:
        self.on_interaction()
        self.backend.toggle_shuffle()

    def _handle_repeat(self, e) -> None:
        self.on_interaction()
        self.backend.cycle_repeat()

    def _handle_like_toggle(self, e) -> None:
        self.on_interaction()
        self.backend.toggle_saved()  # Heart = saved in My Playlist

    def _handle_seek_start(self, e) -> None:
        self.on_interaction()
        self._is_user_seeking = True

    def _handle_seek_end(self, e) -> None:
        self._is_user_seeking = False
        self.backend.seek(float(e.control.value))

    # --- Refresh ---

    def _push(self, *controls: ft.Control) -> None:
        """Sends pending changes of just these controls; a no-op while the view is off the page."""
        if not controls:
            return  # page.update() without arguments would diff the whole page
        try:
            self.page.update(*controls)
        except Exception:
            pass

    def update_view(self, push: bool = True) -> None:
        """
        Syncs every control with the player and sends what changed: the player card
        plus either the two playlist rows whose highlight moved or, when songs were
        added, removed or reordered, the playlist itself.
        Pass push=False while the view is being put back on the page: it is then sent
        whole by that page update.
        """
        self._sync_now_playing()
        self._sync_transport()
        self._sync_progress()
        changed = self._sync_queue()
        if push:
            self._push(self._player_card, *changed)

    def update_progress_only(self) -> None:
        """Once-a-second tick: moves the seek bar and timestamp in a single small update."""
        if not self._is_user_seeking:
            self._sync_progress()
            self._push(self._timeline_row)

    def _sync_now_playing(self) -> None:
        track = self.backend.current_track
        if not track:
            return
        self.img_art.src = track.cover_url or DEFAULT_ART_URL
        self.txt_title.value = track.title
        self.txt_artist.value = track.artist
        self.txt_total.value = track.formatted_duration
        self.slider_progress.max = max(1.0, track.duration_seconds)
        saved = self.backend.is_current_saved
        self.btn_like.icon = ft.Icons.FAVORITE_ROUNDED if saved else ft.Icons.FAVORITE_BORDER_ROUNDED
        self.btn_like.icon_color = ACCENT_RED if saved else TEXT_SECONDARY

    def _sync_transport(self) -> None:
        loading = self.backend.is_loading
        self.ring_loading.visible = loading
        self.icon_play_pause.visible = not loading
        self.icon_play_pause.icon = (
            ft.Icons.PAUSE_ROUNDED if self.backend.is_playing else ft.Icons.PLAY_ARROW_ROUNDED
        )
        self.btn_shuffle.icon_color = ACCENT_RED if self.backend.shuffle else TEXT_MUTED
        repeat = self.backend.repeat
        self.btn_repeat.icon = ft.Icons.REPEAT_ONE_ROUNDED if repeat == "one" else ft.Icons.REPEAT_ROUNDED
        self.btn_repeat.icon_color = TEXT_MUTED if repeat == "off" else ACCENT_RED

    def _sync_progress(self) -> None:
        # Leave the slider alone while it is being scrubbed
        if not self._is_user_seeking:
            pos = self.backend.position_seconds
            self.slider_progress.value = min(pos, self.slider_progress.max)
            self.txt_elapsed.value = _format_time(pos)

    def _sync_queue(self) -> List[ft.Control]:
        """Brings the playlist rows in line with the queue. Returns the controls to send."""
        tracks = self.backend.queue
        ids = [t.id for t in tracks]
        changed: List[ft.Control] = []

        list_changed = ids != self._queue_ids
        if list_changed:
            rows: Dict[str, _QueueRow] = {}
            controls = []
            for index, track in enumerate(tracks):
                if track.id in rows:
                    # Same song saved twice (possible in older playlist files)
                    row = _QueueRow(track, f"queue_track_{track.id}_{index}", self._handle_track_select)
                else:
                    row = self._rows.get(track.id) or _QueueRow(
                        track, f"queue_track_{track.id}", self._handle_track_select
                    )
                    rows[track.id] = row
                controls.append(row.control)
            self._rows = rows
            self._queue_ids = ids
            self.queue_column.controls = controls
            self.txt_queue_count.value = f"{len(ids)} tracks"
            changed += [self.queue_column, self.txt_queue_count]

        current = self.backend.current_track
        active_row = self._rows.get(current.id) if current else None
        if active_row is not self._active_row:
            for row, active in ((self._active_row, False), (active_row, True)):
                # A changed list is sent whole, which covers its rows
                if row and row.set_active(active) and not list_changed:
                    changed.append(row.control)
            self._active_row = active_row
        return changed
