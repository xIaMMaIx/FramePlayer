"""
Library drawer: search YouTube Music at the top, the saved playlist below.
The playlist is also the play queue, so playing a search result adds it to the playlist.

Rows are built when the drawer first opens and kept until the playlist changes, and a
single edit (save, delete, reorder) touches just the row it concerns instead of
rebuilding the list.
"""

import asyncio
from typing import Callable, Dict, List, Optional
import flet as ft

from src.music_backend import Track
from src.services.audio_controller import AudioController
from src.services.ytmusic_service import YTMusicService
from src.ui.theme import (
    ACCENT_CYAN,
    ACCENT_GREEN,
    ACCENT_RED,
    TEXT_MUTED,
    TEXT_PRIMARY,
    TEXT_SECONDARY,
    THUMB_CACHE_HEIGHT,
)

FALLBACK_THUMB_URL = "https://images.unsplash.com/photo-1511671782779-c97d3d27a1d4?w=200&q=80"


class LibraryDrawer(ft.Container):
    def __init__(
        self,
        ytmusic_service: YTMusicService,
        audio_controller: AudioController,
        on_playlist_modified: Optional[Callable[[], None]] = None,
        on_close: Optional[Callable[[], None]] = None,
        async_runner: Optional[Callable] = None,
    ):
        self.ytmusic_service = ytmusic_service
        self.audio_controller = audio_controller
        self.on_playlist_modified = on_playlist_modified or (lambda: None)
        self.on_close_callback = on_close
        self.async_runner = async_runner

        self._is_searching = False
        self._search_results: List[Track] = []

        # What the current rows were built from (see open_drawer), and handles to
        # them for single-row updates
        self._rendered: Optional[tuple] = None
        self._playlist_list: Optional[ft.ReorderableListView] = None
        self._playlist_tiles: Dict[str, ft.Container] = {}
        self._txt_playlist_title: Optional[ft.Text] = None
        self._save_buttons: Dict[str, List[ft.IconButton]] = {}

        # UI Controls
        self.spinner = ft.ProgressRing(width=22, height=22, stroke_width=2.5, color=ACCENT_RED, visible=False)

        # Search Bar Controls
        self.tf_search = ft.TextField(
            hint_text="Search song or artist on YouTube to add...",
            hint_style=ft.TextStyle(color=TEXT_MUTED, size=13),
            bgcolor="rgba(255, 255, 255, 0.06)",
            border_color="rgba(255, 255, 255, 0.12)",
            focused_border_color=ACCENT_RED,
            text_size=13,
            color=TEXT_PRIMARY,
            content_padding=ft.Padding.symmetric(horizontal=14, vertical=10),
            on_submit=self._handle_search,
            expand=True,
            border_radius=10,
        )

        self.btn_search = ft.IconButton(
            icon=ft.Icons.SEARCH_ROUNDED,
            icon_color=TEXT_PRIMARY,
            bgcolor=ACCENT_RED,
            icon_size=20,
            on_click=self._handle_search,
            tooltip="Search YouTube",
        )

        self.btn_clear_search = ft.IconButton(
            icon=ft.Icons.CLEAR_ROUNDED,
            icon_color=TEXT_MUTED,
            icon_size=20,
            visible=False,
            on_click=self._handle_clear_search,
            tooltip="Clear Search & Show My Playlist",
        )

        self.search_row = ft.Row(
            controls=[
                self.tf_search,
                self.btn_clear_search,
                self.btn_search,
            ],
            spacing=8,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        )

        # Main Scrollable Content List
        self.content_list = ft.ListView(
            spacing=8,
            padding=ft.Padding.only(right=6, bottom=16),
            expand=True,
        )
        # Isolated: updating the drawer or the page (open/close, mode switches) does not
        # walk every row. Row changes are sent by updating the list or the row itself.
        self.content_list._isolated = True

        # Build Drawer Box Content
        drawer_content = ft.Column(
            controls=[
                # Top Title & Close Header
                ft.Row(
                    controls=[
                        ft.Row(
                            [
                                ft.Icon(ft.Icons.PLAYLIST_PLAY_ROUNDED, size=24, color=ACCENT_RED),
                                ft.Text("Manage Playlist", size=18, weight=ft.FontWeight.BOLD, color=TEXT_PRIMARY),
                            ],
                            spacing=8,
                        ),
                        ft.Row(
                            [
                                self.spinner,
                                ft.IconButton(
                                    icon=ft.Icons.CLOSE_ROUNDED,
                                    icon_color=TEXT_SECONDARY,
                                    icon_size=22,
                                    on_click=lambda e: self.close_drawer(),
                                    tooltip="Close Drawer",
                                ),
                            ],
                            spacing=8,
                        ),
                    ],
                    alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                ),
                # Always-visible Search Bar
                self.search_row,
                ft.Divider(color="rgba(255, 255, 255, 0.08)", height=8),
                # Main Content
                self.content_list,
            ],
            spacing=12,
            expand=True,
        )

        self.backdrop_area = ft.Container(
            expand=True,
            on_click=lambda e: self.close_drawer(),
        )

        self.drawer_box = ft.Container(
            content=drawer_content,
            width=520,
            bgcolor="#131722",
            border_radius=ft.BorderRadius(top_left=20, bottom_left=20, top_right=0, bottom_right=0),
            border=ft.Border.all(1.2, "rgba(255, 255, 255, 0.12)"),
            padding=16,
            shadow=ft.BoxShadow(spread_radius=8, blur_radius=30, color="rgba(0, 0, 0, 0.8)"),
            alignment=ft.Alignment.CENTER,
        )

        self.drawer_row = ft.Row(
            controls=[
                self.backdrop_area,
                self.drawer_box,
            ],
            expand=True,
            spacing=0,
        )

        super().__init__(
            content=ft.SafeArea(content=self.drawer_row, expand=True),
            bgcolor="rgba(0, 0, 0, 0.65)",
            expand=True,
            visible=False,
        )

    def open_drawer(self) -> None:
        self.visible = True

        # Adaptive width for 9:16 Portrait vs 16:9 Landscape
        try:
            page_w = getattr(self.page, "width", None) if getattr(self, "page", None) else None
            if page_w and page_w < 600:
                # Mobile / Tablet 9:16 Portrait mode
                self.backdrop_area.visible = False
                self.drawer_box.width = None
                self.drawer_box.expand = True
                self.drawer_box.border_radius = ft.BorderRadius(0, 0, 0, 0)
                self.drawer_box.padding = 12
            else:
                # Landscape / Desktop mode
                self.backdrop_area.visible = True
                self.drawer_box.width = min(540, int(page_w * 0.7)) if page_w else 520
                self.drawer_box.expand = False
                self.drawer_box.border_radius = ft.BorderRadius(top_left=20, bottom_left=20, top_right=0, bottom_right=0)
                self.drawer_box.padding = 16
        except Exception:
            pass

        # Building the rows is the expensive part of opening the drawer, so the ones
        # from last time are kept unless the playlist changed in the meantime.
        rows_changed = True
        if self._is_searching:
            if self._rendered != self._search_signature():
                self._render_search_results(push=False)
            else:
                self._restyle_save_buttons()
        elif self._rendered != self._playlist_signature():
            self._render_local_playlist(push=False)
        else:
            rows_changed = False
        self._push(self, *([self.content_list] if rows_changed else []))

    def close_drawer(self) -> None:
        if not self.visible:
            return
        self.visible = False
        try:
            self.update()
        except Exception:
            pass
        if self.on_close_callback:
            self.on_close_callback()

    def _playlist_signature(self) -> tuple:
        return ("playlist", tuple(t.id for t in self.audio_controller.queue))

    def _search_signature(self) -> tuple:
        return ("search", tuple(t.id for t in self._search_results), self.ytmusic_service.last_search_error)

    def _clear_rows(self) -> None:
        self.content_list.controls.clear()
        self._rendered = None
        self._playlist_list = None
        self._playlist_tiles = {}
        self._txt_playlist_title = None
        self._save_buttons = {}

    def _push(self, *controls: ft.Control) -> None:
        """
        Sends pending changes of just these controls. Pushing the drawer itself covers
        its frame (visibility, search bar, spinner) but not the rows in content_list.
        """
        if not controls:
            return  # page.update() without arguments would diff the whole page
        try:
            self.page.update(*controls)
        except Exception:
            pass

    def _dispatch(self, coro):
        if self.async_runner:
            return self.async_runner(coro)
        loop = asyncio.get_event_loop()
        return loop.create_task(coro)

    # ─── Local Playlist View ──────────────────────────────────────────

    def _render_local_playlist(self, push: bool = True) -> None:
        """Renders the saved playlist with a Play All header and a reorderable list."""
        self._clear_rows()
        self._rendered = self._playlist_signature()
        tracks = self.audio_controller.queue

        # Header Info Row
        self._txt_playlist_title = ft.Text(
            f"My Playlist ({len(tracks)})", size=14, weight=ft.FontWeight.BOLD, color=TEXT_PRIMARY
        )
        header = ft.Row(
            controls=[
                ft.Row(
                    [
                        ft.Icon(ft.Icons.QUEUE_MUSIC_ROUNDED, size=18, color=ACCENT_RED),
                        self._txt_playlist_title,
                    ],
                    spacing=4,
                ),
                ft.ElevatedButton(
                    content=ft.Row([ft.Icon(ft.Icons.PLAY_ARROW_ROUNDED, size=15), ft.Text("Play All", size=12, weight=ft.FontWeight.BOLD)], spacing=4),
                    bgcolor=ACCENT_RED,
                    color=TEXT_PRIMARY,
                    style=ft.ButtonStyle(
                        shape=ft.RoundedRectangleBorder(radius=8),
                        padding=ft.Padding.symmetric(horizontal=10, vertical=6),
                    ),
                    on_click=self._handle_play_all,
                    disabled=(len(tracks) == 0),
                ),
            ],
            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
        )
        self.content_list.controls.append(header)
        self.content_list.controls.append(ft.Container(height=4))

        if not tracks:
            self.content_list.controls.append(
                ft.Container(
                    content=ft.Column(
                        [
                            ft.Icon(ft.Icons.PLAYLIST_ADD_ROUNDED, size=46, color=TEXT_MUTED),
                            ft.Text("Your local playlist is empty.", size=14, color=TEXT_SECONDARY, weight=ft.FontWeight.BOLD),
                            ft.Text("Use the search bar above to find and add songs from YouTube!", size=12, color=TEXT_MUTED),
                        ],
                        horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                        spacing=6,
                    ),
                    alignment=ft.Alignment.CENTER,
                    padding=40,
                )
            )
        else:
            reorder_list = ft.ReorderableListView(
                spacing=6,
                expand=True,
                show_default_drag_handles=False,
                on_reorder=self._handle_playlist_reorder,
            )
            for idx, track in enumerate(tracks):
                if track.id in self._playlist_tiles:
                    # Same song saved twice (possible in older playlist files)
                    tile = self._build_local_track_tile(track, f"pl_track_{track.id}_{idx}")
                else:
                    tile = self._build_local_track_tile(track, f"pl_track_{track.id}")
                    self._playlist_tiles[track.id] = tile
                reorder_list.controls.append(tile)
            self._playlist_list = reorder_list
            self.content_list.controls.append(reorder_list)

        if push:
            self._push(self, self.content_list)

    def _handle_play_all(self, e) -> None:
        tracks = self.audio_controller.queue
        if tracks:
            self._play(tracks[0])

    def _build_local_track_tile(self, track: Track, key: str) -> ft.Container:
        """Constructs list tile for local playlist with Drag Handle, Play and Delete actions."""
        return ft.Container(
            key=key,
            content=ft.Row(
                controls=[
                    # Drag Handle for Reordering
                    ft.ReorderableDragHandle(
                        content=ft.Container(
                            content=ft.Icon(ft.Icons.DRAG_HANDLE_ROUNDED, size=18, color=TEXT_MUTED),
                            padding=ft.Padding.only(right=2),
                        ),
                        mouse_cursor=ft.MouseCursor.GRAB,
                    ),
                    ft.Image(
                        src=track.thumb_url or FALLBACK_THUMB_URL,
                        width=40,
                        height=40,
                        border_radius=6,
                        fit=ft.BoxFit.COVER,
                        cache_height=THUMB_CACHE_HEIGHT,
                    ),
                    ft.Container(width=2),
                    ft.Column(
                        controls=[
                            ft.Text(track.title, size=12, weight=ft.FontWeight.BOLD, color=TEXT_PRIMARY, max_lines=1, overflow=ft.TextOverflow.ELLIPSIS),
                            ft.Text(track.artist, size=10, color=TEXT_SECONDARY, max_lines=1, overflow=ft.TextOverflow.ELLIPSIS),
                        ],
                        spacing=1,
                        expand=True,
                    ),
                    ft.Text(track.formatted_duration, size=10, color=TEXT_MUTED),
                    # Play Button
                    ft.IconButton(
                        icon=ft.Icons.PLAY_CIRCLE_FILLED_ROUNDED,
                        icon_color=ACCENT_RED,
                        icon_size=24,
                        on_click=lambda e, t=track: self._play(t),
                        tooltip="Play this track",
                    ),
                    # Delete Button
                    ft.IconButton(
                        icon=ft.Icons.DELETE_OUTLINE_ROUNDED,
                        icon_color="rgba(255, 100, 100, 0.8)",
                        icon_size=20,
                        on_click=lambda e, t_id=track.id: self._handle_delete_track(t_id),
                        tooltip="Remove from Local Playlist",
                    ),
                ],
                alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                spacing=4,
            ),
            padding=ft.Padding.symmetric(horizontal=6, vertical=4),
            border_radius=8,
            bgcolor="rgba(255, 255, 255, 0.03)",
            border=ft.Border.all(1, "rgba(255, 255, 255, 0.06)"),
            ink=True,
            on_click=lambda e, t=track: self._play(t),
        )

    def _handle_playlist_reorder(self, e: ft.OnReorderEvent) -> None:
        old_idx = e.old_index
        new_idx = e.new_index
        if old_idx is None or new_idx is None or old_idx == new_idx:
            return

        self.audio_controller.move_track(old_idx, new_idx)
        self.on_playlist_modified()

        # Move the one tile, the same way the playlist moved the song
        tiles = e.control.controls
        if 0 <= old_idx < len(tiles) and 0 <= new_idx < len(tiles):
            tiles.insert(new_idx, tiles.pop(old_idx))
            self._rendered = self._playlist_signature()
            self._push(e.control)
        else:
            self._render_local_playlist()

    def _handle_delete_track(self, track_id: str) -> None:
        """Removes a song from the playlist (it keeps playing if it is the current one)."""
        self.audio_controller.remove_track(track_id)
        self.on_playlist_modified()
        if self._is_searching:
            self._render_search_results()
            return

        tracks = self.audio_controller.queue
        tile = self._playlist_tiles.pop(track_id, None)
        tiles = self._playlist_list.controls if self._playlist_list else []
        if tile is None or not tracks or len(tiles) - 1 != len(tracks):
            self._render_local_playlist()  # Now empty, or the rows are out of step with the playlist
            return
        tiles.remove(tile)
        self._txt_playlist_title.value = f"My Playlist ({len(tracks)})"
        self._rendered = self._playlist_signature()
        self._push(self._playlist_list, self._txt_playlist_title)

    # ─── YouTube Search & Add Songs ───────────────────────────────────

    def _handle_search(self, e) -> None:
        query = self.tf_search.value.strip()
        if not query:
            self._handle_clear_search(None)
            return
        self._is_searching = True
        self.btn_clear_search.visible = True
        self._dispatch(self._run_search(query))

    def _handle_clear_search(self, e) -> None:
        self._is_searching = False
        self.tf_search.value = ""
        self.btn_clear_search.visible = False
        self._search_results.clear()
        self._render_local_playlist()

    async def _run_search(self, query: str) -> None:
        self.spinner.visible = True
        self._clear_rows()
        self._push(self, self.content_list)

        loop = asyncio.get_running_loop()
        try:
            tracks = await loop.run_in_executor(None, self.ytmusic_service.search_tracks, query, 30)
        except Exception as ex:
            tracks = []
            self.ytmusic_service.last_search_error = f"{type(ex).__name__}: {ex}"
        self.spinner.visible = False
        self._search_results = tracks
        self._render_search_results()

    def _render_search_results(self, push: bool = True) -> None:
        self._clear_rows()
        self._rendered = self._search_signature()

        # Search Results Header
        header = ft.Row(
            controls=[
                ft.Row(
                    [
                        ft.Icon(ft.Icons.SEARCH_ROUNDED, size=18, color=ACCENT_CYAN),
                        ft.Text(f"Search Results ({len(self._search_results)} found)", size=14, weight=ft.FontWeight.BOLD, color=TEXT_PRIMARY),
                    ],
                    spacing=6,
                ),
                ft.TextButton(
                    content=ft.Row([ft.Icon(ft.Icons.ARROW_BACK_ROUNDED, size=16), ft.Text("Back to My Playlist")]),
                    style=ft.ButtonStyle(color=TEXT_SECONDARY),
                    on_click=self._handle_clear_search,
                ),
            ],
            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
        )
        self.content_list.controls.append(header)
        self.content_list.controls.append(ft.Container(height=4))

        if not self._search_results:
            error = self.ytmusic_service.last_search_error
            message = (
                f"Search failed — check your internet connection.\n{error}"
                if error
                else "No songs found. Try a different search term."
            )
            self.content_list.controls.append(
                ft.Container(
                    content=ft.Column(
                        [
                            ft.Icon(ft.Icons.CLOUD_OFF_ROUNDED if error else ft.Icons.SEARCH_OFF_ROUNDED, size=40, color=TEXT_MUTED),
                            ft.Text(message, size=13, color=TEXT_MUTED, text_align=ft.TextAlign.CENTER, selectable=True),
                        ],
                        horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                        spacing=6,
                    ),
                    alignment=ft.Alignment.CENTER,
                    padding=40,
                )
            )
        else:
            for track in self._search_results:
                self.content_list.controls.append(self._build_search_result_tile(track))

        if push:
            self._push(self, self.content_list)

    def _build_search_result_tile(self, track: Track) -> ft.Container:
        """Search result tile: play (adds to the playlist) and add/remove toggle."""
        btn_add = ft.IconButton(
            icon=ft.Icons.ADD_CIRCLE_OUTLINE_ROUNDED,
            icon_size=24,
            on_click=lambda e, t=track: self._toggle_saved(t),
        )
        self._style_save_button(btn_add, self.audio_controller.playlist.contains(track.id))
        self._save_buttons.setdefault(track.id, []).append(btn_add)

        return ft.Container(
            content=ft.Row(
                controls=[
                    ft.Image(
                        src=track.thumb_url or FALLBACK_THUMB_URL,
                        width=40,
                        height=40,
                        border_radius=6,
                        fit=ft.BoxFit.COVER,
                        cache_height=THUMB_CACHE_HEIGHT,
                    ),
                    ft.Container(width=2),
                    ft.Column(
                        controls=[
                            ft.Text(track.title, size=12, weight=ft.FontWeight.BOLD, color=TEXT_PRIMARY, max_lines=1, overflow=ft.TextOverflow.ELLIPSIS),
                            ft.Text(track.artist, size=10, color=TEXT_SECONDARY, max_lines=1, overflow=ft.TextOverflow.ELLIPSIS),
                        ],
                        spacing=1,
                        expand=True,
                    ),
                    ft.Text(track.formatted_duration, size=10, color=TEXT_MUTED),
                    # Play Preview Button
                    ft.IconButton(
                        icon=ft.Icons.PLAY_CIRCLE_FILLED_ROUNDED,
                        icon_color=ACCENT_RED,
                        icon_size=24,
                        on_click=lambda e, t=track: self._play(t),
                        tooltip="Play (adds to My Playlist)",
                    ),
                    # Add to Local Playlist Button
                    btn_add,
                ],
                alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                spacing=4,
            ),
            padding=ft.Padding.symmetric(horizontal=6, vertical=4),
            border_radius=8,
            bgcolor="rgba(255, 255, 255, 0.03)",
            border=ft.Border.all(1, "rgba(255, 255, 255, 0.06)"),
        )

    @staticmethod
    def _style_save_button(button: ft.IconButton, is_saved: bool) -> None:
        button.icon = ft.Icons.CHECK_CIRCLE_ROUNDED if is_saved else ft.Icons.ADD_CIRCLE_OUTLINE_ROUNDED
        button.icon_color = ACCENT_GREEN if is_saved else ACCENT_CYAN
        button.tooltip = "Remove from My Playlist" if is_saved else "Add to My Playlist"

    def _toggle_saved(self, track: Track) -> None:
        playlist = self.audio_controller.playlist
        if playlist.contains(track.id):
            self.audio_controller.remove_track(track.id)
        else:
            playlist.add(track)
        self.on_playlist_modified()

        # Only this song's button changes
        buttons = self._save_buttons.get(track.id, [])
        for button in buttons:
            self._style_save_button(button, playlist.contains(track.id))
        self._push(*buttons)

    def _restyle_save_buttons(self) -> None:
        """Songs may have been saved or removed elsewhere while the drawer was closed."""
        playlist = self.audio_controller.playlist
        for track_id, buttons in self._save_buttons.items():
            for button in buttons:
                self._style_save_button(button, playlist.contains(track_id))

    def _play(self, track: Track) -> None:
        self.audio_controller.play_track(track)
        self.close_drawer()
        self.on_playlist_modified()
