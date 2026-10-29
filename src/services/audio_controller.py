"""
Audio Playback & State Controller (AudioController).
Plays streams through the native Flet Audio control (Android), with volume control,
track queue management, and UI state synchronization.
"""

import asyncio
import random
from typing import Any, Callable, List, Optional

from src.music_backend import BaseMusicBackend, MOCK_TRACKS, Track
from src.services.ytmusic_service import YTMusicService
from src.state import AppState

DEFAULT_AUDIO_PLACEHOLDER = "https://raw.githubusercontent.com/mdn/webaudio-examples/main/audio-analyser/viper.mp3"


def _parse_duration_to_seconds(val) -> float:
    """Safely converts Duration, timedelta, int, float, or None to seconds."""
    if val is None:
        return 0.0
    if hasattr(val, "in_milliseconds"):
        return float(val.in_milliseconds) / 1000.0
    if hasattr(val, "in_seconds"):
        return float(val.in_seconds)
    if hasattr(val, "total_seconds"):
        return float(val.total_seconds())
    if hasattr(val, "milliseconds"):
        return float(val.milliseconds) / 1000.0
    try:
        f = float(val)
        return f / 1000.0 if f > 10000 else f
    except (ValueError, TypeError):
        return 0.0


class AudioController(BaseMusicBackend):
    def __init__(
        self,
        state: AppState,
        ytmusic_service: YTMusicService,
        audio_control: Optional[Any] = None,
        async_runner: Optional[Callable] = None,
    ):
        self.state = state
        self.ytmusic_service = ytmusic_service
        self.audio = audio_control
        self.async_runner = async_runner

        # Playback & Queue State
        self._queue: List[Track] = list(MOCK_TRACKS)
        self._current_index: int = 0
        self._is_playing: bool = False
        self._position_seconds: float = 0.0
        self._duration_seconds: float = 0.0
        self._volume: float = state.volume
        self._shuffle: bool = False
        self._repeat: str = "off"  # "off", "all", "one"
        self._is_loading_stream: bool = False
        self._original_queue: List[Track] = list(self._queue)
        self._loaded_track_id: Optional[str] = None
        self._current_stream_url: Optional[str] = None

        # Callbacks
        self.on_track_changed: Optional[Callable[[Track], None]] = None
        self.on_state_changed: Optional[Callable[[], None]] = None

        # Bind Flet Audio callbacks if provided
        self._setup_flet_audio()

    async def _safe_audio_call(self, coro, timeout: float = 12.0):
        """Safely awaits Flet Audio RPC calls with timeout to prevent hanging."""
        try:
            return await asyncio.wait_for(coro, timeout=timeout)
        except asyncio.TimeoutError:
            print(f"[AudioController] Flet audio operation timed out ({timeout}s).")
        except Exception as e:
            print(f"[AudioController] Flet audio operation note: {e}")

    def _setup_flet_audio(self) -> None:
        if self.audio:
            try:
                self.audio.on_state_change = self._on_flet_audio_state_change
                self.audio.on_position_change = self._on_flet_audio_position_change
                self.audio.on_duration_change = self._on_flet_audio_duration_change
            except Exception as e:
                print(f"[AudioController] Flet audio setup note: {e}")

    def _on_flet_audio_state_change(self, e) -> None:
        state_str = str(getattr(e, "state", "")).lower()
        if "completed" in state_str:
            self._handle_track_completed()

    def _on_flet_audio_position_change(self, e) -> None:
        try:
            # flet_audio AudioPositionChangeEvent has .position (int) in milliseconds
            val = getattr(e, "position", getattr(e, "data", 0))
            secs = float(val) / 1000.0
        except:
            secs = 0.0
        if secs >= 0:
            self._position_seconds = secs
            self.state.position_seconds = self._position_seconds

    def _on_flet_audio_duration_change(self, e) -> None:
        dur_val = getattr(e, "duration", None)
        secs = _parse_duration_to_seconds(dur_val)
        if secs > 0:
            self._duration_seconds = secs

    # --- Transport Controls ---

    @property
    def current_track(self) -> Optional[Track]:
        if 0 <= self._current_index < len(self._queue):
            return self._queue[self._current_index]
        return None

    @property
    def is_playing(self) -> bool:
        return self._is_playing

    @property
    def is_loading(self) -> bool:
        return self._is_loading_stream

    @property
    def queue(self) -> List[Track]:
        return self._queue

    @property
    def position_seconds(self) -> float:
        return self._position_seconds

    @property
    def duration_seconds(self) -> float:
        curr = self.current_track
        return curr.duration_seconds if curr and curr.duration_seconds > 0 else (self._duration_seconds or 180.0)

    @property
    def volume(self) -> float:
        return self._volume

    @property
    def shuffle(self) -> bool:
        return self._shuffle

    @property
    def repeat(self) -> str:
        return self._repeat

    def _run_async(self, coro):
        """Safely dispatches coroutine using thread-safe runner or main event loop."""
        if self.async_runner:
            return self.async_runner(coro)
        try:
            loop = asyncio.get_running_loop()
            return loop.create_task(coro)
        except RuntimeError:
            try:
                loop = asyncio.get_event_loop()
                return loop.create_task(coro)
            except Exception as e:
                print(f"[AudioController] Async dispatch note: {e}")

    def play(self) -> None:
        """Resumes or starts playback of current track."""
        curr = self.current_track
        if not curr:
            return

        self._is_playing = True
        self.state.is_playing = True
        self.state.reset_idle()

        if self._loaded_track_id == curr.id and self._current_stream_url and self.audio:
            self._run_async(self._safe_audio_call(self.audio.resume()))
            self._notify_state()
        else:
            self._run_async(self._load_and_play_track(curr))

    def pause(self) -> None:
        """Pauses audio playback."""
        self._is_playing = False
        self.state.is_playing = False
        if self.audio:
            self._run_async(self._safe_audio_call(self.audio.pause()))
        self._notify_state()

    def toggle_play(self) -> bool:
        """Toggles between play and pause."""
        if self._is_playing:
            self.pause()
        else:
            self.play()
        return self._is_playing

    def next_track(self) -> Optional[Track]:
        """Advances to next track in queue."""
        if not self._queue:
            return None

        if self._repeat == "one":
            self._position_seconds = 0.0
        else:
            self._current_index = (self._current_index + 1) % len(self._queue)
            self._position_seconds = 0.0

        curr = self.current_track
        if curr:
            self._run_async(self._load_and_play_track(curr))
        return curr

    def prev_track(self) -> Optional[Track]:
        """Steps back to previous track in queue."""
        if not self._queue:
            return None

        if self._position_seconds > 3.0:
            self.seek(0)
            return self.current_track

        self._current_index = (self._current_index - 1) % len(self._queue)
        self._position_seconds = 0.0

        curr = self.current_track
        if curr:
            self._run_async(self._load_and_play_track(curr))
        return curr

    def play_track_by_id(self, track_id: str) -> Optional[Track]:
        """Finds track by ID in queue and plays it."""
        curr = self.current_track
        if curr and curr.id == track_id and self._is_playing:
            return curr

        for idx, track in enumerate(self._queue):
            if track.id == track_id:
                self._current_index = idx
                self._position_seconds = 0.0
                self._run_async(self._load_and_play_track(track))
                return track
        return None

    def seek(self, position_seconds: float) -> None:
        """Seeks to specific position in seconds."""
        max_dur = self.duration_seconds
        self._position_seconds = max(0.0, min(position_seconds, max_dur))
        self.state.position_seconds = self._position_seconds

        if self.audio:
            self._run_async(self._safe_audio_call(self.audio.seek(int(self._position_seconds * 1000))))

        self._notify_state()

    def set_volume(self, volume: float) -> None:
        """Sets playback volume (0.0 to 1.0)."""
        self._volume = max(0.0, min(1.0, volume))
        self.state.volume = self._volume

        if self.audio:
            self.audio.volume = self._volume
            try:
                self.audio.update()
            except Exception:
                pass

        self._notify_state()

    def toggle_shuffle(self) -> bool:
        """Toggles shuffle mode and reorders queue."""
        self._shuffle = not self._shuffle
        current = self.current_track

        if self._shuffle:
            shuffled = list(self._original_queue)
            random.shuffle(shuffled)
            if current and current in shuffled:
                shuffled.remove(current)
                shuffled.insert(0, current)
            self._queue = shuffled
            self._current_index = 0
        else:
            self._queue = list(self._original_queue)
            if current and current in self._queue:
                self._current_index = self._queue.index(current)
            else:
                self._current_index = 0

        self._notify_state()
        return self._shuffle

    def cycle_repeat(self) -> str:
        """Cycles repeat mode: off -> all -> one -> off."""
        modes = ["off", "all", "one"]
        current_idx = modes.index(self._repeat)
        self._repeat = modes[(current_idx + 1) % len(modes)]
        self._notify_state()
        return self._repeat

    def toggle_like(self) -> bool:
        """Toggles like status for current track."""
        curr = self.current_track
        if curr:
            curr.is_liked = not curr.is_liked
            self._notify_state()
            return curr.is_liked
        return False

    def load_queue(self, tracks: List[Track], start_index: int = 0, auto_play: bool = True) -> None:
        """Replaces active queue with a new list of tracks and begins playback if auto_play=True."""
        if not tracks:
            return

        self._original_queue = list(tracks)
        self._queue = list(tracks)
        self._current_index = max(0, min(start_index, len(self._queue) - 1))
        self._position_seconds = 0.0

        curr = self.current_track
        if curr:
            if auto_play:
                self._run_async(self._load_and_play_track(curr))
            else:
                self._notify_track()

    def reorder_queue(self, old_index: int, new_index: int) -> None:
        """Reorders queue items while preserving reference to the current playing track."""
        if not (0 <= old_index < len(self._queue) and 0 <= new_index < len(self._queue)):
            return

        current_t = self.current_track
        track = self._queue.pop(old_index)
        self._queue.insert(new_index, track)

        if hasattr(self, "_original_queue") and self._original_queue:
            if 0 <= old_index < len(self._original_queue) and 0 <= new_index < len(self._original_queue):
                orig_track = self._original_queue.pop(old_index)
                self._original_queue.insert(new_index, orig_track)

        if current_t and current_t in self._queue:
            self._current_index = self._queue.index(current_t)

        self._notify_state()

    async def _load_and_play_track(self, track: Track) -> None:
        """Resolves the audio stream and starts playback via native Flet Audio."""
        self._is_loading_stream = True
        self._position_seconds = 0.0
        self._is_playing = False
        self.state.is_playing = False
        self.state.reset_idle()

        # Update track title and UI immediately
        self._notify_track()

        print(f"[AudioController] Preparing audio for: '{track.title}' (ID: {track.id})...")

        stream_url = await self.ytmusic_service.get_stream_url_async(track.id)
        if not stream_url:
            self._is_playing = False
            self.state.is_playing = False
            print(f"[AudioController] Stream URL not found for '{track.title}'.")
            self._is_loading_stream = False
            self._notify_state()
            return
            
        self._current_stream_url = stream_url
        self._loaded_track_id = track.id
        
        if self.audio:
            self.audio.src = stream_url
            self.audio.volume = max(0.0, min(1.0, self._volume))
            try:
                self.audio.update()
            except Exception:
                pass
            await self._safe_audio_call(self.audio.play())
            self._is_playing = True
            self.state.is_playing = True
            print(f"[AudioController] Audio stream playing: '{track.title}'")

        self._is_loading_stream = False
        self._notify_state()

    def _handle_track_completed(self) -> None:
        """Advances track or repeats when audio completes."""
        if self._repeat == "one":
            self.seek(0)
        elif self._repeat == "all" or self._current_index < len(self._queue) - 1:
            self.next_track()
        else:
            self._position_seconds = self.duration_seconds
            self.pause()

    def _notify_track(self) -> None:
        if self.on_track_changed and self.current_track:
            try:
                self.on_track_changed(self.current_track)
            except Exception as e:
                print(f"[AudioController] Track callback note: {e}")
        self._notify_state()

    def _notify_state(self) -> None:
        if self.on_state_changed:
            try:
                self.on_state_changed()
            except Exception as e:
                print(f"[AudioController] State callback note: {e}")
