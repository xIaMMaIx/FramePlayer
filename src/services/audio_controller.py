"""
Audio Playback & State Controller (AudioController).
Integrates dedicated FFPlay hardware streaming engine with HTTP auto-reconnect,
stream stall auto-recovery, volume control, track queue management, and UI state synchronization.
"""

import asyncio
import atexit
import os
import shutil
import subprocess
import time
from typing import Callable, List, Optional
import flet as ft

from src.music_backend import BaseMusicBackend, MOCK_TRACKS, Track
from src.services.ytmusic_service import YTMusicService
from src.state import AppState

DEFAULT_AUDIO_PLACEHOLDER = "https://raw.githubusercontent.com/mdn/webaudio-examples/main/audio-analyser/viper.mp3"


class FFPlayAudioEngine:
    """Subprocess audio playback engine using FFPlay with resilient stream reconnect and clean exit."""

    def __init__(self):
        self._proc: Optional[subprocess.Popen] = None
        self._ffplay_path = shutil.which("ffplay") or r"E:\AI\ffmpeg\bin\ffplay.exe"
        self._volume: int = 75  # 0 to 100
        atexit.register(self.stop)

    def play(self, url: str, start_pos: float = 0.0, volume: float = 0.75) -> bool:
        """Starts streaming audio from direct URL with auto-reconnect enabled."""
        self.stop()
        self._volume = max(0, min(100, int(volume * 100)))

        if not os.path.exists(self._ffplay_path) and not shutil.which("ffplay"):
            print(f"[FFPlayAudioEngine] ffplay not found at {self._ffplay_path}")
            return False

        cmd = [
            self._ffplay_path,
            "-nodisp",
            "-autoexit",
            "-loglevel",
            "quiet",
            "-reconnect",
            "1",
            "-reconnect_streamed",
            "1",
            "-reconnect_delay_max",
            "5",
            "-volume",
            str(self._volume),
        ]
        if start_pos > 1.0:
            cmd.extend(["-ss", str(int(start_pos))])
        cmd.append(url)

        try:
            creationflags = 0
            if os.name == "nt":
                creationflags = subprocess.CREATE_NO_WINDOW

            self._proc = subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=creationflags,
            )
            print(f"[FFPlayAudioEngine] Stream playing via FFPlay (PID: {self._proc.pid}, Pos: {int(start_pos)}s, Vol: {self._volume}%)")
            return True
        except Exception as e:
            print(f"[FFPlayAudioEngine] Error launching ffplay: {e}")
            return False

    def stop(self) -> None:
        """Stops active audio playback process and ensures no orphan survives."""
        if self._proc:
            try:
                self._proc.terminate()
                self._proc.kill()
            except Exception:
                pass
            self._proc = None

        if os.name == "nt":
            try:
                subprocess.run(
                    ["taskkill", "/F", "/IM", "ffplay.exe", "/T"],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
                )
            except Exception:
                pass

    def is_running(self) -> bool:
        """Returns True if audio process is currently active."""
        if self._proc:
            return self._proc.poll() is None
        return False


class AudioController(BaseMusicBackend):
    def __init__(
        self,
        state: AppState,
        ytmusic_service: YTMusicService,
        audio_control: Optional[ft.Audio] = None,
        async_runner: Optional[Callable] = None,
    ):
        self.state = state
        self.ytmusic_service = ytmusic_service
        self.audio = audio_control
        self.async_runner = async_runner

        # Hardware FFPlay Audio Engine
        self.ffplay = FFPlayAudioEngine()

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

        # If audio stream is already loaded, resume with FFPlay from current position
        if self._loaded_track_id == curr.id and self._current_stream_url:
            self.ffplay.play(self._current_stream_url, start_pos=self._position_seconds, volume=self._volume)
            self._notify_state()
        else:
            self._run_async(self._load_and_play_track(curr))

    def pause(self) -> None:
        """Pauses audio playback."""
        self._is_playing = False
        self.state.is_playing = False
        self.ffplay.stop()
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
        """Finds track by ID in queue and plays it. If already playing, ignores to keep playing uninterrupted."""
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
        """Seeks to position in track."""
        max_dur = self.duration_seconds
        self._position_seconds = max(0.0, min(position_seconds, max_dur))
        self.state.position_seconds = self._position_seconds

        if self._current_stream_url and self._is_playing:
            self.ffplay.play(self._current_stream_url, start_pos=self._position_seconds, volume=self._volume)

        self._notify_state()

    def set_volume(self, volume: float) -> None:
        """Sets playback volume (0.0 to 1.0)."""
        self._volume = max(0.0, min(1.0, volume))
        self.state.volume = self._volume

        if self._current_stream_url and self._is_playing:
            self.ffplay.play(self._current_stream_url, start_pos=self._position_seconds, volume=self._volume)

        self._notify_state()

    def toggle_shuffle(self) -> bool:
        """Toggles shuffle mode and reorders queue."""
        import random
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
            if current:
                self._current_index = self._queue.index(current) if current in self._queue else 0

        self._notify_state()
        return self._shuffle

    def cycle_repeat(self) -> str:
        """Cycles between off -> all -> one."""
        modes = ["off", "all", "one"]
        curr_idx = modes.index(self._repeat) if self._repeat in modes else 0
        self._repeat = modes[(curr_idx + 1) % len(modes)]
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

    async def _load_and_play_track(self, track: Track) -> None:
        """Resolves audio stream URL and starts playback via FFPlay hardware streaming."""
        self._is_loading_stream = True
        self._position_seconds = 0.0
        self._is_playing = True
        self.state.is_playing = True
        self.state.reset_idle()

        # Update track title and UI immediately
        self._notify_track()

        print(f"[AudioController] Extracting audio stream for: '{track.title}' (ID: {track.id})...")
        stream_url = await self.ytmusic_service.get_stream_url_async(track.id)

        if stream_url:
            self._current_stream_url = stream_url
            self._loaded_track_id = track.id
            self.ffplay.play(stream_url, start_pos=0.0, volume=self._volume)
            print(f"[AudioController] Audio stream playing successfully via FFPlay: '{track.title}'")
        else:
            print(f"[AudioController] Stream URL not found for '{track.title}'.")

        self._is_loading_stream = False
        self._notify_state()

    def tick_playback(self) -> None:
        """Called every second by background ticker to update elapsed position and handle stream health."""
        if not self._is_playing:
            return

        self._position_seconds += 1.0
        self.state.position_seconds = self._position_seconds

        curr = self.current_track
        dur = curr.duration_seconds if curr and curr.duration_seconds > 0 else self.duration_seconds

        # Stream health monitor: check if ffplay process ended
        if not self.ffplay.is_running():
            if self._position_seconds >= dur - 3:
                # Track reached normal completion
                self._handle_track_completed()
            elif self._current_stream_url and self._position_seconds < dur - 5:
                # Unexpected stream drop / network stall -> auto-reconnect from current position
                print(f"[AudioController] Stream stall detected at {int(self._position_seconds)}s. Auto-reconnecting...")
                self.ffplay.play(self._current_stream_url, start_pos=self._position_seconds, volume=self._volume)

    def _handle_track_completed(self) -> None:
        """Advances track or repeats when audio completes."""
        if self._repeat == "one":
            self.seek(0)
            self.play()
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
