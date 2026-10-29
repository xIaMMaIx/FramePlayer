"""
Application mode and idle-screensaver state shared by the views and background tasks.
"""

from enum import Enum


class AppMode(str, Enum):
    MUSIC_PLAYER = "MUSIC_PLAYER"
    PHOTO_FRAME = "PHOTO_FRAME"
    SETTINGS = "SETTINGS"


class AppState:
    def __init__(self, idle_threshold_seconds: int = 60):
        self.mode: AppMode = AppMode.MUSIC_PLAYER
        self.is_overlay_open: bool = False
        self.idle_seconds: int = 0
        self.idle_threshold_seconds: int = idle_threshold_seconds

    def reset_idle(self) -> None:
        """Called on any user touch or activity."""
        self.idle_seconds = 0

    def set_mode(self, mode: AppMode) -> None:
        if self.mode != mode:
            self.mode = mode
            if mode == AppMode.MUSIC_PLAYER:
                self.is_overlay_open = False
            self.reset_idle()

    def set_overlay(self, open_state: bool) -> None:
        if self.is_overlay_open != open_state:
            self.is_overlay_open = open_state
            self.reset_idle()
