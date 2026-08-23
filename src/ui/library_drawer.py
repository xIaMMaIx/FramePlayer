"""
Unified Local Playlist Manager & YouTube Search Drawer.
Single-screen interface:
- Search YouTube Music directly at the top to add songs
- Manage & play saved local tracks below
- No tabs, completely streamlined
"""

import asyncio
from typing import Any, Callable, Dict, List, Optional
import flet as ft

from src.music_backend import Track
from src.services.audio_controller import AudioController
from src.services.local_playlist_manager import LocalPlaylistManager
from src.services.oauth_manager import OAuthManager
from src.services.ytmusic_service import YTMusicService
from src.ui.theme import (
    ACCENT_CYAN,
    ACCENT_GREEN,
    ACCENT_RED,
    BORDER_RADIUS_CARD,
    SURFACE_CARD,
    SURFACE_ELEVATED,
    SURFACE_TRANSLUCENT,
    TEXT_MUTED,
    TEXT_PRIMARY,
    TEXT_SECONDARY,
    glass_card,
)


class LibraryDrawer(ft.Container):
    def __init__(
        self,
        ytmusic_service: YTMusicService,
        audio_controller: AudioController,
        local_playlist_mgr: LocalPlaylistManager,
        oauth_manager: Optional[OAuthManager] = None,
        on_playlist_modified: Optional[Callable[[], None]] = None,
        on_track_selected: Optional[Callable[[], None]] = None,
        on_open_login: Optional[Callable[[], None]] = None,
        on_close: Optional[Callable[[], None]] = None,
        async_runner: Optional[Callable] = None,
    ):
        self.ytmusic_service = ytmusic_service
        self.audio_controller = audio_controller
        self.local_playlist_mgr = local_playlist_mgr
        self.oauth_manager = oauth_manager
        self.on_playlist_modified = on_playlist_modified or (lambda: None)
        self.on_track_selected = on_track_selected or (lambda: None)
        self.on_open_login = on_open_login
        self.on_close_callback = on_close
        self.async_runner = async_runner

        self._is_searching = False
        self._search_results: List[Track] = []

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
            content_padding=ft.padding.symmetric(horizontal=14, vertical=10),
            on_submit=self._handle_search,
            expand=True,
            border_radius=10,
        )

        self.btn_search = ft.IconButton(
            icon=ft.icons.SEARCH_ROUNDED,
            icon_color=TEXT_PRIMARY,
            bgcolor=ACCENT_RED,
            icon_size=20,
            on_click=self._handle_search,
            tooltip="Search YouTube",
        )

        self.btn_clear_search = ft.IconButton(
            icon=ft.icons.CLEAR_ROUNDED,
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
            padding=ft.padding.only(right=6, bottom=16),
            expand=True,
        )

        # Build Drawer Box Content
        drawer_content = ft.Column(
            controls=[
                # Top Title & Close Header
                ft.Row(
                    controls=[
                        ft.Row(
                            [
                                ft.Icon(ft.icons.PLAYLIST_PLAY_ROUNDED, size=24, color=ACCENT_RED),
                                ft.Text("Manage Playlist", size=18, weight=ft.FontWeight.BOLD, color=TEXT_PRIMARY),
                            ],
                            spacing=8,
                        ),
                        ft.Row(
                            [
                                self.spinner,
                                ft.IconButton(
                                    icon=ft.icons.CLOSE_ROUNDED,
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

        drawer_box = ft.Container(
            content=drawer_content,
            width=580,
            bgcolor="#131722",
            border_radius=ft.border_radius.only(top_left=24, bottom_left=24),
            border=ft.border.all(1.2, "rgba(255, 255, 255, 0.12)"),
            padding=20,
            shadow=ft.BoxShadow(spread_radius=8, blur_radius=30, color="rgba(0, 0, 0, 0.8)"),
            alignment=ft.alignment.center,
        )

        super().__init__(
            content=ft.Row(
                controls=[
                    # Translucent backdrop barrier to close on tap outside
                    ft.Container(
                        expand=True,
                        on_click=lambda e: self.close_drawer(),
                    ),
                    drawer_box,
                ],
                expand=True,
                spacing=0,
            ),
            bgcolor="rgba(0, 0, 0, 0.65)",
            expand=True,
            visible=False,
        )

    def open_drawer(self) -> None:
        self.visible = True
        if self._is_searching:
            self._render_search_results()
        else:
            self._render_local_playlist()
        if getattr(self, "page", None):
            self.update()

    def close_drawer(self) -> None:
        self.visible = False
        if getattr(self, "page", None):
            self.update()
        if self.on_close_callback:
            self.on_close_callback()

    def _dispatch(self, coro):
        if self.async_runner:
            return self.async_runner(coro)
        loop = asyncio.get_event_loop()
        return loop.create_task(coro)

    # ─── Local Playlist View ──────────────────────────────────────────

    def _render_local_playlist(self) -> None:
        """Renders the local saved playlist with Play All header and Delete buttons."""
        self.content_list.controls.clear()
        tracks = self.local_playlist_mgr.get_tracks()

        # Header Info Row
        header = ft.Row(
            controls=[
                ft.Row(
                    [
                        ft.Icon(ft.icons.QUEUE_MUSIC_ROUNDED, size=18, color=ACCENT_RED),
                        ft.Text(f"My Playlist ({len(tracks)} tracks)", size=14, weight=ft.FontWeight.BOLD, color=TEXT_PRIMARY),
                    ],
                    spacing=6,
                ),
                ft.ElevatedButton(
                    content=ft.Row([ft.Icon(ft.icons.PLAY_ARROW_ROUNDED, size=16), ft.Text("Play All", weight=ft.FontWeight.BOLD)]),
                    bgcolor=ACCENT_RED,
                    color=TEXT_PRIMARY,
                    style=ft.ButtonStyle(
                        shape=ft.RoundedRectangleBorder(radius=8),
                        padding=ft.padding.symmetric(horizontal=12, vertical=8),
                    ),
                    on_click=lambda e: self._play_all_local_tracks(),
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
                            ft.Icon(ft.icons.PLAYLIST_ADD_ROUNDED, size=46, color=TEXT_MUTED),
                            ft.Text("Your local playlist is empty.", size=14, color=TEXT_SECONDARY, weight=ft.FontWeight.BOLD),
                            ft.Text("Use the search bar above to find and add songs from YouTube!", size=12, color=TEXT_MUTED),
                        ],
                        horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                        spacing=6,
                    ),
                    alignment=ft.alignment.center,
                    padding=40,
                )
            )
        else:
            for idx, track in enumerate(tracks):
                tile = self._build_local_track_tile(track, tracks, idx)
                self.content_list.controls.append(tile)

        if getattr(self, "page", None):
            self.update()

    def _build_local_track_tile(self, track: Track, tracks: List[Track], index: int) -> ft.Container:
        """Constructs list tile for local playlist with Play and Delete actions."""
        return ft.Container(
            content=ft.Row(
                controls=[
                    ft.Image(
                        src=track.art_url or "https://images.unsplash.com/photo-1511671782779-c97d3d27a1d4?w=200&q=80",
                        width=44,
                        height=44,
                        border_radius=8,
                        fit=ft.ImageFit.COVER,
                    ),
                    ft.Container(width=4),
                    ft.Column(
                        controls=[
                            ft.Text(track.title, size=13, weight=ft.FontWeight.BOLD, color=TEXT_PRIMARY, max_lines=1, overflow=ft.TextOverflow.ELLIPSIS),
                            ft.Text(track.artist, size=11, color=TEXT_SECONDARY, max_lines=1, overflow=ft.TextOverflow.ELLIPSIS),
                        ],
                        spacing=2,
                        expand=True,
                    ),
                    ft.Text(track.formatted_duration, size=11, color=TEXT_MUTED),
                    # Play Button
                    ft.IconButton(
                        icon=ft.icons.PLAY_CIRCLE_FILLED_ROUNDED,
                        icon_color=ACCENT_RED,
                        icon_size=28,
                        on_click=lambda e, q=tracks, i=index: self._play_tracks_queue(q, i),
                        tooltip="Play this track",
                    ),
                    # Delete Button
                    ft.IconButton(
                        icon=ft.icons.DELETE_OUTLINE_ROUNDED,
                        icon_color="rgba(255, 100, 100, 0.8)",
                        icon_size=22,
                        on_click=lambda e, t_id=track.id: self._handle_delete_track(t_id),
                        tooltip="Remove from Local Playlist",
                    ),
                ],
                alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                spacing=8,
            ),
            padding=ft.padding.symmetric(horizontal=10, vertical=6),
            border_radius=10,
            bgcolor="rgba(255, 255, 255, 0.03)",
            border=ft.border.all(1, "rgba(255, 255, 255, 0.06)"),
            ink=True,
            on_click=lambda e, q=tracks, i=index: self._play_tracks_queue(q, i),
        )

    def _handle_delete_track(self, track_id: str) -> None:
        """Deletes track from local storage and refreshes drawer + home screen."""
        self.local_playlist_mgr.remove_track(track_id)
        self.on_playlist_modified()
        if self._is_searching:
            self._render_search_results()
        else:
            self._render_local_playlist()

    def _play_all_local_tracks(self) -> None:
        tracks = self.local_playlist_mgr.get_tracks()
        if tracks:
            self._play_tracks_queue(tracks, 0)

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
        self.content_list.controls.clear()
        if getattr(self, "page", None):
            self.update()

        loop = asyncio.get_event_loop()
        tracks = await loop.run_in_executor(None, self.ytmusic_service.search_tracks, query, 30)
        self.spinner.visible = False
        self._search_results = tracks
        self._render_search_results()

    def _render_search_results(self) -> None:
        self.content_list.controls.clear()

        # Search Results Header
        header = ft.Row(
            controls=[
                ft.Row(
                    [
                        ft.Icon(ft.icons.SEARCH_ROUNDED, size=18, color=ACCENT_CYAN),
                        ft.Text(f"Search Results ({len(self._search_results)} found)", size=14, weight=ft.FontWeight.BOLD, color=TEXT_PRIMARY),
                    ],
                    spacing=6,
                ),
                ft.TextButton(
                    content=ft.Row([ft.Icon(ft.icons.ARROW_BACK_ROUNDED, size=16), ft.Text("Back to My Playlist")]),
                    style=ft.ButtonStyle(color=TEXT_SECONDARY),
                    on_click=self._handle_clear_search,
                ),
            ],
            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
        )
        self.content_list.controls.append(header)
        self.content_list.controls.append(ft.Container(height=4))

        if not self._search_results:
            self.content_list.controls.append(
                ft.Container(
                    content=ft.Column(
                        [
                            ft.Icon(ft.icons.SEARCH_OFF_ROUNDED, size=40, color=TEXT_MUTED),
                            ft.Text("No songs found. Try a different search term.", size=13, color=TEXT_MUTED),
                        ],
                        horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                        spacing=6,
                    ),
                    alignment=ft.alignment.center,
                    padding=40,
                )
            )
        else:
            for idx, track in enumerate(self._search_results):
                tile = self._build_search_result_tile(track, self._search_results, idx)
                self.content_list.controls.append(tile)

        if getattr(self, "page", None):
            self.update()

    def _build_search_result_tile(self, track: Track, results: List[Track], index: int) -> ft.Container:
        """Constructs search result tile with Play and Add to Playlist buttons."""
        is_already_added = self.local_playlist_mgr.has_track(track.id)

        btn_add = ft.IconButton(
            icon=ft.icons.CHECK_CIRCLE_ROUNDED if is_already_added else ft.icons.ADD_CIRCLE_OUTLINE_ROUNDED,
            icon_color=ACCENT_GREEN if is_already_added else ACCENT_CYAN,
            icon_size=28,
            on_click=lambda e, t=track: self._handle_add_track_to_playlist(t),
            tooltip="In Playlist" if is_already_added else "Add to My Playlist",
        )

        return ft.Container(
            content=ft.Row(
                controls=[
                    ft.Image(
                        src=track.art_url or "https://images.unsplash.com/photo-1511671782779-c97d3d27a1d4?w=200&q=80",
                        width=44,
                        height=44,
                        border_radius=8,
                        fit=ft.ImageFit.COVER,
                    ),
                    ft.Container(width=4),
                    ft.Column(
                        controls=[
                            ft.Text(track.title, size=13, weight=ft.FontWeight.BOLD, color=TEXT_PRIMARY, max_lines=1, overflow=ft.TextOverflow.ELLIPSIS),
                            ft.Text(track.artist, size=11, color=TEXT_SECONDARY, max_lines=1, overflow=ft.TextOverflow.ELLIPSIS),
                        ],
                        spacing=2,
                        expand=True,
                    ),
                    ft.Text(track.formatted_duration, size=11, color=TEXT_MUTED),
                    # Play Preview Button
                    ft.IconButton(
                        icon=ft.icons.PLAY_CIRCLE_FILLED_ROUNDED,
                        icon_color=ACCENT_RED,
                        icon_size=28,
                        on_click=lambda e, q=results, i=index: self._play_tracks_queue(q, i),
                        tooltip="Play Preview",
                    ),
                    # Add to Local Playlist Button
                    btn_add,
                ],
                alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                spacing=8,
            ),
            padding=ft.padding.symmetric(horizontal=10, vertical=6),
            border_radius=10,
            bgcolor="rgba(255, 255, 255, 0.03)",
            border=ft.border.all(1, "rgba(255, 255, 255, 0.06)"),
        )

    def _handle_add_track_to_playlist(self, track: Track) -> None:
        """Adds track to local playlist, saves, and updates UI."""
        self.local_playlist_mgr.add_track(track)
        self.on_playlist_modified()
        self._render_search_results()

    def _play_tracks_queue(self, tracks: List[Track], start_index: int) -> None:
        if 0 <= start_index < len(tracks):
            target_track = tracks[start_index]
            curr = self.audio_controller.current_track
            if curr and curr.id == target_track.id and self.audio_controller.is_playing:
                self.close_drawer()
                return

        self.audio_controller.load_queue(tracks, start_index, auto_play=True)
        self.close_drawer()
        self.on_track_selected()

