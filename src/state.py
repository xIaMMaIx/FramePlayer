"""
Application State Management and Enums for Frame Player.
Provides centralized reactive state synchronization across background tasks and UI views.
"""

from enum import Enum
from typing import Any, Callable, List, Optional
import time


class AppMode(str, Enum):
    MUSIC_PLAYER = "MUSIC_PLAYER"
    PHOTO_FRAME = "PHOTO_FRAME"
    SETTINGS = "SETTINGS"


class AppState:
    def __init__(self):
        # Navigation & View State
        self.mode: AppMode = AppMode.MUSIC_PLAYER
        self.is_overlay_open: bool = False

        # Idle Watcher State
        self.idle_seconds: int = 0
        self.idle_threshold_seconds: int = 60
        self.last_interaction_timestamp: float = time.time()

        # Playback State
        self.is_playing: bool = False
        self.position_seconds: float = 0.0
        self.duration_seconds: float = 0.0
        self.volume: float = 0.75
        self.is_muted: bool = False
        self.shuffle: bool = False
        self.repeat: str = "off"  # "off", "all", "one"

        # Active Media & Photos
        self.current_track: Any = None
        self.queue: List[Any] = []
        self.current_photo_path: str = ""
        self.next_photo_path: str = ""
        self.photo_list: List[str] = []

        # Listeners / Callbacks for reactive UI updates
        self._listeners: List[Callable[["AppState", str], None]] = []

    def add_listener(self, callback: Callable[["AppState", str], None]) -> None:
        """Registers a callback to be notified on state modifications."""
        if callback not in self._listeners:
            self._listeners.append(callback)

    def remove_listener(self, callback: Callable[["AppState", str], None]) -> None:
        """Unregisters a listener callback."""
        if callback in self._listeners:
            self._listeners.remove(callback)

    def notify(self, event_name: str = "state_changed") -> None:
        """Dispatches state change event to registered listeners."""
        for cb in list(self._listeners):
            try:
                cb(self, event_name)
            except Exception as e:
                print(f"[AppState] Error in listener callback ({event_name}): {e}")

    def reset_idle(self) -> None:
        """Resets idle timer to 0 upon user touch or activity."""
        self.idle_seconds = 0
        self.last_interaction_timestamp = time.time()
        self.notify("idle_reset")

    def set_mode(self, mode: AppMode) -> None:
        """Transitions application display mode."""
        if self.mode != mode:
            self.mode = mode
            if mode == AppMode.MUSIC_PLAYER:
                self.is_overlay_open = False
            self.reset_idle()
            self.notify("mode_changed")

    def set_overlay(self, open_state: bool) -> None:
        """Toggles the wake quick-action modal overlay."""
        if self.is_overlay_open != open_state:
            self.is_overlay_open = open_state
            self.reset_idle()
            self.notify("overlay_toggled")
