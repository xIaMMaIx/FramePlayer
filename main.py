"""
Main Application Entrypoint for CarPlay YouTube Music & Digital Photo Frame Kiosk.
Integrates Local Playlist Management, YouTube Music Search & Streaming,
yt-dlp Direct Audio Streaming Engine, and Background Screen Automation.
"""

import asyncio
import os
import sys
from pathlib import Path
import flet as ft

from src.config_manager import ConfigManager
from src.photo_engine import PhotoEngine
from src.services.audio_controller import AudioController, DEFAULT_AUDIO_PLACEHOLDER
from src.services.local_playlist_manager import LocalPlaylistManager
from src.services.oauth_manager import OAuthManager
from src.services.ytmusic_service import YTMusicService
from src.state import AppMode, AppState
from src.ui.action_overlay import ActionOverlay
from src.ui.library_drawer import LibraryDrawer
from src.ui.music_view import MusicPlayerView
from src.ui.oauth_modal import OAuthModal
from src.ui.photo_view import PhotoFrameView
from src.ui.settings_view import SettingsView
from src.ui.theme import BG_DARK


async def main(page: ft.Page):
    # Capture the main asyncio loop for thread-safe UI callback scheduling
    main_loop = asyncio.get_running_loop()

    def dispatch_async(coro):
        """Safely dispatches a coroutine to the main asyncio event loop from any worker thread."""
        try:
            return asyncio.run_coroutine_threadsafe(coro, main_loop)
        except Exception as ex:
            print(f"[AsyncDispatch] Error: {ex}")

    # --- 1. Page Configuration & Kiosk Setup ---
    page.title = "CarPlay YouTube Music & Digital Photo Frame"
    page.theme_mode = ft.ThemeMode.DARK
    page.bgcolor = BG_DARK
    page.padding = 0
    page.spacing = 0

    page.fonts = {
        "Prompt": "https://github.com/google/fonts/raw/main/ofl/prompt/Prompt-Regular.ttf",
        "Prompt-Medium": "https://github.com/google/fonts/raw/main/ofl/prompt/Prompt-Medium.ttf",
        "Prompt-Bold": "https://github.com/google/fonts/raw/main/ofl/prompt/Prompt-Bold.ttf",
    }
    page.theme = ft.Theme(font_family="Prompt")

    # --- 2. Initialize Core Subsystems ---
    config_mgr = ConfigManager()
    state = AppState()
    state.idle_threshold_seconds = config_mgr.get("idle_timeout_seconds", 60)
    state.volume = config_mgr.get("volume", 0.75)

    photo_engine = PhotoEngine(
        initial_folder=config_mgr.get("photo_folder"),
        shuffle=config_mgr.get("slideshow_shuffle", True),
        blur_radius=config_mgr.get("background_blur_radius", 24),
    )

    oauth_manager = OAuthManager(config_mgr=config_mgr)
    ytmusic_service = YTMusicService(config_mgr=config_mgr)

    # Window geometry for touch tablet (Orientation-aware)
    orientation = config_mgr.get("orientation", "landscape")
    try:
        if hasattr(page, "window"):
            if orientation == "portrait":
                page.window.width = 600
                page.window.height = 1024
                page.window.min_width = 400
                page.window.min_height = 600
            else:
                page.window.width = 1280
                page.window.height = 720
                page.window.min_width = 800
                page.window.min_height = 480
            page.window.center()

            def handle_window_event(e):
                if e.data in ("close", "destroy"):
                    if "audio_controller" in locals():
                        audio_controller.ffplay.stop()

            page.window.on_event = handle_window_event
    except Exception as e:
        print(f"[Main] Window config note: {e}")
    local_playlist_mgr = LocalPlaylistManager()

    # --- 3. Audio Control Setup & Local Playlist Startup ---
    audio_control = ft.Audio(
        src=DEFAULT_AUDIO_PLACEHOLDER,
        autoplay=False,
        volume=state.volume,
    )
    page.overlay.append(audio_control)

    audio_controller = AudioController(
        state=state,
        ytmusic_service=ytmusic_service,
        audio_control=audio_control,
        async_runner=dispatch_async,
    )

    # Preload Local Playlist directly onto Home Screen with 0 delay
    initial_tracks = local_playlist_mgr.get_tracks()
    if initial_tracks:
        print(f"[Main] Loaded {len(initial_tracks)} tracks from Local Playlist to home dashboard.")
        audio_controller.load_queue(initial_tracks, 0, auto_play=False)

    # --- 4. User Interaction Reset Handler ---
    def handle_global_interaction(e=None):
        state.reset_idle()

    # --- 5. Navigation & Mode Transitions ---
    def set_app_mode(new_mode: AppMode):
        state.set_mode(new_mode)

        if new_mode == AppMode.PHOTO_FRAME:
            action_overlay.hide()
            oauth_modal.close_modal()
            library_drawer.close_drawer()
            dashboard_container.visible = False
            photo_view_container.visible = True
            photo_view.update_now_playing()
        elif new_mode == AppMode.MUSIC_PLAYER:
            action_overlay.hide()
            photo_view_container.visible = False
            dashboard_container.visible = True
            content_area.content = music_view
            music_view.update_view()
        elif new_mode == AppMode.SETTINGS:
            action_overlay.hide()
            photo_view_container.visible = False
            dashboard_container.visible = True
            settings_view.update_folder_info()
            content_area.content = settings_view

        page.update()

    # --- 6. Wake Action Overlay Handlers ---
    def show_wake_overlay():
        state.set_overlay(True)
        action_overlay.show()
        page.update()

    def dismiss_wake_overlay():
        state.set_overlay(False)
        action_overlay.hide()
        page.update()

    def switch_to_music_from_wake():
        dismiss_wake_overlay()
        set_app_mode(AppMode.MUSIC_PLAYER)

    # --- 7. File Picker (Photo Folder) ---
    def on_folder_result(e: ft.FilePickerResultEvent):
        if e.path:
            folder_path = e.path
            config_mgr.set_photo_folder(folder_path)
            photo_count = photo_engine.scan_folder(folder_path)
            settings_view.update_folder_info()
            photo_view.reload_photos()

            snack = ft.SnackBar(
                content=ft.Text(f"Loaded {photo_count} photos from {Path(folder_path).name}"),
                bgcolor="#1E293B",
                duration=3000,
            )
            page.overlay.append(snack)
            snack.open = True
            page.update()

    file_picker = ft.FilePicker(on_result=on_folder_result)
    page.overlay.append(file_picker)

    def trigger_pick_folder():
        state.reset_idle()
        file_picker.get_directory_path(dialog_title="Select Photo Slideshow Folder")

    def wake_and_change_folder():
        dismiss_wake_overlay()
        trigger_pick_folder()

    # --- 8. Local Playlist Synchronization & OAuth Callbacks ---
    def sync_local_playlist_to_queue():
        """Syncs modified local playlist to active player queue without stopping active track."""
        tracks = local_playlist_mgr.get_tracks()
        curr_track = audio_controller.current_track
        curr_idx = 0
        if curr_track and curr_track in tracks:
            curr_idx = tracks.index(curr_track)

        # Update underlying queue preserving playing track
        audio_controller._original_queue = list(tracks)
        audio_controller._queue = list(tracks)
        audio_controller._current_index = curr_idx
        music_view.update_view()

    def on_login_success():
        ytmusic_service.initialize_client()
        settings_view.update_folder_info()
        music_view.update_view()
        snack = ft.SnackBar(
            content=ft.Text("YouTube Music connected successfully!"),
            bgcolor="#059669",
            duration=4000,
        )
        page.overlay.append(snack)
        snack.open = True
        page.update()

    def handle_logout():
        oauth_manager.logout()
        ytmusic_service.initialize_client()
        settings_view.update_folder_info()
        music_view.update_view()
        snack = ft.SnackBar(
            content=ft.Text("Disconnected YouTube Music account."),
            bgcolor="#334155",
            duration=3000,
        )
        page.overlay.append(snack)
        snack.open = True
        page.update()

    # --- 9. Instantiate UI Views & Modals ---
    oauth_modal = OAuthModal(
        oauth_manager=oauth_manager,
        on_login_success=on_login_success,
        on_close=lambda: None,
        async_runner=dispatch_async,
    )

    library_drawer = LibraryDrawer(
        ytmusic_service=ytmusic_service,
        audio_controller=audio_controller,
        local_playlist_mgr=local_playlist_mgr,
        oauth_manager=oauth_manager,
        on_playlist_modified=sync_local_playlist_to_queue,
        on_track_selected=lambda: music_view.update_view(),
        on_open_login=lambda: oauth_modal.open_modal(),
        on_close=lambda: None,
        async_runner=dispatch_async,
    )

    music_view = MusicPlayerView(
        state=state,
        backend=audio_controller,
        oauth_manager=oauth_manager,
        config_mgr=config_mgr,
        on_interaction=handle_global_interaction,
        on_open_library=lambda: library_drawer.open_drawer(),
        on_open_login=lambda: oauth_modal.open_modal(),
        on_open_photos=lambda: set_app_mode(AppMode.PHOTO_FRAME),
        on_open_settings=lambda: set_app_mode(AppMode.SETTINGS),
    )

    photo_view = PhotoFrameView(
        state=state,
        photo_engine=photo_engine,
        on_tap_wake=lambda: set_app_mode(AppMode.MUSIC_PLAYER),
        backend=audio_controller,
    )

    def handle_orientation_change(new_orientation: str):
        try:
            if hasattr(page, "window"):
                if new_orientation == "portrait":
                    page.window.width = 600
                    page.window.height = 1024
                else:
                    page.window.width = 1280
                    page.window.height = 720
                page.window.center()
        except Exception as e:
            print(f"[Main] Window resize note: {e}")
        music_view.rebuild_layout()
        page.update()

    settings_view = SettingsView(
        state=state,
        config_mgr=config_mgr,
        photo_engine=photo_engine,
        oauth_manager=oauth_manager,
        ytmusic_service=ytmusic_service,
        on_pick_folder=trigger_pick_folder,
        on_test_screensaver=lambda: set_app_mode(AppMode.PHOTO_FRAME),
        on_open_login=lambda: oauth_modal.open_modal(),
        on_logout=handle_logout,
        on_back_to_player=lambda: set_app_mode(AppMode.MUSIC_PLAYER),
        on_orientation_changed=handle_orientation_change,
    )

    action_overlay = ActionOverlay(
        state=state,
        on_switch_to_music=switch_to_music_from_wake,
        on_change_folder=wake_and_change_folder,
        on_dismiss=dismiss_wake_overlay,
    )

    # --- 10. Master Layout Structure ---
    content_area = ft.Container(
        content=music_view,
        expand=True,
    )

    dashboard_container = ft.Container(
        content=content_area,
        expand=True,
        visible=True,
    )

    photo_view_container = ft.Container(
        content=photo_view,
        expand=True,
        visible=False,
    )

    # Master Root Stack (Dashboard, Screensaver, Modals)
    root_stack = ft.Stack(
        controls=[
            dashboard_container,
            photo_view_container,
            action_overlay,
            library_drawer,
            oauth_modal,
        ],
        expand=True,
    )

    # Gesture detector to reset idle timer on touch
    gesture_root = ft.GestureDetector(
        content=root_stack,
        on_tap=handle_global_interaction,
        on_pan_start=handle_global_interaction,
        expand=True,
    )

    page.add(gesture_root)
    page.update()

    # --- 11. Background Async Workers ---

    async def idle_watcher_task():
        """Monitors 60s idle pause to trigger screensaver."""
        while True:
            await asyncio.sleep(1)
            try:
                if state.mode != AppMode.PHOTO_FRAME:
                    if not audio_controller.is_playing:
                        state.idle_seconds += 1

                        if state.idle_seconds >= state.idle_threshold_seconds:
                            print(f"[IdleWatcher] Idle threshold reached ({state.idle_threshold_seconds}s). Launching photo frame.")
                            set_app_mode(AppMode.PHOTO_FRAME)
                    else:
                        if state.idle_seconds != 0:
                            state.idle_seconds = 0
            except Exception as ex:
                print(f"[IdleWatcher] Error: {ex}")

    async def slideshow_task():
        """Advances photos at configured interval with crossfade."""
        while True:
            try:
                interval = config_mgr.get("slideshow_interval_seconds", 8)
                await asyncio.sleep(interval)
                if state.mode == AppMode.PHOTO_FRAME and not state.is_overlay_open:
                    photo_view.advance_photo()
            except Exception as ex:
                print(f"[SlideshowTask] Error: {ex}")

    async def progress_tracker_task():
        """Updates track elapsed time and seeker."""
        while True:
            await asyncio.sleep(1)
            try:
                if audio_controller.is_playing:
                    audio_controller.tick_playback()
                    if state.mode == AppMode.MUSIC_PLAYER:
                        music_view.update_progress_only()
                    elif state.mode == AppMode.PHOTO_FRAME:
                        photo_view.update_now_playing()
            except Exception as ex:
                print(f"[ProgressTracker] Error: {ex}")

    page.run_task(idle_watcher_task)
    page.run_task(slideshow_task)
    page.run_task(progress_tracker_task)


if __name__ == "__main__":
    ft.app(target=main)
