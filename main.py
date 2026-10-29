"""
Main Application Entrypoint for CarPlay YouTube Music & Digital Photo Frame Kiosk.
Integrates Local Playlist Management, YouTube Music Search & Streaming,
yt-dlp Direct Audio Streaming Engine, and Background Screen Automation.
"""

import asyncio
from pathlib import Path
import flet as ft

# FLET AST SCANNER WORKAROUND
# The flet build AST scanner might only scan main.py. 
# We include these so it registers the Flutter plugins for Android.
if False:
    from flet import FilePicker
    import flet_audio as fta
    import flet.controls.services.file_picker
    from flet import Wakelock


from src.config_manager import ConfigManager
from src.photo_engine import PhotoEngine
from src.services.audio_controller import AudioController, DEFAULT_AUDIO_PLACEHOLDER
from src.services.local_playlist_manager import LocalPlaylistManager
from src.services.ytmusic_service import YTMusicService
from src.state import AppMode, AppState
from src.ui.action_overlay import ActionOverlay
from src.ui.library_drawer import LibraryDrawer
from src.ui.music_view import MusicPlayerView
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
    
    # Make Android status bar transparent and hide it
    page.window.full_screen = True
    page.padding = 0
    page.spacing = 0

    page.fonts = {
        "Prompt": "https://github.com/google/fonts/raw/main/ofl/prompt/Prompt-Regular.ttf",
        "Prompt-Medium": "https://github.com/google/fonts/raw/main/ofl/prompt/Prompt-Medium.ttf",
        "Prompt-Bold": "https://github.com/google/fonts/raw/main/ofl/prompt/Prompt-Bold.ttf",
    }
    page.theme = ft.Theme(
        font_family="Prompt",
        system_overlay_style=ft.SystemOverlayStyle(
            status_bar_color=ft.Colors.TRANSPARENT,
            system_navigation_bar_color=ft.Colors.TRANSPARENT,
            enforce_system_navigation_bar_contrast=False,
            enforce_system_status_bar_contrast=False,
        )
    )

    # --- 2. Initialize Core Subsystems ---
    config_mgr = ConfigManager()
    
    # Pre-detect orientation on startup based on page dimensions
    if page.height > page.width:
        config_mgr.set("orientation", "portrait")
    else:
        config_mgr.set("orientation", "landscape")

    state = AppState()
    state.idle_threshold_seconds = config_mgr.get("idle_timeout_seconds", 60)
    state.volume = config_mgr.get("volume", 0.75)

    photo_engine = PhotoEngine(
        initial_folder=config_mgr.get("photo_folder"),
        shuffle=config_mgr.get("slideshow_shuffle", True),
        blur_radius=config_mgr.get("background_blur_radius", 24),
    )

    ytmusic_service = YTMusicService(config_mgr=config_mgr)

    local_playlist_mgr = LocalPlaylistManager()

    # --- 3. Audio Control Setup & Local Playlist Startup ---
    audio_control = None
    
    # ANDROID VERSION: Strict flet_audio usage
    import flet_audio as fta
    audio_control = fta.Audio(
        src=DEFAULT_AUDIO_PLACEHOLDER,
        autoplay=False,
        volume=state.volume,
    )
    # page.overlay.append(audio_control) # Service!

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
            library_drawer.close_drawer()
            dashboard_container.visible = False
            photo_view_container.visible = True
            photo_view.apply_settings()
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
    def on_folder_result(e):
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
            page.update()    # FilePicker Service...
    file_picker = ft.FilePicker()

    def trigger_pick_folder():
        state.reset_idle()
        async def pick_task():
            try:
                path = await file_picker.get_directory_path(dialog_title="Select Photo Slideshow Folder")
                if path:
                    class MockEvent:
                        def __init__(self, p): self.path = p
                    on_folder_result(MockEvent(path))
            except Exception as ex:
                print("FilePicker error:", ex)
        page.run_task(pick_task)

    def wake_and_change_folder():
        dismiss_wake_overlay()
        trigger_pick_folder()

    # --- 8. Local Playlist Synchronization ---
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

    # --- 9. Instantiate UI Views & Modals ---
    library_drawer = LibraryDrawer(
        ytmusic_service=ytmusic_service,
        audio_controller=audio_controller,
        local_playlist_mgr=local_playlist_mgr,
        on_playlist_modified=sync_local_playlist_to_queue,
        on_track_selected=lambda: music_view.update_view(),
        on_close=lambda: None,
        async_runner=dispatch_async,
    )

    music_view = MusicPlayerView(
        state=state,
        backend=audio_controller,
        config_mgr=config_mgr,
        on_interaction=handle_global_interaction,
        on_open_library=lambda: library_drawer.open_drawer(),
        on_open_photos=lambda: set_app_mode(AppMode.PHOTO_FRAME),
        on_open_settings=lambda: set_app_mode(AppMode.SETTINGS),
        on_queue_reorder=lambda old, new: local_playlist_mgr.reorder_track(old, new),
    )

    # Auto-detect orientation on resize for Android
    def on_page_resize(e):
        try:
            try:
                w, h = map(float, e.data.split(","))
                is_port = h > w
            except:
                is_port = page.height > page.width
                
            new_ori = "portrait" if is_port else "landscape"
            old_ori = config_mgr.get("orientation", "landscape")
            
            if new_ori != old_ori:
                config_mgr.set("orientation", new_ori)
                music_view.rebuild_layout()
                music_view.update()
                page.update()
        except Exception as ex:
            print("Resize error:", ex)
            
    page.on_resize = on_page_resize


    photo_view = PhotoFrameView(
        state=state,
        photo_engine=photo_engine,
        config_mgr=config_mgr,
        on_tap_wake=lambda: set_app_mode(AppMode.MUSIC_PLAYER),
        backend=audio_controller,
    )

    def handle_orientation_change(new_orientation: str):
        music_view.rebuild_layout()
        music_view.update()
        page.update()

    settings_view = SettingsView(
        state=state,
        config_mgr=config_mgr,
        photo_engine=photo_engine,
        on_pick_folder=trigger_pick_folder,
        on_test_screensaver=lambda: set_app_mode(AppMode.PHOTO_FRAME),
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

    # SafeArea keeps buttons out from under the Android status / navigation bars
    # (the theme draws edge-to-edge with transparent system bars).
    dashboard_container = ft.Container(
        content=ft.SafeArea(content=content_area, expand=True),
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
                    # Keyboard input in the library search doesn't reach the root
                    # GestureDetector, so an open drawer or a loading stream counts as activity.
                    busy = audio_controller.is_playing or audio_controller.is_loading or library_drawer.visible
                    if not busy:
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
                    if state.mode == AppMode.MUSIC_PLAYER:
                        music_view.update_progress_only()
                    elif state.mode == AppMode.PHOTO_FRAME:
                        photo_view.update_now_playing()
            except Exception as ex:
                print(f"[ProgressTracker] Error: {ex}")

    page.run_task(idle_watcher_task)
    page.run_task(slideshow_task)
    page.run_task(progress_tracker_task)

    # Enable Wakelock for Digital Photo Frame
    async def enable_wakelock():
        try:
            wakelock = ft.Wakelock()
            await wakelock.enable()
            print("Wakelock enabled.")
        except Exception as e:
            print("Wakelock error:", e)
    page.run_task(enable_wakelock)


if __name__ == "__main__":
    ft.run(main)
